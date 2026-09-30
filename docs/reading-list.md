# Reading List: Document/Figure/Table Extraction

Curated papers for learning how to pull structured information out of scientific
papers — text, layout, tables, figures/charts, and links — before building
ReproLens's own extraction pipeline (blueprint Phases 1–2).

Read roughly in group order (A → E); F is reference material, not a technique
to implement.

## Group A — Document structure & layout (read first)

1. **[DocLayNet](https://arxiv.org/abs/2206.01062)** — A Large Human-Annotated
   Dataset for Document-Layout Analysis. Defines what a "page object" even is
   (title, section header, table, figure, caption, footnote, etc.). Read this
   to understand *what* you're trying to detect before looking at any model.
2. **[LayoutLMv3](https://arxiv.org/abs/2204.08387)** — Pre-training for
   Document AI with Unified Text and Image Masking. The standard approach for
   jointly modeling text + layout + image in one transformer.

## Group B — Table extraction

3. **[PubTables-1M / Table Transformer](https://arxiv.org/abs/2110.00061)** —
   table detection + structure recognition (rows, columns, merged cells) at
   scale, sourced from scientific articles specifically. Maps to blueprint §11.

## Group C — OCR-free / VLM whole-document parsing

The modern, practical approach — what tools like Docling/MinerU are built on.

4. **[Donut](https://arxiv.org/abs/2111.15664)** — OCR-free Document
   Understanding Transformer. The original "skip OCR entirely, go straight
   from pixels to structured output" model.
5. **[Nougat](https://arxiv.org/abs/2308.13418)** — Neural Optical
   Understanding for Academic Documents. Donut's idea applied specifically to
   academic PDFs, including equations.
6. **[Docling Technical Report](https://arxiv.org/abs/2408.09869)** — combines
   DocLayNet-style layout detection + table structure recognition into one
   production pipeline. One of the two tools the blueprint names as a
   starting point (§28).
7. **[MinerU](https://arxiv.org/pdf/2409.18839)** (and newer
   **[MinerU2.5](https://arxiv.org/html/2509.22186v1)**) — a competing
   pipeline that decouples layout detection from content recognition. Good
   second reference implementation to compare against Docling.

## Group D — Figures & charts (VLM reasoning over images, not OCR)

8. **[MatCha](https://arxiv.org/abs/2212.09662)** — pretrains a VLM
   specifically to "derender" a chart back into its underlying data table.
   Maps to blueprint's Figure Understanding section (§12).
9. **[DePlot](https://github.com/google-research/google-research/blob/master/deplot/README.md)**
   — plot-to-table translation as a standalone step, meant to be chained into
   an LLM afterward for reasoning. Complements MatCha — "translate then
   reason" vs. "reason directly on pixels."

## Group E — Structured extraction from text (methods prose → JSON)

10. **[LLM4IE Survey](https://arxiv.org/abs/2312.17617)** — Large Language
    Models for Generative Information Extraction: A Survey. Broad taxonomy of
    schema-constrained extraction with LLMs; maps to blueprint §13. Skim for
    the extraction-paradigm taxonomy rather than reading cover to cover.

## Group F — Reference / context (not techniques to implement)

11. **[S2ORC](https://arxiv.org/abs/1911.02782)** — The Semantic Scholar Open
    Research Corpus. Shows what a fully-structured scientific corpus looks
    like once extraction is done: text linked to citations, figures, and
    tables as first-class objects. Good target schema to aim for.
12. **[GROBID](https://github.com/kermitt2/grobid)** (tool, not a paper) —
    the standard tool for the "links" part: DOIs, citations,
    author/affiliation metadata, reference-level structure from a PDF.
