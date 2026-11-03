"""Deterministic scoring against the blueprint's rubric, and severity triage.

Blueprint section 21 is explicit that the score must not be invented by a model,
so nothing here asks one. Every point traces to a finding or a checklist entry,
and the rules are written out below rather than learned.

Two decisions shape the whole module.

**A score is a band, not a point.** Each criterion reports a floor and a
ceiling: the floor is what the evidence proves the paper provides, the ceiling
adds back the points the evidence cannot settle either way. This exists because
the alternative silently breaks the thing the project is for -- deducting a
point because the classifier was unsure reads, downstream, as the paper having
failed to state something, and those are not the same claim. The rule is that a
paper loses points for what it did not say, never for what this tool could not
determine. Uncertainty widens the band instead.

**Three of the seven criteria need the repository.** Method completeness,
execution instructions and result traceability are questions about code, and a
number produced for them from the paper alone would be invented precisely where
the blueprint says not to invent one. When no repository was fetched they are
reported as not assessed and the total is quoted out of 65; when one was, all
seven are scored and the total is out of 100. Two more criteria -- code
availability and environment specification -- are half-undetermined bands
without a repository and close to a single number with one.

Which document a criterion is scored from follows from where the evidence lives.
Data availability is a paper question. Environment specification is a repository
question: a methods section that does not list package versions is normal, and a
repository without a manifest is not. Where both can speak, the better evidence
wins, because a reader needs one sufficient specification rather than two.

Severity follows section 22's own taxonomy, where "reference genome
unspecified", "software version missing" and "critical hyperparameters absent"
are all named as major issues -- which is what the checklist already detects.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from reprolens.discovery import roles
from reprolens.discovery.links import Finding
from reprolens.discovery.patterns import normalize
from reprolens.discovery.resolve import NOT_FOUND, PUBLIC, RESTRICTED, UNCHECKED, Resolutions
from reprolens.documents.base import PageText, is_readable
from reprolens.documents.sections import resolve
from reprolens.documents.supplements import Supplements
from reprolens.extraction.checklist import Checklist
from reprolens.extraction.merge import Merge
from reprolens.repository.analysis import RepoAnalysis

RUBRIC_VERSION = "v0.1"

# Blueprint section 21, verbatim.
WEIGHTS: dict[str, int] = {
    "data_availability": 20,
    "code_availability": 20,
    "environment_specification": 15,
    "method_completeness": 15,
    "parameters_configuration": 10,
    "execution_instructions": 10,
    "result_traceability": 10,
}

# Criteria whose evidence lives in the repository rather than the paper.
NOT_ASSESSED: dict[str, str] = {
    "method_completeness": "needs the repository and a model of what the method requires",
    "execution_instructions": "needs the repository's README and entry points",
    "result_traceability": "needs figure-generating code mapped to each result",
}

_AVAILABILITY = ("data_availability", "code_availability", "associated_data")

# A documented command that sets an environment up rather than running the
# analysis. Both ecosystems' forms, since either one answers the criterion.
_INSTALLS = re.compile(
    r"\b(?:conda\s+(?:create|install)|pip3?\s+install|python3?\s+setup\.py|"
    r"install\.packages|install_github|BiocManager::install|renv::restore)\b"
)

_ACCESSION = re.compile(r"\b([A-Z]{3})(\d{4,9})\b")
_URL_ACCESSION = re.compile(r"acc=([A-Z]{3})(\d{4,9})")
_PARENTHETICAL = re.compile(r"\(([^()]{0,240})\)")


@dataclass(slots=True)
class Criterion:
    name: str
    weight: int
    floor: int
    ceiling: int
    basis: list[str] = field(default_factory=list)
    undetermined: list[str] = field(default_factory=list)
    assessed: bool = True
    reason: str = ""


@dataclass(slots=True)
class Issue:
    severity: str  # "hard_blocker" | "major" | "minor"
    kind: str  # the section 22 phrase this matches
    resource: str
    evidence: str


@dataclass(slots=True)
class Assessment:
    version: str
    criteria: list[Criterion]
    issues: list[Issue]

    @property
    def assessable(self) -> int:
        return sum(c.weight for c in self.criteria if c.assessed)

    @property
    def floor(self) -> int:
        return sum(c.floor for c in self.criteria if c.assessed)

    @property
    def ceiling(self) -> int:
        return sum(c.ceiling for c in self.criteria if c.assessed)

    def counts(self) -> dict[str, int]:
        return {
            severity: len([i for i in self.issues if i.severity == severity])
            for severity in ("hard_blocker", "major", "minor")
        }

    def to_dict(self) -> dict:
        return {
            "rubric_version": self.version,
            "assessed_points": self.assessable,
            "score_floor": self.floor,
            "score_ceiling": self.ceiling,
            "severity": self.counts(),
            "criteria": [asdict(c) for c in self.criteria],
            "issues": [asdict(i) for i in self.issues],
        }


def assess(
    pages: list[PageText],
    findings: list[Finding],
    checklist: Checklist,
    repo: RepoAnalysis | None = None,
    figures: Merge | None = None,
    resolutions: Resolutions | None = None,
    supplements: Supplements | None = None,
) -> Assessment:
    """Score one paper against the rubric, from evidence already gathered.

    ``repo`` is optional and absent is not empty: a paper audited without the
    repository channel keeps three criteria unassessed rather than scoring them
    zero, which is the same rule the OCR path follows for an unread page.

    ``supplements`` changes no number at all. A paper that published its
    parameters in a supplementary table did say them, so it cannot lose points
    for that; and this tool has not read the table, so it cannot award them
    either. What it can do is stop reporting a score on the article body as
    though the article body were the whole paper.

    ``resolutions`` is what the archives said about the accessions the paper
    names. It can only cost a paper points, never earn them: a dataset that
    resolves is the expected case, and one the archive does not have is the
    finding. An accession nobody managed to look up changes no number at all.

    ``figures`` is the image channel after reconciliation against the text, and
    only its corroborated state is consulted. An uncorroborated figure reading
    never reaches a score: it cannot be verified, and a value this tool cannot
    verify must not raise a paper's rating. What that leaves is narrow and
    sound -- a value two independent channels assert.
    """
    if not is_readable(pages):
        # Nothing was read, so nothing can be scored. Reporting zeros here would
        # publish a verdict on the paper that is really a verdict on the reader,
        # and no one downstream could tell the two apart.
        return Assessment(
            version=RUBRIC_VERSION,
            criteria=[
                Criterion(
                    name=name,
                    weight=weight,
                    floor=0,
                    ceiling=weight,
                    assessed=False,
                    reason="the document produced no readable text, so nothing was assessed",
                )
                for name, weight in WEIGHTS.items()
            ],
            issues=[],
        )

    classified = [(finding, roles.classify(finding)) for finding in findings]
    sections = {mark.label for page in pages for mark in page.sections}
    mismatches = link_mismatches(pages)
    read_repo = repo if repo is not None and repo.fetched else None

    criteria = [
        _data_availability(classified, sections, mismatches, resolutions),
        _code_availability(classified, sections, read_repo),
        _environment(checklist, read_repo),
        _parameters(checklist, read_repo, figures),
    ]
    if read_repo is None:
        criteria += [
            Criterion(
                name=name,
                weight=WEIGHTS[name],
                floor=0,
                ceiling=WEIGHTS[name],
                assessed=False,
                reason=reason,
            )
            for name, reason in NOT_ASSESSED.items()
        ]
    else:
        criteria += [
            _method_completeness(read_repo, supplements),
            _execution_instructions(read_repo),
            _result_traceability(read_repo),
        ]
    return Assessment(
        version=RUBRIC_VERSION,
        criteria=criteria,
        # Given the analysis itself, not the read-only view: a repository the
        # paper named and this could not fetch is section 22's "essential code
        # absent", and keying that on ``fetched`` meant the one case where it
        # fires could never reach the issue list.
        issues=_issues(checklist, mismatches, repo, figures, resolutions),
    )


# --------------------------------------------------------------------------- #
# criteria
# --------------------------------------------------------------------------- #


def _data_availability(
    classified, sections, mismatches, resolutions: Resolutions | None = None
) -> Criterion:
    basis: list[str] = []
    undetermined: list[str] = []
    floor = 0

    if "data_availability" in sections or "associated_data" in sections:
        floor += 8
        basis.append("a data availability statement is present")
    else:
        basis.append("no data availability statement found")

    datasets = [
        (finding, classification)
        for finding, classification in classified
        if classification.role in ("own_data", "external_data")
    ]
    if datasets:
        floor += 8
        basis.append(f"{len(datasets)} dataset(s) named by a recognized accession or archive")

    ambiguous = [
        finding
        for finding, classification in classified
        if classification.role == "unclassified"
        and any(o.section in _AVAILABILITY for o in finding.occurrences)
    ]
    if ambiguous:
        # Not a deduction. The wording around these did not settle whether the
        # paper deposited them or reused them, and that is this tool's limit
        # rather than a defect in the paper.
        undetermined.append(
            f"{len(ambiguous)} resource(s) in an availability statement could not be "
            f"resolved to a role: {', '.join(f.value for f in ambiguous[:4])}"
        )

    ceiling = floor + (4 if ambiguous else 0)
    if not ambiguous and floor >= 16:
        floor += 4
        ceiling = floor
        basis.append("every resource in the statement resolved to a role")

    for prefix, prose, link in mismatches:
        # Two points, not four. The record itself is still reachable: the
        # sentence names GSE114952 correctly and only the printed URL is wrong,
        # so a reader loses time rather than access.
        floor -= 2
        ceiling -= 2
        basis.append(
            f"a link in the statement resolves to {prefix}{link} while the sentence "
            f"beside it names {prefix}{prose}"
        )

    if resolutions is not None:
        named = {f.value.strip().upper() for f, _c in datasets}
        relevant = [e for e in resolutions.entries if e.accession in named]
        absent = [e for e in relevant if e.status == NOT_FOUND]
        restricted = [e for e in relevant if e.status == RESTRICTED]
        unchecked = [e for e in relevant if e.status == UNCHECKED]
        confirmed = [e for e in relevant if e.status == PUBLIC]

        if confirmed:
            basis.append(
                f"{len(confirmed)} of {len(relevant)} named dataset(s) confirmed present "
                f"in the archive they name"
            )
        if absent:
            # The archive answered and does not have it. A reproducer following
            # this statement arrives at nothing, which is a floor fact about the
            # paper rather than an uncertainty in the audit.
            cost = min(8, 2 * len(absent))
            floor -= cost
            ceiling -= cost
            basis.append(
                f"{len(absent)} named dataset(s) are NOT in the archive: "
                f"{', '.join(e.accession for e in absent[:4])}"
            )
        if restricted:
            # Named, real, and still not obtainable. Two points once rather than
            # per accession, because one access request covers a study and the
            # barrier is single however many accessions sit behind it. Not a
            # flaw in the writing -- but readiness is about whether someone can
            # actually run this, and they cannot without approval.
            floor -= 2
            ceiling -= 2
            basis.append(
                f"{len(restricted)} named dataset(s) are under controlled access and cannot "
                f"be obtained without an approved request"
            )
        if unchecked:
            # Costs nothing. A lookup that did not happen is a fact about this
            # run, and the rule throughout is that a paper loses points for what
            # it did not say, never for what this tool could not determine.
            undetermined.append(
                f"{len(unchecked)} named dataset(s) were not confirmed to exist "
                f"({unchecked[0].detail}); the points above assume they do"
            )

    weight = WEIGHTS["data_availability"]
    return Criterion(
        name="data_availability",
        weight=weight,
        floor=max(0, min(floor, weight)),
        ceiling=max(0, min(ceiling, weight)),
        basis=basis,
        undetermined=undetermined,
    )


def _code_availability(classified, sections, repo: RepoAnalysis | None) -> Criterion:
    basis: list[str] = []
    floor = 0

    code = [
        finding for finding, classification in classified if classification.role == "analysis_code"
    ]
    declared = [
        finding for finding in code if any(o.section in _AVAILABILITY for o in finding.occurrences)
    ]

    undetermined: list[str] = []

    if declared:
        floor += 10
        basis.append(f"{len(declared)} code resource(s) named in an availability statement")
        # Keyed on the role rather than on a "Code availability" heading: BMC
        # journals put code in the data availability statement, and penalising
        # LocusMasterTE for its publisher's house style would measure the
        # journal rather than the paper.
        if any(finding.kind in ("github", "gitlab", "zenodo") for finding in declared):
            basis.append("named as a resolvable repository, not 'available on request'")
    else:
        basis.append("no analysis code named in any availability statement")

    weight = WEIGHTS["code_availability"]
    ceiling = floor

    if repo is None:
        if declared:
            # The remaining half of this criterion is whether the repository
            # holds code that covers the published analysis, and nothing here
            # fetched one. Claiming the full 20 would assert something this tool
            # has not looked at.
            undetermined.append("the repository was not fetched, so its contents are unverified")
            ceiling = floor + 10
        return Criterion(
            name="code_availability",
            weight=weight,
            floor=min(floor, weight),
            ceiling=min(ceiling, weight),
            basis=basis,
            undetermined=undetermined,
        )

    for entry in repo.unfetched:
        # A repository named in an availability statement that does not resolve
        # is section 22's "essential code absent", not a smaller version of
        # available. The ten points for declaring it are not withdrawn -- the
        # paper did state where the code is -- but nothing is added.
        verb = "could not be fetched" if entry.get("attempted", True) else "was not fetched"
        basis.append(f"{entry['repository']} was named and {verb}: {entry['reason']}")

    if repo.checkouts:
        floor += 5
        commits = ", ".join(f"{c['repository']}@{c['commit'][:10]}" for c in repo.checkouts)
        basis.append(f"{len(repo.checkouts)} repository(ies) resolved and read: {commits}")

    source_files = repo.inventory.by_kind("python", "r", "shell", "notebook")
    if source_files and repo.execution.runnable:
        floor += 5
        basis.append(
            f"{len(source_files)} source file(s) and "
            f"{len(repo.execution.runnable)} runnable command(s) present"
        )
    elif source_files:
        basis.append(f"{len(source_files)} source file(s) but no command that runs them")

    ceiling = floor
    if repo.figures.assessable:
        # Blueprint section 2 names this failure mode directly: "the repository
        # does not contain the code required for a reported figure".
        penalty = min(4, 2 * len(repo.figures.uncovered))
        if penalty:
            floor -= penalty
            ceiling -= penalty
            basis.append(
                f"no generating code found for figure(s) "
                f"{', '.join(str(n) for n in repo.figures.uncovered)}"
            )
    elif repo.figures.paper_figures:
        # Nothing in the repositories is named for a figure, so whether each
        # published figure has code cannot be settled either way. Widening the
        # band by the largest deduction says that honestly; deducting would
        # assert an absence that was never established.
        floor -= 4
        undetermined.append(
            "no file is named for a figure, so whether the repository covers each "
            "published figure could not be determined"
        )

    return Criterion(
        name="code_availability",
        weight=weight,
        floor=max(0, min(floor, weight)),
        ceiling=max(0, min(ceiling, weight)),
        basis=basis,
        undetermined=undetermined,
    )


def _environment(checklist: Checklist, repo: RepoAnalysis | None) -> Criterion:
    basis: list[str] = []
    floor = 0

    languages = [s for s in checklist.software if s.kind == "language" and s.declared]
    environments = [s for s in checklist.software if s.kind == "environment" and s.declared]

    if languages:
        floor += 5
        basis.append(f"language named: {', '.join(s.name for s in languages)}")
        if any(s.specificity == "pinned" for s in languages):
            floor += 5
            basis.append("with a version")
        else:
            basis.append("without a version")
    else:
        basis.append("no implementation language named")

    if environments:
        floor += 5
        basis.append(f"environment declared: {', '.join(s.name for s in environments)}")
    else:
        basis.append("no environment file, conda env or container named")

    weight = WEIGHTS["environment_specification"]
    if repo is None:
        # A paper rarely states its environment and a repository usually does.
        # Scoring this at the floor would report every paper as having no
        # environment, when what is true is that the paper does not describe one
        # and the repository has not been read.
        return Criterion(
            name="environment_specification",
            weight=weight,
            floor=min(floor, weight),
            ceiling=weight,
            basis=basis,
            undetermined=[
                "an environment may be declared in the repository, which was not fetched"
            ],
        )

    # Scored from the repository, which is where an environment is declared. The
    # three components are a design choice and worth naming as one: a manifest
    # an installer reads (5), an interpreter version (4), and how much of the
    # dependency set resolves to an exact version (6).
    repo_basis: list[str] = []
    repo_floor = 0
    manifests = repo.manifests

    installable = manifests.installable
    if installable:
        repo_floor += 5
        files = sorted({d.source for d in installable})
        repo_basis.append(f"dependencies declared in {', '.join(files[:3])}")
    else:
        repo_basis.append("no dependency manifest an installer reads")

    pinned_interpreters = [i for i in manifests.interpreters if i.pinning == "pinned"]
    if any(not i.prose_only for i in pinned_interpreters):
        repo_floor += 4
        repo_basis.append("interpreter version pinned in a manifest")
    elif pinned_interpreters:
        # A README that gives the exact "conda create ... python=3.6" line
        # specifies the environment; it just does not install it. One point
        # short of a manifest, not four.
        repo_floor += 3
        interpreter = pinned_interpreters[0]
        repo_basis.append(
            f"interpreter pinned to {interpreter.ecosystem} {interpreter.version}, "
            f"but only in {interpreter.source}"
        )
    else:
        repo_basis.append("no interpreter version declared anywhere")

    distinct = manifests.distinct_pinning()
    if distinct:
        exact = len([v for v in distinct.values() if v == "pinned"])
        repo_floor += round(6 * exact / len(distinct))
        repo_basis.append(f"{exact} of {len(distinct)} distinct packages resolve to one version")

    for conflict in manifests.conflicts[:2]:
        repo_floor -= 2
        repo_basis.append(
            f"{conflict.name} is pinned to {conflict.left_constraint} in "
            f"{conflict.left_source} and {conflict.right_constraint} in {conflict.right_source}"
        )

    for language in manifests.unmanaged_languages:
        repo_floor -= 3
        repo_basis.append(
            f"{len(repo.inventory.by_kind(language))} {language.upper()} source file(s) "
            f"with no {language.upper()} dependency or version declaration anywhere"
        )

    # Only for languages that do have a manifest. An undeclared R package in a
    # repository with no R manifest at all is the same fact as the line above,
    # and counting it twice would charge one omission to two components.
    undeclared = [
        used
        for used in manifests.undeclared_imports
        if used.ecosystem not in manifests.unmanaged_languages
    ]
    if undeclared:
        repo_floor -= min(2, len(undeclared))
        repo_basis.append(
            f"{len(undeclared)} import(s) no manifest declares: "
            f"{', '.join(used.name for used in undeclared[:4])}"
        )

    # Whichever document specifies the environment better. A reader needs one
    # sufficient specification, not two.
    if repo_floor >= floor:
        floor, basis = repo_floor, repo_basis
    else:
        basis += ["the repository specifies less than the paper does", *repo_basis]

    return Criterion(
        name="environment_specification",
        weight=weight,
        floor=max(0, min(floor, weight)),
        ceiling=max(0, min(floor, weight)),
        basis=basis,
    )


def _parameters(
    checklist: Checklist, repo: RepoAnalysis | None, figures: Merge | None = None
) -> Criterion:
    basis: list[str] = []
    undetermined: list[str] = []
    floor = 0

    if checklist.commands:
        floor += 3
        basis.append(f"{len(checklist.commands)} runnable command(s) given")
    else:
        basis.append("no runnable command given")

    valued = [p for p in checklist.parameters if p.value]
    if checklist.parameters:
        if len(valued) == len(checklist.parameters):
            floor += 4
            basis.append("every named flag carries a value")
        else:
            basis.append(
                f"{len(checklist.parameters) - len(valued)} of {len(checklist.parameters)} "
                f"named flag(s) carry no value"
            )
    else:
        # No flags named is not evidence of good practice and not evidence of
        # bad practice. It is no evidence.
        undetermined.append("no command-line flags named anywhere, so none could be checked")

    declared = [s for s in checklist.software if s.declared]
    pinned = [s for s in declared if s.specificity == "pinned"]
    if declared and len(pinned) * 2 > len(declared):
        floor += 3
        basis.append(f"{len(pinned)} of {len(declared)} declared tools pinned to a version")
    elif declared:
        basis.append(f"only {len(pinned)} of {len(declared)} declared tools pinned to a version")

    if figures is not None:
        stated = figures.corroborated_values("parameters_visible")
        if stated:
            # A figure-stated parameter raises the FLOOR, where a
            # repository-stated one raises only the ceiling, and the asymmetry is
            # the point. A command in a README may be a worked example that has
            # nothing to do with the published numbers. A figure *is* the
            # published result, so a threshold printed on it is the paper
            # documenting the configuration behind that result -- and this only
            # counts values the document's own text repeats, so two independent
            # channels assert each one.
            #
            # Capped, because the cap is doing real work: ASPEN's figures also
            # yield "Log(TPM) < 3", which is a display bin rather than a
            # configured threshold, and nothing here can tell the two apart. A
            # bound keeps a chatty figure from carrying the criterion on values
            # this layer does not understand.
            credit = min(2, len(stated))
            floor += credit
            basis.append(
                f"{len(stated)} parameter value(s) stated in a figure and repeated in the "
                f"text (e.g. {stated[0]})"
            )

    weight = WEIGHTS["parameters_configuration"]
    ceiling = floor + (4 if not checklist.parameters else 0)

    if repo is not None:
        valued_flags = [f for f in repo.execution.flags if f.value]
        if valued_flags:
            # A documented command raises the ceiling and not the floor, and the
            # distinction is the whole point of this criterion. MATES's README
            # spells out "--species Human" and a full STAR invocation, so the
            # configuration may well be recoverable -- but nothing ties those
            # values to the run that produced the published numbers. Scoring
            # them as the paper's parameters would report a worked example as
            # the experiment.
            ceiling += 3
            undetermined.append(
                f"{len(valued_flags)} flag(s) carry concrete values in repository commands "
                f"(e.g. {valued_flags[0].flag} {valued_flags[0].value}), but nothing "
                f"identifies them as the configuration behind the published results"
            )
        for missing in repo.execution.missing_inputs:
            if missing.status != "demo_scale":
                continue
            # The published input is definitely not here, which is a floor fact
            # rather than an uncertainty.
            floor -= 3
            ceiling -= 3
            basis.append(
                f"{missing.path}, a required input of {missing.named_by}, "
                f"is present only at demo scale: {missing.detail}"
            )

    return Criterion(
        name="parameters_configuration",
        weight=weight,
        floor=max(0, min(floor, weight)),
        ceiling=max(0, min(ceiling, weight)),
        basis=basis,
        undetermined=undetermined,
    )


# --------------------------------------------------------------------------- #
# criteria that need the repository
# --------------------------------------------------------------------------- #


def _method_completeness(repo: RepoAnalysis, supplements: Supplements | None = None) -> Criterion:
    """Whether the method can be followed, from both documents at once.

    Only two of the three things this criterion is about can be established.
    That the code implementing the method is readable, and that something
    describes how its steps fit together, are both checkable. Whether the
    description is otherwise *complete* -- every preprocessing choice stated,
    every intermediate step specified -- needs a model of what the method
    requires, which is the same gap the resource checklist reports about itself.
    So the floor is what the two checkable components prove and the ceiling
    stays at the full weight.
    """
    basis: list[str] = []
    undetermined: list[str] = []
    floor = 0

    source_files = repo.inventory.by_kind("python", "r", "shell", "notebook")
    if source_files:
        floor += 5
        basis.append(f"the method's implementation is present: {len(source_files)} source file(s)")
    else:
        basis.append("no source code found in the repositories")

    if repo.execution.documented_in:
        floor += 5
        basis.append(f"the steps are described in {', '.join(repo.execution.documented_in[:3])}")
    else:
        basis.append("no documentation file shows how the steps are run")

    for index, step in enumerate(repo.undocumented_steps):
        # Section 22's "preprocessing unclear". The first undocumented step
        # establishes that the methods section is incomplete; each further one
        # reinforces that rather than multiplying the harm, and most are
        # conventional glue around the one that changes the data.
        floor -= 2 if index == 0 else 1
        basis.append(f"{step.tool} is run by the repository and not named in the paper")

    if supplements is not None:
        deferred = supplements.deferred_from_methods
        if deferred:
            # No point change in either direction. A paper that put a step in a
            # supplementary table did say it, so it cannot be marked down for
            # that; and nothing here has read the table, so nothing can be
            # awarded for it. What the note buys is that the number above stops
            # being reported as a verdict on the whole method when part of the
            # method is in a file this audit never opened.
            undetermined.append(
                f"the Methods section defers to {len(deferred)} supplementary item(s) "
                f"({', '.join(r.label for r in deferred[:4])}) whose contents were not read, "
                f"so the score above covers the article body only"
            )
        elif supplements.inventory != "declared":
            undetermined.append(
                "the input carries no supplement manifest, so whether method detail was "
                "published outside the article body could not be determined"
            )

    weight = WEIGHTS["method_completeness"]
    return Criterion(
        name="method_completeness",
        weight=weight,
        floor=max(0, min(floor, weight)),
        ceiling=weight,
        basis=basis,
        undetermined=[
            "whether the description covers every preprocessing choice needs a model "
            "of what the method requires, which this pipeline does not have",
            *undetermined,
        ],
    )


def _execution_instructions(repo: RepoAnalysis) -> Criterion:
    """Whether someone could run it from what is written down."""
    basis: list[str] = []
    undetermined: list[str] = []
    floor = 0

    if repo.execution.runnable:
        floor += 3
        first = repo.execution.runnable[0]
        basis.append(f"{len(repo.execution.runnable)} command(s), e.g. {first.name}")
    else:
        basis.append("no entry point with a command")

    documented = [e for e in repo.execution.entry_points if e.kind == "documented"]
    if documented:
        floor += 3
        basis.append(f"{len(documented)} command(s) shown in the documentation")
    else:
        basis.append("no command shown in any documentation file")

    # Matched on the command rather than its first word, because an R install
    # line does not start with the installer: "devtools::install_github(...)"
    # and "if(!require(devtools)) install.packages(\"devtools\")" both show
    # setup, and neither has a head token worth keying on.
    setup = [e for e in documented if _INSTALLS.search(e.command)]
    if setup:
        floor += 2
        basis.append("installation or environment setup is shown as a command")
    else:
        basis.append("no installation command shown")

    placeholders = [i for i in repo.execution.inputs if i.status == "user_supplied"]
    resolved = [i for i in repo.execution.inputs if i.status == "present"]
    if placeholders:
        # The example commands name files the user has to bring. Whether the
        # documentation explains adequately what those files are is a judgement
        # about prose, so the two points are a band rather than a verdict.
        undetermined.append(
            f"{len(placeholders)} input(s) in the documented commands are placeholders "
            f"the user must supply: {', '.join(i.path for i in placeholders[:4])}"
        )
        ceiling = floor + 2
    elif resolved:
        floor += 2
        ceiling = floor
        basis.append("every input named by a command is present in the repository")
    else:
        ceiling = floor
        basis.append("no command names an input file")

    weight = WEIGHTS["execution_instructions"]
    return Criterion(
        name="execution_instructions",
        weight=weight,
        floor=max(0, min(floor, weight)),
        ceiling=max(0, min(ceiling, weight)),
        basis=basis,
        undetermined=undetermined,
    )


def _result_traceability(repo: RepoAnalysis) -> Criterion:
    """Whether each published result can be traced to the code that made it.

    Scored on the mapping and nothing else. A file called ``fig3.R`` answers
    "which code produced Figure 3"; whether running it reproduces the figure is
    a different question, and the blueprint keeps it separate -- section 5
    distinguishes reproducibility readiness from verified reproduction, and the
    benchmark records score the two independently.
    """
    basis: list[str] = []
    weight = WEIGHTS["result_traceability"]

    if not repo.figures.paper_figures:
        return Criterion(
            name="result_traceability",
            weight=weight,
            floor=0,
            ceiling=weight,
            basis=["no figure references found in the paper"],
            undetermined=["no published result to trace"],
        )

    total = len(repo.figures.paper_figures)
    if not repo.figures.assessable:
        return Criterion(
            name="result_traceability",
            weight=weight,
            floor=0,
            ceiling=weight,
            basis=[f"{total} figure(s) in the paper, no file named for any of them"],
            undetermined=[
                "figures may be generated by a pipeline step whose name says what it "
                "computes rather than which figure it fills, which this cannot tell apart "
                "from no figure code at all"
            ],
        )

    covered = len(repo.figures.covered)
    floor = round(weight * covered / total)
    basis.append(f"{covered} of {total} published figures have a script named for them")
    for number, source in repo.figures.scripts:
        basis.append(f"figure {number} <- {source}")
    if repo.figures.uncovered:
        basis.append(f"no script for figure(s) {', '.join(str(n) for n in repo.figures.uncovered)}")
    return Criterion(
        name="result_traceability",
        weight=weight,
        floor=floor,
        ceiling=floor,
        basis=basis,
    )


# --------------------------------------------------------------------------- #
# severity, per blueprint section 22
# --------------------------------------------------------------------------- #


def _resolution_issues(resolutions: Resolutions) -> list[Issue]:
    """Datasets the paper names that a reproducer cannot actually get.

    Two findings, kept apart because they ask different things of the reader. An
    accession the archive does not have is probably a typo or a withdrawal, and
    someone has to work out which. One under controlled access is neither: it is
    real, correctly cited, and still months away behind a data-access request
    that can be refused.
    """
    issues: list[Issue] = []
    for entry in resolutions.entries:
        if entry.status == NOT_FOUND:
            issues.append(
                Issue(
                    "major",
                    "a named dataset is not present in the archive it names",
                    entry.accession,
                    entry.detail,
                )
            )
        elif entry.status == RESTRICTED:
            issues.append(
                Issue(
                    "major",
                    "essential data is under controlled access",
                    entry.accession,
                    entry.detail,
                )
            )
    return issues


def _conflict_issues(figures: Merge) -> list[Issue]:
    """A paper's own figure and text disagreeing about a value.

    Raised as an issue and left out of the arithmetic on purpose. Which channel
    is wrong decides what the finding means -- a figure showing the version
    actually used against a methods section that was never updated is a
    different paper from the reverse -- and nothing here can tell them apart.
    Scoring it would put a number on a judgement this tool has not made, while
    saying nothing sends a reproducer to a value that may be the wrong one. So
    it is reported at major severity, which is the same treatment
    ``blockers_side_by_side`` gives a comparison whose meaning needs a reader.
    """
    return [
        Issue(
            "major",
            "the paper's figure and its text disagree about a value",
            conflict.key,
            conflict.evidence,
        )
        for conflict in figures.conflicts
    ]


def _issues(
    checklist: Checklist,
    mismatches,
    repo: RepoAnalysis | None,
    figures: Merge | None = None,
    resolutions: Resolutions | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    issues += _repository_issues(repo) if repo is not None else []
    issues += _conflict_issues(figures) if figures is not None else []
    issues += _resolution_issues(resolutions) if resolutions is not None else []

    for item in checklist.gaps():
        if item.kind == "reference":
            issues.append(
                Issue(
                    "major",
                    "reference genome or annotation unspecified",
                    item.name,
                    item.evidence,
                )
            )
        elif item.kind in ("tool", "language"):
            issues.append(Issue("major", "software version missing", item.name, item.evidence))
        else:
            issues.append(Issue("minor", "package version missing", item.name, item.evidence))

    for parameter in checklist.parameters:
        if parameter.value is None:
            issues.append(
                Issue(
                    "major",
                    "critical hyperparameters absent",
                    parameter.flag,
                    parameter.evidence,
                )
            )

    for prefix, prose, link in mismatches:
        issues.append(
            Issue(
                "major",
                "a declared resource does not resolve",
                f"{prefix}{prose}",
                f"the link beside it resolves to {prefix}{link}",
            )
        )

    order = {"hard_blocker": 0, "major": 1, "minor": 2}
    return sorted(issues, key=lambda i: (order[i.severity], i.resource.casefold()))


def _repository_issues(repo: RepoAnalysis) -> list[Issue]:
    """Section 22 severities for what the repository channel found.

    Section 16's consistency checks map onto the taxonomy fairly directly:
    a referenced file that does not exist, a version inconsistency and an
    undocumented environment variable are each named there, and section 22 gives
    the severity band each one belongs in.
    """
    issues: list[Issue] = []

    for entry in repo.unfetched:
        if not entry.get("attempted", True):
            # Nothing was tried, so nothing was established. This belongs in
            # what could not be determined, which the audit's warnings carry.
            continue
        issues.append(
            Issue(
                "hard_blocker",
                "essential code absent",
                entry["repository"],
                f"Named by the paper and not retrievable: {entry['reason']}",
            )
        )

    for missing in repo.execution.missing_inputs:
        if missing.status == "demo_scale":
            # Section 22's "required dataset unavailable". The repository holds
            # a file at the path the command expects and holds nothing else of
            # that kind, so what ships is a worked example and the published
            # input is not here.
            #
            # The rule is wrong in one case it cannot yet see: a repository that
            # ships a demo and documents where to download the real input is not
            # blocked. Establishing that needs the dataset channel of blueprint
            # section 17, which checks whether a named archive actually serves
            # the file. Until then this is reported with its evidence attached
            # so the claim can be checked rather than taken.
            issues.append(
                Issue("hard_blocker", "required dataset unavailable", missing.path, missing.detail)
            )
        else:
            issues.append(
                Issue(
                    "minor",
                    "referenced file that does not exist",
                    missing.path,
                    f"named by {missing.named_by} and absent from every repository",
                )
            )

    for number in repo.figures.uncovered if repo.figures.assessable else []:
        issues.append(
            Issue(
                "major",
                "the repository does not contain the code required for a reported figure",
                f"figure {number}",
                # Starts with a capital, so the report's quote trimmer reads it
                # as constructed evidence rather than a window cut from prose.
                f"Scripts are named for figure(s) "
                f"{', '.join(str(n) for n in repo.figures.covered)}, not this one",
            )
        )

    for step in repo.undocumented_steps:
        issues.append(Issue("major", "preprocessing unclear", step.tool, step.evidence))

    for conflict in repo.manifests.conflicts:
        issues.append(
            Issue(
                "major",
                "version inconsistency between declarations",
                conflict.name,
                f"{conflict.left_constraint} in {conflict.left_source}, "
                f"{conflict.right_constraint} in {conflict.right_source}",
            )
        )

    for language in repo.manifests.unmanaged_languages:
        count = len(repo.inventory.by_kind(language))
        issues.append(
            Issue(
                "major",
                "no dependency declaration for a language the repository uses",
                language.upper(),
                f"{count} {language.upper()} source file(s), no manifest and no version",
            )
        )

    for used in repo.manifests.undeclared_imports:
        if used.ecosystem in repo.manifests.unmanaged_languages:
            continue  # already reported once, as the whole missing environment
        issues.append(
            Issue(
                "minor",
                "a dependency the code imports is declared nowhere",
                used.name,
                f"imported in {used.source}",
            )
        )

    # One note per interpreter version, not per file naming it: MATES pins
    # python=3.9 in two different READMEs.
    reported: set[str] = set()
    for interpreter in repo.manifests.interpreters:
        if interpreter.end_of_life and interpreter.version not in reported:
            reported.add(interpreter.version)
            issues.append(
                Issue(
                    "minor",
                    "the pinned interpreter is out of support",
                    f"{interpreter.ecosystem} {interpreter.version}",
                    f"support ended {interpreter.end_of_life}; pinned in {interpreter.source}",
                )
            )

    for variable in repo.execution.env_vars:
        if not variable.documented:
            issues.append(
                Issue(
                    "minor",
                    "undocumented environment variable",
                    variable.name,
                    f"read in {variable.source}, named in no documentation file",
                )
            )

    return issues


# --------------------------------------------------------------------------- #
# evidence
# --------------------------------------------------------------------------- #


def link_mismatches(pages: list[PageText]) -> list[tuple[str, str, str]]:
    """Accessions whose URL disagrees with the sentence printed beside them.

    MATES's data availability statement reads "(GSE114952,
    https://...acc.cgi?acc=GSE11495)": the link drops a digit and resolves to a
    different record. The paper says the dataset is available and it is, but not
    at the address given, which no amount of reading the sentence reveals.

    Scoped per accession prefix, and comparing only prose against URL. Two
    different samples in one parenthetical is normal -- the same statement names
    GSM4800803 "for 10x" and GSM4800807 "for Pacbio" -- so a bare "two different
    values here" test reports that correct sentence as broken.
    """
    resolver = resolve(pages)
    seen: set[tuple[str, str, str]] = set()
    found: list[tuple[str, str, str]] = []

    for page in pages:
        text = normalize(page.text)
        for group in _PARENTHETICAL.finditer(text):
            if resolver.at(page.page, group.start()).label not in _AVAILABILITY:
                continue
            body = group.group(1)
            in_link = {(p, d) for p, d in _URL_ACCESSION.findall(body)}
            in_prose = {(p, d) for p, d in _ACCESSION.findall(_URL_ACCESSION.sub("", body))}
            for prefix in {p for p, _ in in_link} & {p for p, _ in in_prose}:
                links = {d for p, d in in_link if p == prefix}
                prose = {d for p, d in in_prose if p == prefix}
                if links == prose:
                    continue
                for stated in sorted(prose - links):
                    for target in sorted(links - prose):
                        key = (prefix, stated, target)
                        if key not in seen:
                            seen.add(key)
                            found.append(key)
    return found
