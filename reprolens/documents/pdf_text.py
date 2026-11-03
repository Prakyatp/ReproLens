"""Text backend: the PDF's own embedded text layer, via PyMuPDF.

This is the first and cheapest channel. For born-digital papers it is exact --
no model, no cost, no hallucination risk -- so it runs first and OCR only covers
the pages it cannot read.

Three things this module does that a flat text extraction does not:

**Spans, not pages.** ``get_text("text")`` glues superscript citation markers
onto the token before them. Real example from MATES, page 20::

    github.com/mcgilldinglab/MATES + superscript "90"  ->  ".../MATES90"

**Headings by typography, not by keyword.** Matching heading words against the
start of a line finds MATES's 7 real headings and 10 false positives -- body
lines that happen to begin "methods," or "Supplementary Fig. S5".

Typography means *size or weight*, and which one is available depends on the
publisher. Nature sets headings in a separate font face
(``AdvOT3d287b35.B``) and leaves the bold flag clear, so on MATES size is the
only signal there is. PLOS sets every heading in ``ArialMTStd-Bold`` with the
flag set -- and sets its back-matter headings at the *body* size, so there
"Availability of data and materials" is distinguished by weight alone. Keying
on size alone missed it, and missing that one heading cost the whole code
availability criterion: with no availability section the repository URLs were
read as citations, nothing was cloned, and a paper that publishes an R package
scored zero out of twenty for code availability.

So size stays the primary signal and weight is admitted alongside it, under
the condition that the *whole* line is bold. That last part is what separates a
heading from a bold run-in lead-in, which shares its line with the prose that
follows it.

**Page furniture, separated.** MATES repeats its DOI in the running header of 21
pages. Left in the body text it inflates one finding into 19 occurrences and
interrupts the text mid-sentence; it is pulled out to ``PageText.furniture``,
still extracted but attributable as boilerplate.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import NamedTuple

import pymupdf

from reprolens.documents.base import Backend, PageText
from reprolens.documents.sections import SectionMark, classify_heading
from reprolens.documents.textrepair import rejoin_broken_urls

# PyMuPDF span flags: bit 0 marks a superscript, bit 4 marks bold.
_FLAG_SUPERSCRIPT = 1
_FLAG_BOLD = 16

# A superscript dropped as a citation marker must look like one: digits, with
# optional separators for ranges and lists ("12", "4,5", "7-9"). Anything else
# (units, exponents, footnote daggers) is kept.
_CITATION_MARKER = re.compile(r"^[\d,–—\-\s]+$")

# A heading sits above the body size by more than float noise.
_HEADING_SIZE_TOLERANCE = 0.3

# "Availability of data and materials" is 34 characters; a wrapped body line is
# longer. The abstract of MATES is set at 9.96pt -- larger than the 8.22pt body
# -- so the size test alone would accept its lines, and this is the second guard.
_HEADING_MAX_CHARS = 60

# Figure panel labels ("a.", "b.") pass every other test: short, large, and
# containing a letter. A real heading carries a word.
_HEADING_MIN_LETTERS = 3

# A heading never ends mid-clause.
# A heading does not end mid-phrase. The colon is deliberately NOT here: this
# publisher class ends every back-matter heading with one -- "Code
# availability:", "Data availability:" -- and rejecting those lost both
# statements on ALIGNN, which is how a paper that publishes its repository and
# its Figshare collection scored zero for each. A bold line of sixty characters
# or fewer ending in a colon is a heading; the prose line that ends in one is
# not bold and is far longer, so the other guards already exclude it.
_HEADING_BAD_TAIL = (",", ";", "and", "of", "the")

# A bold line ending in a full stop is a run-in lead-in ("Results." followed by
# the paragraph), not a heading. Only applied on the weight path: a heading
# recognised by size is allowed to end however its publisher likes.
_RUN_IN_TAIL = (".", "!", "?")

# Running header/footer live within this fraction of the page's top/bottom edge.
_EDGE_TOP = 0.08
_EDGE_BOTTOM = 0.92

# Page numbers differ between pages, so compare furniture on its digit-free
# template: "Nature Communications| (2024) 15:8798 20" -> "... (####) ##:#### ##".
_DIGIT_RUN = re.compile(r"\d+")


class Line(NamedTuple):
    """One rendered line of a block, with the signals headings turn on."""

    text: str
    size: float
    bold: bool
    #: The leading bold run, when the line continues into unbolded prose. This
    #: is a run-in heading, and an accepted-manuscript PDF writes its most
    #: important sections that way: ALIGNN sets "Code availability: The code and
    #: full model..." as one line, bold prefix then regular body. Judged as a
    #: whole the line is 80 characters and not bold end to end, so it is not a
    #: heading by either signal, and the section vanishes.
    prefix: str = ""


class PdfTextBackend:
    name: Backend = "pdf_text"

    def read(self, path: Path) -> list[PageText]:
        with pymupdf.open(path) as doc:
            layout = [_blocks(page) for page in doc]
            body_size = _body_size(layout)
            furniture = _furniture_blocks(layout, [page.rect.height for page in doc])
            levels = _heading_levels(layout, body_size)

            pages: list[PageText] = []
            for index, (page, blocks) in enumerate(zip(doc, layout, strict=True), start=1):
                text, marks, strays = _assemble(
                    blocks,
                    body_size=body_size,
                    furniture=furniture.get(index, set()),
                    levels=levels,
                )
                pages.append(
                    PageText(
                        page=index,
                        text=text,
                        links=_link_uris(page),
                        has_images=bool(page.get_images(full=True)) or _has_drawings(page),
                        backend=self.name,
                        confidence=None,  # text layer is exact
                        sections=marks,
                        furniture=strays,
                    )
                )
        _drop_front_matter_headings(pages)
        _inherit_labels(pages)
        return pages


# --------------------------------------------------------------------------- #
# pass 1: layout
# --------------------------------------------------------------------------- #


def _blocks(page: pymupdf.Page) -> list[dict]:
    """Text blocks reduced to what later passes need: lines, sizes, geometry."""
    out: list[dict] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:  # 0 == text; skip images
            continue
        lines: list[Line] = []
        for line in block["lines"]:
            kept = [span for span in line["spans"] if not _is_citation_marker(span)]
            rendered = "".join(span["text"] for span in kept)
            if rendered.strip():
                lines.append(
                    Line(
                        text=rendered,
                        size=max(span["size"] for span in kept),
                        bold=_all_bold(kept),
                        prefix=_bold_prefix(kept),
                    )
                )
        if lines:
            out.append({"lines": lines, "y0": block["bbox"][1]})
    return out


def _bold_prefix(spans: list[dict]) -> str:
    """The leading bold run of a mixed-weight line, or "" if there is none.

    Returns text only when a bold opening is followed by something unbolded,
    which is exactly the run-in heading shape. A line that is bold throughout
    is already handled by ``_all_bold``, and one that opens unbolded has no
    heading to recover.
    """
    carrying = [span for span in spans if span["text"].strip()]
    if len(carrying) < 2:
        return ""
    prefix: list[str] = []
    for span in carrying:
        if not _is_bold(span):
            break
        prefix.append(span["text"])
    if not prefix or len(prefix) == len(carrying):
        return ""
    return "".join(prefix)


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & _FLAG_BOLD) or "bold" in span.get("font", "").casefold()


def _all_bold(spans: list[dict]) -> bool:
    """Whether every span carrying text on this line is bold.

    Two signals, because publishers use different ones: the flag bit, and a
    font name that says so. PLOS sets both; a PDF that sets only the name would
    otherwise read as unweighted.

    The requirement that *all* text-bearing spans be bold is what keeps a bold
    run-in lead-in out: "**Results.** We found that..." is one line with a bold
    span and a regular one, while a real heading line is bold end to end.
    """
    carrying = [span for span in spans if span["text"].strip()]
    if not carrying:
        return False
    return all(_is_bold(span) for span in carrying)


def _body_size(layout: list[list[dict]]) -> float:
    """The document's body font size: the modal size, weighted by characters.

    Weighting by characters rather than by line count is what makes this robust.
    A paper has few heading lines but they are short; a reference list has many
    lines at a smaller size. Characters track which size carries the prose.
    """
    weights: Counter[float] = Counter()
    for blocks in layout:
        for block in blocks:
            for line in block["lines"]:
                weights[round(line.size, 1)] += len(line.text.strip())
    if not weights:
        return 0.0
    return weights.most_common(1)[0][0]


def _heading_levels(layout: list[list[dict]], body_size: float) -> dict[float, int]:
    """Rank the heading sizes, largest first, so level 1 is the outermost.

    Levels are what make nesting work, and nesting is load-bearing: MATES sets
    "Methods" at 10.71pt and "Raw reads preprocessing" at 8.72pt immediately
    after it. Without levels that subsection resets the section to ``other`` and
    the entire Methods section is mislabelled -- which is the one place in the
    paper where tool versions and parameters live.
    """
    sizes = {
        round(line.size, 1)
        for blocks in layout
        for block in blocks
        for line in block["lines"]
        if _is_heading(line, body_size)
    }
    return {size: rank for rank, size in enumerate(sorted(sizes, reverse=True), start=1)}


def _furniture_blocks(layout: list[list[dict]], heights: list[float]) -> dict[int, set[int]]:
    """Which blocks are the running header/footer, per page.

    Grouped by digit-free text template rather than by y-coordinate: the same
    words on most pages is a far stronger signal than the same position, and it
    rejects body paragraphs that merely happen to start near a page edge. MATES
    has three such paragraphs at y0 713-724, each unique, correctly kept.
    """
    threshold = max(2, math.ceil(0.5 * len(layout)))
    groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for page_number, (blocks, height) in enumerate(zip(layout, heights, strict=True), start=1):
        for block_index, block in enumerate(blocks):
            y0 = block["y0"]
            if not (y0 < height * _EDGE_TOP or y0 > height * _EDGE_BOTTOM):
                continue
            text = " ".join(line.text for line in block["lines"]).strip()
            groups[_DIGIT_RUN.sub("#", text)].append((page_number, block_index))

    furniture: dict[int, set[int]] = defaultdict(set)
    for members in groups.values():
        if len({page for page, _ in members}) >= threshold:
            for page_number, block_index in members:
                furniture[page_number].add(block_index)
    return furniture


# --------------------------------------------------------------------------- #
# pass 2: assembly
# --------------------------------------------------------------------------- #


def _assemble(
    blocks: list[dict],
    *,
    body_size: float,
    furniture: set[int],
    levels: dict[float, int],
) -> tuple[str, list[SectionMark], list[str]]:
    """Body text, the section marks indexing into it, and the furniture lines.

    A heading is emitted as its own piece rather than left at the head of its
    block. Journals typeset a heading as line 1 of the block that continues into
    the paragraph below it, so splitting is what makes a mark's offset exact
    instead of merely usually right -- URL rejoining can merge lines, which would
    otherwise shift every offset after it. It also keeps a heading out of the
    rejoiner's reach, where it has no business being considered for gluing.

    Consecutive leading lines at the *same* size are one wrapped heading and are
    merged; a size change starts a new one, which is what keeps MATES's
    "Results" (10.71pt) separate from the "Methods overview" subsection (8.72pt)
    printed directly beneath it.
    """
    pieces: list[str] = []
    marks: list[SectionMark] = []
    strays: list[str] = []
    offset = 0

    for block_index, block in enumerate(blocks):
        if block_index in furniture:
            strays.extend(line.text for line in block["lines"])
            continue

        lines = _split_run_in(block["lines"], body_size)
        index = 0
        while index < len(lines) and _is_heading(lines[index], body_size):
            size = lines[index].size
            bold = lines[index].bold
            parts = [lines[index].text.strip()]
            index += 1
            while (
                index < len(lines)
                and _is_heading(lines[index], body_size)
                and abs(lines[index].size - size) < 0.1
                and lines[index].bold == bold
            ):
                parts.append(lines[index].text.strip())
                index += 1
            heading = " ".join(parts)
            marks.append(
                SectionMark(
                    offset=offset,
                    heading=heading,
                    label=classify_heading(heading),
                    level=levels.get(round(size, 1), 1),
                )
            )
            pieces.append(heading)
            offset += len(heading) + 1  # +1 for the joining newline

        rest = [line.text for line in lines[index:]]
        if rest:
            joined = rejoin_broken_urls(rest)
            pieces.append(joined)
            offset += len(joined) + 1

    return "\n".join(pieces), marks, strays


def _split_run_in(lines: list[Line], body_size: float) -> list[Line]:
    """Turn a run-in heading into the wrapped shape the merge loop already reads.

    Rewriting the line rather than teaching the heading loop a second shape:
    once the bold prefix is its own line and the prose is another, every rule
    downstream -- merging, levels, offsets -- applies unchanged.
    """
    if not lines:
        return lines
    first = lines[0]
    if _is_heading(first, body_size) or not first.prefix:
        return lines
    candidate = Line(first.prefix.strip(), first.size, True)
    if not _is_heading(candidate, body_size):
        return lines
    remainder = first.text[len(first.prefix) :]
    rest = [Line(remainder, first.size, False)] if remainder.strip() else []
    return [candidate, *rest, *lines[1:]]


def _is_heading(line: Line, body_size: float) -> bool:
    """Whether this line is set as a heading rather than as prose.

    Either signal will do, and both are needed across publishers: size for
    Nature, which leaves the bold flag clear, and weight for PLOS, whose
    back-matter headings sit at the body size.
    """
    stripped = line.text.strip()
    if not stripped or len(stripped) > _HEADING_MAX_CHARS:
        return False
    # Figure panel labels ("a.", "b.") are short, large and alphabetic.
    if sum(character.isalpha() for character in stripped) < _HEADING_MIN_LETTERS:
        return False

    lowered = stripped.casefold()
    if any(lowered.endswith(tail) for tail in _HEADING_BAD_TAIL):
        return False

    by_size = line.size > body_size + _HEADING_SIZE_TOLERANCE
    by_weight = line.bold and line.size >= body_size - _HEADING_SIZE_TOLERANCE
    if by_size:
        return True
    if not by_weight:
        return False
    # Weight alone is the weaker signal, so it carries the extra condition.
    return not stripped.endswith(_RUN_IN_TAIL)


def _drop_front_matter_headings(pages: list[PageText]) -> None:
    """Discard unrecognizable headings that precede the paper's first real one.

    A title page is set in display type throughout -- the article-type label, the
    title, the author list -- so typography cannot tell those apart from a
    section heading, and on MATES it yields marks for "Article" and
    "Ruohan Wang". Position can tell them apart: until the paper names a section
    we recognize, there is no section to name, and the default ``front_matter``
    is both correct and honest. A genuinely unrecognized *first* section costs us
    one boundary, which is the conservative direction to err.
    """
    seen = False
    for page in pages:
        kept: list[SectionMark] = []
        for mark in page.sections:
            seen = seen or mark.label != "other"
            if seen:
                kept.append(mark)
        page.sections = kept


def _inherit_labels(pages: list[PageText]) -> None:
    """Give an unrecognized subsection the label of the section containing it.

    "Raw reads preprocessing" is a real boundary but not a nameable section, and
    the text under it is still Methods. Without this, every finding after the
    first Methods subsection is labelled ``other``.
    """
    enclosing: list[tuple[int, str]] = []
    for page in pages:
        for mark in page.sections:
            while enclosing and enclosing[-1][0] >= mark.level:
                enclosing.pop()
            if mark.label == "other":
                if enclosing:
                    mark.label = enclosing[-1][1]
            else:
                enclosing.append((mark.level, mark.label))


def _is_citation_marker(span: dict) -> bool:
    if not span["flags"] & _FLAG_SUPERSCRIPT:
        return False
    text = span["text"]
    return bool(text.strip()) and bool(_CITATION_MARKER.match(text))


def _link_uris(page: pymupdf.Page) -> list[str]:
    """URI targets of the page's link annotations.

    Worth pulling separately from the text: journals routinely typeset a long URL
    as truncated display text ("github.com/...") while the annotation carries the
    full target. Regex over the visible text alone misses those.
    """
    return [uri for link in page.get_links() if (uri := link.get("uri"))]


def _has_drawings(page: pymupdf.Page) -> bool:
    """Whether the page carries vector content.

    A scanned page is usually one big raster, but a page can also be effectively
    unreadable while holding vector line art. Either counts as "there is
    something here we may not be reading".
    """
    try:
        return bool(page.get_drawings())
    except Exception:
        return False
