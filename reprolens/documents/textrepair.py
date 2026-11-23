"""Repairs that apply to extracted text regardless of which channel produced it.

Both the PDF text layer and OCR break URLs across line ends, for different
reasons -- the typesetter wraps the column, Tesseract detects a new line -- and
the damage is identical: an identifier that no longer matches. The repair is
therefore shared rather than owned by either backend.
"""

from __future__ import annotations

import re

# A line whose final token is part of a URL.
_URL_TAIL = re.compile(r"(?:https?://|www\.)\S*$")

# Characters that can only continue a URL, never end an English sentence.
_BREAKS_MID_URL = tuple("/=?&-_:")

# Characters that can only continue a URL, never begin an English word.
_CONTINUES_URL = re.compile(r"^[./=?&_%\d]")

# A numbered reference-list marker: "67. Winkler, A. M., ...". It starts with a
# digit, so it satisfies _CONTINUES_URL, but it is not a URL continuation. In a
# reference list the running-header DOI ends a line and the next line opens with
# the entry number, which otherwise yields a plausible, wrong DOI
# ("10.1038/s41467-024-53114-7" + "67." -> "...53114-767"). A genuine
# continuation has its digits followed by a path character, never ". ".
_LIST_MARKER = re.compile(r"^\d{1,3}[.)]?\s")


def rejoin_broken_urls(lines: list[str]) -> str:
    """Join lines where a URL was split across a line break.

    Two independent signals, either sufficient, both keyed on characters that
    cannot occur at an English sentence boundary:

    * the line ends mid-URL -- ``.../acc.cgi?acc=`` wrapping before its accession;
    * the next line begins with a character that cannot start a word --
      ``https://www`` + ``.ncbi.nlm.nih.gov/...``, or ``https://doi.org/10.`` +
      ``1038/s41587-023-01767-y``, which is how OCR split that DOI.

    Line geometry looks like the natural signal for the PDF case and is not: a
    block's right edge is defined by its own longest line, so that line trivially
    "fills" the block. On MATES page 1 that glues the running-header DOI onto the
    article title. Token shape has no such circularity -- a title beginning
    ``MATES:`` is plainly not a URL continuation -- and it transfers to OCR,
    where no block geometry exists at all.

    Apply per block, since wrapping only happens within one.
    """
    out: list[str] = []
    for text in lines:
        previous = out[-1].rstrip() if out else ""
        if (
            out
            and _URL_TAIL.search(previous)
            and not _LIST_MARKER.match(text.lstrip())
            and (previous.endswith(_BREAKS_MID_URL) or _CONTINUES_URL.match(text.lstrip()))
        ):
            out[-1] = previous + text.lstrip()
        else:
            out.append(text)
    return "\n".join(out)
