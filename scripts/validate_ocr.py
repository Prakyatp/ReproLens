#!/usr/bin/env python3
"""Measure the OCR backend against the PDF text layer.

    python scripts/validate_ocr.py data/papers/mates.pdf --pages 19,20,21

The problem this solves: validating OCR normally needs scanned documents with
known transcriptions, and we have none. A born-digital paper supplies both for
free. Rasterize it, OCR the images, and the text layer is the reference -- so
character error rate and, more importantly, accession agreement are both
measurable with zero annotation.

Accession agreement is the stricter test and the one that matters. A 2% CER
sounds tolerable until one digit flips in GSE212945 and the result is a
plausible, wrong, unverifiable accession.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from reprolens.discovery import links
from reprolens.documents.ocr import OcrBackend
from reprolens.documents.pdf_text import PdfTextBackend

IDENTIFIER_KINDS = ("geo_", "sra_", "bioproject", "biosample", "ena_", "github", "doi")


def levenshtein(a: str, b: str) -> int:
    """Edit distance with a rolling row; O(min(len)) memory."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def collapse(text: str) -> str:
    """Whitespace-insensitive comparison; the two channels wrap lines differently."""
    return re.sub(r"\s+", " ", text).strip()


def identifiers(pages: list) -> set[str]:
    return {f.value.upper() for f in links.extract(pages) if f.kind.startswith(IDENTIFIER_KINDS)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare OCR output to the PDF text layer.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", help="comma-separated 1-indexed pages for the CER sample")
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()

    reference = PdfTextBackend().read(args.pdf)
    sample = [int(n) for n in args.pages.split(",")] if args.pages else [p.page for p in reference]

    print(f"OCR at {args.dpi} dpi vs text layer: {args.pdf.name}\n")

    ocr_pages = OcrBackend(dpi=args.dpi).read(args.pdf, pages=sample)
    by_page = {p.page: p for p in reference}

    print(f"{'page':>5}  {'conf':>6}  {'CER':>7}  {'ref chars':>10}")
    total_distance = total_chars = 0
    for page in ocr_pages:
        truth = collapse(by_page[page.page].text)
        got = collapse(page.text)
        distance = levenshtein(truth, got)
        total_distance += distance
        total_chars += len(truth)
        cer = distance / len(truth) if truth else 0.0
        print(f"{page.page:>5}  {page.confidence:>6.3f}  {cer:>6.2%}  {len(truth):>10}")

    overall = total_distance / total_chars if total_chars else 0.0
    print(f"\n  CER over {len(ocr_pages)} page(s): {overall:.2%}")

    want = identifiers([by_page[n] for n in sample])
    got = identifiers(ocr_pages)
    print("\n  identifier agreement on the same pages")
    print(f"    text layer : {len(want)}")
    print(f"    via OCR    : {len(got)}")
    print(f"    recovered  : {len(want & got)}/{len(want)}")
    if want - got:
        print(f"    LOST       : {', '.join(sorted(want - got))}")
    if got - want:
        print(f"    INVENTED   : {', '.join(sorted(got - want))}")
        print("      (OCR digit confusion -- each is a plausible, wrong identifier)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
