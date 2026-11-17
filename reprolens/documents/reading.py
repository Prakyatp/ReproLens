"""Reading one document into pages, with OCR for the pages the text layer cannot serve.

Shared by the article and by any supplement dropped beside it, so that both go
through exactly the same reader and the same fallback. OCR runs *before* the
readability gate: a fully scanned document has no text layer on any page, and
judging it unreadable first would skip the one reader built for it.
"""

from __future__ import annotations

from pathlib import Path

from reprolens.documents.base import PageText, TextBackend, is_readable
from reprolens.documents.jats_xml import JatsXmlBackend
from reprolens.documents.ocr import OcrBackend
from reprolens.documents.pdf_text import PdfTextBackend


def pick_backend(path: Path) -> TextBackend:
    if path.suffix.lower() in {".xml", ".nxml"}:
        return JatsXmlBackend()
    return PdfTextBackend()


def read_pages(
    path: Path, *, use_ocr: bool, document: str = ""
) -> tuple[list[PageText], list[str]]:
    """The text channel for one file: text layer first, OCR for what it cannot serve.

    ``document`` names the file in every page's provenance; empty means the
    article itself. The notes say what happened to the pages, and the first
    note is THE DOCUMENT WAS NOT READ when the two readers together produced
    too little to conclude anything -- which the caller must treat as "could
    not read", never as "found nothing".
    """
    pages = pick_backend(path).read(path)
    notes: list[str] = []

    unreadable = [p.page for p in pages if p.needs_ocr]
    if unreadable:
        listed = ", ".join(str(n) for n in unreadable)
        if use_ocr:
            recovered = {p.page: p for p in OcrBackend().read(path, pages=unreadable)}
            pages = [recovered.get(p.page, p) for p in pages]
            low = [f"p{n}" for n, p in recovered.items() if (p.confidence or 0) < 0.80]
            notes.append(f"pages {listed} had no text layer and were read by OCR (approximate).")
            if low:
                notes.append(
                    f"low OCR confidence on {', '.join(low)} -- identifiers there may be wrong."
                )
        else:
            notes.append(
                f"{len(unreadable)} of {len(pages)} pages have no usable text layer "
                f"(pages {listed}) and OCR is disabled. Findings are INCOMPLETE: "
                f"absence of a resource on these pages is not evidence of absence."
            )

    if document:
        for page in pages:
            page.document = document

    if not is_readable(pages):
        total = sum(page.char_count for page in pages)
        notes.insert(
            0,
            f"THE DOCUMENT WAS NOT READ: {len(pages)} segment(s) and {total} characters "
            f"came out of {path.name}. A real paper runs to tens of thousands. Nothing "
            f"below is evidence about the paper, and every rubric criterion is reported "
            f"as not assessed rather than scored.",
        )
    return pages, notes


NOT_READ = "THE DOCUMENT WAS NOT READ"
