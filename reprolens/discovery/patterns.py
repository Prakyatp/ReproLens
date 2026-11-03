"""Identifier patterns for scientific resources, plus the text normalization
that has to happen before any of them are applied.

The normalization is not cosmetic. Journal PDFs hyphenate across line breaks,
use non-breaking spaces and Unicode dashes, and occasionally typeset an
accession with a space in it ("GSE 212945"). Matching raw extracted text misses
real identifiers for all four reasons.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Trailing characters a greedy DOI/URL match tends to swallow from prose.
_TRAILING_JUNK = ".,;:)]}>'\"’”"


@dataclass(frozen=True, slots=True)
class Pattern:
    kind: str
    regex: re.Pattern[str]
    uppercase: bool = False  # accessions are conventionally uppercase
    strip_inner_space: bool = False  # "GSE 212945" -> "GSE212945"
    strip_trailing: bool = False  # drop sentence punctuation a greedy match ate


_INVISIBLE = ("­", "﻿")  # soft hyphen, BOM
_HYPHENS = "-‐‑‒–—−"  # ASCII hyphen plus Unicode dashes


# Typographic ligatures, which a PDF text layer hands back as single
# characters. MATES carries 514 of U+FB01 and 42 of U+FB02, so the word
# "quantification" appears in its normalized text zero times while
# "quantifiﬁcation" appears 177 times, and every pattern or vocabulary term
# containing "fi", "fl" or "ff" silently fails to match. Nothing announces it:
# the extractor reports that the paper simply never mentioned Nextflow.
#
# Expanded from an explicit table rather than by unicodedata.normalize with
# NFKC, which would fix these and also rewrite superscripts into digits. These
# papers are full of superscript reference markers, and turning one into a
# digit beside an accession is a worse bug than the one being fixed.
_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}


def normalize(text: str) -> str:
    """Make extracted text safe to run patterns over."""
    return normalize_with_offsets(text)[0]


def normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    """Normalized text, plus the source index of each character it kept.

    The offsets exist because normalization is not length-preserving: removing a
    soft hyphen drops one character and dehyphenating a line break drops two or
    more. Match positions are therefore positions in the *normalized* string,
    and section boundaries are positions in the original, so one has to be
    translated into the other. Without the map, every finding after the first
    dehyphenation on a page is attributed from a slightly wrong offset -- which
    is invisible until a drifting offset crosses a section boundary and silently
    files a reference-list DOI under Data availability.

    Order matches the single-pass version this replaced: strip invisibles, fold
    dashes to ASCII, then rejoin hyphenated line breaks. Ligatures expand in
    the same pass, and are the one step that makes the string *longer* --
    which the offsets absorb because each expanded character records the
    index of the single source character it came from.
    """
    kept: list[str] = []
    offsets: list[int] = []
    index = 0
    length = len(text)

    while index < length:
        character = text[index]

        if character in _INVISIBLE:
            index += 1
            continue

        if character in _HYPHENS:
            after = index + 1
            if after < length and text[after] == "\n":
                after += 1
                while after < length and text[after] in " \t":
                    after += 1
                index = after  # dehyphenated: the break and its indent go away
                continue
            kept.append("-")
            offsets.append(index)
            index += 1
            continue

        if (expansion := _LIGATURES.get(character)) is not None:
            # Each character of the expansion records the index of the single
            # source character it came from, so an offset taken from the
            # normalized string still lands on the ligature in the original.
            for letter in expansion:
                kept.append(letter)
                offsets.append(index)
            index += 1
            continue

        kept.append(" " if character == " " else character)
        offsets.append(index)
        index += 1

    return "".join(kept), offsets


# Space-tolerant accession bodies: a single optional space or newline after the
# prefix, which is how typesetting splits them.
_S = r"[ \t\n]?"

PATTERNS: tuple[Pattern, ...] = (
    # --- sequence / expression archives -------------------------------------
    Pattern("geo_series", re.compile(rf"\bGSE{_S}\d{{4,7}}\b"), True, True),
    Pattern("geo_sample", re.compile(rf"\bGSM{_S}\d{{5,8}}\b"), True, True),
    Pattern("geo_platform", re.compile(rf"\bGPL{_S}\d{{3,6}}\b"), True, True),
    Pattern("sra_run", re.compile(rf"\bSRR{_S}\d{{6,9}}\b"), True, True),
    Pattern("sra_experiment", re.compile(rf"\bSRX{_S}\d{{6,9}}\b"), True, True),
    Pattern("sra_study", re.compile(rf"\bSRP{_S}\d{{6,9}}\b"), True, True),
    Pattern("bioproject", re.compile(rf"\bPRJ(?:NA|EB|DB){_S}\d{{5,9}}\b"), True, True),
    Pattern("biosample", re.compile(rf"\bSAMN{_S}\d{{8}}\b"), True, True),
    Pattern("ena_run", re.compile(rf"\bERR{_S}\d{{6,9}}\b"), True, True),
    Pattern("ena_study", re.compile(rf"\bERP{_S}\d{{6,9}}\b"), True, True),
    Pattern("dbgap", re.compile(rf"\bphs{_S}\d{{6}}\b"), True, True),
    # --- repositories and archives ------------------------------------------
    Pattern("github", re.compile(r"\bgithub\.com/[\w.-]+/[\w.-]+"), strip_trailing=True),
    Pattern("gitlab", re.compile(r"\bgitlab\.com/[\w.-]+/[\w.-]+"), strip_trailing=True),
    Pattern(
        "zenodo",
        re.compile(r"\b(?:zenodo\.org/record(?:s)?/\d+|10\.5281/zenodo\.\d+)"),
        strip_trailing=True,
    ),
    Pattern("figshare", re.compile(r"\bfigshare\.com/[^\s]+"), strip_trailing=True),
    Pattern(
        "dryad",
        re.compile(r"\b(?:datadryad\.org/[^\s]+|10\.5061/dryad\.[\w.]+)"),
        strip_trailing=True,
    ),
    # --- literature identifiers ---------------------------------------------
    # Both host forms. NCBI moved PubMed to its own subdomain, but publishers
    # still print the legacy path form: PLOS gives every reference a
    # "www.ncbi.nlm.nih.gov/pubmed/15229602" link, and matching only the modern
    # form sent 49 of ASPEN's citations through the url catch-all, where they
    # arrived as unclassified resources competing with its real findings.
    Pattern(
        "pubmed",
        re.compile(r"\b(?:pubmed\.ncbi\.nlm\.nih\.gov/|ncbi\.nlm\.nih\.gov/pubmed/)\d+"),
        strip_trailing=True,
    ),
    Pattern("pmc", re.compile(r"\bncbi\.nlm\.nih\.gov/pmc/articles/PMC\d+"), strip_trailing=True),
    Pattern("arxiv", re.compile(r"\barXiv:\s?\d{4}\.\d{4,5}(?:v\d+)?\b"), strip_inner_space=True),
    Pattern("doi", re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+"), strip_trailing=True),
    # --- catch-all, deliberately last ---------------------------------------
    Pattern("url", re.compile(r"\bhttps?://[^\s<>\"]+"), strip_trailing=True),
)


def clean_value(raw: str, pattern: Pattern) -> str:
    """Apply a pattern's own normalization to one matched string."""
    value = raw
    if pattern.strip_inner_space:
        value = re.sub(r"[\s]+", "", value)
    if pattern.strip_trailing:
        value = value.rstrip(_TRAILING_JUNK)
        if pattern.kind in {"github", "gitlab"}:
            value = value.removesuffix(".git").rstrip("/")
    if pattern.uppercase:
        value = value.upper()
    return value
