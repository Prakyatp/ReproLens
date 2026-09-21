# ReproLens: AI-Assisted Scientific Reproducibility Auditor

## 1. Project Overview

**ReproLens** is an AI system designed to analyze a scientific paper and determine how ready that work is for independent reproduction.

The system will not only read the main paper. It will also inspect:

- Supplementary PDFs
- Supplementary spreadsheets
- Figures and tables
- GitHub repositories
- Dataset links
- GEO / SRA / Zenodo / Figshare / Dryad entries
- Model checkpoints
- Configuration files
- Environment files
- Protocol links
- Referenced external methods
- Scripts used for preprocessing, training, evaluation, and figure generation

The ultimate goal is to answer:

> "If I started reproducing this paper today, what can I reproduce, what is missing, where will I likely get blocked, and why?"

The first version should measure **reproducibility readiness**, not claim that a paper is fully reproduced.

A later version can actually attempt execution in a sandboxed/containerized environment and compare reproduced results with the published results.

---

# 2. Why I Am Building This

Scientific reproducibility is often expensive in time.

A researcher may spend days or weeks trying to reproduce a method before discovering that an essential item is missing:

- A dataset is unavailable
- A supplementary file is missing
- The preprocessing procedure is underspecified
- Software versions are not reported
- A model checkpoint is missing
- Hyperparameters are absent
- The repository does not contain the code required for a reported figure
- The README does not match the actual implementation
- A paper references another paper for an essential method
- The public dataset does not contain all samples described in the paper

This is a problem I have repeatedly encountered in my own research.

Instead of discovering these problems manually after investing significant effort, I want a system that audits the paper before reproduction begins.

The system should produce an evidence-based report describing:

1. What resources are required
2. Which resources are available
3. Which resources are missing
4. Which methodological details are ambiguous
5. Which individual results appear reproducible
6. Which results are blocked
7. What exact dependency causes each blocker
8. Where every conclusion came from

---

# 3. Main Research Question

The central question of the project is:

> Can an AI system automatically inspect the complete ecosystem around a scientific paper and estimate its reproducibility readiness while providing evidence for every identified gap?

This is not simply a PDF summarization problem.

It is a **multimodal, multi-document, multi-source reasoning problem** involving:

- Natural language
- PDFs
- OCR
- Tables
- Figures
- Source code
- Configuration files
- Dataset repositories
- Web pages
- Metadata
- Dependency graphs
- Scientific reasoning

---

# 4. What the System Should Eventually Do

Input:

```text
DOI
arXiv URL
PubMed link
paper URL
or
PDF
```

Output:

```text
Reproducibility Readiness Score: 78 / 100

Hard blockers:
- Pretrained model checkpoint unavailable

Major issues:
- Python dependency versions unspecified
- Random seed missing
- Preprocessing parameter unclear

Available:
- Raw data
- Main repository
- Training script
- Evaluation script
- Genome reference
- Supplementary tables
```

The system should also provide **per-result analysis**.

Example:

```text
Figure 2A
Status: High reproducibility readiness

✓ Raw dataset available
✓ Sample IDs found
✓ Processing code found
✓ Parameters specified
✓ Plotting script found
```

```text
Figure 4C
Status: Blocked

✓ Input data available
✓ Training code available
✗ Required model checkpoint unavailable

Likely blocker:
weights/final_model.pt is referenced by the evaluation script but is not present in the repository or linked supplementary material.
```

---

# 5. Important Terminology

## Reproducibility Readiness

This means:

> Does the publication provide enough information and resources that reproduction appears feasible?

It does **not** mean that the results were actually reproduced.

---

## Verified Reproduction

This means:

> The system or an independent researcher actually executed the workflow and obtained results sufficiently close to those reported in the paper.

These should remain separate metrics.

Example:

```text
Reproducibility Readiness: 91 / 100
Verified Reproduction: Not attempted
```

Later:

```text
Reproducibility Readiness: 91 / 100
Verified Reproduction: 84 / 100
```

---

# 6. Core System Architecture

```text
                         PAPER / DOI
                             |
                             v
                    DOCUMENT DISCOVERY
                             |
          +------------------+-------------------+
          |                  |                   |
          v                  v                   v
      Main PDF         Supplements        External Links
          |                  |                   |
          v                  v          +--------+---------+
      PDF Parser          Parser        GitHub   Data   Protocols
          |                  |             |       |        |
          +------------------+-------------+-------+--------+
                             |
                             v
                   MULTIMODAL EXTRACTION
                             |
             +---------------+---------------+
             |               |               |
             v               v               v
          Methods         Results         Resources
             |               |               |
             +---------------+---------------+
                             |
                             v
                    DEPENDENCY GRAPH
                             |
                             v
                    GAP / BLOCKER ANALYSIS
                             |
                  +----------+----------+
                  |                     |
                  v                     v
            Readiness Score       Execution Engine
                                        |
                                        v
                               Reproduction Attempt
                                        |
                                        v
                               Result Comparison
```

---

# 7. Major Components

## 7.1 Paper Discovery

The system needs to identify all resources referenced by the paper.

Examples:

- DOI
- Supplementary material
- GitHub URL
- GEO accession
- SRA accession
- Zenodo DOI
- Figshare link
- Dryad link
- Model checkpoint
- Protocol repository
- External software package
- Previous paper containing referenced methodology

### Output

```json
{
  "paper": "...",
  "supplements": [],
  "repositories": [],
  "datasets": [],
  "protocols": [],
  "external_methods": []
}
```

---

# 8. Unstructured Data Components

This project should intentionally involve several kinds of unstructured data.

## 8.1 Main Scientific PDF

Scientific PDFs contain:

- Multi-column text
- Equations
- Figures
- Tables
- Captions
- Footnotes
- References
- URLs
- Dataset accession numbers

The system should preserve document structure instead of converting everything into plain text.

### Learn

- PDF internals
- document layout analysis
- OCR
- bounding boxes
- reading order
- structured document representations

### Tools to explore

- PyMuPDF
- Docling
- pdfplumber
- PaddleOCR
- Tesseract
- Surya
- MinerU

Do not try to learn all of them deeply.

Use one strong parser as the baseline and compare alternatives later.

---

# 9. OCR

OCR is required for:

- Scanned papers
- Image-based supplementary PDFs
- Figure text
- Diagram labels
- Axis labels
- Tables embedded as images
- Older scientific publications

## Topics to study

### Fundamentals

Understand:

- Character recognition
- Text detection vs text recognition
- Word Error Rate
- Character Error Rate
- Bounding boxes
- Deskewing
- Image preprocessing
- OCR confidence scores

### Metrics

#### Character Error Rate

```text
CER = (substitutions + deletions + insertions) / number of characters
```

#### Word Error Rate

```text
WER = (substitutions + deletions + insertions) / number of words
```

### Practical experiments

Compare:

```text
Tesseract
PaddleOCR
document-native text extraction
VLM-based transcription
```

using a manually labeled subset of scientific pages.

---

# 10. Document Layout Understanding

The system should recognize objects such as:

```text
title
section heading
paragraph
table
figure
caption
equation
reference
header
footer
```

A page should not become one giant string.

Example:

```text
Page 4

Methods
  Paragraph 1
  Paragraph 2

Figure 2
  Image
  Caption

Table 1
  Rows
  Columns
```

## Study

Learn:

- object detection basics
- bounding boxes
- IoU
- mAP
- document layout models
- reading order

Useful datasets to study:

- DocLayNet
- PubLayNet

Optional models:

- LayoutLM family
- Detectron-style document detectors
- YOLO-based document detectors

You do not need to train a layout model immediately.

First use a pretrained system.

Later evaluate or fine-tune one if useful.

---

# 11. Table Extraction

Scientific tables frequently contain critical reproducibility information:

- Sample IDs
- Parameters
- Dataset accessions
- Experimental conditions
- Metrics
- Hyperparameters
- Reagent information

The system should convert tables into structured representations.

Example:

```text
Treatment     Dose     Viability
Control       0 uM       100
Drug A       10 uM        41
```

becomes:

```json
{
  "columns": [
    "treatment",
    "dose",
    "dose_unit",
    "viability"
  ],
  "rows": [
    ["Control", 0, "uM", 100],
    ["Drug A", 10, "uM", 41]
  ]
}
```

## Study

Learn:

- table detection
- table structure recognition
- row detection
- column detection
- merged cells
- hierarchical headers
- table normalization

Dataset:

- PubTables-1M

Models/tools to investigate:

- Table Transformer
- Docling table extraction
- PaddleOCR table pipeline
- VLM-based table extraction

---

# 12. Figure Understanding

Figures can contain information not explicitly stated in text.

Examples:

- Pipeline diagrams
- Neural network architectures
- Experimental workflows
- Plots
- Microscopy
- Western blots
- Heatmaps
- Kaplan-Meier curves
- Scatter plots
- Bar graphs

A VLM can help interpret these.

Example input:

```text
FASTQ
  |
  v
STAR
  |
  v
featureCounts
  |
  v
DESeq2
```

Expected extraction:

```json
{
  "workflow": [
    "FASTQ",
    "STAR",
    "featureCounts",
    "DESeq2"
  ]
}
```

## Study

Learn:

- vision-language models
- image embeddings
- multimodal prompting
- image grounding
- structured VLM outputs
- chart understanding

Models worth understanding conceptually:

- Qwen-VL family
- LLaVA
- InternVL
- Florence-style vision-language systems
- GPT-class VLM APIs

The specific model can change over time.

The important skill is understanding the architecture and evaluation problem.

---

# 13. Structured Scientific Information Extraction

The system should convert free text into structured information.

Example source text:

```text
HCT116 cells were treated with 10 μM compound X for 24 hours.
```

Output:

```json
{
  "cell_line": "HCT116",
  "treatment": "compound X",
  "concentration": 10,
  "concentration_unit": "uM",
  "duration": 24,
  "duration_unit": "hours"
}
```

## Study

Learn:

- named entity recognition
- relation extraction
- information extraction
- schema-based extraction
- constrained generation
- JSON Schema
- Pydantic
- tool/function calling concepts

Do not allow unconstrained natural language where structured data is required.

---

# 14. Provenance and Grounding

Every extracted fact must be traceable to its source.

Example:

```json
{
  "value": "HCT116",
  "source": {
    "document": "paper.pdf",
    "page": 4,
    "section": "Methods",
    "bbox": [100, 220, 480, 310]
  }
}
```

This is extremely important.

Without provenance, the system risks becoming a hallucination engine.

The UI should eventually allow a user to click:

```text
Cell line: HCT116
```

and jump to the exact location in the paper.

## Study

Learn:

- source attribution
- retrieval grounding
- bounding-box referencing
- citation systems
- hallucination detection
- confidence estimation

---

# 15. GitHub / Repository Analysis

A paper may link to a repository containing:

```text
README.md
requirements.txt
environment.yml
Dockerfile
setup.py
pyproject.toml
config.yaml
Python
R
Shell
Jupyter notebooks
```

The system should inspect the repository and answer:

```text
What is the entry point?
What command runs the experiment?
Which scripts perform preprocessing?
Which scripts perform training?
Which scripts generate figures?
What datasets are required?
What model weights are required?
What dependencies are required?
Are dependency versions specified?
```

## Study

Learn:

- Git
- GitHub repositories
- static code analysis basics
- dependency parsing
- ASTs
- import graphs
- call graphs
- configuration management
- code search
- repository-level LLM reasoning

For Python specifically, learn:

```text
ast
importlib concepts
requirements.txt
pyproject.toml
conda environment.yml
```

You do not need to build a full compiler.

The goal is to infer the execution and dependency structure.

---

# 16. Repository Consistency Checking

One interesting capability is detecting contradictions.

Example:

README:

```text
Python >= 3.8
```

requirements:

```text
tensorflow==1.15
```

Code:

```python
import tensorflow.compat.v1
```

Possible system output:

```text
WARNING:
The documented environment may be inconsistent with the required TensorFlow version.
```

Other checks:

```text
Referenced files that do not exist
Model weights referenced but missing
Dataset paths hardcoded to local machines
Undocumented environment variables
Undocumented preprocessing steps
Version inconsistencies
Broken download links
```

---

# 17. Dataset Repository Analysis

The system should inspect scientific data sources.

Examples:

- GEO
- SRA
- Zenodo
- Figshare
- Dryad

Questions:

```text
Does the dataset exist?
Is it publicly accessible?
Are raw files available?
Are only processed files available?
How many samples are available?
Do sample names match the paper?
Are metadata files available?
Are licenses or access restrictions present?
```

Example:

```text
Paper reports: 18 samples
Repository contains: 16 identifiable samples

WARNING:
Two samples could not be matched.
```

## Study

Learn:

- scientific dataset identifiers
- metadata formats
- APIs
- accession numbers
- data provenance
- sample metadata
- checksum concepts

Because of your bioinformatics background, GEO/SRA is a good starting domain.

---

# 18. Multi-Document Reasoning

Papers frequently contain chains like:

```text
Paper
  |
  v
Supplementary Methods
  |
  v
"Performed as previously described"
  |
  v
Previous Paper
  |
  v
Original protocol
```

Your system should follow these dependencies.

That means it needs to reason across multiple documents.

## Study

Learn:

- retrieval-augmented generation
- chunking
- semantic search
- embeddings
- reranking
- multi-hop retrieval
- knowledge graphs

Important:

Do not make basic RAG the main contribution.

RAG is infrastructure that helps the larger reproducibility task.

---

# 19. Reproduction Dependency Graph

This should become the core internal representation.

Example:

```text
                     Figure 4B
                        |
                  plotting script
                        |
                   model output
                        |
             +----------+----------+
             |                     |
       trained model            test data
             |                     |
       training script          SRA dataset
             |
      +------+------+
      |             |
 training data    config
      |
   GEO dataset
```

Every node should have a status:

```text
AVAILABLE
PARTIAL
MISSING
UNCERTAIN
```

Example structure:

```json
{
  "node": "model_checkpoint",
  "status": "MISSING",
  "required_by": "Figure 4B",
  "evidence": [
    "evaluation.py line ...",
    "Methods page ..."
  ]
}
```

## Study

Learn:

- graph data structures
- DAGs
- dependency graphs
- topological sorting
- graph traversal
- graph databases

You can initially use:

```text
NetworkX
```

Later consider:

```text
Neo4j
```

if the graph becomes complex.

---

# 20. Claim-Level Reproducibility

Do not treat the entire paper as one object.

Model:

```text
Paper
 |
 +-- Claim 1
 |    +-- Figure 1A
 |    +-- Figure 1B
 |
 +-- Claim 2
 |    +-- Table 2
 |
 +-- Claim 3
      +-- Figure 5
```

Each claim/result gets its own reproducibility analysis.

Example:

| Result | Readiness | Blocker |
|---|---:|---|
| Figure 1A | 96% | None |
| Figure 2 | 82% | Environment versions |
| Figure 4C | 41% | Missing model checkpoint |
| Figure 5 | 0% | Private dataset |

This is more useful than one global score.

---

# 21. Reproducibility Scoring

The score should not be invented by the LLM.

Build a deterministic rubric.

Initial example:

| Category | Weight |
|---|---:|
| Data availability | 20 |
| Code availability | 20 |
| Environment specification | 15 |
| Method completeness | 15 |
| Parameters/configuration | 10 |
| Execution instructions | 10 |
| Result-to-code traceability | 10 |
| **Total** | **100** |

Example:

```text
Data                20 / 20
Code                17 / 20
Environment          7 / 15
Methods             13 / 15
Parameters           6 / 10
Execution            5 / 10
Traceability         7 / 10

TOTAL               75 / 100
```

The scoring policy should be versioned.

Example:

```text
ReproLens Rubric v0.1
```

---

# 22. Severity Classification

In addition to numerical scoring, classify issues.

## Hard blocker

Examples:

```text
Required dataset unavailable
Private data
Missing model checkpoint
Required proprietary tool unavailable
Essential code absent
```

## Major issue

Examples:

```text
Preprocessing unclear
Reference genome unspecified
Software version missing
Critical hyperparameters absent
```

## Minor issue

Examples:

```text
Random seed missing
Hardware unspecified
Plotting package version missing
```

Output:

```text
2 blockers
4 major issues
5 minor issues
```

This may be more useful than the score itself.

---

# 23. Automated Execution — Later Phase

After the auditing system works, add execution.

Pipeline:

```text
Clone repository
      |
      v
Inspect dependencies
      |
      v
Create isolated environment
      |
      v
Download required data
      |
      v
Run preprocessing
      |
      v
Run experiment
      |
      v
Generate outputs
      |
      v
Compare with paper
```

Use containers for safety and reproducibility.

## Study

Learn:

- Docker
- container images
- volumes
- environment variables
- resource limits
- subprocess management
- job queues
- sandboxing concepts

Later:

- Kubernetes concepts
- cloud execution
- workflow engines

Do not begin here.

This is Phase 3+.

---

# 24. Result Comparison

For computational papers, compare reproduced results to reported results.

Example:

```text
Reported AUROC:   0.913
Reproduced AUROC: 0.907
Difference:      -0.006
```

For tables:

```text
numeric difference
relative error
correlation
```

For charts:

Possible future approaches:

```text
chart data extraction
curve comparison
image similarity
semantic VLM comparison
```

For ML:

```text
accuracy
AUROC
F1
precision
recall
loss
```

---

# 25. Benchmark Dataset

A strong project requires evaluation.

Create a manually audited benchmark.

Start with:

```text
20 papers
```

Later:

```text
50
100
200
```

For each paper annotate:

```text
code available?
data available?
environment complete?
model weights available?
supplements available?
parameters complete?
execution instructions?
main blocker?
which figures reproducible?
```

Example record:

```json
{
  "paper_id": "paper_001",
  "code_available": true,
  "data_available": true,
  "environment_complete": false,
  "weights_available": false,
  "blocker": "missing_model_weights"
}
```

This becomes your ground truth.

---

# 26. Evaluation Metrics

## Resource Detection

```text
Precision
Recall
F1
```

Evaluate:

```text
GitHub link detection
dataset link detection
supplement detection
model checkpoint detection
```

---

## Missing Resource Detection

Measure whether the system correctly identifies:

```text
missing data
missing code
missing weights
missing environment
missing parameters
```

Use:

```text
Precision
Recall
F1
```

---

## Evidence Grounding

Measure:

```text
correct source document
correct page
correct paragraph
correct bounding box
```

---

## Table Extraction

Possible metrics:

```text
cell accuracy
row/column accuracy
structure similarity
GriTS
```

---

## OCR

```text
CER
WER
```

---

## Scoring Agreement

Compare system score against expert annotations.

Possible metrics:

```text
Pearson correlation
Spearman correlation
MAE
```

---

# 27. Recommended MVP

Do not build everything.

## MVP Goal

Given one computational biology paper:

1. Parse the PDF
2. Identify external resources
3. Locate supplementary materials
4. Locate GitHub
5. Locate datasets
6. Extract methods
7. Extract software/tools
8. Extract parameters
9. Analyze repository
10. Determine missing dependencies
11. Generate dependency graph
12. Produce evidence-backed reproducibility readiness report

Target:

```text
20-30 computational biology papers
```

This is enough to demonstrate the concept.

---

# 28. MVP Tech Stack

## Backend

```text
Python
FastAPI
Pydantic
```

## PDF

Start with:

```text
Docling
PyMuPDF
```

## OCR

Start with one:

```text
PaddleOCR
```

Optional baseline:

```text
Tesseract
```

## LLM/VLM

Use an API or open model initially.

Do not fine-tune immediately.

## Repository parsing

```text
Git
Python AST
regex
YAML parser
TOML parser
```

## Graph

```text
NetworkX
```

## Database

Start:

```text
SQLite / PostgreSQL
```

Later:

```text
PostgreSQL + pgvector
```

## Frontend

Later:

```text
React / Next.js
```

For the first prototype:

```text
Streamlit
```

is completely acceptable.

---

# 29. Suggested Repository Structure

```text
reprolens/
│
├── README.md
├── pyproject.toml
│
├── app/
│   ├── api/
│   └── ui/
│
├── reprolens/
│   ├── discovery/
│   │   ├── paper.py
│   │   ├── links.py
│   │   └── supplements.py
│   │
│   ├── documents/
│   │   ├── pdf_parser.py
│   │   ├── ocr.py
│   │   ├── tables.py
│   │   └── figures.py
│   │
│   ├── extraction/
│   │   ├── methods.py
│   │   ├── entities.py
│   │   ├── claims.py
│   │   └── resources.py
│   │
│   ├── repositories/
│   │   ├── github.py
│   │   ├── dependencies.py
│   │   ├── entrypoints.py
│   │   └── code_graph.py
│   │
│   ├── datasets/
│   │   ├── geo.py
│   │   ├── sra.py
│   │   ├── zenodo.py
│   │   └── metadata.py
│   │
│   ├── graph/
│   │   ├── dependency_graph.py
│   │   └── claim_graph.py
│   │
│   ├── scoring/
│   │   ├── rubric.py
│   │   └── severity.py
│   │
│   ├── evaluation/
│   │   └── metrics.py
│   │
│   └── models/
│       └── schemas.py
│
├── tests/
├── benchmark/
└── notebooks/
```

---

# 30. Development Roadmap

# Phase 0 — Define the Task

Before writing major code:

1. Select 10 papers you already know.
2. Manually answer:
   - What data is needed?
   - What code is needed?
   - What environment is needed?
   - What parameters are needed?
   - What is missing?
3. Define the first scoring rubric.
4. Define the JSON output schema.

## What to study

```text
Scientific reproducibility
Reproducibility vs replicability
Artifact evaluation
FAIR data principles
Scientific software documentation
```

---

# Phase 1 — PDF and Document Parsing

Build:

```text
PDF
  ->
structured document
```

Extract:

```text
sections
paragraphs
tables
figures
captions
links
DOIs
accession numbers
```

## Study

```text
PDF structure
OCR basics
layout detection
bounding boxes
reading order
PyMuPDF
Docling
PaddleOCR
```

## Deliverable

```text
paper.json
```

with provenance.

---

# Phase 2 — Scientific Information Extraction

Extract:

```text
datasets
software
software versions
parameters
model names
reference genome
annotations
hardware
random seed
sample IDs
training details
evaluation metrics
```

## Study

```text
NER
relation extraction
structured LLM output
Pydantic
JSON Schema
prompt design
few-shot extraction
evaluation
```

## Deliverable

```text
methods.json
resources.json
```

---

# Phase 3 — Link and Supplement Discovery

Automatically identify:

```text
supplementary material
GitHub
Zenodo
GEO
SRA
Figshare
Dryad
URLs
DOIs
```

## Study

```text
HTTP
HTML
web scraping fundamentals
URL resolution
DOI metadata
Crossref concepts
PubMed metadata
scientific accession patterns
```

## Deliverable

```text
resources_discovered.json
```

---

# Phase 4 — GitHub Analysis

Clone repository and extract:

```text
dependencies
entry points
commands
configs
checkpoints
datasets
scripts
figure-generation code
```

## Study

```text
Git
repository structure
Python AST
dependency graphs
requirements.txt
pyproject.toml
environment.yml
Dockerfile
static analysis
```

## Deliverable

```text
repo_analysis.json
```

---

# Phase 5 — Dataset Verification

Check:

```text
dataset exists
public access
sample count
raw vs processed data
metadata availability
paper-to-dataset sample match
```

Start with:

```text
GEO
SRA
```

because they fit computational biology.

## Study

```text
GEO
SRA
NCBI metadata
sample/run accessions
API requests
metadata normalization
```

---

# Phase 6 — Dependency Graph

Create:

```text
Result
  ->
script
  ->
model
  ->
data
  ->
configuration
```

## Study

```text
graphs
DAGs
NetworkX
graph traversal
topological sorting
dependency resolution
```

## Deliverable

Visual interactive graph.

---

# Phase 7 — Reproducibility Scoring

Implement deterministic scoring.

Example:

```python
score = (
    data_score +
    code_score +
    environment_score +
    methods_score +
    parameter_score +
    execution_score +
    traceability_score
)
```

The LLM should provide evidence.

The scoring engine should calculate the final score.

## Study

```text
rubric design
calibration
classification metrics
inter-rater agreement
confidence intervals
```

---

# Phase 8 — Benchmark

Manually annotate:

```text
20-50 papers
```

Evaluate:

```text
resource extraction
missing dependency detection
score agreement
evidence retrieval
```

## Study

```text
precision
recall
F1
confusion matrix
MAE
correlation
error analysis
```

This phase is crucial.

---

# Phase 9 — VLM Integration

Add figure interpretation.

Tasks:

```text
workflow extraction
chart interpretation
architecture diagram extraction
figure-method linking
```

## Study

```text
vision transformers
CLIP
multimodal transformers
VLM prompting
image tokenization
cross attention
visual grounding
```

Important conceptual questions:

```text
How are images represented?
How does a VLM combine text and vision?
What is a vision encoder?
What is a projection layer?
What is cross-attention?
What are image tokens?
```

You should be able to explain these in an interview.

---

# Phase 10 — Automated Execution

Only after the audit system works.

Build:

```text
repo
 ->
container
 ->
install
 ->
download data
 ->
execute
 ->
capture logs
```

## Study

```text
Docker
Linux namespaces conceptually
containers
dependency isolation
resource limits
subprocess
logging
timeouts
job orchestration
security
```

---

# Phase 11 — Result Verification

Compare:

```text
reported metrics
vs
generated metrics
```

Then eventually compare:

```text
tables
plots
figures
```

## Study

```text
statistical comparison
numeric tolerances
plot digitization
chart extraction
image similarity
scientific metric validation
```

---

# 31. Study Roadmap

Do not try to learn everything before coding.

Use this order.

## First

Learn enough to build:

```text
PDF -> structured text
```

Study:

```text
PyMuPDF
Docling
OCR basics
document layouts
```

---

## Second

Learn:

```text
LLM structured extraction
Pydantic
JSON schemas
prompt evaluation
```

Build:

```text
methods text
 ->
structured methods JSON
```

---

## Third

Learn:

```text
Git
GitHub repository structure
Python AST
dependency files
```

Build:

```text
repo
 ->
required resources
```

---

## Fourth

Learn:

```text
graphs
NetworkX
```

Build dependency graph.

---

## Fifth

Learn:

```text
RAG
embeddings
reranking
multi-hop retrieval
```

Only when multiple documents become difficult to search.

---

## Sixth

Learn VLMs.

Study:

```text
CNN basics review
Vision Transformer
CLIP
multimodal transformer
vision encoder
projection layer
cross-attention
instruction tuning
```

Then use the VLM for figures and diagrams.

---

## Seventh

Learn Docker.

Only after you begin automatic execution.

---

# 32. Deep Learning Topics I Should Know

Because this project may be discussed in ML interviews, understand:

## Transformers

```text
self-attention
query/key/value
multi-head attention
positional embeddings
encoder vs decoder
causal attention
```

## Vision Transformers

Understand:

```text
image patches
patch embeddings
CLS token
transformer encoder
```

## CLIP

Understand:

```text
image encoder
text encoder
contrastive learning
shared embedding space
```

## VLMs

Understand the high-level architecture:

```text
image
 ->
vision encoder
 ->
visual embeddings
 ->
projector
 ->
language model
 ->
text output
```

## Fine-tuning

Learn:

```text
full fine-tuning
LoRA
QLoRA
instruction tuning
```

Do not fine-tune initially.

Use evaluation to determine whether fine-tuning is necessary.

---

# 33. NLP Topics I Should Know

```text
tokenization
embeddings
semantic similarity
named entity recognition
relation extraction
information extraction
retrieval
reranking
RAG
structured generation
hallucination
grounding
context windows
chunking
```

---

# 34. Computer Vision Topics I Should Know

```text
image preprocessing
bounding boxes
IoU
object detection
mAP
OCR
layout detection
Vision Transformers
image embeddings
chart understanding
```

---

# 35. Software Engineering Topics I Should Know

This project should also demonstrate engineering.

Study:

```text
REST APIs
FastAPI
async I/O
databases
PostgreSQL
queues
caching
Docker
logging
testing
CI/CD
configuration management
error handling
```

Later:

```text
distributed workers
Celery / task queues
Kubernetes concepts
cloud storage
object storage
```

---

# 36. Data Engineering Topics

You will deal with many formats.

Study:

```text
JSON
JSONL
CSV
TSV
XLSX
PDF
HTML
XML
YAML
TOML
FASTA
FASTQ
BAM metadata
```

You do not need deep expertise in every format.

Focus on robust ingestion and normalization.

---

# 37. Things NOT to Do

Do not build:

```text
PDF -> embeddings -> chatbot
```

and call the project complete.

Do not allow:

```text
LLM -> arbitrary reproducibility score
```

Do not claim:

```text
"This paper is reproducible"
```

without actually running it.

Do not rely on one giant prompt.

Do not remove provenance.

Do not hide uncertainty.

Do not build a complicated multi-agent framework before the core extraction works.

Do not use ten different frameworks when simple Python will work.

---

# 38. What Makes This Project Strong

A strong final version demonstrates:

```text
OCR
document AI
VLMs
LLMs
structured information extraction
web/resource discovery
code understanding
graph reasoning
scientific data validation
RAG
evaluation
software engineering
containerization
scientific reproducibility
```

But more importantly, these technologies solve a coherent real-world problem.

---

# 39. Resume Version

A future resume bullet might look like:

> Built a multimodal scientific reproducibility auditing system that analyzes research papers, supplementary documents, code repositories, and dataset records to identify missing reproduction dependencies and generate claim-level, evidence-grounded reproducibility reports.

Later, after evaluation:

> Developed a multimodal reproducibility auditor for computational biology papers using OCR, VLMs, repository analysis, and dependency graphs; evaluated missing-resource detection across 100 manually audited papers with XX% precision and XX% recall.

Later, after execution:

> Extended the system with containerized execution to automatically reconstruct research environments, run published pipelines, and compare reproduced metrics against reported results.

---

# 40. Final Project Goal

The long-term vision is:

> A researcher provides a paper before attempting reproduction.

ReproLens responds:

```text
You can likely reproduce Figures 1, 2, and 3.

Figure 4 cannot currently be reproduced because the
required pretrained checkpoint is missing.

Figure 5 is partially reproducible, but the exact preprocessing
threshold is not specified.

All raw sequencing data are available under GSEXXXXX.

The GitHub repository contains the training and evaluation code,
but its documented Python environment is inconsistent with
the dependency versions.

Estimated reproduction readiness: 76/100.

Estimated effort: Moderate-to-high.

Recommended first action:
Contact the authors for the missing model checkpoint before
beginning reproduction.
```

If this system can reliably provide that answer with evidence, it solves a real and expensive problem in scientific research.

---

# 41. First Concrete Tasks

Start here.

## Week 1 target

1. Create the GitHub repository.
2. Select 5 computational biology papers you already know.
3. Manually annotate their reproducibility requirements.
4. Define `paper.json`.
5. Parse one PDF with Docling.
6. Extract:
   - sections
   - links
   - figures
   - tables
   - captions
7. Preserve page numbers and bounding boxes.
8. Write a script that extracts:
   - GitHub links
   - GEO IDs
   - SRA IDs
   - DOI references
9. Create your first manual reproducibility report.

Do not add a VLM yet.

Understand the underlying document pipeline first.

---

# 42. First Milestone

The first meaningful milestone should be:

```text
python audit.py paper.pdf
```

produces:

```text
output/
├── paper.json
├── links.json
├── methods.json
├── resources.json
├── figures/
├── tables/
└── report.md
```

`report.md` should answer:

```text
What is required?
What was found?
What is missing?
Where was each item mentioned?
What should the researcher investigate before starting reproduction?
```

Once that works reliably, begin GitHub and VLM integration.

---

# 43. Guiding Principle

Every new model, framework, or feature should answer:

> What specific reproducibility problem does this solve?

Examples:

```text
OCR
-> reads scanned supplementary documents

VLM
-> understands workflow diagrams and scientific figures

LLM
-> converts methods prose into structured requirements

GitHub analysis
-> identifies code and environment dependencies

Graph
-> connects results to the resources required to produce them

Docker
-> verifies whether the workflow can actually execute
```

If a technology does not solve a concrete part of the problem, do not add it simply because it is popular.

---

# 44. Success Criteria

The project is successful when it can:

1. Discover most resources associated with a computational research paper.
2. Correctly extract reproduction requirements.
3. Identify missing resources and ambiguous methodological details.
4. Map important results to their dependencies.
5. Provide source evidence for every finding.
6. Produce a consistent reproducibility-readiness score.
7. Perform well against manually audited papers.
8. Eventually attempt execution and identify exact failure points.

The strongest version of the project is not an AI that says:

> "This paper looks hard to reproduce."

It is an AI that says:

> "Figure 4B depends on `evaluation.py`, which loads `weights/final_model.pt`. The repository does not contain that file, the supplementary materials do not link a checkpoint, and the manuscript does not provide an alternative download. This result is therefore blocked until the checkpoint is obtained."

That is the level of precision ReproLens should aim for.
