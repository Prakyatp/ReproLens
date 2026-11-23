"""Reading the supplementary files a person drops beside the paper.

The archives gate supplement downloads, so the only way a supplement's contents
reach this audit is as a file the reader supplies. These tests pin what happens
to each format, that every page carries the supplement's name for provenance,
and that a received file can mark a Methods deferral as covered.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import openpyxl
import pymupdf

from reprolens.discovery import links
from reprolens.documents.base import PageText
from reprolens.documents.sections import SectionMark, classify_heading
from reprolens.documents.supplements import Received, collect, labels_in, read_files
from reprolens.extraction import checklist as checklist_build


def sheet(path: Path, rows: list[list[str]], title: str = "Sheet1") -> Path:
    book = openpyxl.Workbook()
    ws = book.active
    ws.title = title
    for row in rows:
        ws.append(row)
    book.save(path)
    return path


def docx(path: Path, paragraphs: list[str]) -> Path:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="x"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


def pdf(path: Path, text: str) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(60, 60, 540, 760), text, fontsize=10)
    doc.save(path)
    return path


def methods_page(text: str) -> PageText:
    return PageText(
        page=1,
        text=f"Methods\n{text}",
        sections=[SectionMark(offset=0, heading="Methods", label=classify_heading("Methods"))],
    )


class TestEachFormat:
    def test_a_spreadsheet_becomes_one_page_per_sheet(self, tmp_path):
        path = sheet(tmp_path / "Supplementary_Table_2.xlsx", [["a", "b"], ["1", "2"]])
        pages, received = read_files([path])
        assert received[0].readable
        assert received[0].backend == "text"
        assert len(pages) == 1
        assert "1\t2" in pages[0].text

    def test_a_version_column_is_read_as_versions(self, tmp_path):
        # "tool | version" is how every software table is laid out, and the
        # header is the table saying so. Rendered the way prose says it, the
        # same extractor that reads "STAR version 2.7.10a" in Methods reads it.
        path = sheet(
            tmp_path / "S3_Table.xlsx",
            [["tool", "version"], ["RepeatMasker", "4.1.2"], ["samtools", "1.15"]],
        )
        pages, _ = read_files([path])
        built = checklist_build.build(pages)
        versions = {s.name: s.version for s in built.software}
        assert versions.get("RepeatMasker") == "4.1.2"
        assert versions.get("samtools") == "1.15"

    def test_a_word_file_is_read_without_a_word_library(self, tmp_path):
        path = docx(tmp_path / "S2_Appendix.docx", ["S2 Appendix. Parameters.", "FDR 0.05"])
        pages, received = read_files([path])
        assert received[0].readable
        assert "FDR 0.05" in pages[0].text

    def test_a_one_page_pdf_is_not_rejected_as_unread(self, tmp_path):
        # The article-level readability gate is calibrated for a paper and
        # would call a one-page supplementary note unread. A supplement is
        # readable if any text came out of it.
        path = pdf(tmp_path / "Supplementary_Note_1.pdf", "Supplementary Note 1. GSE999901.")
        pages, received = read_files([path])
        assert received[0].readable, received[0].note
        assert received[0].backend == "pdf_text"
        assert {f.value for f in links.extract(pages)} >= {"GSE999901"}

    def test_delimited_text_is_read(self, tmp_path):
        path = tmp_path / "S4_Data.csv"
        path.write_text("sample,accession\nA,GSE123456\n")
        pages, received = read_files([path])
        assert received[0].readable
        assert "GSE123456" in pages[0].text

    def test_an_unreadable_format_is_recorded_not_dropped(self, tmp_path):
        path = tmp_path / "movie.mp4"
        path.write_bytes(b"\x00" * 32)
        pages, received = read_files([path])
        assert pages == []
        assert received[0].readable is False
        assert "not a format this reads" in received[0].note

    def test_a_corrupt_file_is_recorded_not_raised(self, tmp_path):
        path = tmp_path / "broken.xlsx"
        path.write_bytes(b"not a zip")
        _, received = read_files([path])
        assert received[0].readable is False
        assert "could not be opened" in received[0].note


class TestProvenance:
    def test_every_page_carries_the_supplement_name(self, tmp_path):
        path = sheet(tmp_path / "Supplementary_Table_2.xlsx", [["x"]])
        pages, received = read_files([path])
        assert received[0].document == "Supplementary Table 2"
        assert pages[0].document == "Supplementary Table 2"

    def test_an_occurrence_names_the_document(self, tmp_path):
        path = docx(tmp_path / "S2_Appendix.docx", ["S2 Appendix. Data in GSE123456."])
        pages, _ = read_files([path])
        finding = next(f for f in links.extract(pages) if f.value == "GSE123456")
        assert finding.occurrences[0].document == "S2 Appendix"

    def test_a_supplement_page_does_not_inherit_the_articles_sections(self, tmp_path):
        # Both documents have a page 1. The article's page 1 is in Methods;
        # the supplement's must not be, or every supplement finding would be
        # filed under whatever section the article happened to be in.
        article = methods_page("see Supplementary Table 2 for GSE111111")
        path = sheet(tmp_path / "Supplementary_Table_2.xlsx", [["GSE222222"]])
        supplement, _ = read_files([path])
        by_value = {f.value: f for f in links.extract([article, *supplement])}
        assert by_value["GSE111111"].occurrences[0].section == "methods"
        assert by_value["GSE222222"].occurrences[0].section != "methods"

    def test_the_filename_names_the_labels_it_covers(self):
        assert labels_in("Supplementary_Table_S2 extra") == ["Supplementary Table 2"]
        assert labels_in("S2 Appendix and S4 Fig") == ["S2 Appendix", "S4 Fig"]


class TestCoveringADeferral:
    def test_a_received_file_clears_the_deferral_it_answers_to(self, tmp_path):
        article = [methods_page("as described in Supplementary Table S2 and S4 Fig")]
        received = [Received(filename="x.xlsx", readable=True, covers=["Supplementary Table 2"])]
        out = collect(tmp_path / "paper.pdf", article, received)
        assert [r.label for r in out.deferred_from_methods] == ["S4 Fig", "Supplementary Table 2"]
        assert [r.label for r in out.deferred_unread] == ["S4 Fig"]
        assert out.to_dict()["summary"]["contents_read"] == 1

    def test_an_unreadable_file_covers_nothing(self, tmp_path):
        article = [methods_page("as described in Supplementary Table S2")]
        received = [Received(filename="x.bin", readable=False, covers=["Supplementary Table 2"])]
        out = collect(tmp_path / "paper.pdf", article, received)
        assert [r.label for r in out.deferred_unread] == ["Supplementary Table 2"]
        assert any("could not be read" in n for n in out.notes)

    def test_the_note_says_which_deferrals_remain(self, tmp_path):
        article = [methods_page("see Supplementary Note 1 and Supplementary Note 2")]
        received = [Received(filename="n1.pdf", readable=True, covers=["Supplementary Note 1"])]
        out = collect(tmp_path / "paper.pdf", article, received)
        note = next(n for n in out.notes if "defers to" in n)
        assert "1 of which were not supplied (Supplementary Note 2)" in note

    def test_all_covered_says_so(self, tmp_path):
        article = [methods_page("see Supplementary Note 1")]
        received = [Received(filename="n1.pdf", readable=True, covers=["Supplementary Note 1"])]
        out = collect(tmp_path / "paper.pdf", article, received)
        assert any("all of which were supplied and read" in n for n in out.notes)
