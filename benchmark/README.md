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

## Adding a paper

The two Tier-1 records took five months each and cannot be the model for the
remaining eighteen. A Tier-2 record is about an hour: read the paper and its
repository, fill in what is documented and what is missing, and score it.

```bash
cp benchmark/tier2-template.json benchmark/papers/<paper_id>.json
# edit it -- paper_id MUST equal the filename without .json

uv run python check.py --validate-only      # before there is anything to grade
uv run python audit.py data/papers/<paper_id>.pdf --out output/
uv run python check.py --out output/
```

`--validate-only` is the step that makes this cheap. A record can be perfectly
well-formed JSON and still be wrong in ways that produce a *normal-looking*
grading run against the wrong thing, so the validator runs on every invocation
and the flag exists to check a record before any app output exists. What it
catches:

- **`severity` written in the app's vocabulary.** The app's issues carry
  `hard_blocker` and `report.md` prints that phrase, so writing it into a record
  is the natural mistake — and `blockers_side_by_side` filters on `hard`, so the
  blocker silently vanishes from the comparison it exists to drive. A record says
  `hard` / `major` / `minor`.
- **`severity_summary` counts that no longer match the `blockers` list** — the
  likeliest edit of all, a blocker added and the summary above it left alone.
- **`scoring_rubric_v0.1.total` not equal to its own seven parts**, or a criterion
  above its weight. `total` is what the app's band is graded against, so a total
  that does not add up makes every criterion row unfalsifiable.
- `paper_id` disagreeing with the filename, an empty pointer field, a tier that
  is neither 1 nor 2, a misspelled criterion name, `readiness_score` disagreeing
  with `total`.

Scoring is a judgement and the validator does not touch it. Score what the paper
**documents**, before anyone tries to run it — that is the
reproducibility-*readiness* question, kept separate from what happens when
someone actually tries (blueprint §5). The weights come from `WEIGHTS` in
`reprolens/scoring/rubric.py`, so they cannot drift from the app's.

### Which fields a Tier-2 record needs

Required: `paper_id`, `title`, `citation`, `github`, `data_accessions`,
`annotation_provenance.tier`, `severity_summary`, `scoring_rubric_v0.1`.

Optional, and mostly Tier-1 territory: `resource_requirements`,
`per_result_analysis`, `verified_reproduction`, `methodological_risks`, and
per-blocker `evidence`. A cold read cannot honestly fill
`verified_reproduction` — leave it out rather than guess.

## What the grader measures

- Resource detection recall against `data_accessions` and `github`.
- Hard blockers, printed side by side rather than scored: whether "annotation.gtf
  is present only at demo scale" is the same finding as "the exact TE annotation
  GTF was never released" is a judgement about meaning, and automating it would
  turn a readable comparison into a number whose basis no one can check.
- Per-criterion agreement between the app's floor–ceiling band and
  `scoring_rubric_v0.1`, plus severity counts.
