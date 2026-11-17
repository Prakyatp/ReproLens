"""The app must not read its own answer key.

The ground-truth records state their conclusions in prose -- mates.json says
"RepeatMasker and GENCODE versions were never specified", which is exactly the
finding the app is meant to reach unaided. If that text reached the app's input,
every score measured afterwards would be meaningless and nothing would fail
visibly. This test makes the separation structural instead of a convention.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRADER_ONLY = {"check.py"}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of Constant nodes that are docstrings, not code.

    Prose about the rule is not a violation of it: audit.py's own docstring says
    it must never read benchmark/, and that sentence must not trip the check.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            ids.add(id(body[0].value))
    return ids


def _references_benchmark(source: str) -> bool:
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            if "benchmark" in node.value.lower():
                return True
        if isinstance(node, ast.Attribute | ast.Name):
            name = node.attr if isinstance(node, ast.Attribute) else node.id
            if "benchmark" in name.lower():
                return True
    return False


def test_app_package_never_references_benchmark():
    offenders = [
        path.relative_to(ROOT)
        for path in (ROOT / "reprolens").rglob("*.py")
        if _references_benchmark(path.read_text())
    ]
    assert not offenders, f"app code refers to benchmark/: {offenders}"


def test_audit_entrypoint_never_references_benchmark():
    assert not _references_benchmark((ROOT / "audit.py").read_text())


def test_the_viewer_never_references_benchmark():
    # The UI shows a person the audit, so it is on the app's side of the line:
    # ground truth reaching it would put the answers next to the findings on
    # one screen, which is the most persuasive possible way to be wrong.
    assert not _references_benchmark((ROOT / "ui.py").read_text())
    assert not _references_benchmark((ROOT / "app" / "server.py").read_text())
    assert not _references_benchmark((ROOT / "reprolens" / "reporting" / "view.py").read_text())


def test_grader_is_the_one_place_that_does():
    # Guards against the rule being satisfied by the grader quietly losing its
    # ground-truth comparison altogether.
    assert _references_benchmark((ROOT / "check.py").read_text())
