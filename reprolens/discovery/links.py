"""Find every external resource a paper points at: datasets, repositories, DOIs, URLs.

``extract`` takes already-read pages, never a file path. That is deliberate: the
same function serves the PDF text layer today and OCR output later, with no
change. Whatever read the page is recorded on each finding instead.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from reprolens.discovery.patterns import PATTERNS, clean_value, normalize_with_offsets
from reprolens.documents.base import Backend, PageText
from reprolens.documents.sections import SectionLabel, SectionResolver, resolve

CONTEXT_CHARS = 120

# Enough to tell a real path-less host from a URL cut off mid-name. Any
# two-letter country code is accepted alongside these, and a URL that carries a
# path is never checked against this list at all.
_TLDS = frozenset(
    {
        "com",
        "org",
        "net",
        "edu",
        "gov",
        "int",
        "mil",
        "io",
        "ai",
        "co",
        "dev",
        "me",
        "info",
        "biz",
        "app",
        "cloud",
        "xyz",
        "eu",
        "tech",
        "bio",
    }
)


@dataclass(slots=True)
class Occurrence:
    """One place a value was seen. Kept per-occurrence, not collapsed.

    Where a resource is mentioned carries meaning the value alone does not: a GEO
    accession in a Data Availability statement is this paper's own data, while the
    same accession in the reference list is someone else's. Later steps need that
    distinction, so the page and surrounding text are preserved for every hit.
    """

    page: int
    source: str  # "text" | "annotation" | "furniture"
    context: str
    backend: Backend = "pdf_text"
    confidence: float | None = None
    section: SectionLabel = "front_matter"
    section_heading: str = ""  # as printed, when the document named it


@dataclass(slots=True)
class Finding:
    value: str
    kind: str
    occurrences: list[Occurrence] = field(default_factory=list)

    @property
    def pages(self) -> list[int]:
        return sorted({o.page for o in self.occurrences})

    @property
    def backends(self) -> list[str]:
        return sorted({o.backend for o in self.occurrences})

    @property
    def sections(self) -> list[SectionLabel]:
        return sorted({o.section for o in self.occurrences})

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "kind": self.kind,
            "pages": self.pages,
            "sections": self.sections,
            "backends": self.backends,
            "n_occurrences": len(self.occurrences),
            "occurrences": [asdict(o) for o in self.occurrences],
        }


def extract(pages: list[PageText]) -> list[Finding]:
    """All resource identifiers across the given pages, deduplicated by value."""
    findings: dict[tuple[str, str], Finding] = {}
    resolver = resolve(pages)

    for page in pages:
        for value, kind, occurrence in _scan_page(page, resolver):
            key = (kind, value)
            finding = findings.get(key)
            if finding is None:
                finding = Finding(value=value, kind=kind)
                findings[key] = finding
            finding.occurrences.append(occurrence)

    return _drop_truncated_urls(sorted(findings.values(), key=lambda f: (f.kind, f.value)))


def _drop_truncated_urls(findings: list[Finding]) -> list[Finding]:
    """Remove URL matches that are the severed head of a longer URL.

    MATES prints "https://www. ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE84465"
    with a space after "www." -- a break inside a line rather than at the end of
    one, so the line-rejoining repair never sees it. The URL pattern then matches
    only "https://www", and that arrives as a resource.

    The test cannot be "is this a prefix of a longer URL we found", which was the
    first thing tried: the complete URL is never a finding here, because the
    accession inside it claims that span first and the catch-all is suppressed.
    So the fragment has to be recognizable on its own, and it is -- it has no
    path and its host does not end in anything that could be a top-level domain.
    Requiring both keeps a real path-less host ("https://mates.cellcycle.org")
    and never judges a URL that has a path, whatever its domain looks like.
    """
    return [
        finding
        for finding in findings
        if not (finding.kind == "url" and _is_severed_host(finding.value))
    ]


def _is_severed_host(value: str) -> bool:
    scheme, separator, remainder = value.partition("://")
    if not separator:
        # "mailto:someone@example.com" has no authority to be severed. Without
        # this the test silently swallowed MATES's corresponding-author address,
        # reaching the right outcome by the wrong rule and leaving the rule that
        # was supposed to handle it unreachable.
        return False
    if "/" in remainder:
        return False  # has a path; judged complete
    host = remainder.partition("?")[0].partition("#")[0].rstrip(".")
    label = host.rpartition(".")[2].casefold()
    return label not in _TLDS and not (len(label) == 2 and label.isalpha())


def _scan_page(page: PageText, resolver: SectionResolver) -> list[tuple[str, str, Occurrence]]:
    """(value, kind, occurrence) for every match on one page."""
    results: list[tuple[str, str, Occurrence]] = []

    def occurrence(source: str, context: str, label: SectionLabel, heading: str) -> Occurrence:
        return Occurrence(
            page=page.page,
            source=source,
            context=context,
            backend=page.backend,
            confidence=page.confidence,
            section=label,
            section_heading=heading,
        )

    # The body, where position is known precisely. Offsets come back mapped to
    # the original text, because section boundaries are recorded against that.
    body, offsets = normalize_with_offsets(page.text)
    in_text: set[tuple[str, str]] = set()
    for value, kind, start, end in _matches(body):
        mark = resolver.at(page.page, offsets[start])
        in_text.add((kind, value))
        results.append(
            (value, kind, occurrence("text", _context(body, start, end), mark.label, mark.heading))
        )

    # Link annotations are a separate channel, not a duplicate of the text one:
    # journals truncate the displayed URL while the annotation holds the full
    # target, so a repo visible only as "github.com/..." is recoverable here.
    #
    # An annotation carries no character offset, so it can only be attributed to
    # the section in force where its page or segment opens. On the JATS path that
    # is exact: one segment is one section and its <ext-link>s are its own. On a
    # PDF page it is a guess, and a guess here is actively harmful rather than
    # merely vague -- MATES page 20 opens in Methods and carries the Data
    # availability statement, so its GEO links arrived labelled Methods, which
    # asserts the paper depends on someone else's dataset when in fact that is
    # its own deposited data.
    #
    # So an annotation is only recorded for a value the text channel did not
    # already find on this page, which is the job it exists for: recovering a
    # target the typesetting truncated to "github.com/...". When both channels
    # see the same value the text one wins, because it knows where it is. A
    # truncated display string and its full target are different values, so
    # nothing is lost.
    opening = resolver.at(page.page, 0)
    for uri in page.links:
        normalized_uri, _ = normalize_with_offsets(uri)
        uri_matches = _matches(normalized_uri)
        if uri_matches:
            for value, kind, _s, _e in uri_matches:
                if (kind, value) in in_text:
                    continue
                results.append(
                    (value, kind, occurrence("annotation", uri, opening.label, opening.heading))
                )
        elif ("url", uri.rstrip()) not in in_text:
            results.append(
                (uri.rstrip(), "url", occurrence("annotation", uri, opening.label, opening.heading))
            )

    # The running header and footer. Still extracted -- "found nothing" and
    # "did not look" must never be the same result -- but attributed to the page
    # rather than to a section, which is what stops MATES's header DOI arriving
    # as 19 occurrences competing with the paper's real findings.
    furniture, _ = normalize_with_offsets(page.furniture_text)
    for value, kind, start, end in _matches(furniture):
        results.append(
            (
                value,
                kind,
                occurrence("furniture", _context(furniture, start, end), "page_furniture", ""),
            )
        )

    return results


def _matches(text: str) -> list[tuple[str, str, int, int]]:
    """Run every pattern over text, suppressing less specific overlaps.

    Patterns are ordered specific-to-general, so a span already claimed by e.g.
    ``github`` is not re-reported by the ``url`` catch-all. Without this, every
    repository URL would appear twice under two different kinds.
    """
    claimed: list[tuple[int, int]] = []
    found: list[tuple[str, str, int, int]] = []

    for pattern in PATTERNS:
        for match in pattern.regex.finditer(text):
            start, end = match.span()
            if any(start < c_end and end > c_start for c_start, c_end in claimed):
                continue
            value = clean_value(match.group(0), pattern)
            if not value:
                continue
            claimed.append((start, end))
            found.append((value, pattern.kind, start, end))

    return found


def _context(text: str, start: int, end: int) -> str:
    """The surrounding sentence fragment, as the evidence quote for this hit."""
    left = max(0, start - CONTEXT_CHARS)
    right = min(len(text), end + CONTEXT_CHARS)
    snippet = text[left:right].replace("\n", " ")
    return " ".join(snippet.split())
