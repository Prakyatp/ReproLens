"""Regressions for the ground-truth record validator in ``check.py``.

Every case here is a mistake an annotator can make while writing a record that
leaves it well-formed JSON, so nothing breaks and the grading run afterwards
looks entirely normal while comparing against the wrong thing. That is the only
kind of error worth a validator: a malformed record announces itself.

The benchmark is about to grow from two hand-made Tier-1 records to twenty
mostly cold-read ones, and these are the mistakes that scale with that.
"""

from __future__ import annotations

import check
from reprolens.scoring.rubric import WEIGHTS


def record(**overrides) -> dict:
    """A minimal Tier-2 record that validates clean, for mutating per case."""
    base = {
        "paper_id": "example",
        "title": "An example paper",
        "citation": "Author et al., Journal, 2026",
        "github": "https://github.com/example/example",
        "data_accessions": ["GSE000001 (the paper's own data)"],
        "annotation_provenance": {"tier": 2},
        "blockers": [{"severity": "major", "description": "A version is never stated."}],
        "severity_summary": {"hard_blockers": 0, "major_issues": 1, "minor_issues": 0},
        "scoring_rubric_v0.1": dict.fromkeys(WEIGHTS, 0) | {"total": 0},
    }
    return base | overrides


class TestTheShippedRecords:
    def test_every_finished_record_validates(self):
        # The validator's own ground truth: the two Tier-1 records were written
        # by hand before it existed, and it must not have been built to a shape
        # they fail.
        #
        # "Finished" is the qualifier, and it is not a loophole. Blank
        # skeletons from scripts/prep_benchmark.py live in papers/ alongside
        # real records and are *supposed* to fail -- that is how the annotator
        # finds out what is left to fill, and check.py refuses to grade them.
        # So this asserts the stronger thing: no record is failing for any
        # reason other than being an unstarted skeleton.
        import json

        template = json.loads(check.TEMPLATE.read_text())
        papers, problems = check.read_records()
        assert papers

        unexpected = {}
        for paper_id, found in problems.items():
            record = json.loads((check.BENCHMARK / f"{paper_id}.json").read_text())
            if record.get("scoring_rubric_v0.1") == template.get("scoring_rubric_v0.1"):
                continue  # an unstarted skeleton, failing exactly as designed
            unexpected[paper_id] = found
        assert unexpected == {}

    def test_the_finished_records_are_still_there(self):
        papers, problems = check.read_records()
        for paper_id in ("locusmasterte", "mates"):
            assert paper_id in papers and paper_id not in problems


class TestABaselineRecordIsAccepted:
    def test_the_fixture_itself_is_clean(self):
        assert check.validate_record("example", record()) == []


class TestTheSeverityVocabulary:
    """The trap: three spellings of the same three severities.

    A record says "hard", the app's issues say "hard_blocker", and
    ``severity_summary`` says "hard_blockers". ``blockers_side_by_side`` filters
    on the record's spelling, so the app's spelling in a record does not raise
    -- it makes the blocker disappear from the comparison it exists to drive.
    """

    def test_the_apps_word_is_rejected_by_name(self):
        broken = record(
            blockers=[
                {"severity": "hard_blocker", "description": "The exact GTF was never released."}
            ],
            severity_summary={"hard_blockers": 1, "major_issues": 0, "minor_issues": 0},
        )
        problems = check.validate_record("example", broken)
        assert any("'hard_blocker'" in p and "'hard'" in p for p in problems)

    def test_the_records_own_word_is_accepted(self):
        fixed = record(
            blockers=[{"severity": "hard", "description": "The exact GTF was never released."}],
            severity_summary={"hard_blockers": 1, "major_issues": 0, "minor_issues": 0},
        )
        assert check.validate_record("example", fixed) == []

    def test_an_invented_severity_names_the_alternatives(self):
        broken = record(blockers=[{"severity": "critical", "description": "x"}])
        problems = check.validate_record("example", broken)
        assert any("expected one of hard, major, minor" in p for p in problems)

    def test_a_rejected_spelling_does_not_also_blame_the_summary(self):
        # The tally cannot count a severity it did not recognise, so a count
        # mismatch here would be a second message for one mistake, pointing at
        # the wrong field.
        broken = record(
            blockers=[{"severity": "hard_blocker", "description": "x"}],
            severity_summary={"hard_blockers": 1, "major_issues": 0, "minor_issues": 0},
        )
        problems = check.validate_record("example", broken)
        assert not any("severity_summary" in p for p in problems)


class TestTheSummaryMatchesTheBlockers:
    def test_a_count_that_drifted_from_the_list_is_caught(self):
        # The likeliest edit of all: a blocker gets added and the summary above
        # it is left alone.
        broken = record(
            blockers=[
                {"severity": "major", "description": "one"},
                {"severity": "major", "description": "two"},
            ],
        )
        problems = check.validate_record("example", broken)
        assert any("major_issues says 1" in p and "holds 2" in p for p in problems)

    def test_a_missing_summary_key_is_reported(self):
        broken = record(severity_summary={"major_issues": 1, "minor_issues": 0})
        assert any(
            "severity_summary.hard_blockers is missing" in p
            for p in check.validate_record("example", broken)
        )

    def test_a_blocker_with_no_description_is_reported(self):
        broken = record(blockers=[{"severity": "major", "description": "  "}])
        assert any("no description" in p for p in check.validate_record("example", broken))


class TestTheHandAssignedScore:
    """``total`` is what the app's band is graded against, so it has to add up."""

    def test_a_total_that_does_not_equal_its_parts_is_caught(self):
        broken = record(
            **{
                "scoring_rubric_v0.1": dict.fromkeys(WEIGHTS, 0)
                | {"data_availability": 10, "total": 72}
            }
        )
        problems = check.validate_record("example", broken)
        assert any("total says 72" in p and "sum to 10" in p for p in problems)

    def test_a_criterion_over_its_weight_is_caught(self):
        over = WEIGHTS["parameters_configuration"] + 1
        broken = record(
            **{
                "scoring_rubric_v0.1": dict.fromkeys(WEIGHTS, 0)
                | {"parameters_configuration": over, "total": over}
            }
        )
        problems = check.validate_record("example", broken)
        assert any(
            "parameters_configuration" in p and "expected an integer 0-" in p for p in problems
        )

    def test_a_missing_criterion_does_not_also_blame_the_total(self):
        # Same rule as the severity tally: a criterion that could not be read
        # leaves the subtotal short, and calling that a total mismatch sends the
        # annotator to the wrong line.
        rubric = dict.fromkeys(WEIGHTS, 0) | {"total": 0}
        del rubric["result_traceability"]
        problems = check.validate_record("example", record(**{"scoring_rubric_v0.1": rubric}))
        assert any("result_traceability is missing" in p for p in problems)
        assert not any("total says" in p for p in problems)

    def test_a_criterion_that_is_not_in_the_rubric_is_caught(self):
        rubric = dict.fromkeys(WEIGHTS, 0) | {"total": 0, "data_avilability": 18}
        problems = check.validate_record("example", record(**{"scoring_rubric_v0.1": rubric}))
        assert any("data_avilability is not one of" in p for p in problems)

    def test_readiness_score_must_agree_with_the_total(self):
        broken = record(readiness_score=74)
        problems = check.validate_record("example", broken)
        assert any("readiness_score is 74" in p for p in problems)

    def test_a_missing_rubric_is_a_single_clear_problem(self):
        broken = record()
        del broken["scoring_rubric_v0.1"]
        problems = check.validate_record("example", broken)
        assert len(problems) == 1
        assert "no hand-assigned score" in problems[0]


class TestIdentity:
    def test_paper_id_must_match_the_filename(self):
        problems = check.validate_record("mates", record())
        assert any("but the file is named mates.json" in p for p in problems)

    def test_an_empty_pointer_field_is_reported(self):
        problems = check.validate_record("example", record(github=""))
        assert any("github is missing or empty" in p for p in problems)

    def test_the_tier_must_be_one_of_the_two_the_readme_defines(self):
        problems = check.validate_record("example", record(annotation_provenance={"tier": 3}))
        assert any("expected 1 or 2" in p for p in problems)

    def test_accessions_must_be_a_list(self):
        problems = check.validate_record("example", record(data_accessions="GSE000001"))
        assert any("must be a list" in p for p in problems)


class TestASkeletonNobodyHasFilledIn:
    """The failure that arrived with the tooling meant to make annotating fast.

    ``scripts/prep_benchmark.py`` writes a blank record per paper, and every
    structural rule above is satisfied by one: placeholder prose is non-empty,
    seven zeros total zero correctly, and the template's one example blocker is
    counted correctly by the template's summary. So an unstarted annotation
    validated clean and would have been graded against -- the comparison
    looking entirely normal while measuring nothing.
    """

    def template(self) -> dict:
        import json

        return json.loads(check.TEMPLATE.read_text())

    def test_an_untouched_skeleton_is_rejected(self):
        problems = check.validate_record(
            "CHANGEME-must-equal-this-file-s-name-without-json", self.template()
        )
        assert problems

    def test_each_unfilled_field_is_named_separately(self):
        # The validator doubles as the annotator's checklist, so one problem
        # reading "this record is a template" would be worth less than six
        # naming what to fill.
        problems = " ".join(
            check.validate_record(
                "CHANGEME-must-equal-this-file-s-name-without-json", self.template()
            )
        )
        for field in ("title", "citation", "data_accessions", "blockers", "annotators"):
            assert field in problems
        assert "scoring_rubric_v0.1" in problems

    def test_it_points_at_the_worksheet(self):
        record = self.template() | {"paper_id": "alignn"}
        problems = " ".join(check.validate_record("alignn", record))
        assert "benchmark/worksheets/alignn.md" in problems

    def test_a_filled_field_stops_being_reported(self):
        record = self.template() | {"title": "Atomistic Line Graph Neural Network"}
        problems = " ".join(check.validate_record("x", record))
        assert "title is still" not in problems
        assert "citation is still" in problems

    def test_a_real_record_is_untouched_by_the_rule(self):
        # The guard is equality with the template, so a genuine record can only
        # trip it by coincidence -- and the two shipped Tier-1 records are the
        # standing proof it does not.
        papers, problems = check.read_records()
        for paper_id in ("locusmasterte", "mates"):
            assert paper_id in papers
            assert paper_id not in problems


class TestSeveralRepositories:
    def test_a_list_of_repositories_is_all_expected(self):
        # ALIGNN points at alignn and jarvis, ASPEN at the package and the
        # manuscript. Keeping only the first understates what a reproducer has
        # to obtain, and understates it invisibly: recall would still read 100%.
        _accessions, repos, skipped = check.expected_resources(
            {
                "github": [
                    "https://github.com/usnistgov/alignn",
                    "https://github.com/usnistgov/jarvis",
                ]
            }
        )
        assert len(repos) == 2
        assert skipped == []

    def test_a_single_repository_still_works(self):
        _accessions, repos, _skipped = check.expected_resources(
            {"github": "https://github.com/mcgilldinglab/MATES"}
        )
        assert len(repos) == 1

    def test_a_placeholder_among_real_ones_is_skipped_not_expected(self):
        _accessions, repos, skipped = check.expected_resources(
            {"github": ["https://github.com/a/b", "exact repo URL not confirmed"]}
        )
        assert len(repos) == 1
        assert len(skipped) == 1
