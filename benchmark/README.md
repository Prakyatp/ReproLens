# ReproLens Benchmark (Golden Dataset)

Manually annotated ground truth for evaluating ReproLens's reproducibility-readiness
scoring against real outcomes, per the project blueprint (§25–26).

## Tiers

Not all annotations in this benchmark carry the same evidentiary weight, so each
record's `annotation_provenance.tier` says which kind it is:

- **Tier 1 — first-hand reproduction.** The annotator actually attempted the
  reproduction, over months, with a dated log of every attempt, dead end, and
  eventual outcome. This is the strongest possible ground truth: it captures not
  just "the paper doesn't say X" but "we spent N weeks discovering that X mattered
  and wasn't said." The two records currently in this benchmark (`locusmasterte.json`,
  `mates.json`) are Tier 1, sourced from a real lab worklog (Sep 2025–Jun 2026,
  RIT, Prof. Feng Cui's lab).
- **Tier 2 — cold-read annotation.** A researcher familiar with the domain reads
  the paper and its linked resources without attempting execution, and annotates
  based on what's documented vs. missing. Faster to produce, weaker ground truth
  (can miss blockers that only surface once you actually try). Future benchmark
  papers (the blueprint's target of 20–50) will mostly be Tier 2 unless a specific
  reproduction attempt is available.

## Schema

Each file in `papers/` is one annotated paper, with these top-level fields:

- `paper_id`, `title`, `github`, `citation`, `data_accessions` — identity/pointers.
- `annotation_provenance` — tier, annotators, source, duration.
- `resource_requirements` — data / code / environment / model_checkpoints / parameters,
  each with `required`, `available` (bool), and `evidence` (dated pointers into the
  source worklog, playing the role the blueprint's `bbox`/`page` provenance plays
  for a PDF — see §14).
- `blockers` — list of `{severity: hard|major|minor, description, evidence, resolved}`,
  per the severity classification in blueprint §22.
- `per_result_analysis` — claim/figure-level reproducibility attempts and outcomes,
  per blueprint §20.
- `scoring_rubric_v0.1` — the paper's readiness scored against the blueprint's
  7-category, 100-point rubric (§21), i.e. "how reproducible did this look before
  anyone tried."
- `verified_reproduction` — what actually happened when someone tried, with an
  `outcome` (`success` | `partial` | `failed`) and a `summary`. Kept separate from
  the readiness score per the Reproducibility Readiness vs. Verified Reproduction
  distinction in blueprint §5.
- `severity_summary` — blocker counts by severity, for the "2 blockers / 4 major
  issues / 5 minor issues" style output in blueprint §22.

## Why these two papers first

LocusMasterTE and MATES are both TE (transposable element) locus-quantification
methods the lab attempted to reproduce back-to-back on the same HCT116/GSE212945
data. Between them they exercise almost every blocker category the blueprint cares
about — an unreleased-but-load-bearing artifact (LocusMasterTE's exact TE-GTF),
undisclosed alignment/annotation parameters (MATES), an ambiguous validation-sample
description, and a circular-validation methodology trap that was independently
re-discovered twice. They're a good pair for calibrating the rubric and severity
classifier before expanding to a wider, mostly-Tier-2 benchmark set.

## Using this benchmark

Once ReproLens's scoring pipeline exists, run it against each paper (PDF/DOI +
linked GitHub repo + linked datasets) and compare its output to the corresponding
file here:

- Resource detection precision/recall against `resource_requirements`.
- Missing-resource detection precision/recall against `blockers`.
- Score agreement (Pearson/Spearman/MAE) between ReproLens's readiness score and
  `scoring_rubric_v0.1.total`.

This is deferred until the core pipeline (Phases 1–2 of the roadmap) exists —
see the main project blueprint.
