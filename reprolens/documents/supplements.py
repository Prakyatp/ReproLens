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

import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile
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
class Received:
    """One supplementary file that was dropped beside the paper and opened.

    The only way a supplement's *contents* enter this audit. The archives gate
    programmatic downloads (see the module docstring), so the reader supplies
    the file, and this records what was done with it: how it was read, how
    much came out, and which of the paper's own supplement labels it answers
    to -- "S2 Appendix", "Supplementary Table 3" -- matched from its filename
    and its opening text, so a Methods deferral can be marked as covered.
    """

    filename: str
    readable: bool
    backend: str = ""
    pages: int = 0
    chars: int = 0
    covers: list[str] = field(default_factory=list)
    declared_as: str = ""
    kind: str = "other"
    note: str = ""

    @property
    def document(self) -> str:
        """The name provenance uses for this file."""
        return self.declared_as or (self.covers[0] if self.covers else self.filename)

    def as_dict(self) -> dict:
        return asdict(self) | {"document": self.document}


@dataclass(slots=True)
class Supplements:
    inventory: str = INVENTORY_UNAVAILABLE
    declared: list[Supplement] = field(default_factory=list)
    referenced: list[Reference] = field(default_factory=list)
    received: list[Received] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def covered(self) -> set[str]:
        """Supplement labels whose contents were actually read."""
        return {label for r in self.received if r.readable for label in r.covers}

    @property
    def deferred_unread(self) -> list[Reference]:
        """Methods deferrals no received file answers to -- the ones still outside the audit."""
        covered = self.covered
        return [r for r in self.deferred_from_methods if r.label not in covered]

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
                "deferred_unread": len(self.deferred_unread),
                "received": len(self.received),
                "contents_read": sum(1 for r in self.received if r.readable),
            },
            "notes": self.notes,
            "declared_files": [s.as_dict() for s in self.declared],
            "references": [r.as_dict() for r in self.referenced],
            "received_files": [r.as_dict() for r in self.received],
        }


def collect(
    path: Path, pages: list[PageText], received: list[Received] | None = None
) -> Supplements:
    """The paper's supplements: what it declares, what its prose relies on, what was read.

    ``pages`` are the article's own pages, not the supplements' -- a supplement
    titled "Supplementary Table 1" would otherwise count as a reference to
    itself.
    """
    result = Supplements()
    result.received = list(received or [])

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

    # A received file is matched to the declared inventory by filename, so a
    # JATS-declared "pcbi.s012.docx" dropped in under that name is known to be
    # S2 Appendix even if nothing inside it says so.
    by_filename = {d.filename: d for d in result.declared if d.filename}
    for item in result.received:
        declared = by_filename.get(item.filename)
        if declared and not item.declared_as:
            item.declared_as = declared.label
            item.kind = declared.kind
            if declared.label not in item.covers:
                item.covers.append(declared.label)

    read = [r for r in result.received if r.readable]
    unread = [r for r in result.received if not r.readable]
    if read:
        result.notes.append(
            f"{len(read)} supplementary file(s) were supplied alongside the paper and read "
            f"({', '.join(r.document for r in read[:4])}); what they state is in the "
            f"findings below with its provenance."
        )
    if unread:
        result.notes.append(
            f"{len(unread)} supplied supplementary file(s) could not be read "
            f"({', '.join(f'{r.filename}: {r.note}' for r in unread[:3])}). Their contents "
            f"are absent from this audit -- a gap in the audit, not in the paper."
        )

    if result.declared:
        bearing = result.method_bearing
        missing = [d for d in bearing if d.label not in result.covered]
        if missing:
            result.notes.append(
                f"{len(result.declared)} supplementary file(s) declared, {len(bearing)} of "
                f"which could carry method detail; {len(missing)} of those were not supplied "
                f"({', '.join(d.label for d in missing[:4])}). The archives gate supplement "
                f"files against automated access, so drop them beside the paper to have "
                f"them read; until then anything stated only there is outside this audit."
            )
    deferred = result.deferred_from_methods
    still = result.deferred_unread
    if deferred and still:
        result.notes.append(
            f"the Methods section defers to {len(deferred)} supplementary item(s), "
            f"{len(still)} of which were not supplied ({', '.join(r.label for r in still[:4])}); "
            f"the detail they carry was not assessed either way."
        )
    elif deferred:
        result.notes.append(
            f"the Methods section defers to {len(deferred)} supplementary item(s) "
            f"({', '.join(r.label for r in deferred[:4])}), all of which were supplied and read."
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


# ---------------------------------------------------------------------------
# Reading supplied files

READABLE = frozenset({".pdf", ".xlsx", ".xlsm", ".csv", ".tsv", ".txt", ".md", ".docx", ".xml"})

# How much of a file's opening text is searched for the labels it answers to.
# The first page of a supplement is where "Supplementary Table 2" is printed.
_LABEL_WINDOW = 3000


def read_files(paths: list[Path], *, use_ocr: bool = True) -> tuple[list[PageText], list[Received]]:
    """Open every supplied supplement, returning its pages and a record per file.

    PDFs go through the same reader as the article (text layer, OCR fallback).
    Spreadsheets, delimited text and Word files become one page per sheet or
    file, read as plain rows. Anything else is recorded as received and
    unreadable rather than dropped, so the report can say a file arrived that
    the audit could not open.
    """
    from reprolens.documents.reading import read_pages

    pages: list[PageText] = []
    received: list[Received] = []
    for path in paths:
        suffix = path.suffix.lower()
        item = Received(filename=path.name, readable=False)
        try:
            if suffix == ".pdf":
                # The article-level gate (is_readable) is calibrated for a
                # paper and would reject a one-page supplementary note as
                # unread. A supplement is readable if any text came out of
                # it; the OCR fallback inside read_pages still applies.
                got, _notes = read_pages(path, use_ocr=use_ocr)
                got = [p for p in got if p.char_count]
                if not got:
                    item.note = "no text came out of it, even with OCR"
                else:
                    item.backend = got[0].backend
            elif suffix in {".xlsx", ".xlsm"}:
                got = _sheets(path)
                item.backend = "text"
            elif suffix in {".csv", ".tsv", ".txt", ".md"}:
                got = [_text_page(path.read_text(encoding="utf-8", errors="replace"))]
                item.backend = "text"
            elif suffix == ".docx":
                got = [_text_page(_docx_text(path))]
                item.backend = "text"
            elif suffix == ".xml":
                got, _ = read_pages(path, use_ocr=False)
                item.backend = "jats_xml"
            else:
                got = []
                item.note = f"a {suffix.lstrip('.') or 'binary'} file is not a format this reads"
        except Exception as error:  # a corrupt or password-protected file
            got = []
            item.note = f"could not be opened ({type(error).__name__})"

        got = [p for p in got if p.char_count]
        if got:
            item.readable = True
            item.pages = len(got)
            item.chars = sum(p.char_count for p in got)
            head = " ".join(p.text for p in got)[:_LABEL_WINDOW]
            item.covers = labels_in(f"{_words(path.stem)} {head}")
            item.kind = classify(" ".join(item.covers), head[:200])
        elif not item.note:
            item.note = "the file was empty"

        name = item.document
        for page in got:
            page.document = name
        pages += got
        received.append(item)
    return pages, received


def labels_in(text: str) -> list[str]:
    """Every distinct supplement label the text names, in order of appearance."""
    seen: list[str] = []
    # Filenames spell the label with underscores; the pattern wants spaces.
    for match in _REFERENCE.finditer(text.replace("_", " ")):
        label = _label(match)
        if label and label not in seen:
            seen.append(label)
    return seen


def _words(stem: str) -> str:
    """``Supplementary_Table_S2`` -> ``Supplementary Table S2``, so a filename can match."""
    return re.sub(r"[_\-]+", " ", stem)


def _text_page(text: str, page: int = 1) -> PageText:
    return PageText(page=page, text=text, backend="text")


def _sheets(path: Path) -> list[PageText]:
    """One page per worksheet, cells joined by tabs so a row reads as a row."""
    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    pages: list[PageText] = []
    for number, sheet in enumerate(book.worksheets, start=1):
        lines = [sheet.title]
        version_column: int | None = None
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if v is None else str(v).strip() for v in row]
            if not any(cells):
                continue
            lower = [c.lower() for c in cells]
            if version_column is None and any(c in _VERSION_HEADERS for c in lower):
                # The header row itself: remember which column it says holds
                # versions. "tool | version" is how every software table is
                # laid out, and the header is the table saying so.
                version_column = next(i for i, c in enumerate(lower) if c in _VERSION_HEADERS)
                lines.append("\t".join(cells).rstrip())
                continue
            if version_column is not None and len(cells) > version_column:
                name = next((c for i, c in enumerate(cells) if i != version_column and c), "")
                value = cells[version_column]
                if name and value:
                    # Spelled the way prose spells it, so the same extractor
                    # that reads "STAR version 2.7.10a" in Methods reads it here.
                    lines.append(f"{name} version {value}")
                    continue
            lines.append("\t".join(cells).rstrip())
        pages.append(_text_page("\n".join(lines), page=number))
    book.close()
    return pages


_VERSION_HEADERS = frozenset({"version", "ver", "release", "software version", "tool version"})


def _docx_text(path: Path) -> str:
    """The paragraphs of a Word file, without a Word library.

    A .docx is a zip whose ``word/document.xml`` holds the text in ``<w:t>``
    runs; paragraphs end at ``</w:p>``. That is enough to recover the prose
    and the tables as lines, which is all the extractors need.
    """
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("word/document.xml").decode("utf-8", errors="replace")
    raw = re.sub(r"</w:p>", "\n", raw)
    raw = re.sub(r"</w:tc>", "\t", raw)
    text = re.sub(r"<[^>]+>", "", raw)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _delimited(text: str) -> list[list[str]]:
    """Rows of a delimited file, for callers that want cells rather than lines."""
    sample = text[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))
