"""The shared reader, and the order of its two readers.

The bug this file exists for: a fully scanned paper has no text layer on any
page. Judged for readability *before* OCR, it tripped THE DOCUMENT WAS NOT READ
and the fallback that exists for exactly that document never ran. OCR now goes
first and the gate judges what both readers produced together.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pymupdf
import pytest

from reprolens.documents.reading import NOT_READ, read_pages

HAS_TESSERACT = shutil.which("tesseract") is not None

# Three genuinely different pages. The reader strips blocks that repeat across
# pages as running furniture, so pages that differ only by a number would read
# as empty -- which is the reader working, not failing.
PAGES = [
    "Methods. Reads were aligned with STAR version 2.7.10a to GRCh38 using the standard "
    "two-pass procedure, and duplicates were marked afterwards. The raw sequencing data "
    "were deposited in GEO under accession GSE212945 and GSE114952, and the processed "
    "count matrices accompany them. Quality control removed cells with fewer than two "
    "hundred detected genes or more than ten percent mitochondrial reads. "
    "Normalisation followed the library-size method before any downstream analysis.",
    "Results. The model recovered the expected cell populations in every replicate, and "
    "the clusters were stable across random seeds. Marker genes agreed with the published "
    "annotation in the large majority of cases. Where they disagreed, the discrepancy was "
    "traced to ambient contamination in two samples, which were removed from the final "
    "analysis. Training used a learning rate of 0.001 and a batch size of 64 for fifty "
    "epochs, with early stopping on the validation loss.",
    "Discussion. The approach generalises to other tissues provided the reference is "
    "matched, but it is sensitive to the choice of alignment index, and that choice is "
    "rarely reported. We therefore release the exact index alongside the code. Future "
    "work will extend the comparison to long-read protocols, where multi-mapping is more "
    "severe. All software versions and parameters are listed in the supplement, and the "
    "code is available from the repository named in the code availability statement.",
]


def born_digital(path: Path, pages: int = 3) -> Path:
    doc = pymupdf.open()
    for number in range(pages):
        page = doc.new_page()
        text = " ".join([PAGES[number % len(PAGES)]] * 3)
        page.insert_textbox(pymupdf.Rect(60, 60, 540, 760), text, fontsize=10)
    doc.save(path)
    return path


def scanned(path: Path, source: Path) -> Path:
    """Rasterise every page and throw the text layer away."""
    src = pymupdf.open(source)
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=200)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, pixmap=pix)
    out.save(path)
    return path


class TestTheTextLayer:
    def test_a_born_digital_pdf_is_read_from_its_text_layer(self, tmp_path):
        pages, notes = read_pages(born_digital(tmp_path / "a.pdf"), use_ocr=False)
        assert [p.backend for p in pages] == ["pdf_text"] * 3
        assert notes == []
        assert "GSE212945" in pages[0].text

    def test_the_document_name_is_stamped_on_every_page(self, tmp_path):
        pages, _ = read_pages(born_digital(tmp_path / "a.pdf"), use_ocr=False, document="S1 Text")
        assert {p.document for p in pages} == {"S1 Text"}

    def test_the_article_has_no_document_name(self, tmp_path):
        pages, _ = read_pages(born_digital(tmp_path / "a.pdf"), use_ocr=False)
        assert {p.document for p in pages} == {""}


class TestAScannedDocument:
    def test_with_ocr_off_it_is_reported_unread_not_empty(self, tmp_path):
        image_only = scanned(tmp_path / "scan.pdf", born_digital(tmp_path / "a.pdf"))
        pages, notes = read_pages(image_only, use_ocr=False)
        assert all(p.needs_ocr for p in pages)
        assert notes[0].startswith(NOT_READ)
        # And the reason survives alongside, so a reader knows what to switch on.
        assert any("OCR is disabled" in n for n in notes)

    @pytest.mark.skipif(not HAS_TESSERACT, reason="tesseract is not installed")
    def test_with_ocr_on_the_fallback_actually_runs(self, tmp_path):
        # The regression. Before the reorder this came back with 0 characters
        # on every page and the OCR note absent, because the readability gate
        # fired first and returned early.
        image_only = scanned(tmp_path / "scan.pdf", born_digital(tmp_path / "a.pdf"))
        pages, notes = read_pages(image_only, use_ocr=True)
        assert [p.backend for p in pages] == ["ocr"] * 3
        assert all(p.char_count > 500 for p in pages)
        assert not any(n.startswith(NOT_READ) for n in notes)
        assert any("read by OCR" in n for n in notes)

    @pytest.mark.skipif(not HAS_TESSERACT, reason="tesseract is not installed")
    def test_ocr_recovers_the_accessions_the_text_layer_had(self, tmp_path):
        # The stricter test: not character accuracy but whether the identifiers
        # survive. A single misread digit yields a plausible, wrong accession.
        from reprolens.discovery import links

        clean = born_digital(tmp_path / "a.pdf")
        image_only = scanned(tmp_path / "scan.pdf", clean)
        expected = {f.value for f in links.extract(read_pages(clean, use_ocr=False)[0])}
        got = {f.value for f in links.extract(read_pages(image_only, use_ocr=True)[0])}
        assert {"GSE212945", "GSE114952"} <= expected
        assert {"GSE212945", "GSE114952"} <= got
