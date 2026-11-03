"""Tables, read from the geometry the PDF already carries.

Built on word rectangles rather than on OCR, and the reason is worth stating
because the intuition runs the other way. OCR returns words with boxes and
confidences; it does not return rows, columns, spans or headers. Structure has
to be recovered by clustering boxes either way -- so the question is only whose
boxes to cluster, and on a born-digital page the text layer's are *exact* while
OCR's are estimated from pixels. Rasterising a page to recover coordinates it
already stores would be slower and worse.

The algorithm is two clusterings, in the order the page is written:

1. **Rows**, by baseline. Words whose tops agree within a few points are one
   row, which is also what makes a wrapped cell detectable: its continuation
   lands on its own baseline with nothing beside it.
2. **Columns**, by the gap between words. Inside a cell the gap is a space, a
   few points wide; between columns it is the gutter. Splitting on the gap
   between one word's right edge and the next word's left edge separates them.

The second clustering is where a plausible mistake lives, and it cost a pass to
find: comparing the *start* of consecutive words instead of the space between
them makes every long word look like a column break, and the detector then
reports tables on all 27 pages of a paper that has them on four.

What this does not do is model spans or header hierarchies. A row is a list of
cells, which is enough to ask whether the values in a table also appear in the
prose, and not enough to say which column heading governs which cell.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf

#: Words whose tops agree within this are one row.
ROW_TOLERANCE = 3.0

#: The space between two words of the same cell never reaches this; a column
#: gutter always exceeds it. Measured on ALIGNN, whose body text runs 3-15pt
#: between words and whose table gutters run 25pt and wider.
COLUMN_GAP = 22.0

#: A row of one cell is a caption, a wrapped continuation, or prose.
MIN_CELLS = 2

#: Fewer rows than this is not a table; two numbers side by side in a sentence
#: would otherwise qualify.
MIN_ROWS = 3

#: A single-cell row of at least this many words is the paragraph resuming,
#: not a wrapped cell.
PROSE_WORDS = 6

_CAPTION = re.compile(r"^\s*(Table\s+(\d{1,2}|[IVX]{1,4}))\s*[.:]?\s*(.*)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Table:
    label: str
    caption: str
    page: int
    rows: list[list[str]]

    @property
    def columns(self) -> int:
        """The widest row's cell count, which is the column count a reader sees."""
        return max((len(r) for r in self.rows), default=0)

    @property
    def values(self) -> list[str]:
        return [cell for row in self.rows for cell in row if cell.strip()]

    def as_dict(self) -> dict:
        return asdict(self) | {"columns": self.columns, "n_rows": len(self.rows)}


@dataclass(slots=True)
class Tables:
    found: list[Table] = field(default_factory=list)
    captions_seen: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def unparsed(self) -> list[str]:
        """Captions with no grid recovered beneath them.

        Reported rather than dropped. A caption this found and a table it could
        not read is a gap in the audit; silently listing four tables for a paper
        that printed six would misreport the paper instead.
        """
        parsed = {t.label.lower() for t in self.found}
        return [c for c in self.captions_seen if c.lower() not in parsed]

    def to_dict(self) -> dict:
        return {
            "summary": {
                "captions_found": len(self.captions_seen),
                "tables_parsed": len(self.found),
                "captions_unparsed": len(self.unparsed),
                "cells_read": sum(len(t.values) for t in self.found),
            },
            "notes": self.notes,
            "unparsed": self.unparsed,
            "tables": [t.as_dict() for t in self.found],
        }


def extract(path: Path) -> Tables:
    """Every table this can recover from a PDF, anchored on its caption."""
    result = Tables()
    if path.suffix.lower() != ".pdf":
        result.notes.append(
            f"table extraction needs page geometry, which a {path.suffix.lstrip('.')} "
            f"input does not carry."
        )
        return result

    with pymupdf.open(path) as doc:
        for number, page in enumerate(doc, start=1):
            rows = _rows(page)
            for index, (_y, cells) in enumerate(rows):
                match = _CAPTION.match(" ".join(cells))
                if not match:
                    continue
                label = " ".join(match.group(1).split())
                if label not in result.captions_seen:
                    result.captions_seen.append(label)
                grid = _grid_below(rows, index)
                if len(grid) >= MIN_ROWS:
                    result.found.append(
                        Table(
                            label=label,
                            caption=" ".join(match.group(3).split())[:300],
                            page=number,
                            rows=grid,
                        )
                    )

    if result.unparsed:
        result.notes.append(
            f"{len(result.unparsed)} table caption(s) were found with no readable grid "
            f"beneath them ({', '.join(result.unparsed[:4])}); their contents are absent "
            f"from this audit."
        )
    if result.found:
        result.notes.append(
            f"{len(result.found)} table(s) read, "
            f"{sum(len(t.values) for t in result.found)} cell(s) total. Cell values are "
            f"searchable; which column heading governs which cell is not modelled."
        )
    return result


def agreement(result: Tables, document_text: str) -> dict:
    """How much of what the tables say the prose also says.

    Framed carefully, because the obvious reading of a low number is wrong. A
    data table exists precisely to carry values the prose does not repeat, so
    most of its cells being absent from the text is correct behaviour and not a
    disagreement. What the comparison is good for is the opposite direction:
    the *names* a table puts on screen -- the baselines a results table
    compares against -- which the prose usually does mention and the curated
    software vocabulary often does not.
    """
    haystack = document_text.casefold()
    cells = [c.strip() for t in result.found for c in t.values if c.strip()]
    named = sorted(
        {
            cell
            for cell in cells
            # A name, not a measurement: carries a letter, is short, and is not
            # a unit. Numbers are the one thing a table is guaranteed to hold
            # that the prose will not repeat.
            if any(ch.isalpha() for ch in cell) and len(cell) <= 24 and not _MEASUREMENT.match(cell)
        }
    )
    echoed = [n for n in named if n.casefold() in haystack]
    return {
        "cells": len(cells),
        "named_values": len(named),
        "named_values_echoed_in_prose": len(echoed),
        "share_echoed": round(len(echoed) / len(named), 3) if named else None,
        "not_in_prose": [n for n in named if n not in echoed][:20],
    }


#: A cell that is a quantity rather than a name.
_MEASUREMENT = re.compile(r"^[\d.,+\-±%()/\s]*$|^[\d.,]+\s*[A-Za-z%µÅ()\-/]{0,8}$")


def _rows(page: pymupdf.Page) -> list[tuple[float, list[str]]]:
    """The page's words grouped into rows, each split into cells."""
    bands: dict[float, list[tuple[float, float, str]]] = {}
    for x0, y0, x1, _y1, word, *_rest in page.get_text("words"):
        if not word.strip():
            continue
        key = round(y0 / ROW_TOLERANCE) * ROW_TOLERANCE
        bands.setdefault(key, []).append((x0, x1, word))

    out: list[tuple[float, list[str]]] = []
    for key in sorted(bands):
        out.append((key, _cells(sorted(bands[key]))))
    return out


def _cells(words: list[tuple[float, float, str]]) -> list[str]:
    """Split one row's words into cells wherever a column gutter opens."""
    cells: list[str] = []
    current = [words[0][2]]
    for before, after in zip(words, words[1:], strict=False):
        if after[0] - before[1] > COLUMN_GAP:
            cells.append(" ".join(current))
            current = [after[2]]
        else:
            current.append(after[2])
    cells.append(" ".join(current))
    return cells


def _grid_below(rows: list[tuple[float, list[str]]], caption_index: int) -> list[list[str]]:
    """The multi-cell rows following a caption, until the grid stops.

    Single-cell rows are skipped rather than ending the grid, because a wrapped
    cell lands on its own baseline with nothing beside it -- ALIGNN's "Formation
    energy" occupies two, and its Table 3 stacks a wrapped column heading
    ("MAE") directly above a wrapped unit ("eV(atom)-1").

    What ends the grid is a single-cell row that reads as *prose*, which is the
    paragraph resuming after the table. Counting consecutive single-cell rows
    instead looked equivalent and was not: two in a row is exactly the shape of
    that stacked heading and unit, so Table 3 terminated after its header and
    reported one row out of fifteen.
    """
    grid: list[list[str]] = []
    for _y, cells in rows[caption_index + 1 :]:
        if len(cells) >= MIN_CELLS:
            grid.append(cells)
            continue
        if grid and _is_prose(cells):
            break
    return grid


def _is_prose(cells: list[str]) -> bool:
    """Whether a single-cell row is a sentence rather than a wrapped cell.

    Length is the signal available. A wrapped cell is a heading, a unit or a
    couple of words; the line that resumes the paragraph runs the width of the
    column.
    """
    return len(" ".join(cells).split()) >= PROSE_WORDS
