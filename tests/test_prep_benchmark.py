"""The other half of the no-leak rule, pointing the opposite way.

``tests/test_no_benchmark_leak.py`` asserts the app never reads the ground
truth. This asserts the reverse: that the tooling which helps produce the
ground truth never puts the app's answers in front of the annotator.

Both failures are the same failure. The benchmark's whole job is to be an
independent check on the app, and an independent check that was written while
reading the app's output is not one -- the agreement number would be measuring
the tool against itself, it would look excellent, and nothing about it would be
true. That is worth a test rather than a comment, because the pull toward
leaking is real: the app already extracts the accessions the record needs, and
pasting them in would genuinely save the annotator time.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts import prep_benchmark

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "scripts" / "prep_benchmark.py"

# The layers that form an opinion about a paper. ``WEIGHTS`` is exempt and named
# explicitly: it is the criterion names and their point values, which
# benchmark/README.md requires the worksheet to take from the app so the two
# cannot drift. Everything else in the scoring layer is a verdict.
FORBIDDEN_MODULES = (
    "reprolens.extraction",
    "reprolens.discovery",
    "reprolens.graph",
    "reprolens.repository.analysis",
    "reprolens.repository.manifests",
    "reprolens.repository.datarefs",
    "reprolens.repository.execution",
    "reprolens.reporting",
)
ALLOWED_FROM_SCORING = {"WEIGHTS"}


def _imports(source: str) -> list[tuple[str, tuple[str, ...]]]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out.extend((alias.name, ()) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module, tuple(alias.name for alias in node.names)))
    return out


class TestTheNeutralityOfTheGenerator:
    def test_it_does_not_import_a_layer_that_forms_an_opinion(self):
        offenders = [
            module
            for module, _names in _imports(SOURCE.read_text())
            if any(module == f or module.startswith(f + ".") for f in FORBIDDEN_MODULES)
        ]
        assert not offenders, f"the worksheet generator imports verdicts: {offenders}"

    def test_the_only_thing_taken_from_scoring_is_the_weights(self):
        # Not a blanket ban: the weights must come from the app or the
        # worksheet's column and the app's rubric drift apart silently.
        taken = {
            name
            for module, names in _imports(SOURCE.read_text())
            if module.startswith("reprolens.scoring")
            for name in names
        }
        assert taken <= ALLOWED_FROM_SCORING, f"also taken from scoring: {taken}"

    def test_it_never_calls_the_assessor(self):
        source = SOURCE.read_text()
        called = {
            node.func.id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "assess" not in called
        assert "build" not in called


@pytest.fixture(scope="module")
def sheet():
    path = ROOT / "benchmark" / "worksheets" / "alignn.md"
    if not path.is_file():
        pytest.skip("no worksheet generated yet; run scripts/prep_benchmark.py")
    return path.read_text()


class TestTheWorksheetItself:
    def test_it_carries_the_apps_weights(self, sheet):
        from reprolens.scoring.rubric import WEIGHTS

        for name, weight in WEIGHTS.items():
            assert f"| {name} | {weight} |" in sheet

    def test_it_quotes_the_availability_statement_verbatim(self, sheet):
        # The time saving the whole script exists for: one paragraph instead of
        # twenty-seven pages. Verbatim paper text is raw material; the set of
        # accessions the app pulled out of it would be the answer.
        assert "Availability statements, verbatim" in sheet
        assert "figshare.com/collections/ALIGNN_data" in sheet

    def test_it_states_that_it_carries_no_findings(self, sheet):
        assert "contains no findings" in sheet

    def test_it_leaves_the_scores_blank(self, sheet):
        # Every criterion row ends in two empty cells. A worksheet that arrived
        # pre-scored would be the leak, in the most convenient possible form.
        rows = [line for line in sheet.splitlines() if line.startswith("| data_availability |")]
        assert rows == ["| data_availability | 20 | | |"]


class TestTheSkeleton:
    def test_the_title_is_left_for_the_annotator(self):
        # Page 1's first long line is "Atomistic Line Graph Neural Network for
        # Improved Materials Property" -- the title minus its second line. A
        # blank field gets filled; a plausible wrong one gets shipped.
        record = prep_benchmark.skeleton("example", ["https://github.com/a/b"])
        assert record["title"] == json.loads(prep_benchmark.TEMPLATE.read_text())["title"]

    def test_it_fills_in_only_what_is_mechanically_certain(self):
        record = prep_benchmark.skeleton("example", ["https://github.com/a/b"])
        assert record["paper_id"] == "example"
        assert record["github"] == "https://github.com/a/b"
        assert record["annotation_provenance"]["tier"] == 2

    def test_several_repositories_are_all_kept(self):
        # ALIGNN points at two (alignn and jarvis), and a record that silently
        # kept the first would understate what a reproducer has to obtain.
        record = prep_benchmark.skeleton("example", ["https://a/b", "https://c/d"])
        assert record["github"] == ["https://a/b", "https://c/d"]
