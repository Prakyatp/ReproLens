"""The repository channel's verdict: what the code shows that the paper cannot.

This module joins the two sides. On its own, a repository reading says what
exists; what makes it evidence about reproducibility is the comparison with the
paper. Two comparisons are made here, and both produced findings on the
benchmark papers that neither document alone contains:

* **Figures the paper publishes against scripts the repository names.**
  LocusMasterTE's companion repository holds ``fig1.R``, ``fig3.R``, ``fig4.R``
  and ``fig5.R``. The paper has five main figures. Figure 2 has no generating
  script, and that is visible only by putting the two side by side.
* **Steps the code performs against steps the paper describes.** The same
  repository's long-read wrapper runs Pychopper as step one. The string
  "pychopper" does not occur anywhere in the paper. Someone following the
  methods section builds a different pipeline than the authors ran.

Both comparisons use the paper-side checklist's vocabulary, so a divergence is a
fact about the two documents rather than an artifact of two word lists.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from reprolens.extraction.checklist import SOFTWARE_KINDS
from reprolens.repository import datarefs as datarefs_read
from reprolens.repository import execution as execution_read
from reprolens.repository import inventory as inventory_read
from reprolens.repository import manifests as manifests_read
from reprolens.repository.fetch import FetchResult

# "fig3.R", "Figure_4.ipynb", "fig_5b.py". A supplementary figure's script is
# matched separately: the main repository is not expected to hold it, so its
# absence is not a finding.
_FIGURE_SCRIPT = re.compile(
    r"^(?:supp(?:l(?:ementary)?)?[\s_-]*)?fig(?:ure)?[\s_.-]*(\d{1,2})", re.I
)
_SUPPLEMENTARY = re.compile(r"^(?:supp|s)(?:[\s_-]|fig)", re.I)


@dataclass(slots=True)
class FigureCoverage:
    paper_figures: list[int] = field(default_factory=list)
    scripts: list[tuple[int, str]] = field(default_factory=list)
    covered: list[int] = field(default_factory=list)
    uncovered: list[int] = field(default_factory=list)

    @property
    def assessable(self) -> bool:
        """Whether the comparison can be made at all.

        A repository with no figure-named script anywhere is not evidence that
        the figures are untraceable: plenty of projects generate figures from a
        pipeline step or a notebook whose name says what it computes rather than
        which figure it fills. That case is reported as undetermined, not as a
        failure, which is the same rule the rest of the scoring follows.
        """
        return bool(self.paper_figures and self.scripts)


@dataclass(slots=True)
class UndocumentedStep:
    tool: str
    evidence: str  # where in the repository it is called


@dataclass(slots=True)
class RepoAnalysis:
    checkouts: list[dict] = field(default_factory=list)
    unfetched: list[dict] = field(default_factory=list)
    inventory: inventory_read.Inventory = field(default_factory=inventory_read.Inventory)
    manifests: manifests_read.Manifests = field(default_factory=manifests_read.Manifests)
    execution: execution_read.Execution = field(default_factory=execution_read.Execution)
    figures: FigureCoverage = field(default_factory=FigureCoverage)
    figure_data: datarefs_read.DataRefs = field(default_factory=datarefs_read.DataRefs)
    undocumented_steps: list[UndocumentedStep] = field(default_factory=list)

    @property
    def fetched(self) -> bool:
        """Whether there is a repository to reason about at all.

        Everything downstream keys on this. No repository named, a clone that
        failed and a repository full of nothing are three different states, and
        only the last one is a finding about the paper.
        """
        return bool(self.checkouts)

    def to_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "repositories": self.checkouts,
            "not_fetched": self.unfetched,
            "inventory": self.inventory.summary(),
            "files": [asdict(f) for f in self.inventory.files],
            "dependencies": self.manifests.to_dict(),
            "execution": self.execution.to_dict(),
            "figure_traceability": {
                "assessable": self.figures.assessable,
                "paper_figures": self.figures.paper_figures,
                "scripts": [{"figure": n, "source": s} for n, s in self.figures.scripts],
                "covered": self.figures.covered,
                "uncovered": self.figures.uncovered,
            },
            "figure_data": self.figure_data.to_dict(),
            "undocumented_steps": [asdict(s) for s in self.undocumented_steps],
        }


def analyze(
    results: list[FetchResult],
    *,
    paper_figures: list[int],
    paper_software: set[str],
) -> RepoAnalysis:
    """Read every fetched repository and compare it against the paper."""
    checkouts = [r.checkout for r in results if r.checkout is not None]
    analysis = RepoAnalysis(
        checkouts=[c.to_dict() for c in checkouts],
        unfetched=[
            {
                "repository": r.ref.slug,
                "url": r.ref.url,
                "reason": r.reason,
                "attempted": r.attempted,
            }
            for r in results
            if r.checkout is None
        ],
    )
    if not checkouts:
        return analysis

    analysis.inventory = inventory_read.take(checkouts)
    analysis.manifests = manifests_read.read(analysis.inventory)
    analysis.execution = execution_read.read(analysis.inventory)
    analysis.figures = _figure_coverage(analysis.inventory, paper_figures)
    analysis.figure_data = datarefs_read.read(analysis.inventory, analysis.figures.scripts)
    analysis.undocumented_steps = _undocumented_steps(analysis.execution, paper_software)
    return analysis


def _figure_coverage(
    inventory: inventory_read.Inventory, paper_figures: list[int]
) -> FigureCoverage:
    coverage = FigureCoverage(paper_figures=sorted(paper_figures))
    for file in inventory.by_kind("r", "python", "notebook", "shell"):
        stem = file.name.rsplit(".", 1)[0]
        if _SUPPLEMENTARY.match(stem):
            continue
        match = _FIGURE_SCRIPT.match(stem)
        if match:
            coverage.scripts.append((int(match.group(1)), file.label))
    coverage.scripts.sort()
    named = {number for number, _ in coverage.scripts}
    coverage.covered = sorted(named & set(coverage.paper_figures))
    coverage.uncovered = sorted(set(coverage.paper_figures) - named)
    return coverage


def _undocumented_steps(
    execution: execution_read.Execution, paper_software: set[str]
) -> list[UndocumentedStep]:
    """Pipeline tools the repository runs that the paper never names.

    Blueprint section 16 calls this an undocumented preprocessing step. It is
    the one class of method incompleteness that can be established rather than
    guessed at: the comparison is between two concrete lists, and the evidence
    for each side is a file and a line.

    Restricted to things of kind ``tool``, which is the whole content of the
    claim. A methods section that does not name every Python package the code
    imports is a normal methods section; the unreported ``conda``, ``PyTorch``
    and ``Ensembl`` that an unrestricted comparison produced were noise around
    two real findings -- LocusMasterTE runs Pychopper and samtools, and names
    neither as a step it performs.
    """
    declared = {name.casefold() for name in paper_software}
    return [
        UndocumentedStep(tool=call.tool, evidence=f"{call.source}: {call.evidence}")
        for call in execution.tools_called
        if SOFTWARE_KINDS.get(call.tool) == "tool" and call.tool.casefold() not in declared
    ]
