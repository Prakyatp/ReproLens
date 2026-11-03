"""Reading the same page twice, on purpose.

The text channel is a cascade: the PDF's own text layer runs first, and OCR
only fires on a page that came back empty. That answers "can this page be
read", and it leaves a different question untouched -- *is the text layer
telling the truth*. A text layer can be present, complete, and wrong. It
happens through font subsetting, bad encodings, and typographic ligatures, and
when it does, nothing downstream notices: a pattern simply fails to match and
the audit reports that the paper never said the thing.

So this module runs the two readers over the same page and compares them, the
way the image channel is compared against the text channel. Neither is treated
as authoritative, because neither is: on a born-digital page the text layer is
exact and OCR guesses, while on a page with a damaged text layer it is the
other way round. What the comparison produces is not a winner but a *flag* --
pages where the two accounts of the same ink disagree, and identifiers one
reader found that the other did not.

The cost is the reason this is opt-in rather than always on. Measured on MATES:
the text layer reads all 22 pages in 0.19 s and OCR takes 2.86 s per page, so
cross-checking a paper is roughly 340 times the cost of reading it. That buys
nothing on a clean born-digital PDF, where the disagreements are all OCR's own
errors. It is worth paying when a paper's findings look thin for its length, or
on a scanned or accepted-manuscript PDF where the text layer is suspect.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from reprolens.discovery.patterns import PATTERNS, normalize
from reprolens.documents.base import PageText

AGREE = "agree"
DIVERGE = "diverge"
OCR_FAILED = "ocr_failed"
TOO_SHORT = "too_short"

# Below this token overlap the two readers are not describing the same page.
# Set from the observed range rather than guessed: on a clean born-digital page
# the two agree in the high 0.8s or better, and OCR's own errors account for the
# remainder, so 0.6 leaves generous room before anything is called a divergence.
DIVERGENCE_THRESHOLD = 0.6

# A page with less text than this cannot produce a meaningful overlap -- a
# figure-only page with four words in it would swing wildly on one misread
# token -- so it is reported as unmeasured rather than as agreement.
MIN_TOKENS = 40

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.casefold()))


@dataclass(frozen=True, slots=True)
class PageAgreement:
    page: int
    verdict: str
    overlap: float | None
    text_tokens: int
    ocr_tokens: int
    confidence: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Divergence:
    """An identifier one reader saw and the other did not.

    The most actionable thing this comparison produces. An accession is a short
    run of letters and digits with no redundancy, so a single misread character
    yields a plausible, wrong, unverifiable identifier -- and whichever channel
    is wrong, the fact that they differ is what a reader needs to know.
    """

    value: str
    kind: str
    seen_by: str
    page: int

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class CrossCheck:
    attempted: bool = True
    pages: list[PageAgreement] = field(default_factory=list)
    divergences: list[Divergence] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def diverging(self) -> list[PageAgreement]:
        return [p for p in self.pages if p.verdict == DIVERGE]

    @property
    def measured(self) -> list[PageAgreement]:
        return [p for p in self.pages if p.overlap is not None]

    @property
    def agreement(self) -> float | None:
        """Mean overlap across the pages where it could be measured.

        ``None`` rather than zero when nothing was measurable, for the same
        reason the rubric distinguishes a floor of zero from an unassessed
        criterion: no measurement is not a bad measurement.
        """
        measured = self.measured
        if not measured:
            return None
        return sum(p.overlap for p in measured) / len(measured)

    def to_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "summary": {
                "pages_compared": len(self.pages),
                "pages_measured": len(self.measured),
                "pages_diverging": len(self.diverging),
                "mean_overlap": self.agreement,
                "identifier_divergences": len(self.divergences),
            },
            "notes": self.notes,
            "pages": [p.as_dict() for p in self.pages],
            "divergences": [d.as_dict() for d in self.divergences],
        }


def compare(text_pages: list[PageText], ocr_pages: list[PageText]) -> CrossCheck:
    """Agreement between the text layer and OCR, page by page."""
    result = CrossCheck()
    by_number = {p.page: p for p in ocr_pages}

    for page in text_pages:
        other = by_number.get(page.page)
        mine = _tokens(normalize(page.text))
        if other is None:
            result.pages.append(PageAgreement(page.page, OCR_FAILED, None, len(mine), 0))
            continue

        theirs = _tokens(normalize(other.text))
        if len(mine) < MIN_TOKENS and len(theirs) < MIN_TOKENS:
            result.pages.append(
                PageAgreement(page.page, TOO_SHORT, None, len(mine), len(theirs), other.confidence)
            )
            continue

        union = mine | theirs
        overlap = len(mine & theirs) / len(union) if union else 0.0
        result.pages.append(
            PageAgreement(
                page.page,
                AGREE if overlap >= DIVERGENCE_THRESHOLD else DIVERGE,
                round(overlap, 3),
                len(mine),
                len(theirs),
                other.confidence,
            )
        )
        result.divergences.extend(_identifier_divergences(page, other))

    result.notes.extend(_notes(result))
    return result


def _identifier_divergences(text_page: PageText, ocr_page: PageText) -> list[Divergence]:
    """Identifiers one reader matched on this page and the other did not."""
    mine = _identifiers(text_page.text)
    theirs = _identifiers(ocr_page.text)
    out: list[Divergence] = []
    for kind, value in sorted(mine - theirs):
        out.append(Divergence(value, kind, "text layer only", text_page.page))
    for kind, value in sorted(theirs - mine):
        out.append(Divergence(value, kind, "OCR only", text_page.page))
    return out


def _identifiers(text: str) -> set[tuple[str, str]]:
    normalized = normalize(text)
    found: set[tuple[str, str]] = set()
    for pattern in PATTERNS:
        # The catch-all URL pattern is excluded: a URL differing by one
        # character between readers is near-certain on every page and would
        # bury the identifiers that matter.
        if pattern.kind == "url":
            continue
        for match in pattern.regex.finditer(normalized):
            found.add((pattern.kind, match.group(0).upper()))
    return found


def _notes(result: CrossCheck) -> list[str]:
    notes: list[str] = []
    if not result.pages:
        return notes

    diverging = result.diverging
    if diverging:
        notes.append(
            f"the text layer and OCR disagree about {len(diverging)} page(s) "
            f"({', '.join(str(p.page) for p in diverging[:6])}); on those pages one of the "
            f"two readings is wrong and this comparison cannot say which"
        )
    failed = [p for p in result.pages if p.verdict == OCR_FAILED]
    if failed:
        notes.append(f"OCR produced nothing for {len(failed)} page(s), so they were not compared")
    if result.divergences:
        sample = ", ".join(f"{d.value} ({d.seen_by})" for d in result.divergences[:4])
        notes.append(
            f"{len(result.divergences)} identifier(s) were matched by only one of the two "
            f"readers: {sample}. An accession has no redundancy, so a single misread "
            f"character yields a plausible, wrong identifier."
        )
    if (mean := result.agreement) is not None:
        notes.append(
            f"text layer and OCR agree on {mean:.0%} of tokens across "
            f"{len(result.measured)} measured page(s)."
        )
    return notes
