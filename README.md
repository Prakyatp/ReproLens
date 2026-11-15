# ReproLens

AI-assisted scientific reproducibility auditor — analyzes a scientific paper and its surrounding ecosystem (supplements, code repositories, datasets, checkpoints) to estimate how ready the work is for independent reproduction, with evidence-grounded findings.

See [`ReproLens_Project_Blueprint.md`](./ReproLens_Project_Blueprint.md) for the full project plan, architecture, roadmap, and study notes.

## Status

Step 6 of the build, and the MVP is complete. Resources come out of a paper
(step 1), get labelled by section and role (step 2), the checklist reports
whether each named tool is pinned down (step 3), the rubric turns that into a
scored band with a severity list (step 4), the repositories the paper points at
are cloned and read (step 5), and `report.md` arranges all of it for a reader
(step 6). Step 7 ran the whole thing against a paper it was not built on and
fixed what broke.

```bash
uv run python audit.py data/papers/mates.pdf --out output/
# -> output/mates/report.md     the thing to read
#    output/mates/links.json    every finding, with provenance
#    output/mates/repo.json     the repository channel's reading
#    output/mates/{checklist,assessment}.json
#    output/mates/figures/
```

```bash
uv run streamlit run ui.py          # the same audit, read by a person
```

## The product

```bash
ollama serve &                 # the figure channel reads through a local model
uv run streamlit run ui.py
```

One page. Drop a paper in the middle of it; the audit runs; the result comes
out. There is no paper library and no sidebar: the five papers this project was
developed against are a verification set, not furniture for the product.

Nothing is kept. The upload and its audit live in a temporary directory for the
length of the session and are deleted when another paper is dropped, so the
page carries no state from the last visitor. The upload goes into an empty
directory of its own and is passed to `audit.py` by path; nothing in it, or in
any repository it points at, is ever executed. Figures are read by a model
served locally by Ollama (`qwen2.5vl:7b`), so a dropped manuscript is not sent
anywhere to be read; `REPROLENS_VLM=anthropic` switches that to the API, which
does send the figure images off this machine.

The page states the condition of every channel above the result — text,
figures, repositories, archives — whether each one ran or not. This is not
decoration. The figure channel was once switched off here behind a hardcoded
`--no-vlm`, and because nothing said so, every paper dropped on the page was
scored as though its figures were empty. A channel that did not run and a
channel that found nothing are indistinguishable unless the page distinguishes
them, which is the same mistake this tool exists to catch papers making.

The result is the score band, then two panels — **what is not available** and
**what is**. Every row in either carries the link *the paper itself gave* and
the place in the paper that named it: page, section, and the sentence verbatim.

Whose link it is matters, and is the one thing this panel has to get right. A
GEO landing page looks identical whether the paper printed it or this tool
built it from the accession, so the two are only distinguishable if the page
says which:

- **the paper's own link** — read out of the text beside the identifier. MATES's
  Data availability statement writes `(GSE212945, https://www.ncbi.nlm.nih.gov/
  geo/query/acc.cgi?acc=GSE212945)` for 5 of its 10 accessions.
- **no link** — stated plainly. ASPEN, LocusMasterTE and the other half of MATES
  name an accession and leave the reader to find it.
- **a constructed lookup** — offered beside it, labelled "built from the
  identifier, not a link the paper gave".

That middle case is why accession links are read from the surrounding text
rather than from the `url` findings: the accession pattern claims the span
first, so none of MATES's five GEO URLs survives as a separate `url` finding.
Comparing the accession list against the url list reports that no paper links
anything — which is what I concluded the first time, and it was wrong.

Archive lookups run, because a page whose job is to say what is *not available*
cannot make that claim without asking the archive. Figure reading does not: it
needs a vision backend that may not be running, and a missing backend should
not fail an audit.

The page extracts nothing itself — every number on it came out of a JSON file
`audit.py` wrote. It is tested by being run: `tests/test_ui.py` drives both
states through Streamlit's `AppTest`, because an early version returned HTTP
200 in a browser while raising `TypeError: unhashable type: 'slice'` on every
paper. A live server answering 200 would never have shown that.

`.streamlit/config.toml` binds it to `localhost`. Streamlit's default listens
on every interface and prints an "External URL" on the machine's public
address, which would put a paper's audit — and any unpublished data named in it
— on whatever network the laptop is attached to.

## Two commands, kept apart

```bash
uv run python audit.py data/papers/mates.pdf --out output/   # the app
uv run python check.py --out output/                         # the grader
```

`audit.py` is the product and never reads `benchmark/`. The ground-truth records
there state their findings in prose — `mates.json` says "RepeatMasker and
GENCODE versions were never specified", which is exactly the conclusion the app
is meant to reach unaided — so if that text reached the app's input, every score
measured afterwards would be meaningless and nothing would visibly break.
`check.py` is the only module allowed to read it, enforced by
`tests/test_no_benchmark_leak.py`.

## Three channels, not a ladder

| | channel | runs | gets you |
|---|---|---|---|
| text | PDF text layer (`pdf_text`), or JATS XML | always, first | body text + embedded hyperlinks |
| text | OCR (`ocr`) | only for pages with no text layer | text from scanned pages |
| image | VLM over figures | **always, independently** | data that exists only inside pictures |
| code | the paper's own repositories, cloned | always, independently | what the code does, versus what the paper says it does |

The text backends are a cascade competing for one job. The VLM is not a fallback:
a born-digital paper never needs OCR but still has pipeline diagrams and panel
labels no text extractor can reach. Nor is the code channel: three of the
rubric's seven criteria are questions about code, and the paper is not the
document that answers them.

An unreadable page is reported as unreadable, never as empty. For a tool whose
purpose is detecting what a paper failed to provide, conflating "found nothing"
with "could not read it" is the worst available bug.

### Two kinds of superscript

The text layer is read span by span, because `get_text("text")` glues a raised
reference number onto the token before it — MATES p20 turns
`github.com/mcgilldinglab/MATES` + raised `90` into `.../MATES90`. Dropping
every digit-shaped superscript fixes that and causes a worse problem, because
the other thing a raised digit means is a power:

| | before | after |
| --- | --- | --- |
| ASPEN p2 | `p < 2.22 × 10` | `p < 2.22 × 10^-16` |
| MATES p4 | `P < 1 × 10` | `P < 1 × 10^-6` |
| ALIGNN p21 | `weight decay of 10` | `weight decay of 10^-5` |

**57 of MATES's 57 scientific-notation numbers were being printed with the
exponent deleted**, and every one of them was a p-value. The values stayed
plausible, which is what made it silent.

Three signals separate the two, and between them they classify all 65
superscript-after-a-digit occurrences in the three PDFs correctly: a power this
module has already opened and not yet filled (publishers split `10⁻⁶` into two
raised spans), a leading sign with digits after it (the only thing that
identifies an exponent on a unit, `Vm⁻²`, where what precedes is a letter), and
otherwise what the superscript is attached to — a power hangs off a number that
no letter opens, a reference number hangs off a name. A name ending in a digit
is what makes the simple rule fail: `QM9⁴⁶`, `CD74³⁷` and `Aldh18a1⁵⁷` are
citations. `CD8⁺` is neither — a bare sign on a name stays the phenotype it is.

Two occurrences in ASPEN are set as Unicode superscript glyphs in an unraised
span (`10⁻⁸`) rather than as raised spans. Nothing is lost there; they are just
not normalised to the `^` form.

## Sections, then roles

An identifier tells you the kind of thing it is; it does not tell you what it is
for. Without that distinction the output is unreadable: 79% of what the extractor
found on LocusMasterTE is its reference list, which is not wrong and not noise,
but a DOI cited there means nothing like `GSE225377` in the Data availability
statement.

Each finding therefore carries the section it was found in and a role, with the
evidence for it:

```
own_data               a dataset this paper deposited
external_data          a dataset from elsewhere that the work depends on
analysis_code          code or scripts for this paper's analysis
software_dependency    a tool the method uses
reference_resource     a genome build or annotation track
cited_literature       a paper
publisher_boilerplate  journal, licence, ORCID, running header
unclassified           said plainly, rather than guessed at
```

Every role records whether it came from the paper (`stated`) or from us
(`inferred`), and quotes what decided it.

**Headings are found by typography, not by keyword.** Matching heading words
against the start of a line finds MATES's 7 real headings and 10 body lines that
merely begin "methods," or "Supplementary Fig. S5". Font size separates them; the
bold *flag* does not, because Nature sets headings in a different face and leaves
that flag clear. A section is a character offset, not a page: MATES page 20
carries Data availability, Code availability and References between them.

**Appearing in a Data availability statement does not mean the data is the
paper's own.** Every one of the six GEO accessions in MATES's statement belongs
to another study — "as detailed in Shiau et al.", "published by Zhu et al." —
so MATES deposited nothing, and a rule keyed on the section alone records the
exact opposite. LocusMasterTE's statement holds both kinds in one paragraph, so
the deposit-or-reuse cue nearest the identifier decides, scoped to its own
sentence. Where no cue is near enough, the role is `unclassified`; guessing
`own_data` moves the blame for a missing resource onto the wrong party.

## The checklist: named is not specified

Finding "RepeatMasker" in a methods section is easy and nearly useless. The
reportable fact is that it is named and never versioned, which is the gap the
lab actually hit on both papers.

The obvious implementation gets this backwards. Across both benchmark papers
there are three version strings in total — `v2.8.2`, `version 0.17`,
`version 42` — against 25 or so distinct tools named between them. A detector
that keys on version tokens therefore finds the few tools that are already
documented and misses every one that is not, reporting a paper as well specified
in exactly the case where it is worst. So names are matched independently of any
version, and the version is checked for afterwards.

Each named tool comes out as `pinned`, `deferred_to_citation` or `named_only`. A
genome assembly is recorded but never accepted as a version: "created using
RepeatMasker for GRCh38" fixes the coordinate system and not the annotation
track, and that sentence is LocusMasterTE's hard blocker verbatim.

Two gap classes exist and only one is visible from the text. A tool named
without a version is detectable. A resource the method requires and the paper
never mentions is not — MATES needs a gene annotation and the string "GENCODE"
appears nowhere in it. The grader reports those separately as
`not-in-paper` rather than counting them against recall, because no reading of
the paper recovers them.

## Scoring: a band, not a number

Blueprint §21 says the score must not be invented by a model, so nothing here
asks one. Every point traces to a finding or a checklist entry.

Two rules shape it.

**A paper loses points for what it did not say, never for what this tool could
not determine.** Deducting a point because the classifier was unsure reads,
downstream, as the paper having failed to state something, and those are not the
same claim. So each criterion reports a floor and a ceiling: the floor is what
the evidence proves, the ceiling adds back what the evidence cannot settle.

**An unread channel is never scored as an empty one.** With no repository
fetched, method completeness, execution instructions and result traceability are
reported as not assessed and the total is quoted out of 65; with one, all seven
are scored out of 100. Which document a criterion is scored from follows from
where the evidence lives — data availability is a paper question, environment
specification is a repository one — and where both can speak, the better
evidence wins, because a reader needs one sufficient specification rather than
two.

Against the two hand-scored records, 6 of 7 criteria agree on each paper, and
the hard-blocker counts match. The two disagreements are the informative part:

- *MATES parameters, app 3–6 against 2.* One point, on a ten-point criterion.
- *LocusMasterTE traceability, app 8 against 3.* The repository names `fig1.R`,
  `fig3.R`, `fig4.R` and `fig5.R` for five published figures, so the mapping
  really is there for four of them. The hand-assigned 3 reflects that those
  scripts could not be run, which this rubric charges to parameters and
  environment, where it already cost points. Blueprint §5 separates
  reproducibility readiness from verified reproduction, and the benchmark
  records score the two independently — so the sub-scores are not independent of
  each other, and that is worth knowing about the rubric.

Severity still diverges, by design. The rubric reports every unversioned tool as
a major issue per §22's own taxonomy — 17 for MATES against the 3 the annotators
recorded — because whether a gap blocks you is not visible from the paper.
Ranking by how load-bearing a tool is would need evidence this does not gather.

## The repository channel

```bash
uv run python audit.py data/papers/mates.pdf --out output/   # clones as needed
uv run python audit.py data/papers/mates.pdf --no-repo       # cache only, offline
```

Which repositories get cloned is decided by the role classifier, not by the
pattern that matched: a paper cites the repository of every tool it uses, and
cloning those would audit the field rather than the paper. Clones are cached
under `data/repos/` (gitignored) and reused at the commit recorded in
`repo.json`, so re-running an audit a week later does not quietly change the
findings. **Nothing in a checkout is ever executed** — Python is read through
`ast`, which evaluates nothing, and everything else as text.

A paper's repositories are analysed together, not one at a time. LocusMasterTE
publishes the method in one and the figure scripts in another, so judging either
alone gets it wrong twice: the method looks untraceable and the figures look
unrunnable.

Almost every useful finding here is a *disagreement*, which is what a reader of
either document alone cannot see:

| finding | the two benchmark repositories |
|---|---|
| two manifests pinning one package differently (§16) | MATES asks for `torch==2.0.1` in `requirements.txt` and `torch==2.0.0` in `setup.py` |
| a required input present only at demo scale | `run_sample.sh` takes `annotation.gtf`; the repository ships 20 records |
| a published figure with no generating code (§2) | scripts exist for figures 1, 3, 4 and 5 of LocusMasterTE's five |
| a step the code runs and the paper never names (§16) | `long_read_wrapper.sh` runs Pychopper; the string appears nowhere in the paper |
| a language used with nothing declaring it | 5 R files, 14 `library()` calls, no `DESCRIPTION`, no `renv.lock`, no R version |
| an import no manifest declares | LocusMasterTE imports `HTSeq` and declares it nowhere |

Pinning is counted per distinct package, not per declaration. LocusMasterTE asks
for `numpy>=1.16.3` in `setup.py` and `numpy=1.16.3` in its README; that is one
dependency with a resolvable version, not one good declaration and one bad one.
Counting declarations measures how many times the authors wrote a name down.

## Generalisation: the third paper

The pipeline was built against two papers, and 78 places in the app are
justified by one of them. No measurement taken on those two can say which of the
78 generalise, so before scaling the benchmark the whole thing was run against
**ASPEN** (PLOS Computational Biology, CC BY) — a different lab, a different
publisher, an R package plus a separate manuscript repository.

What held: accession recall **6/6** on both the XML and the PDF path; the section
outline correct on a third publisher; a version format neither benchmark paper
uses (`scater (v1.28.0)`) read correctly.

What broke, and what the fixes were:

| broke | fix | effect on ASPEN |
|---|---|---|
| `efetch` wraps the article in `<pmc-articleset>`; the backend assumed a bare `<article>` and returned **0 segments silently** | tolerate the wrapper, plus `base.is_readable` so an unread document makes every criterion *unassessed* rather than zero | 0 → 7 segments; an unreadable file now says so instead of scoring |
| `"Availability of data and materials"` is **body-size bold**, so the size-only heading rule missed it | admit weight alongside size, requiring the whole line to be bold | `data_availability` 8 → **20/20**, `code_availability` 0 → **13/20**, repos cloned, all 7 criteria assessed |
| 5 of 8 tools the paper names were outside the vocabulary, all Bioconductor, all pinned | added them, and recorded the measured ceiling | **8 of 14** tools pinned, was 3 of 11 |
| legacy PubMed URL form unmatched | one pattern covering both host forms | **0** unclassified findings, was 49 |

A fifth gap the probe opened, and then closed: ASPEN scored
`execution_instructions` **0 of 10** because an R package has no shell script
and no `console_scripts`, so the execution reader found no entry point. An R
package declares its public surface in `NAMESPACE` and shows how to call it in
the README, so the reader now reads both — 20 exported functions, the
`devtools::install_github` line, and the Quick start's calls. R named arguments
are read the same way as shell flags, because they are the same evidence: six
of ASPEN's parameters (`min_cells = 5`, `delta_set = 50`, `thetaFilter = 0.001`)
were written down with values and the app saw none of them.

Readiness went from **13–23 of 65** to **72–80 of 100**, and the benchmark papers
did not move: 6-of-7 criterion agreement and 100% recall on both, before and
after every fix.

The assumption this overturned is worth stating plainly. The project had
established that bold flags are useless for finding headings, because all eleven
MATES headings have the flag clear — true of Nature's subset-embedded fonts and
wrong in general:

```
MATES   p20  size=10.71  flag_bold=False  AdvOT3d287b35.B  'Data availability'
ASPEN   p19  size=10.00  flag_bold=True   ArialMTStd-Bold  'Availability of data and materials'
ASPEN   p23  size=11.00  flag_bold=True   ArialMTStd-Bold  'Acknowledgments'
```

Size stays primary because some publishers offer nothing else; weight is a real
signal where it exists. Neither alone generalises.

A value that is a bare identifier is recorded as *absent*, not as a value:
`min_cells = 5` documents a parameter, while `genes.excl = genes2remove`
documents only that one is passed. Same rule as a shell flag whose value is
`$VAR`.

Still open from the probe: an R call that spans several lines is read only as
far as its first line, so parameters on continuation lines are missed.

The vocabulary ceiling has since been measured on two materials-science
papers, and it was the whole story: ALIGNN named **1** tool and Atomate2 **1**,
against ASPEN's 16. Both were scored for environment specification and
parameters as though they had declared almost nothing. Adding 45 materials
names — mined from the two papers' text rather than recalled — takes them to 15
and 31, and the two annotated biology papers do not move at all.

Three of the names could not simply be added, and measuring said so:

| name | why it was dropped |
| --- | --- |
| `GAP` | a Gaussian Approximation Potential, and also *band gap* — 5 hits in ALIGNN, 14 in Atomate2 |
| `SCAN` | also an exchange-correlation functional, and an English verb |
| `MP` | also an author's initials in LocusMasterTE's reference list |
| `NOMAD` | in Atomate2 it appears only as an author affiliation |

`ASE` is the one collision that crosses the two fields: in ASPEN it is
allele-specific expression, 12 occurrences. The Atomic Simulation Environment is
therefore matched only where a paper spells the name out or introduces the
abbreviation in parentheses, which costs mention counts and never misfires.

A fixed list is still the wrong long-term answer — two fields in and the list is
121 names — and replacing it needs a model proposing names with the text
available to check them against.

## The report

`report.md` answers blueprint §42's five questions as its section headings —
what is required, what was found, what is missing, where each item was
mentioned, and what to investigate before starting — with the last one printed
first. A researcher deciding whether to spend a semester on a paper needs the
blockers before the inventory, and burying them under three tables would be a
formatting decision with a cost measured in months.

Each issue is rendered as an instruction rather than a restatement, and the
long tail is ordered so the one-off findings come before the repetitive one:

```
### Hard blockers (1)

- Obtain `annotation.gtf` at publication scale before starting. The repository's
  copy is a demo.
  - *required dataset unavailable* — …/LocusMasterTE/data/annotation.gtf holds 20
    records (1457 bytes), too few to be a reference annotation

### Major issues (21)

- Ask the authors for the code behind `figure 2`, or plan to rewrite it.
- Expect to reconstruct the `R` environment from scratch. Nothing declares it.
- Find out how `Pychopper` was configured. The code runs it and the paper does
  not describe it, so following the methods section builds a different pipeline.
```

**The renderer reads the audit's own JSON and nothing else** — not the pages,
not the documents, not a model. That is a constraint rather than a convenience:
it makes the report provably a *view* of the findings, unable to assert anything
`links.json` does not already contain. A report that did its own extraction
could disagree with the findings it summarises, and the disagreement would be
invisible.

Three of blueprint §37's prohibitions are about this file, and each is tested:

- *Do not claim "this paper is reproducible" without actually running it.*
  Nothing is called reproducible. The report states a readiness band and names
  the distinction where a reader cannot miss it.
- *Do not remove provenance.* Every row carries where it was read — a section
  and segment for the paper, a repository and path for the code. Section first:
  a page number alone is not provenance when MATES page 20 holds three sections
  and an accession's role depends on which one it sits in.
- *Do not hide uncertainty.* "What could not be determined" is a section with a
  heading, not a footnote, because an undetermined item is the thing most likely
  to be mistaken for a finding. An unassessed criterion is never a zero.

## Vision backends

The VLM sits behind a protocol with two implementations, selected per run:

```bash
uv run python audit.py paper.pdf --vlm ollama                 # local, default
uv run python audit.py paper.pdf --vlm ollama --vlm-model minicpm-v:8b
uv run python audit.py paper.pdf --vlm anthropic              # needs ANTHROPIC_API_KEY
```

Local models run through [Ollama](https://ollama.com), which constrains
generation to a JSON schema, so the same Pydantic model defines both backends
and their outputs are directly diffable:

```bash
ollama pull qwen2.5vl:7b
uv run python scripts/compare_vlm.py data/papers/mates.pdf --a ollama --b anthropic
```

Two backends is not redundancy. The image channel cannot verify itself, so the
only available checks are corroboration against the text channel and agreement
between independent models — and one backend forecloses the second.

## Papers

`data/papers/` is gitignored; journal PDFs have varying redistribution licences.

- **MATES** — *Nat Commun* 2024, `10.1038/s41467-024-53114-7`, downloads directly.
- **LocusMasterTE** — *Genome Biology* 2025, `10.1186/s13059-025-03522-9`,
  `PMC11948968`. The publisher PDF is bot-blocked; the JATS XML is available from
  Europe PMC and parses better anyway. Download the PDF by hand for page-level
  provenance and figures.

## Deviations from blueprint §42

- `methods.json` is not emitted; `links.json`, `figures.json` and
  `checklist.json` are. The checklist that `methods.json` was meant to hold is
  in the third of those.
- `graph.json` is emitted and §42 does not name it. It holds the dependency
  graph (§27 goal 11) as nodes, edges and one verdict per result, and is built
  from the other records rather than from a second pass over the repository, so
  it cannot disagree with them about a paper.
- Table extraction exists (`tables` in `links.json`), which an earlier version
  of this section said it did not. Tables are read as rows of cells with no
  column-heading semantics, so the pipeline can say a value appears in Table 3
  and cannot say which heading governs it.

## Development

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run python scripts/validate_ocr.py data/papers/mates.pdf --pages 17,19,20,22
```
