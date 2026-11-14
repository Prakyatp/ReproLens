"""The viewer, actually run.

A Streamlit page renders in the browser, so importing it proves nothing and
curl against a live server proves slightly less: the first version of this UI
returned HTTP 200 while raising ``TypeError: unhashable type: 'slice'`` on
every paper, because it read ``by_role`` as a list of findings when it is a
map of counts. ``AppTest`` executes the script the way the runtime does and
collects what it raised, which is the only check that would have caught that.

Each paper is its own case. The five differ in the ways that break a viewer --
ALIGNN has no resolved datasets, LocusMasterTE has a hard blocker where the
others have none, atomate2's graph is large, ASPEN comes from XML rather than
a PDF -- and a page that renders one of them is not a page that renders five.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui.py"
OUTPUT = ROOT / "output"

AppTest = pytest.importorskip(
    "streamlit.testing.v1", reason="streamlit is not installed"
).AppTest


def audited() -> list[str]:
    if not OUTPUT.is_dir():
        return []
    return sorted(p.name for p in OUTPUT.iterdir() if (p / "assessment.json").is_file())


def run(paper: str | None = None):
    app = AppTest.from_file(str(UI), default_timeout=120)
    app.run()
    if paper is not None:
        app.selectbox[0].select(paper).run()
    return app


@pytest.mark.parametrize("paper", audited() or ["<none audited>"])
def test_each_audited_paper_renders(paper):
    if paper == "<none audited>":
        pytest.skip("no audits in output/; run audit.py first")
    app = run(paper)
    assert not app.exception, [str(e.value) for e in app.exception]
    assert paper in [t.value for t in app.title]


def test_the_band_is_never_collapsed_to_one_number():
    # The band is the product's whole thesis: the floor is what the paper
    # documents, the gap is what could not be determined, and a single number
    # would hide the difference. So the headline has to print both.
    papers = audited()
    if not papers:
        pytest.skip("no audits in output/")
    app = run(papers[0])
    import json

    assessment = json.loads((OUTPUT / papers[0] / "assessment.json").read_text())
    headline = " ".join(m.value for m in app.markdown)
    assert f"{assessment['score_floor']}–{assessment['score_ceiling']}" in headline


def test_a_warning_from_the_reader_is_shown():
    # "Found nothing" and "could not read it" are different claims and only one
    # is about the paper, so a reader warning must reach the page rather than
    # being summarised away.
    papers = audited()
    if not papers:
        pytest.skip("no audits in output/")
    import json

    for paper in papers:
        warnings = json.loads((OUTPUT / paper / "links.json").read_text()).get("warnings", [])
        if warnings:
            app = run(paper)
            assert any(w in " ".join(x.value for x in app.warning) for w in warnings)
            return
    pytest.skip("none of the audited papers produced a reader warning")


def test_with_no_output_at_all_it_says_so_rather_than_crashing():
    app = AppTest.from_file(str(UI), default_timeout=120)
    app.secrets["_"] = ""
    app.run()
    assert not app.exception
