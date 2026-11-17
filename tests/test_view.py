"""The view model every front end renders from.

Presentation rules that carry meaning live in one place so two front ends
cannot disagree about an audit: whose link it is, whether a channel ran, and
that a score never travels without its coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolens.reporting import view


class TestWhoseLinkItIs:
    def test_a_url_the_paper_printed_is_the_papers(self):
        url, how = view.paper_link({"value": "https://zenodo.org/record/1", "kind": "zenodo"})
        assert url == "https://zenodo.org/record/1"
        assert how == "printed in the text"

    def test_an_annotation_is_said_to_be_one(self):
        finding = {
            "value": "github.com/a/b",
            "kind": "github",
            "occurrences": [{"source": "annotation", "context": "", "page": 2}],
        }
        assert view.paper_link(finding) == ("https://github.com/a/b", "an embedded hyperlink")

    def test_an_accessions_link_is_read_from_beside_it(self):
        finding = {
            "value": "GSE212945",
            "kind": "geo_series",
            "occurrences": [
                {
                    "source": "text",
                    "page": 20,
                    "section": "data_availability",
                    "context": "(GSE212945, https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE212945)",
                }
            ],
        }
        url, how = view.paper_link(finding)
        assert url == "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE212945"
        assert "beside the identifier" in how

    def test_a_bare_accession_has_no_paper_link(self):
        finding = {
            "value": "GSE1",
            "kind": "geo_series",
            "occurrences": [{"source": "text", "page": 3, "context": "deposited as GSE1."}],
        }
        assert view.paper_link(finding) == (None, "")

    def test_the_lookup_is_carried_separately_so_the_label_can_differ(self):
        row = view.item("GSE1", "", {"value": "GSE1", "kind": "geo_series"}, lookup="https://x")
        assert row["paper_link"] is None
        assert row["lookup"] == "https://x"


class TestWhereItWasSaid:
    def test_the_article_is_page_and_section(self):
        assert view.where({"page": 20, "section_heading": "Data availability"}) == (
            "page 20, Data availability"
        )

    def test_a_supplement_is_named_first(self):
        assert view.where({"page": 3, "document": "S2 Appendix", "section": "front_matter"}) == (
            "S2 Appendix, page 3"
        )

    def test_running_headers_are_not_the_mention(self):
        finding = {
            "occurrences": [
                {"source": "furniture", "page": 1, "context": "doi in the header"},
                {"source": "text", "page": 20, "section": "methods", "context": "the real one"},
            ]
        }
        assert [m["quote"] for m in view.mentions(finding)] == ["the real one"]


class TestTheChannels:
    def test_unread_figures_are_flagged_not_silent(self):
        rows = view.channels({"backend": "pdf_text"}, [{"reading": None}, {"reading": None}])
        figures = next(r for r in rows if r["name"] == "figures")
        assert figures["ran"] is False
        assert "NONE read" in figures["text"]

    def test_archives_not_asked_differs_from_nothing_found(self):
        rows = view.channels({"datasets_resolved": {"attempted": False}}, [])
        assert {"name": "archives", "ran": False, "text": "Archives NOT asked"} in rows

    def test_ocr_pages_are_reported(self):
        rows = view.channels({"pages": [{"backend": "ocr"}, {"backend": "pdf_text"}]}, [])
        assert any(r["name"] == "ocr" and "1 page(s)" in r["text"] for r in rows)

    def test_supplied_supplements_are_a_channel(self):
        rows = view.channels({"supplements": {"summary": {"received": 3, "contents_read": 2}}}, [])
        assert any(r["name"] == "supplements" and "2 of 3" in r["text"] for r in rows)


class TestBuildingFromADirectory:
    def test_a_result_directory_builds_without_an_audit_in_output(self, tmp_path):
        (tmp_path / "links.json").write_text(
            json.dumps({"paper_id": "p", "backend": "pdf_text", "warnings": ["w"], "findings": []})
        )
        (tmp_path / "assessment.json").write_text(
            json.dumps(
                {
                    "score": 0.8,
                    "coverage": 0.7,
                    "score_floor": 56,
                    "score_ceiling": 86,
                    "assessed_points": 100,
                    "determined_points": 70,
                    "severity": {"major": 2},
                    "criteria": [],
                    "issues": [],
                }
            )
        )
        (tmp_path / "checklist.json").write_text(json.dumps({"software": [], "settings": []}))
        built = view.build(Path(tmp_path))
        assert built["headline"]["score"] == 0.8
        assert built["headline"]["coverage"] == 0.7
        assert built["headline"]["severity"] == {"hard_blocker": 0, "major": 2, "minor": 0}
        assert built["warnings"] == ["w"]
        assert built["missing"]["count"] == 0
