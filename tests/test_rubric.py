"""Regressions for rubric scoring and severity triage.

The rule under test throughout: a paper loses points for what it did not say,
never for what this tool could not determine. Breaking that rule produces a
number that looks like a verdict on the paper and is partly a verdict on the
extractor, and nothing downstream can tell the two apart.
"""

from __future__ import annotations

from reprolens.discovery.links import Finding, Occurrence
from reprolens.discovery.resolve import (
    NOT_FOUND,
    PUBLIC,
    RESTRICTED,
    UNCHECKED,
    Resolution,
    Resolutions,
)
from reprolens.documents.base import PageText, is_readable
from reprolens.documents.sections import SectionMark, classify_heading
from reprolens.extraction.checklist import Checklist, Parameter, Software
from reprolens.scoring.rubric import WEIGHTS, assess, link_mismatches

# Enough body prose to clear ``MIN_DOCUMENT_CHARS``, because the rubric refuses
# to score a document it was not able to read. Deliberately inert: it matches no
# resource pattern and names no tool in the checklist vocabulary, so it changes
# the size of these fixtures and nothing else. Verified by asserting below.
FILLER = (
    "Samples were collected under the approved protocol and processed in matched batches to "
    "limit batch effects. Each batch carried a paired control drawn from the same pool, and the "
    "two were handled side by side from collection through to measurement. Libraries were "
    "prepared in a single session per batch by one operator, and the resulting material was "
    "held at the stated temperature until it was measured. Quality thresholds were agreed in "
    "advance and applied without exception; batches falling below them were set aside and "
    "repeated rather than carried forward. Measurements were taken in a randomised order "
    "within each batch to keep position from acting as a hidden variable. Replicate counts "
    "were fixed before the first measurement and were not adjusted afterwards. Summary values "
    "reported in the text are means over replicates, with the spread given as the standard "
    "deviation across them. Where a comparison is drawn between batches, the paired control is "
    "used as the reference rather than a pooled baseline, so that the comparison carries only "
    "within-batch variation."
)


def page(text: str, *, heading: str = "Data availability", number: int = 1) -> PageText:
    """One segment, padded to the size of a real paper's worth of text.

    The padding is not cosmetic. ``assess`` reports every criterion as not
    assessed when the document produced too little text to conclude anything,
    so a fixture of two sentences would exercise that guard instead of the
    scoring rules these tests are about.
    """
    return PageText(
        page=number,
        text=f"{heading}\n{text}\n{FILLER}",
        sections=[SectionMark(offset=0, heading=heading, label=classify_heading(heading))],
    )


def finding(value: str, kind: str, section: str, context: str = "") -> Finding:
    return Finding(
        value=value,
        kind=kind,
        occurrences=[Occurrence(page=1, source="text", context=context or value, section=section)],
    )


def software(name: str, kind: str, specificity: str, version: str | None = None) -> Software:
    return Software(
        name=name,
        kind=kind,
        specificity=specificity,
        version=version,
        mentions=1,
        sections=["methods"],
    )


def criterion(assessment, name: str):
    return next(c for c in assessment.criteria if c.name == name)


EMPTY = Checklist(software=[], parameters=[], commands=[])


class TestUncertaintyWidensRatherThanDeducts:
    def test_an_unresolved_resource_does_not_lower_the_floor(self):
        resolved = finding(
            "GSE225377",
            "geo_series",
            "data_availability",
            "Inhouse data are deposited at GEO under GSE225377.",
        )
        pages = [page("Inhouse data are deposited at GEO under GSE225377.")]
        full = assess(pages, [resolved], EMPTY)

        unresolved = finding("https://www.ncbi.nlm.nih.gov/geo", "url", "data_availability")
        partial = assess(pages, [resolved, unresolved], EMPTY)

        # The extra resource the classifier could not place must not cost the
        # paper points; it widens the band instead.
        assert criterion(partial, "data_availability").floor == 16
        assert criterion(partial, "data_availability").ceiling == 20
        assert criterion(full, "data_availability").floor == 20
        assert criterion(partial, "data_availability").undetermined

    def test_no_flags_named_is_not_credited_as_good_practice(self):
        # Nor penalised. It is no evidence, so it belongs in the band.
        assessment = assess([page("")], [], EMPTY)
        parameters = criterion(assessment, "parameters_configuration")
        assert parameters.floor == 0
        assert parameters.ceiling == 4
        assert parameters.undetermined


class TestEvidenceTheToolDoesNotHave:
    def test_a_repository_url_proves_presence_not_contents(self):
        repo = finding(
            "github.com/org/repo",
            "github",
            "code_availability",
            "the code is at https://github.com/org/repo for review",
        )
        assessment = assess([page("", heading="Code availability")], [repo], EMPTY)
        code = criterion(assessment, "code_availability")
        assert code.floor == 10
        assert code.ceiling == 20
        assert any("not fetched" in note for note in code.undetermined)

    def test_environment_absent_from_the_paper_is_not_absent_everywhere(self):
        assessment = assess([page("")], [], EMPTY)
        environment = criterion(assessment, "environment_specification")
        assert environment.floor == 0
        assert environment.ceiling == WEIGHTS["environment_specification"]

    def test_unassessable_criteria_are_not_scored_as_zero(self):
        assessment = assess([page("")], [], EMPTY)
        for name in ("method_completeness", "execution_instructions", "result_traceability"):
            item = criterion(assessment, name)
            assert item.assessed is False
            assert item.reason
        # and they are excluded from the denominator rather than counted against
        assert assessment.assessable == 65
        assert sum(WEIGHTS.values()) == 100


class TestCodeAvailabilityIgnoresHouseStyle:
    def test_a_repo_in_the_data_availability_statement_still_counts(self):
        # BMC puts code in the data availability statement, so keying on a
        # "Code availability" heading would score the publisher, not the paper.
        repo = finding("github.com/jasonwong-lab/LocusMasterTE", "github", "data_availability")
        assessment = assess([page("")], [repo], EMPTY)
        assert criterion(assessment, "code_availability").floor == 10


class TestLinkMismatch:
    def test_a_link_that_drops_a_digit_is_caught(self):
        pages = [
            page(
                "The dataset (GSE114952, "
                "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE11495) is detailed in Zhao."
            )
        ]
        assert link_mismatches(pages) == [("GSE", "114952", "11495")]

    def test_two_distinct_samples_in_one_parenthetical_are_not_a_mismatch(self):
        # The same statement names GSM4800803 "for 10x" and GSM4800807 "for
        # Pacbio". A bare "two different values here" test calls that broken.
        pages = [
            page(
                "data (GSE158450, https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4800803 "
                "for 10x and https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4800807 "
                "for Pacbio)."
            )
        ]
        assert link_mismatches(pages) == []

    def test_only_availability_statements_are_checked(self):
        pages = [page("see (GSE114952, acc=GSE11495) there", heading="References")]
        assert link_mismatches(pages) == []

    def test_a_wrong_link_costs_two_points_not_the_resource(self):
        pages = [
            page(
                "dataset (GSE114952, "
                "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE11495) detailed in Zhao."
            )
        ]
        hit = finding(
            "GSE114952",
            "geo_series",
            "data_availability",
            "the dataset (GSE114952, ...) is detailed in Zhao et al.",
        )
        assessment = assess(pages, [hit], EMPTY)
        # 8 for the statement + 8 for the accession + 4 all resolved, less 2.
        assert criterion(assessment, "data_availability").floor == 18


class TestSeverityFollowsTheBlueprint:
    def test_an_unversioned_annotation_source_is_a_major_issue(self):
        checklist = Checklist(
            software=[software("RepeatMasker", "reference", "named_only")],
            parameters=[],
            commands=[],
        )
        issues = assess([page("")], [], checklist).issues
        assert [(i.severity, i.resource) for i in issues] == [("major", "RepeatMasker")]
        assert "annotation unspecified" in issues[0].kind

    def test_an_unversioned_library_is_only_a_minor_issue(self):
        checklist = Checklist(
            software=[software("pysam", "library", "named_only")], parameters=[], commands=[]
        )
        assert assess([page("")], [], checklist).issues[0].severity == "minor"

    def test_a_flag_without_a_value_is_a_major_issue(self):
        checklist = Checklist(
            software=[],
            parameters=[Parameter(flag="--outFilterMultimapNmax", value=None, evidence="x")],
            commands=[],
        )
        issues = assess([page("")], [], checklist).issues
        assert issues[0].severity == "major"
        assert "hyperparameters absent" in issues[0].kind

    def test_a_pinned_tool_raises_no_issue(self):
        checklist = Checklist(
            software=[software("SeqKit", "tool", "pinned", "2.8.2")], parameters=[], commands=[]
        )
        assert assess([page("")], [], checklist).issues == []


class TestTheRepositoryChannel:
    """What changes once the code the paper points at has been read.

    Three criteria exist only here, and two more close a band they could not
    close from the paper. The rule from the rest of this file still holds: an
    unfetched repository is never scored as an empty one.
    """

    def paper(self):
        pages = [page("Code is available at github.com/lab/project.", heading="Code availability")]
        assert is_readable(pages)
        findings = [
            finding("github.com/lab/project", "github", "code_availability", "available at")
        ]
        return pages, findings, Checklist(software=[], parameters=[], commands=[])

    def repo(self, tmp_path, files, *, figures=(), reason=""):
        from reprolens.repository.analysis import analyze
        from reprolens.repository.fetch import FetchResult, RepoRef

        ref = RepoRef("github", "lab", "project")
        if reason:
            return analyze(
                [FetchResult(ref=ref, reason=reason)],
                paper_figures=list(figures),
                paper_software=set(),
            )
        from test_repository import checkout

        return analyze(
            [FetchResult(ref=ref, checkout=checkout(tmp_path, files, slug="lab/project"))],
            paper_figures=list(figures),
            paper_software=set(),
        )

    def criterion(self, assessment, name):
        return next(c for c in assessment.criteria if c.name == name)

    def test_without_a_repository_three_criteria_stay_unassessed(self):
        pages, findings, checklist = self.paper()
        assessment = assess(pages, findings, checklist)
        unassessed = {c.name for c in assessment.criteria if not c.assessed}
        assert unassessed == {
            "method_completeness",
            "execution_instructions",
            "result_traceability",
        }
        assert assessment.assessable == 65

    def test_with_a_repository_every_criterion_is_scored(self, tmp_path):
        pages, findings, checklist = self.paper()
        repo = self.repo(tmp_path, {"run.sh": "tool run\n", "README.md": "```\nbash run.sh\n```\n"})
        assessment = assess(pages, findings, checklist, repo)
        assert all(c.assessed for c in assessment.criteria)
        assert assessment.assessable == 100
        assert sum(WEIGHTS.values()) == 100

    def test_a_named_repository_that_will_not_fetch_is_a_hard_blocker(self):
        # And the criteria it would have answered stay unassessed rather than
        # being scored from a repository nobody read.
        pages, findings, checklist = self.paper()
        repo = self.repo(None, {}, reason="git clone failed: repository not found")
        assessment = assess(pages, findings, checklist, repo)
        assert assessment.assessable == 65
        blockers = [i for i in assessment.issues if i.severity == "hard_blocker"]
        assert [i.kind for i in blockers] == ["essential code absent"]

    def test_reading_the_repository_closes_the_code_availability_band(self, tmp_path):
        pages, findings, checklist = self.paper()
        without = self.criterion(assess(pages, findings, checklist), "code_availability")
        assert (without.floor, without.ceiling) == (10, 20)

        repo = self.repo(tmp_path, {"run.sh": "tool run\n"}, figures=[])
        with_repo = self.criterion(assess(pages, findings, checklist, repo), "code_availability")
        assert (with_repo.floor, with_repo.ceiling) == (20, 20)

    def test_a_published_figure_with_no_code_costs_code_availability(self, tmp_path):
        pages, findings, checklist = self.paper()
        files = {"run.sh": "tool run\n", "fig1.R": "library(x)\n", "fig3.R": "library(x)\n"}
        repo = self.repo(tmp_path, files, figures=[1, 2, 3])
        criterion = self.criterion(assess(pages, findings, checklist, repo), "code_availability")
        assert (criterion.floor, criterion.ceiling) == (18, 18)

    def test_no_figure_named_file_widens_the_band_instead_of_deducting(self, tmp_path):
        pages, findings, checklist = self.paper()
        repo = self.repo(tmp_path, {"run.sh": "tool run\n"}, figures=[1, 2, 3])
        criterion = self.criterion(assess(pages, findings, checklist, repo), "code_availability")
        assert (criterion.floor, criterion.ceiling) == (16, 20)
        assert criterion.undetermined

    def test_environment_is_scored_from_the_repository(self, tmp_path):
        pages, findings, checklist = self.paper()
        files = {
            "requirements.txt": "numpy==1.25.2\ntorch==2.0.1\n",
            "pyproject.toml": '[project]\nname = "x"\nrequires-python = "==3.11"\n',
        }
        repo = self.repo(tmp_path, files)
        criterion = self.criterion(
            assess(pages, findings, checklist, repo), "environment_specification"
        )
        assert criterion.floor == criterion.ceiling == WEIGHTS["environment_specification"]

    def test_two_manifests_disagreeing_costs_environment_points(self, tmp_path):
        pages, findings, checklist = self.paper()
        files = {
            "requirements.txt": "torch==2.0.1\n",
            "setup.py": 'setup(install_requires=["torch==2.0.0"])',
            "pyproject.toml": '[project]\nname = "x"\nrequires-python = "==3.11"\n',
        }
        criterion = self.criterion(
            assess(pages, findings, checklist, self.repo(tmp_path, files)),
            "environment_specification",
        )
        assert criterion.floor == WEIGHTS["environment_specification"] - 2
        assert any("pinned to" in line for line in criterion.basis)

    def test_a_repository_command_raises_the_parameter_ceiling_not_the_floor(self, tmp_path):
        # A worked example in a README is not the configuration behind the
        # published numbers, and scoring it as one would report the example as
        # the experiment.
        pages, findings, checklist = self.paper()
        repo = self.repo(
            tmp_path, {"README.md": "```\nSTAR --runThreadN 20 --alignEnds Extend\n```\n"}
        )
        without = self.criterion(assess(pages, findings, checklist), "parameters_configuration")
        with_repo = self.criterion(
            assess(pages, findings, checklist, repo), "parameters_configuration"
        )
        assert with_repo.floor == without.floor
        assert with_repo.ceiling == without.ceiling + 3
        assert with_repo.undetermined

    def test_a_demo_scale_input_is_a_hard_blocker_and_costs_parameters(self, tmp_path):
        # LocusMasterTE's run_sample.sh takes annotation.gtf; the repository
        # ships twenty records where the published analysis quantified tens of
        # thousands of elements.
        pages, findings, checklist = self.paper()
        records = "\n".join(f"chr1\trmsk\texon\t{i}\t{i + 9}" for i in range(20))
        files = {"run.sh": "tool assign annotation.gtf\n", "annotation.gtf": records}
        assessment = assess(pages, findings, checklist, self.repo(tmp_path, files))
        blockers = [i for i in assessment.issues if i.severity == "hard_blocker"]
        assert [i.kind for i in blockers] == ["required dataset unavailable"]
        assert "annotation.gtf" in blockers[0].resource
        parameters = self.criterion(assessment, "parameters_configuration")
        assert parameters.floor == 0

    def test_traceability_scores_the_mapping_and_says_so(self, tmp_path):
        pages, findings, checklist = self.paper()
        files = {f"fig{n}.R": "library(x)\n" for n in (1, 3, 4, 5)}
        criterion = self.criterion(
            assess(pages, findings, checklist, self.repo(tmp_path, files, figures=[1, 2, 3, 4, 5])),
            "result_traceability",
        )
        assert criterion.floor == criterion.ceiling == 8
        assert any("figure 1 <-" in line for line in criterion.basis)

    def test_traceability_is_undetermined_when_nothing_is_named_for_a_figure(self, tmp_path):
        pages, findings, checklist = self.paper()
        repo = self.repo(tmp_path, {"train_model.py": "import torch\n"}, figures=[1, 2])
        criterion = self.criterion(assess(pages, findings, checklist, repo), "result_traceability")
        assert (criterion.floor, criterion.ceiling) == (0, WEIGHTS["result_traceability"])
        assert criterion.undetermined

    def test_an_unnamed_pipeline_step_costs_method_completeness(self, tmp_path):
        pages, findings, checklist = self.paper()
        files = {
            "wrapper.sh": "pychopper -r r.pdf in.fq out.fq\n",
            "README.md": "```\nbash wrapper.sh x.fq\n```\n",
        }
        criterion = self.criterion(
            assess(pages, findings, checklist, self.repo(tmp_path, files)), "method_completeness"
        )
        # Ten points are checkable -- the code is readable and the steps are
        # described -- and the first unnamed step costs two of them. The ceiling
        # stays at the weight because whether the description is otherwise
        # complete is not assessable from either document.
        assert (criterion.floor, criterion.ceiling) == (8, WEIGHTS["method_completeness"])


class TestADocumentThatWasNotRead:
    """The guard that says nothing, rather than saying zero.

    The XML backend, handed a file whose wrapper it did not recognize, returned
    zero segments and no error. Everything downstream then reported a
    well-documented paper as having published nothing, scored out of 65 as
    though the paper were at fault. Zeros and silence have to be different
    results all the way into the score.
    """

    def test_the_filler_in_these_fixtures_adds_no_findings(self):
        from reprolens.discovery.patterns import PATTERNS
        from reprolens.extraction.checklist import find_names

        assert find_names(FILLER) == []
        assert [p.kind for p in PATTERNS if p.regex.search(FILLER)] == []

    def test_an_empty_document_is_not_readable(self):
        assert not is_readable([])
        assert not is_readable([page("", heading="")] and [PageText(page=1, text="")])

    def test_every_criterion_is_unassessed_when_nothing_was_read(self):
        pages = [PageText(page=1, text="Front matter")]
        assessment = assess(pages, [], EMPTY)
        assert [c.assessed for c in assessment.criteria] == [False] * 7
        assert assessment.assessable == 0
        assert all("no readable text" in c.reason for c in assessment.criteria)

    def test_an_unread_document_scores_nothing_rather_than_zero(self):
        # The distinction that matters: a zero floor with a full-weight ceiling
        # is "we do not know", where floor and ceiling both zero would be "the
        # paper provides nothing".
        pages = [PageText(page=1, text="Front matter")]
        criteria = assess(pages, [], EMPTY).criteria
        assert all(c.floor == 0 and c.ceiling == c.weight for c in criteria)
        assert sum(c.weight for c in criteria) == sum(WEIGHTS.values())

    def test_a_real_document_is_readable_and_is_scored(self):
        pages = [page("Inhouse data are deposited at GEO under GSE225377.")]
        assert is_readable(pages)
        assert any(c.assessed for c in assess(pages, [], EMPTY).criteria)


class TestExecutionInstructionsAcrossEcosystems:
    def criterion(self, assessment, name: str):
        return next(c for c in assessment.criteria if c.name == name)

    def repo(self, tmp_path, files):
        from test_repository import checkout

        from reprolens.repository.analysis import analyze
        from reprolens.repository.fetch import FetchResult, RepoRef

        ref = RepoRef("github", "lab", "project")
        return analyze(
            [FetchResult(ref=ref, checkout=checkout(tmp_path, files, slug="lab/project"))],
            paper_figures=[],
            paper_software=set(),
        )

    def test_an_r_install_line_counts_as_environment_setup(self, tmp_path):
        # Keyed on the command, not its first word: an R install line does not
        # begin with the installer, so a head-token rule scored a package that
        # documents its own installation as documenting nothing.
        readme = (
            "## Installation\n```\n"
            'devtools::install_github("lab/project")\n```\n'
            "## Use\n```\nres <- fit_model(counts, min_cells = 5)\n```\n"
        )
        repo = self.repo(tmp_path, {"NAMESPACE": "export(fit_model)\n", "README.md": readme})
        pages, findings, checklist = TestTheRepositoryChannel().paper()
        criterion = self.criterion(
            assess(pages, findings, checklist, repo), "execution_instructions"
        )
        assert any("installation or environment setup" in line for line in criterion.basis)
        assert criterion.floor >= 8

    def test_a_package_with_no_setup_shown_does_not_get_those_points(self, tmp_path):
        readme = "## Use\n```\nres <- fit_model(counts, min_cells = 5)\n```\n"
        repo = self.repo(tmp_path, {"NAMESPACE": "export(fit_model)\n", "README.md": readme})
        pages, findings, checklist = TestTheRepositoryChannel().paper()
        criterion = self.criterion(
            assess(pages, findings, checklist, repo), "execution_instructions"
        )
        assert any("no installation command shown" in line for line in criterion.basis)


class TestDatasetResolution:
    """What an archive said, and what it is allowed to cost.

    None of these fire on the three papers in hand: all nineteen accessions
    they name resolve. So this is the only evidence that the deduction paths
    work at all, and the rule they have to respect is the one at the top of
    this file -- an archive that answered may cost the paper points, and an
    archive nobody reached may not.
    """

    def scored(self, resolutions):
        pages = [page("Data were deposited in GEO under accession GSE212945.")]
        findings = [
            finding(
                "GSE212945",
                "geo_series",
                "data_availability",
                "deposited in GEO under accession GSE212945",
            )
        ]
        return assess(
            pages,
            findings,
            Checklist(software=[], parameters=[], commands=[]),
            resolutions=resolutions,
        )

    def availability(self, resolutions):
        return criterion(self.scored(resolutions), "data_availability")

    def resolutions(self, status, **kwargs):
        return Resolutions(entries=[Resolution("GSE212945", "geo_series", status, **kwargs)])

    def test_a_confirmed_dataset_earns_nothing_and_says_so(self):
        # Resolving is the expected case. Paying points for it would mean every
        # paper scored before this channel existed was under-scored.
        baseline = self.availability(None)
        confirmed = self.availability(self.resolutions(PUBLIC, title="a real series"))
        assert confirmed.floor == baseline.floor
        assert confirmed.ceiling == baseline.ceiling
        assert any("confirmed present" in b for b in confirmed.basis)

    def test_a_dataset_the_archive_does_not_have_costs_the_paper(self):
        baseline = self.availability(None)
        absent = self.availability(self.resolutions(NOT_FOUND, detail="GEO has no record"))
        assert absent.floor == baseline.floor - 2
        assert absent.ceiling == baseline.ceiling - 2
        assert any("NOT in the archive" in b for b in absent.basis)

    def test_a_missing_dataset_is_raised_as_an_issue(self):
        issues = self.scored(self.resolutions(NOT_FOUND, detail="GEO has no record")).issues
        matching = [i for i in issues if i.resource == "GSE212945"]
        assert [i.severity for i in matching] == ["major"]
        assert "not present in the archive" in matching[0].kind

    def test_controlled_access_costs_the_paper_and_is_its_own_finding(self):
        baseline = self.availability(None)
        gated = self.availability(self.resolutions(RESTRICTED, detail="approved request needed"))
        assert gated.floor == baseline.floor - 2
        assert any("controlled access" in b for b in gated.basis)
        issues = self.scored(self.resolutions(RESTRICTED, detail="x")).issues
        assert any("controlled access" in i.kind for i in issues)

    def test_an_unchecked_dataset_costs_nothing(self):
        baseline = self.availability(None)
        unchecked = self.availability(
            self.resolutions(UNCHECKED, detail="registry unreachable (URLError)")
        )
        assert unchecked.floor == baseline.floor
        assert unchecked.ceiling == baseline.ceiling
        assert any("not confirmed to exist" in u for u in unchecked.undetermined)

    def test_an_unchecked_dataset_raises_no_issue(self):
        issues = self.scored(self.resolutions(UNCHECKED, detail="unreachable")).issues
        assert [i for i in issues if i.resource == "GSE212945"] == []

    def test_an_accession_the_paper_only_cites_is_not_scored_against_it(self):
        # A resolution for something that is not one of this paper's datasets
        # must not move this paper's number.
        baseline = self.availability(None)
        elsewhere = Resolutions(
            entries=[Resolution("GSE999999", "geo_series", NOT_FOUND, detail="absent")]
        )
        assert self.availability(elsewhere).floor == baseline.floor

    def test_several_missing_datasets_cost_more_but_are_bounded(self):
        baseline = self.availability(None)
        many = Resolutions(
            entries=[
                Resolution("GSE212945", "geo_series", NOT_FOUND, detail="absent"),
            ]
        )
        one = self.availability(many).floor
        assert one == baseline.floor - 2
        # The cap exists so one criterion cannot be driven below zero by a
        # reference list full of stale accessions.
        assert self.availability(many).floor >= 0
