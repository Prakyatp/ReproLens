"""Section labels, and the lookup that says which section a finding came from.

This module is deliberately free of PyMuPDF and of XML: it holds the vocabulary
every backend normalizes *to*, so the PDF path (headings detected by typography)
and the JATS path (headings handed to us in ``<title>``) produce the same labels.

Why the project needs this at all, measured on the two benchmark papers:

    LocusMasterTE -- 212 occurrences
      Data availability     20   GSE225377, GSE225380, 3 repositories
      References           168   65 DOIs, 101 URLs, 2 Zenodo records
      Associated Data       20   PMC's verbatim repeat of Data availability
      Front matter           4

79% of what the extractor finds is cited literature. It is not noise and it is
not wrong, but a DOI in the reference list means something entirely different
from ``GSE225377`` in the Data availability statement, and without a section
label the two arrive in the same undifferentiated list.

A section is a character offset into a page's text, not a page number. That is
forced by the data rather than chosen: MATES page 20 carries Data availability,
Code availability and References, 49 occurrences between them. Label by page and
those three collapse into one bucket.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

SectionLabel = Literal[
    "front_matter",
    "abstract",
    "background",
    "results",
    "methods",
    "discussion",
    "conclusions",
    "data_availability",
    "code_availability",
    "reporting_summary",
    "references",
    "acknowledgments",
    "author_contributions",
    "funding",
    "declarations",
    "supplementary",
    "associated_data",
    # Not a section: the running header/footer, which belongs to the page
    # rather than to any part of the document.
    "page_furniture",
    "other",
]

# Everything before the first recognized heading. A paper always has some.
DEFAULT_LABEL: SectionLabel = "front_matter"


@dataclass(slots=True)
class SectionMark:
    """A section heading, located by where it starts in a page's text.

    ``offset`` indexes ``PageText.text``. The heading itself is part of that
    text -- journals typeset a heading as the first line of the block that
    continues into the paragraph below it (MATES p20: one block reading
    "Data availability The TE reference data was sourced from...") -- so a
    finding inside the section always has a larger offset than its heading.
    """

    offset: int
    heading: str  # as printed, e.g. "Availability of data and materials"
    label: SectionLabel
    level: int = 1  # 1 = section, 2+ = subsection

    def as_dict(self) -> dict:
        return {"heading": self.heading, "label": self.label, "level": self.level}


# Ordered: the first pattern that matches a heading wins, so combined forms
# ("Data and code availability") must precede the single-resource ones.
_HEADING_RULES: tuple[tuple[str, SectionLabel], ...] = (
    # -- availability statements: the two sections the rubric weights most -----
    (r"^(data|code|software)\s+and\s+(code|data|software)\s+availab", "data_availability"),
    (r"^availability\s+of\s+(data|code|materials)", "data_availability"),
    (r"^(data|dataset)\s+availab", "data_availability"),
    (r"^data\s+access|^accession\s+(codes|numbers)", "data_availability"),
    (r"^(code|software)\s+availab|^code\s+access", "code_availability"),
    (r"^reporting\s+summary", "reporting_summary"),
    # -- body ------------------------------------------------------------------
    # Anchored, unlike the availability statements above. These names are single
    # words that also open longer subsection titles, and the subsection is often
    # not in the section its first word names: MATES puts "Method benchmarking
    # in single-cell TE quantification" on page 11, inside Results, four pages
    # before Methods begins. Prefix-matching sends every finding in it to the
    # wrong section. An unmatched subsection inherits its parent instead, which
    # gets the same heading right for the right reason.
    (r"^(abstract|summary)[.:]?$", "abstract"),
    (r"^(background|introduction)[.:]?$", "background"),
    (r"^(star\s+)?(online\s+)?(materials?\s+and\s+)?methods?[.:]?$", "methods"),
    (r"^methods?\s+and\s+materials?[.:]?$", "methods"),
    (r"^experimental\s+(procedures|section)[.:]?$", "methods"),
    (r"^results?[.:]?$", "results"),
    (r"^results?\s+and\s+discussion[.:]?$", "results"),
    (r"^discussion[.:]?$", "discussion"),
    # The trailing phrases are enumerated rather than left open, so the rule
    # stays anchored for the reason the comment above gives. Atomate2 titles
    # its last body section "Conclusions and future work", and an anchored
    # ^conclusions?$ sent its 8 finding occurrences to "other".
    (
        r"^conclusions?(\s+and\s+"
        r"(future\s+(work|directions?|outlook)|outlook|perspectives?))?[.:]?$",
        "conclusions",
    ),
    # -- back matter -----------------------------------------------------------
    (r"^(references|bibliography|literature\s+cited|reference\s+list)[.:]?$", "references"),
    (r"^acknowledge?ments?\b", "acknowledgments"),
    (r"^(authors?.{0,3}\s+)?contributions?\b", "author_contributions"),
    (r"^(funding|financial\s+support)\b", "funding"),
    (r"^declarations?\b|^competing\s+interests?\b", "declarations"),
    (r"^conflicts?\s+of\s+interest\b|^ethics\b", "declarations"),
    (r"^(supplementary|supporting\s+information|additional\s+files?)\b", "supplementary"),
    (r"^associated\s+data\b", "associated_data"),
)

_COMPILED = tuple((re.compile(source), label) for source, label in _HEADING_RULES)


def classify_heading(heading: str) -> SectionLabel:
    """Normalize a printed heading to a label.

    Unrecognized headings return ``other`` rather than being dropped: an
    unknown heading is still a real section boundary, and swallowing it would
    attribute the text under it to whatever section came before.
    """
    text = heading.strip().lstrip("0123456789.) \t").casefold()
    for pattern, label in _COMPILED:
        if pattern.match(text):
            return label
    return "other"


class SectionResolver:
    """Which section a given (page, offset) falls in, across a whole document.

    Carry-over across pages is the point. MATES's Methods heading is on page 15
    and the next heading is on page 20, so a finding on page 17 belongs to
    Methods even though page 17 contains no heading at all.
    """

    __slots__ = ("_keys", "_marks")

    def __init__(self, marks: Sequence[tuple[int, int, SectionMark]]) -> None:
        ordered = sorted(marks, key=lambda m: (m[0], m[1]))
        self._keys = [(page, offset) for page, offset, _ in ordered]
        self._marks = [mark for _, _, mark in ordered]

    def at(self, page: int, offset: int = 0) -> SectionMark:
        index = bisect_right(self._keys, (page, offset)) - 1
        if index < 0:
            return SectionMark(offset=0, heading="", label=DEFAULT_LABEL, level=1)
        return self._marks[index]

    def labels(self) -> list[SectionLabel]:
        """Every label present, in document order, for reporting."""
        return [mark.label for mark in self._marks]


def resolve(pages: Sequence) -> SectionResolver:
    """Build a resolver from pages carrying ``sections``."""
    return SectionResolver(
        [(page.page, mark.offset, mark) for page in pages for mark in page.sections]
    )
