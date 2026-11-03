"""Extract figure regions from a PDF as images, anchored on their captions.

Deliberately not built on ``page.get_images()``. That returns embedded image
XObjects, and a journal figure is typically vector line art plus a handful of
small rasters, so the XObject list yields fragments rather than figures.
Rendering the *region* produces one coherent image per figure whatever it is
made of, and gives a real bbox for provenance.

Finding that region takes three observations about journal layout, each of which
breaks an obvious simpler rule (all examples from MATES):

1. A figure is as wide as the page, not as wide as its caption. Figure 1's
   caption occupies the left column only, while the graphic spans both.
2. The region cannot be bounded by "the nearest text above", because a figure
   is full of text -- panel letters, axis labels, P-values. Figure 6 has forty
   such blocks inside it. The bound has to be the nearest *prose*.
3. The caption is not always on the figure's page. Figures 3 and 5 are
   full-page graphics whose captions open the following page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from reprolens.documents.base import BBox, Figure

DEFAULT_DPI = 200

# "Fig. 2", "Figure 2", "Supplementary Fig. 3" -- the label that opens a caption.
_CAPTION_START = re.compile(
    r"^\s*((?:Supplementary\s+)?(?:Fig(?:ure)?\.?)\s*(\d+)[\s.:|])", re.IGNORECASE
)

# A caption block has prose; a cross-reference in body text ("as shown in
# Fig. 2") does not.
_MIN_CAPTION_CHARS = 40

# What separates body prose from text that is part of a figure. Panel labels,
# axis titles and P-values are short and narrow; a paragraph is neither.
_PROSE_MIN_CHARS = 200
_PROSE_MIN_WIDTH = 200.0

# Running headers and footers, which bound the printable area.
_HEADER_BAND = 45.0
_FOOTER_BAND = 755.0

_PAD = 4.0
_MIN_REGION_HEIGHT = 60.0
_MIN_REGION_WIDTH = 120.0


def extract(pdf_path: Path, out_dir: Path, dpi: int = DEFAULT_DPI) -> list[Figure]:
    """Render one image per detected figure into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    figures: list[Figure] = []

    with pymupdf.open(pdf_path) as doc:
        stem = pdf_path.stem
        for index, page in enumerate(doc, start=1):
            blocks = _text_blocks(page)
            for caption_bbox, label, caption in _captions(blocks):
                region, source_page = _figure_region(doc, index, caption_bbox)
                if region is None:
                    continue
                figure_id = f"{stem}-p{source_page}-{_slug(label)}"
                image_path = out_dir / f"{figure_id}.png"
                clip = pymupdf.Rect(*region)
                doc[source_page - 1].get_pixmap(clip=clip, dpi=dpi).save(image_path)
                figures.append(
                    Figure(
                        figure_id=figure_id,
                        label=label,
                        page=source_page,
                        bbox=region,
                        caption=caption,
                        image_path=image_path,
                    )
                )
    return figures


def _text_blocks(page: pymupdf.Page) -> list[tuple[BBox, str]]:
    blocks: list[tuple[BBox, str]] = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        if isinstance(text, str) and text.strip():
            blocks.append(((x0, y0, x1, y1), text))
    return blocks


def _captions(blocks: list[tuple[BBox, str]]) -> list[tuple[BBox, str, str]]:
    found: list[tuple[BBox, str, str]] = []
    for bbox, text in blocks:
        flat = " ".join(text.split())
        match = _CAPTION_START.match(flat)
        if match and len(flat) >= _MIN_CAPTION_CHARS:
            found.append((bbox, match.group(1).strip(" .:|"), flat))
    return found


def _is_prose(bbox: BBox, text: str) -> bool:
    """Body text, as opposed to text belonging to a figure."""
    return len(text.strip()) >= _PROSE_MIN_CHARS and (bbox[2] - bbox[0]) >= _PROSE_MIN_WIDTH


def _content_box(blocks: list[tuple[BBox, str]], page: pymupdf.Rect) -> BBox:
    """The printable area, excluding running header and footer."""
    inside = [b for b, _t in blocks if b[1] >= _HEADER_BAND and b[3] <= _FOOTER_BAND]
    if not inside:
        return (page.x0 + _PAD, _HEADER_BAND, page.x1 - _PAD, _FOOTER_BAND)
    return (
        min(b[0] for b in inside),
        _HEADER_BAND,
        max(b[2] for b in inside),
        _FOOTER_BAND,
    )


def _figure_region(
    doc: pymupdf.Document, page_number: int, caption: BBox
) -> tuple[BBox | None, int]:
    """The graphic for a caption, and which page it is on.

    Preference order: the band above the caption on its own page; failing that
    -- a caption opening a page, with nothing above it -- the whole printable
    area of the preceding page, which is where journals put a full-page figure.
    """
    page = doc[page_number - 1]
    blocks = _text_blocks(page)
    cx0, cy0, cx1, _cy1 = caption
    content = _content_box(blocks, page.rect)

    top = content[1]
    for bbox, text in blocks:
        if bbox[3] <= cy0 and _is_prose(bbox, text):
            top = max(top, bbox[3])

    region = (content[0], top + _PAD, content[2], cy0 - _PAD)
    if _big_enough(region):
        return region, page_number

    if page_number > 1:
        previous = doc[page_number - 2]
        previous_blocks = _text_blocks(previous)
        previous_content = _content_box(previous_blocks, previous.rect)
        # Mirror of the rule above: the graphic sits at the top of the page and
        # the prose it interrupted resumes beneath it, so bound the region by the
        # FIRST prose block rather than the last.
        bottom = min(
            (b[1] for b, t in previous_blocks if _is_prose(b, t)),
            default=previous_content[3],
        )
        region = (previous_content[0], previous_content[1], previous_content[2], bottom - _PAD)
        if _big_enough(region):
            return region, page_number - 1

    return None, page_number


def _big_enough(region: BBox) -> bool:
    return (
        region[3] - region[1] >= _MIN_REGION_HEIGHT and region[2] - region[0] >= _MIN_REGION_WIDTH
    )


# A reference to a figure in the body text: "Fig. 3", "Figure 3b", "Figs. 1-3".
# No trailing word boundary, because "Fig. 1b" has none between the digit and
# the panel letter and the panel is exactly how papers cite their own figures.
# "Fig. S5A" is deliberately not matched: a supplementary figure is a different
# document and its generating code is not expected in the main repository.
_FIGURE_REFERENCE = re.compile(
    r"\bFig(?:ure)?s?\.?\s*(\d{1,2})(?!\d)(?:\s*[-\u2010\u2013]\s*(\d{1,2})(?!\d))?", re.I
)

# A span wider than this is not a figure range. "Figs. 1-30" in a paper with
# five figures is a page range, a year or a typo, and expanding it would invent
# twenty-five published figures with no generating code.
_MAX_FIGURE_RANGE = 10


def figure_numbers(text: str) -> list[int]:
    """Main-text figure numbers a document refers to, in order.

    Works off the text rather than off extracted figure regions, so it answers
    the same question on a PDF and on JATS XML. The repository channel needs it
    to ask which published figures have generating code, and LocusMasterTE is
    read from XML, where there are no figure regions to extract at all.

    A range names every figure in it: "Figs. 1-3" is three figures, and taking
    only the first means a figure mentioned nowhere else goes uncounted -- which
    would shrink the denominator of the traceability comparison and hide a
    published result that has no code.
    """
    numbers: set[int] = set()
    for match in _FIGURE_REFERENCE.finditer(text):
        start = int(match.group(1))
        numbers.add(start)
        if match.group(2):
            end = int(match.group(2))
            if start < end <= start + _MAX_FIGURE_RANGE:
                numbers.update(range(start + 1, end + 1))
    return sorted(numbers)


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", label.lower()) or "fig"
