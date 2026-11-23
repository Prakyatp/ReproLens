"""Regressions for the supplement inventory.

The distinction everything here protects: a paper that published no supplements
and an input that cannot say are not the same, and the audit must never report
the second as the first. MATES and ASPEN are the pair that makes it concrete --
ASPEN declares twelve files in its JATS and MATES declares none in its PDF
because a PDF has no manifest at all.
"""

from __future__ import annotations

from pathlib import Path

from reprolens.documents.base import PageText
from reprolens.documents.sections import SectionMark, classify_heading
from reprolens.documents.supplements import (
    DECLARED,
    INVENTORY_UNAVAILABLE,
    classify,
    collect,
    from_xml,
    references,
)

JATS = """<?xml version="1.0"?>
<pmc-articleset><article>
  <body><sec><title>Methods</title><p>as described in S2 Appendix</p></sec></body>
  <back>
    <supplementary-material id="s001"><label>S4 Fig</label>
      <caption><title>ASPEN workflow.</title><p>(TIF)</p></caption>
      <media xmlns:ns1="http://www.w3.org/1999/xlink" ns1:href="pcbi.s004.tif"
             mimetype="image" mime-subtype="tiff"/>
    </supplementary-material>
    <supplementary-material id="s002"><label>S2 Appendix</label>
      <caption><title>Supplemental Tables.</title><p>(DOCX)</p></caption>
      <media xmlns:ns1="http://www.w3.org/1999/xlink" ns1:href="pcbi.s012.docx"/>
    </supplementary-material>
    <supplementary-material id="dup_s001">
      <label>S4 Fig</label><caption><title>ASPEN workflow.</title></caption>
      <media xmlns:ns1="http://www.w3.org/1999/xlink" ns1:href="pcbi.s004.tif"/>
    </supplementary-material>
  </back>
</article></pmc-articleset>
"""

# Springer ships no <label>, only a caption that opens with the file's name, and
# records the byte size in a processing instruction ElementTree throws away.
SPRINGER = """<?xml version="1.0"?>
<article>
  <back><supplementary-material id="MOESM1">
    <media xmlns:xlink="http://www.w3.org/1999/xlink"
           xlink:href="13059_MOESM1_ESM.pdf" mimetype="application" mime-subtype="pdf">
      <?size 1891846?>
      <caption><p>Additional file 1. Supplementary figures, Fig. S1 - S8.</p></caption>
    </media>
  </supplementary-material></back>
</article>
"""


def page(text: str, heading: str = "Methods") -> PageText:
    return PageText(
        page=1,
        text=f"{heading}\n{text}",
        sections=[SectionMark(offset=0, heading=heading, label=classify_heading(heading))],
    )


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


class TestTheInventory:
    def test_a_jats_article_declares_its_files(self, tmp_path):
        found = from_xml(write(tmp_path, "a.xml", JATS))
        assert [s.label for s in found] == ["S4 Fig", "S2 Appendix"]
        assert found[0].media_type == "image/tiff"

    def test_each_file_is_listed_once_however_often_pmc_repeats_it(self, tmp_path):
        # PMC emits every entry a second time under a synthetic id, which would
        # otherwise double the size of every paper's supplement.
        assert len(from_xml(write(tmp_path, "a.xml", JATS))) == 2

    def test_a_label_is_recovered_from_the_caption_when_the_publisher_ships_none(self, tmp_path):
        found = from_xml(write(tmp_path, "s.xml", SPRINGER))
        assert [s.label for s in found] == ["Additional file 1"]
        assert found[0].filename == "13059_MOESM1_ESM.pdf"

    def test_a_size_in_a_processing_instruction_is_still_read(self, tmp_path):
        found = from_xml(write(tmp_path, "s.xml", SPRINGER))
        assert found[0].size == 1891846

    def test_a_missing_size_is_none_rather_than_zero(self, tmp_path):
        found = from_xml(write(tmp_path, "a.xml", JATS))
        assert found[0].size is None

    def test_unparseable_xml_yields_nothing_rather_than_raising(self, tmp_path):
        assert from_xml(write(tmp_path, "bad.xml", "<article><oops>")) == []


class TestNoManifestIsNotNoSupplements:
    """The rule this module exists for."""

    def test_a_pdf_input_reports_the_inventory_as_unavailable(self, tmp_path):
        out = collect(tmp_path / "paper.pdf", [page("see Supplementary Table S2")])
        assert out.inventory == INVENTORY_UNAVAILABLE
        assert out.declared == []
        assert any("limit of the input" in n for n in out.notes)
        assert any("NOT a paper that published none" in n for n in out.notes)

    def test_an_xml_input_reports_the_inventory_as_declared(self, tmp_path):
        out = collect(write(tmp_path, "a.xml", JATS), [page("see S2 Appendix")])
        assert out.inventory == DECLARED
        assert len(out.declared) == 2

    def test_the_note_says_the_contents_were_never_read(self, tmp_path):
        out = collect(write(tmp_path, "a.xml", JATS), [page("x")])
        assert any("were not supplied" in n for n in out.notes)
        assert out.to_dict()["summary"]["contents_read"] == 0


class TestDeferralFromMethods:
    """A supplement cited from Methods is part of the method, not an extra."""

    def test_a_methods_citation_is_marked_as_deferral(self):
        found = references([page("as described in Supplementary Table S2", "Methods")])
        assert [(r.label, r.in_methods) for r in found] == [("Supplementary Table 2", True)]

    def test_a_results_citation_is_not(self):
        found = references([page("shown in Supplementary Fig. S5", "Results")])
        assert [(r.label, r.in_methods) for r in found] == [("Supplementary Figure 5", False)]

    def test_panels_of_one_figure_are_one_reference(self):
        found = references([page("Supplementary Fig. S1a and Supplementary Fig. S1d")])
        assert [r.label for r in found] == ["Supplementary Figure 1"]
        assert found[0].mentions == 2

    def test_every_spelling_of_one_figure_is_one_reference(self):
        # The regex admits Fig, Figs, Figure and Figures, and a paper will use
        # more than one of them. Four labels for one file would both inflate how
        # much of the method sits outside the article and split this signal.
        found = references(
            [
                page(
                    "Supplementary Fig. S1a, Supplementary Figs. 1, "
                    "Supplementary Figure 1 and Supplementary Figures 1"
                )
            ]
        )
        assert [r.label for r in found] == ["Supplementary Figure 1"]
        assert found[0].mentions == 4

    def test_both_label_styles_are_recognized(self):
        found = references([page("Additional file 1 and S2 Appendix and Supplementary Note 1")])
        assert {r.label for r in found} == {
            "Additional file 1",
            "S2 Appendix",
            "Supplementary Note 1",
        }

    def test_references_are_ordered_by_how_often_the_paper_leans_on_them(self):
        found = references([page("Additional file 1 " * 3 + " S2 Appendix")])
        assert [r.label for r in found] == ["Additional file 1", "S2 Appendix"]


class TestKindTellsWhereParametersHide:
    def test_a_table_or_appendix_may_carry_method_detail(self):
        assert classify("S2 Appendix", "Supplemental Tables.") == "table"
        assert classify("S1 Appendix", "Supplemental Results.") == "appendix"

    def test_a_workflow_figure_counts_too(self):
        # ASPEN's S4 Fig *is* the pipeline, which is why figures are not
        # excluded however many false positives that admits.
        from reprolens.documents.supplements import Supplement

        assert Supplement(
            "S4 Fig", "ASPEN workflow.", "x.tif", kind="figure"
        ).may_carry_method_detail

    def test_a_movie_does_not(self):
        from reprolens.documents.supplements import Supplement

        assert classify("Supplementary Movie 1", "Rotating cell") == "media"
        assert not Supplement("S1 Movie", "", "x.mp4", kind="media").may_carry_method_detail

    def test_peer_review_history_is_not_method_detail(self):
        assert classify("Additional file 2", "Peer review history") == "other"
