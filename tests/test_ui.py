"""The product, actually run.

A Streamlit page renders in the browser, so importing it proves nothing and
curl against a live server proves slightly less: an early version of this UI
returned HTTP 200 while raising ``TypeError: unhashable type: 'slice'`` on
every paper, because it read ``by_role`` as a list of findings when it is a map
of counts. ``AppTest`` executes the script the way the runtime does and
collects what it raised, which is the only check that would have caught that.

The page has two states and both are tested: the landing page, which is the
whole product before a paper arrives, and the result, seeded from an audit on
disk because ``AppTest`` cannot drive a file uploader.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui.py"

AppTest = pytest.importorskip("streamlit.testing.v1", reason="streamlit is not installed").AppTest

# Audits produced by running audit.py locally. They are not committed (output/
# is ignored), so every test that needs one skips without it rather than
# inventing a shape the app would never actually be handed.
AUDITS = ROOT / "output"


def an_audit() -> Path | None:
    if not AUDITS.is_dir():
        return None
    found = sorted(p for p in AUDITS.iterdir() if (p / "assessment.json").is_file())
    return found[0] if found else None


def landing():
    app = AppTest.from_file(str(UI), default_timeout=120)
    app.run()
    return app


def words(app) -> str:
    """Every word the page renders, markdown and captions alike.

    The score is a markdown block and the coverage that qualifies it is a
    caption, so a test that reads only one of the two can pass while the page
    publishes a bare percentage.
    """
    return " ".join([element.value for element in app.markdown] + [c.value for c in app.caption])


def showing(result: Path):
    app = AppTest.from_file(str(UI), default_timeout=120)
    app.session_state["result_dir"] = str(result)
    app.session_state["paper_name"] = f"{result.name}.pdf"
    app.run()
    return app


class TestTheLandingPage:
    def test_it_renders_one_place_to_drop_a_paper(self):
        app = landing()
        assert not app.exception, [str(e.value) for e in app.exception]
        assert len(app.file_uploader) == 1

    def test_it_offers_no_library_of_papers(self):
        # The product is a page you drop a paper into. An earlier version listed
        # the five papers this project was developed against, which were the
        # author's own verification set and have no business in the product.
        app = landing()
        assert app.selectbox.values == []

    def test_it_says_that_nothing_is_kept(self):
        app = landing()
        text = " ".join(m.value for m in app.markdown)
        assert "Nothing is stored" in text
        assert "is ever executed" in text


class TestTheResult:
    def test_it_renders_without_raising(self):
        result = an_audit()
        if result is None:
            pytest.skip("no audit in output/; run audit.py first")
        app = showing(result)
        assert not app.exception, [str(e.value) for e in app.exception]

    def test_one_percentage_leads_the_page(self):
        # This replaces a test that asserted the opposite -- that the floor and
        # ceiling must always appear as a range and never collapse. The band
        # still exists and is still drawn; what changed is the headline, which
        # is now a single figure because "74-84" is not a result anybody can
        # use. The band's information is kept in the caption and the bar.
        result = an_audit()
        if result is None:
            pytest.skip("no audit in output/")
        assessment = json.loads((result / "assessment.json").read_text())
        text = words(showing(result))
        if assessment.get("score") is None:
            assert "Not scored" in text
            return
        assert f"{assessment['score']:.0%}" in text
        assert "documented" in text

    def test_the_percentage_never_appears_without_its_coverage(self):
        # The score excludes undetermined points from its denominator, so it
        # reads as better-established than it is unless coverage is beside it.
        result = an_audit()
        if result is None:
            pytest.skip("no audit in output/")
        assessment = json.loads((result / "assessment.json").read_text())
        if assessment.get("score") is None:
            pytest.skip("this audit publishes no score")
        text = words(showing(result))
        assert f"{assessment['coverage']:.0%}" in text

    def test_the_page_does_not_call_the_number_reproducible(self):
        # Nothing is executed, so no wording on the page may claim the work
        # reproduces. The number measures what the paper writes down.
        result = an_audit()
        if result is None:
            pytest.skip("no audit in output/")
        text = words(showing(result)).lower()
        assert "% reproducible" not in text
        assert "no code was executed" in text

    def test_a_reader_warning_leads_the_page(self):
        # "Found nothing" and "could not read it" are different claims and only
        # one is about the paper, so a reader warning must reach the page.
        if not AUDITS.is_dir():
            pytest.skip("no audits in output/")
        for result in sorted(AUDITS.iterdir()):
            if not (result / "links.json").is_file():
                continue
            warnings = json.loads((result / "links.json").read_text()).get("warnings", [])
            if warnings:
                app = showing(result)
                shown = " ".join(w.value for w in app.warning)
                assert any(warning in shown for warning in warnings)
                return
        pytest.skip("none of the local audits produced a reader warning")

    def test_every_tab_count_matches_its_panel(self):
        # The tab read "Present (0)" above a panel listing six repositories,
        # because the count omitted most of what the panel renders.
        import ui

        if not AUDITS.is_dir():
            pytest.skip("no audits in output/")
        for result in sorted(AUDITS.iterdir()):
            if not (result / "assessment.json").is_file():
                continue
            links = json.loads((result / "links.json").read_text())
            checklist = json.loads((result / "checklist.json").read_text())
            assessment = json.loads((result / "assessment.json").read_text())
            repositories = [
                f for f in links.get("findings", []) if f.get("kind") in ("github", "gitlab")
            ]
            if repositories:
                count = ui._count_present(assessment, links, checklist)
                assert count >= len(repositories), result.name


class TestFindingWhatTheAuditWrote:
    def test_it_looks_for_the_directory_audit_py_chose(self, tmp_path):
        # audit.py names the output directory after the document's stem, not
        # after anything the caller passed, so the caller has to look.
        import ui

        produced = tmp_path / "dropped"
        produced.mkdir()
        (produced / "assessment.json").write_text("{}")
        assert ui.find_result(tmp_path) == produced

    def test_a_directory_without_an_assessment_is_not_a_result(self, tmp_path):
        # The audit can write a partial reading and still refuse to score it.
        # Showing that as a result would present "could not be read" as
        # "nothing was found", which is the one confusion this project exists
        # to prevent.
        import ui

        partial = tmp_path / "dropped"
        partial.mkdir()
        (partial / "links.json").write_text("{}")
        assert ui.find_result(partial) is None
        assert ui.find_result(tmp_path) is None

    def test_a_missing_output_directory_is_not_an_error(self, tmp_path):
        import ui

        assert ui.find_result(tmp_path / "never-written") is None


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
        # survives as a separate `url` finding, because the accession pattern
        # claims the span first. Comparing the accession list against the url
        # list therefore reports that no paper links anything -- which is what
        # I concluded the first time, and it was wrong.
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


class TestTheChannelsThePageReportsOn:
    """The regression this class exists for.

    The page once called ``audit.py --no-vlm`` from a hardcoded argument list.
    Every paper dropped on it was therefore scored as though its figures held
    nothing, and the page said nothing about it -- the one confusion this whole
    project is built to prevent, committed by the product itself.

    Two things have to hold for that to stay fixed: the page must not switch
    the channel off, and the page must state the channel's condition whether it
    ran or not.
    """

    def test_the_page_does_not_switch_the_figure_channel_off(self):
        source = Path("ui.py").read_text()
        assert "--no-vlm" not in source, (
            "ui.py is suppressing the figure channel again; an unread figure "
            "then enters the score as a figure containing nothing"
        )

    def test_figures_extracted_but_unread_is_flagged_not_silent(self):
        from ui import channels

        figures = [{"figure_id": "f1", "reading": None}, {"figure_id": "f2", "reading": None}]
        rows = channels({"backend": "pdf_text"}, figures)
        figure_row = [row for row in rows if "figure" in row[1]]
        assert len(figure_row) == 1
        ran, text = figure_row[0]
        assert ran is False
        assert "NONE read" in text

    def test_figures_that_were_read_name_the_model(self):
        from ui import channels

        figures = [{"figure_id": "f1", "reading": {"model": "qwen2.5vl:7b"}}]
        ran, text = next(row for row in channels({}, figures) if "figure" in row[1])
        assert ran is True
        assert "qwen2.5vl:7b" in text

    def test_no_figures_at_all_is_its_own_state(self):
        from ui import channels

        ran, text = next(row for row in channels({}, []) if "figure" in row[1])
        assert ran is False
        assert "No figures extracted" in text

    def test_archives_not_asked_differs_from_nothing_found(self):
        from ui import channels

        not_asked = channels({"datasets_resolved": {"attempted": False}}, [])
        assert (False, "Archives NOT asked") in not_asked

        asked = channels(
            {"datasets_resolved": {"attempted": True, "summary": {"checked": 0, "unchecked": 4}}},
            [],
        )
        ran, text = next(row for row in asked if "datasets" in row[1])
        assert ran is False
        assert "0 of 4" in text

    def test_repositories_not_fetched_differs_from_none_reachable(self):
        from ui import channels

        assert (False, "Repositories NOT fetched") in channels({"repository": {}}, [])
        assert (False, "No repository was reachable") in channels(
            {"repository": {"fetched": True, "repositories": []}}, []
        )


class TestWhetherTheVisionBackendCanRun:
    """Asked before a run, so "could not read" never prints as "nothing there"."""

    def test_an_unknown_backend_explains_itself(self):
        from reprolens.extraction import vlm

        reason = vlm.blocked("gpt4v")
        assert reason is not None
        assert "unknown vlm backend" in reason

    def test_a_missing_ollama_model_names_the_pull_command(self):
        from reprolens.extraction import vlm

        reason = vlm.blocked("ollama", "a-model-nobody-has:0b")
        # Only meaningful when a server is actually answering; when none is,
        # the reason says *that* instead, which is equally the point.
        assert reason is not None
        assert "ollama pull a-model-nobody-has:0b" in reason or "ollama serve" in reason
