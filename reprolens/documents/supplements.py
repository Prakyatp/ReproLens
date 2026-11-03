"""What the paper put outside the paper.

Methods detail migrates to the supplement constantly, and when it does, every
criterion scored on the main text is scored on an incomplete document without
saying so. ASPEN is the clean example: its ``S4 Fig`` *is* the ASPEN workflow --
"scRNA data pre-processing steps, including the generation of the F1 index file"
-- and its ``S2 Appendix`` holds the supplemental tables, including the
breakdown of genes behind Fig 3B. None of that is in the article body.

Two sources, and they are not equally good:

**A JATS inventory is exact.** ``<supplementary-material>`` carries a label, a
caption title, the filename, its media type and often its byte size. ASPEN
declares twelve; LocusMasterTE declares two, one of which is the peer review
history. This is read from the file already on disk, so it is free and it cannot
be wrong about what exists.

**A PDF has no inventory at all.** MATES references fifty-five supplementary
items in its prose and ships no manifest, because the manifest is not part of a
PDF. So a PDF-sourced paper gets ``INVENTORY_UNAVAILABLE`` rather than an empty
list, and nothing downstream may read the absence of declared files as a paper
that published none. This is the same rule the OCR path follows for a page it
could not read, and it matters here because the two inputs would otherwise score
differently for a difference in how the audit was fed.

**Nothing is fetched, and that is not a shortcut.** It was tried. PMC serves a
Google reCAPTCHA challenge page -- with HTTP 200 and ``content-type:
text/html`` -- in place of any supplement binary, and PLOS returns 403. A naive
status-code check therefore reports a captcha page as a successfully reached
supplement, which is worse than not checking. Those gates are deliberate and
working around them is not something this tool should do; the sanctioned route
for bulk programmatic access is PMC's Open Access service, which serves packages
rather than files and is a separate piece of work. So this module reports what
the paper declares and says plainly that the contents were never read.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

from reprolens.documents.base import PageText
from reprolens.documents.jats_xml import _article, _local

DECLARED = "declared"
INVENTORY_UNAVAILABLE = "inventory_unavailable"

# "Supplementary Table S2", "Supplementary Fig. S5a", "Additional file 1",
# "Supporting Information S1", "S2 Appendix". The trailing panel letter is kept
# out of the label: S5a and S5b are one file.
_REFERENCE = re.compile(
    r"\b(?:(?:Supplementary|Supplemental|Supporting)\s+"
    r"(?P<what>Tables?|Fig(?:ure)?s?|Data|Notes?|Methods?|Information|Movies?|Videos?|"
    r"Files?|Appendix|Appendices)\.?\s*(?P<num>S?\d{1,2})?"
    r"|Additional\s+file\s+(?P<add>\d{1,2})"
    r"|S(?P<sn>\d{1,2})\s+(?P<swhat>Fig|Table|Appendix|Text|File))",
    re.IGNORECASE,
)

_KINDS = (
    ("table", ("table",)),
    ("figure", ("fig",)),
    ("appendix", ("appendix", "appendices")),
    ("data", ("data", "dataset")),
    ("text", ("note", "method", "text", "information", "results")),
    ("media", ("movie", "video", "audio")),
)


def classify(label: str, title: str = "") -> str:
    """What sort of supplement this is, from its label and caption.

    The kind is what decides whether a supplement matters to reproducibility.
    A supplementary movie is not where a parameter hides; a supplementary table
    very often is, and so is anything called an appendix.
    """
    haystack = f"{label} {title}".lower()
    for kind, needles in _KINDS:
        if any(needle in haystack for needle in needles):
            return kind
    return "other"


# Kinds that plausibly carry method detail a reproduction would need. A figure
# can too -- ASPEN's workflow is one -- so figures are included and movies are
# not.
BEARING = frozenset({"table", "appendix", "data", "text", "figure"})


@dataclass(frozen=True, slots=True)
class Supplement:
    """One file the paper declares."""

    label: str
    title: str
    filename: str
    media_type: str = ""
    size: int | None = None
    kind: str = "other"

    @property
    def may_carry_method_detail(self) -> bool:
        return self.kind in BEARING

    def as_dict(self) -> dict:
        return asdict(self) | {"may_carry_method_detail": self.may_carry_method_detail}


@dataclass(frozen=True, slots=True)
class Reference:
    """A supplement the prose points at.

    Kept separate from a declared file because it is weaker evidence of a
    different thing: that the paper relies on the supplement, not that the
    supplement exists.
    """

    label: str
    mentions: int
    in_methods: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Supplements:
    inventory: str = INVENTORY_UNAVAILABLE
    declared: list[Supplement] = field(default_factory=list)
    referenced: list[Reference] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def method_bearing(self) -> list[Supplement]:
        return [s for s in self.declared if s.may_carry_method_detail]

    @property
    def deferred_from_methods(self) -> list[Reference]:
        """Supplements the Methods section itself points at.

        The sharpest signal available here. A supplement cited from Results is
        usually a further figure; one cited from Methods is a step of the method
        that is not in the paper.
        """
        return [r for r in self.referenced if r.in_methods]

    def to_dict(self) -> dict:
        return {
            "inventory": self.inventory,
            "summary": {
                "declared": len(self.declared),
                "may_carry_method_detail": len(self.method_bearing),
                "referenced_in_prose": len(self.referenced),
                "deferred_from_methods": len(self.deferred_from_methods),
                "contents_read": 0,
            },
            "notes": self.notes,
            "declared_files": [s.as_dict() for s in self.declared],
            "references": [r.as_dict() for r in self.referenced],
        }


def collect(path: Path, pages: list[PageText]) -> Supplements:
    """The paper's supplements: what it declares, and what its prose relies on."""
    result = Supplements()

    if path.suffix.lower() == ".xml":
        result.inventory = DECLARED
        result.declared = from_xml(path)
    else:
        result.notes.append(
            f"a {path.suffix.lstrip('.') or 'binary'} input carries no supplement manifest, so "
            f"which files the paper published could not be listed. This is a limit of the "
            f"input, NOT a paper that published none."
        )

    result.referenced = references(pages)

    if result.declared:
        bearing = result.method_bearing
        result.notes.append(
            f"{len(result.declared)} supplementary file(s) declared, {len(bearing)} of which "
            f"could carry method detail. None were downloaded or read: the archives gate "
            f"supplement files against automated access, so anything stated only in a "
            f"supplement is outside this audit."
        )
    deferred = result.deferred_from_methods
    if deferred:
        result.notes.append(
            f"the Methods section defers to {len(deferred)} supplementary item(s) "
            f"({', '.join(r.label for r in deferred[:4])}); the detail they carry was not "
            f"assessed either way."
        )
    return result


def from_xml(path: Path) -> list[Supplement]:
    """Every distinct file a JATS article declares.

    Deduplicated by filename. PMC repeats each entry under a second synthetic id
    -- LocusMasterTE's two files appear four times -- and counting those would
    double the size of every paper's supplement.
    """
    try:
        root = _article(ET.parse(path).getroot())
    except (ET.ParseError, OSError):
        return []

    sizes = _sizes(path)
    found: dict[str, Supplement] = {}
    for element in root.iter():
        if _local(element.tag) != "supplementary-material":
            continue
        title = _first_text(element, "title") or _first_text(element, "p")
        label = _first_text(element, "label") or _label_from(title)
        filename, media_type = _media(element)
        key = filename or f"{label}:{title}"[:80]
        if not key or key in found:
            continue
        found[key] = Supplement(
            label=label or filename,
            title=title,
            filename=filename,
            media_type=media_type,
            size=sizes.get(filename),
            kind=classify(label, title),
        )
    return list(found.values())


def _label_from(title: str) -> str:
    """A label taken from the caption, for publishers that ship no ``<label>``.

    Springer's JATS has none: LocusMasterTE's two files are identified only by
    captions opening "Additional file 1." Without this the label falls back to
    the filename, and a report calling a supplement
    ``13059_2025_3522_MOESM1_ESM.pdf`` has told the reader nothing they can
    match against the paper's own prose.
    """
    if match := _REFERENCE.search(title):
        return _label(match)
    return ""


def _sizes(path: Path) -> dict[str, int]:
    """Byte sizes, which PMC records in a processing instruction.

    ``<?size 1891846?>`` is a processing instruction, and ElementTree discards
    those while parsing, so no walk of the tree can reach them. Worth a second
    pass over the raw text because size is the one field that says whether a
    supplement is a one-page note or a two-megabyte figure pack.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    sizes: dict[str, int] = {}
    for match in re.finditer(r'href="([^"]+)"', raw):
        filename = match.group(1)
        if filename in sizes:
            continue
        window = raw[match.end() : match.end() + 400]
        if found := re.search(r"<\?size (\d+)\?>", window):
            sizes[filename] = int(found.group(1))
    return sizes


def _first_text(element: ET.Element, tag: str) -> str:
    for child in element.iter():
        if _local(child.tag) == tag:
            return " ".join("".join(child.itertext()).split())
    return ""


def _media(element: ET.Element) -> tuple[str, str]:
    """The filename and media type a ``<media>`` child carries.

    The href attribute is namespaced and the namespace prefix varies by
    publisher -- ``xlink:href`` at one, ``ns1:href`` at another -- so it is
    matched on the local name instead of a fixed key.
    """
    for child in element.iter():
        if _local(child.tag) != "media":
            continue
        href = ""
        for key, value in child.attrib.items():
            if _local(key) == "href":
                href = value.strip()
        media_type = "/".join(
            part for part in (child.get("mimetype", ""), child.get("mime-subtype", "")) if part
        )
        return href, media_type
    return "", ""


def references(pages: list[PageText]) -> list[Reference]:
    """Supplementary items the prose points at, and whether Methods points at them."""
    counts: dict[str, int] = {}
    in_methods: set[str] = set()

    for page in pages:
        sections = sorted(page.sections, key=lambda m: m.offset)
        for match in _REFERENCE.finditer(page.text):
            label = _label(match)
            if not label:
                continue
            counts[label] = counts.get(label, 0) + 1
            if _section_at(sections, match.start()) == "methods":
                in_methods.add(label)

    return sorted(
        (Reference(label, counts[label], label in in_methods) for label in counts),
        key=lambda r: (-r.mentions, r.label),
    )


# One supplement, however the paper spelled it. A paper that writes both
# "Supplementary Fig. S1" and "Supplementary Figure 1" means the same file, and
# without this it is counted as two -- which inflates how much of the method
# sits outside the article and splits the Methods-deferral signal in half.
_CANONICAL = {
    "fig": "Figure",
    "figs": "Figure",
    "figure": "Figure",
    "figures": "Figure",
    "table": "Table",
    "tables": "Table",
    "appendix": "Appendix",
    "appendices": "Appendix",
    "note": "Note",
    "notes": "Note",
    "method": "Methods",
    "methods": "Methods",
    "data": "Data",
    "information": "Information",
    "file": "File",
    "files": "File",
    "movie": "Movie",
    "movies": "Movie",
    "video": "Movie",
    "videos": "Movie",
}


def _label(match: re.Match) -> str:
    if match.group("add"):
        return f"Additional file {match.group('add')}"
    if match.group("sn"):
        return f"S{match.group('sn')} {match.group('swhat').title()}"
    raw = (match.group("what") or "").lower()
    if not raw:
        return ""
    what = _CANONICAL.get(raw, raw.title().rstrip("s"))
    number = (match.group("num") or "").upper().lstrip("S")
    return f"Supplementary {what} {number}".strip()


def _section_at(sections, offset: int) -> str:
    label = ""
    for mark in sections:
        if mark.offset <= offset:
            label = mark.label
        else:
            break
    return label
