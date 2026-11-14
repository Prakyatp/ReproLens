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

AppTest = pytest.importorskip("streamlit.testing.v1", reason="streamlit is not installed").AppTest


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


class TestTheLinkThePaperGave:
    """Whose link it is, which is the distinction this panel turns on.

    A GEO landing page looks identical whether the paper printed it or this
    tool built it from the accession, so the two can only be told apart by
    saying which. One is the paper referencing a dataset; the other is this
    tool guessing where that dataset would live if it existed.
    """

    def link(self, **finding):
        import ui

        return ui.paper_link(finding)

    def test_a_repository_path_is_already_a_link(self):
        # A typesetter drops the scheme; "github.com/owner/name" is a URL.
        url, how = self.link(value="github.com/mcgilldinglab/MATES", kind="github")
        assert url == "https://github.com/mcgilldinglab/MATES"
        assert how == "printed in the text"

    def test_a_doi_resolves_through_doi_org(self):
        url, _how = self.link(value="10.5281/zenodo.13738122", kind="zenodo")
        assert url == "https://doi.org/10.5281/zenodo.13738122"

    def test_an_accessions_link_is_read_out_of_the_text_beside_it(self):
        # Where it actually lives. MATES's Data availability statement writes
        # "(GSE212945, https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=
        # GSE212945)" for 5 of its 10 accessions, and NONE of those URLs
        # survives as a separate `url` finding -- the accession pattern claims
        # the span first. Comparing the accession list against the url list
        # therefore reports that no paper links anything, which is exactly how
        # this was missed the first time round.
        url, how = self.link(
            value="GSE212945",
            kind="geo_series",
            occurrences=[
                {
                    "page": 20,
                    "context": "nanopore (GSE212945, https://www.ncbi.nlm.nih.gov/geo/"
                    "query/acc.cgi?acc=GSE212945) as detailed in Shiau et al.",
                }
            ],
        )
        assert url == "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE212945"
        assert "page 20" in how

    def test_a_bare_accession_reports_no_link_rather_than_inventing_one(self):
        # ASPEN, LocusMasterTE and half of MATES name an accession and give no
        # URL. Saying so is the honest answer; a constructed lookup is offered
        # separately and labelled as constructed.
        url, how = self.link(
            value="GSE164978",
            kind="geo_series",
            occurrences=[{"page": 19, "context": "downloaded from the GSE164978 dataset [32]"}],
        )
        assert url is None
        assert how == ""

    def test_the_closing_bracket_is_not_part_of_the_url(self):
        url, _how = self.link(
            value="GSE1",
            kind="geo_series",
            occurrences=[{"page": 1, "context": "(GSE1, https://x.org/acc?a=GSE1) and then"}],
        )
        assert url == "https://x.org/acc?a=GSE1"


class TestTheTabCountsMatchTheirPanels:
    def test_present_counts_everything_the_panel_lists(self):
        # atomate2 pins no version and deposits no dataset, so an earlier
        # version labelled its tab "Present (0)" above a panel listing six
        # repositories.
        import json

        import ui

        for paper in audited():
            links = json.loads((OUTPUT / paper / "links.json").read_text())
            checklist = json.loads((OUTPUT / paper / "checklist.json").read_text())
            assessment = json.loads((OUTPUT / paper / "assessment.json").read_text())
            count = ui._count_present(assessment, links, checklist)
            repositories = [
                f for f in links.get("findings", []) if f.get("kind") in ("github", "gitlab")
            ]
            if repositories:
                assert count >= len(repositories), paper
