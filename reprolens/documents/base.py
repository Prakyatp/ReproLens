"""Normalized document shapes, and the seam every text backend sits behind.

Nothing downstream of this module knows which backend produced a page: the PDF
text layer (``pdf_text``), OCR over a rasterized page (``ocr``), or anything
added later. That is the whole point of the module -- adding a backend is a new
file implementing ``TextBackend``, not a change to the extractors.

No PyMuPDF type crosses this boundary. A bbox is a plain tuple of floats, never
a ``fitz.Rect``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from reprolens.documents.sections import SectionMark

BBox = tuple[float, float, float, float]

# "text" is a document that arrived as plain rows rather than pages -- a
# spreadsheet, a CSV, a Word file dropped alongside the paper as a supplement.
Backend = Literal["pdf_text", "jats_xml", "ocr", "vlm", "text"]

# A page with fewer than this many characters, on a page that carries images, is
# treated as unreadable rather than empty. See PageText.needs_ocr.
MIN_CHARS_PER_PAGE = 100

# A whole document below this is not a paper that says little; it is a document
# this pipeline failed to read. Set far below any real paper -- the three in the
# benchmark run 85,000 to 95,000 characters -- so that crossing it is a
# statement about the reader rather than a judgement about the writing.
MIN_DOCUMENT_CHARS = 1000


@dataclass(slots=True)
class PageText:
    """One page's text, however it was obtained."""

    page: int  # 1-indexed
    text: str
    links: list[str] = field(default_factory=list)  # embedded URI annotations
    has_images: bool = False
    backend: Backend = "pdf_text"
    confidence: float | None = None  # None means exact (text layer); OCR sets a real value
    sections: list[SectionMark] = field(default_factory=list)  # offsets into .text
    furniture: list[str] = field(default_factory=list)  # running header/footer lines
    # Which document this page belongs to. Empty for the article itself; the
    # supplement's label or filename otherwise. Provenance has to be able to say
    # "Supplementary Table 2, page 3" and not just "page 3", because a page
    # number alone points into the wrong file once there is more than one.
    document: str = ""

    @property
    def furniture_text(self) -> str:
        """The running header and footer, kept out of ``text`` but not discarded.

        MATES repeats ``https://doi.org/10.1038/s41467-024-53114-7`` in the
        header of 21 of its 22 pages, which is why that DOI previously showed up
        as 19 separate occurrences. Removing it from ``text`` stops it competing
        with real findings and stops it interrupting a sentence mid-URL; keeping
        it here means it is still extracted and reported, labelled as
        boilerplate, rather than silently dropped.
        """
        return "\n".join(self.furniture)

    @property
    def char_count(self) -> int:
        return len(self.text.strip())

    @property
    def needs_ocr(self) -> bool:
        """True when this page looks unreadable rather than genuinely empty.

        This distinction is load-bearing. A scanned page yields no text, finds no
        accessions, and would otherwise be reported as "nothing here" -- which is
        indistinguishable from a real finding in a tool whose job is detecting
        absence. Such a page must be reported as unreadable instead.
        """
        if self.backend != "pdf_text":
            return False
        return self.char_count < MIN_CHARS_PER_PAGE and self.has_images


def is_readable(pages: list[PageText]) -> bool:
    """Whether enough text came out of the document to conclude anything.

    The per-page version of this question is ``PageText.needs_ocr``, and it only
    answers for the PDF path. This is the document-level counterpart, and it
    exists because the XML path had no equivalent: handed a file whose structure
    it did not recognize, it returned zero segments, found zero resources, and
    reported a well-documented paper as having published nothing -- silently,
    and scored out of 65 as though the paper were at fault.

    Everything downstream keys on it. A document that was not read is not a
    document with nothing in it, and the difference has to survive into the
    score rather than being noted in a warning nobody reads.
    """
    return sum(page.char_count for page in pages) >= MIN_DOCUMENT_CHARS


@dataclass(slots=True)
class Figure:
    """A figure region rendered to an image file, with its caption."""

    figure_id: str  # e.g. "mates-p3-fig2"
    label: str | None  # e.g. "Figure 2", as printed
    page: int
    bbox: BBox
    caption: str
    image_path: Path


@runtime_checkable
class TextBackend(Protocol):
    """Anything that can turn a document into pages of text."""

    name: Backend

    def read(self, path: Path) -> list[PageText]: ...
