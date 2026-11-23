#!/usr/bin/env python3
"""Run two vision backends over the same figures and diff their readings.

    python scripts/compare_vlm.py data/papers/mates.pdf --a ollama --b anthropic

The image channel has no self-check: unlike a regex match, a model's reading of
a picture cannot be confirmed against the document. Two things can be measured
instead, and this script measures both:

* **corroboration** -- how much of what a model reports the paper's own text
  also contains. High corroboration with low yield means the model is reading
  only what was already available elsewhere; uncorroborated output is where its
  errors concentrate.
* **agreement** -- what two independent models say about the same image. A value
  both produce is unlikely to be either one's invention; a value only one
  produces needs a human.

Run with a single backend (``--a`` alone) to get corroboration only, which is
what is available before a second model is configured.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reprolens.documents.figures import extract
from reprolens.documents.pdf_text import PdfTextBackend
from reprolens.extraction import vlm
from reprolens.extraction.schema import FigureContents
from reprolens.llm.cache import ResponseCache

LIST_FIELDS = [
    name
    for name, field in FigureContents.model_fields.items()
    if getattr(field.annotation, "__origin__", None) is list
]


def values(contents: FigureContents) -> set[str]:
    out: set[str] = set()
    for field in LIST_FIELDS:
        for value in getattr(contents, field):
            out.add(f"{field}:{' '.join(value.split()).lower()}")
    return out


def read_all(figures: list, backend_name: str, model: str | None, cache: ResponseCache) -> dict:
    backend = vlm.get_backend(backend_name, model)
    readings = {}
    for figure in figures:
        print(f"    {backend.model} <- {figure.figure_id}", flush=True)
        readings[figure.figure_id] = vlm.read_figure(figure, backend, cache)
    return readings


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare vision backends on a paper's figures.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--a", default="ollama", help="first backend")
    parser.add_argument("--a-model")
    parser.add_argument("--b", help="second backend (omit for corroboration only)")
    parser.add_argument("--b-model")
    parser.add_argument("--out", type=Path, default=Path("output"))
    args = parser.parse_args()

    paper_id = args.pdf.stem
    figures = extract(args.pdf, args.out / paper_id / "figures")
    document_text = "\n".join(p.text for p in PdfTextBackend().read(args.pdf))
    cache = ResponseCache()

    print(f"{len(figures)} figures from {paper_id}\n")
    print(f"  reading with {args.a}")
    a_readings = read_all(figures, args.a, args.a_model, cache)

    b_readings = None
    if args.b:
        print(f"\n  reading with {args.b}")
        b_readings = read_all(figures, args.b, args.b_model, cache)

    header = f"\n{'figure':<18} {'type':<10} {'values':>7} {'corrob':>7}"
    if b_readings:
        header += f" {'shared':>7} {'only-a':>7} {'only-b':>7}"
    print(header)
    print("-" * len(header))

    totals = dict.fromkeys(("values", "corroborated", "shared", "only_a", "only_b"), 0)
    for figure in figures:
        a = a_readings[figure.figure_id]
        corroborated, _unverified = vlm.corroborate(a, document_text)
        a_values = values(a)
        row = (
            f"{figure.label or figure.figure_id:<18} {a.figure_type:<10} "
            f"{len(a_values):>7} {len(corroborated):>7}"
        )
        totals["values"] += len(a_values)
        totals["corroborated"] += len(corroborated)

        if b_readings:
            b_values = values(b_readings[figure.figure_id])
            row += (
                f" {len(a_values & b_values):>7} {len(a_values - b_values):>7} "
                f"{len(b_values - a_values):>7}"
            )
            totals["shared"] += len(a_values & b_values)
            totals["only_a"] += len(a_values - b_values)
            totals["only_b"] += len(b_values - a_values)
        print(row)

    print(f"\n  values reported by {args.a}: {totals['values']}")
    print(f"  of which the paper's text also contains: {totals['corroborated']}")
    if b_readings:
        print(f"\n  agreed by both models : {totals['shared']}")
        print(f"  {args.a} only           : {totals['only_a']}")
        print(f"  {args.b} only           : {totals['only_b']}")
        print("\n  Values from one model only are not errors -- they are the set a human")
        print("  has to adjudicate, and the number worth driving down.")

    cache.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
