# Tier-2 annotation worksheet — `aspen`

Source: `data/papers/aspen.pdf` · 26 segment(s) · generated 2026-11-14

> **This worksheet contains no findings.** Everything below is the paper's own
> text or the repository's own files, quoted verbatim with provenance. It
> deliberately carries no score, no severity, no resource verdict and no
> extracted identifier, because this record is the ground truth ReproLens is
> graded against: if the app's answers reached the annotator, the agreement
> number would be measuring the app against itself. Read the quotes and
> decide. Where the quotes are not enough, open the paper.

Fill in `benchmark/papers/aspen.json`, then:

```bash
uv run python check.py --validate-only
```

## The seven questions

Score what the paper **documents**, before anyone tries to run it. A cold read
cannot honestly fill `verified_reproduction` — leave it out rather than guess.

| criterion | weight | your score | why |
| --- | --- | --- | --- |
| data_availability | 20 | | |
| code_availability | 20 | | |
| environment_specification | 15 | | |
| method_completeness | 15 | | |
| parameters_configuration | 10 | | |
| execution_instructions | 10 | | |
| result_traceability | 10 | | |

Severity vocabulary for `blockers`: `hard` (reproduction impossible without
it), `major` (must be guessed), `minor` (costs time). Not `hard_blocker` —
that is the app's word, and a record using it vanishes from the comparison.

## Front matter, verbatim

`title` and `citation` are copied from here. They are not pre-filled: a
journal sets a title over two lines, so taking the first one gives a
plausible-looking wrong answer, and a blank field is honest where a
truncated one is not.

    OPEN ACCESS
    Citation: Petrova V, Niu M, Vierbuchen TS,
    Wong ES (2025) ASPEN: Robust detection of
    allelic dynamics in single cell RNA-seq. PLoS
    Comput Biol 21(12): e1013837. https://doi.
    org/10.1371/journal.pcbi.1013837
    Editor: Ilya Ioshikhes, ., CANADA
    Received: September 16, 2025
    Accepted: December 13, 2025
    Published: December 19, 2025
    Copyright: © 2025 Petrova et al. This is an
    open access article distributed under the terms
    of the Creative Commons Attribution License,
    which permits unrestricted use, distribution,
    and reproduction in any medium, provided the
    original author and source are credited.
    Data availability statement: ASPEN is
    available as an R package at https://github.

## Where the paper's own sections are

| page | label | heading as printed |
| --- | --- | --- |
| 1 | `abstract` | Abstract |
| 1 | `abstract` | Author summary |
| 2 | `background` | Introduction |
| 2 | `results` | Results and discussion |
| 5 | `results` | ASPEN robustly detects allelic imbalance in single-cell data |
| 7 | `results` | Beyond imbalance, modeling allelic variance |
| 9 | `results` | Detection of random and incomplete X inactivation |
| 11 | `conclusions` | Conclusion |
| 12 | `methods` | Methods |
| 13 | `methods` | Combined genome generation |
| 13 | `methods` | Beta-binomial modeling of allelic counts |
| 14 | `methods` | Bayesian shrinkage implementation |
| 14 | `methods` | Treatment of genes with low allelic variation |
| 15 | `methods` | Statistical framework for testing allelic imbalance |
| 16 | `methods` | Detecting group-level changes |
| 16 | `methods` | Generation of simulated data |
| 17 | `methods` | Detecting allelic imbalance in the simulated data |
| 17 | `methods` | Bulk RNA-Seq data processing |
| 17 | `methods` | scRNA data preprocessing |
| 18 | `methods` | Single cell data allelic testing in CD8 + T cells |
| 18 | `methods` | Pseudobulked allelic testing in CD8 + T cells |
| 18 | `methods` | Analysis of mouse brain organoid single-cell RNA-seq data |
| 19 | `methods` | Identification of random monoallelic expression |
| 19 | `methods` | Allele-specific TF binding motif enrichment analyses |
| 19 | `methods` | Gene stability analyses |
| 19 | `methods` | Functional enrichment analysis |
| 19 | `data_availability` | Availability of data and materials |
| 20 | `supplementary` | Supporting information |
| 23 | `acknowledgments` | Acknowledgments |
| 23 | `author_contributions` | Authors’ contributions |
| 23 | `author_contributions` | Author contributions |
| 23 | `author_contributions` | Conceptualization: |
| 23 | `author_contributions` | Data curation: |
| 23 | `author_contributions` | Formal analysis: |
| 23 | `author_contributions` | Methodology: |
| 23 | `author_contributions` | Project administration: |
| 23 | `author_contributions` | Resources: |
| 23 | `author_contributions` | Software: |
| 23 | `author_contributions` | Supervision: |
| 23 | `author_contributions` | Visualization: |
| 23 | `author_contributions` | Writing – original draft: |
| 23 | `author_contributions` | Writing – review & editing: |
| 23 | `references` | References |

## Availability statements, verbatim

### `data_availability` — page 19

> Availability of data and materials ASPEN is available as an R package at https://github.com/ewonglab/ASPEN The source code and data used to produce the results and analyses presented in this manuscript are available from Github repository: https://github.com/ewonglab/ASPEN_manuscript. Single-cell RNA-seq data for CD8 T cells from naïve, day 7, and day 40 LCMV Armstrong infection samples were downloaded from the GSE164978 dataset (SRA: SRR13450127, SRR13450128) [32]. Bulk RNA-Seq data for CD8 + T cells 7 days after LCMV Armstrong infection were

### `supplementary` — page 20

> Supporting information S1 Fig. Comparing two F1 hybrid reads mapping strategies: SNPs level variation and SNPs and indels level vari­ ation between the parental genomes. Schematic for F1 breeding strategy (top panel). The difference in the number of reads mapped to the combined genomes generated with either SNPs only or both SNPs and indels using fibroblast cells from four mouse F1 hybrids – Bl6 × Cast, Bl6 × Molf, Bl6 × Pwk and Bl6 × Spret (bottom panel). (TIF) S2 Fig. Genes with low dispersion involved in broad cellular functions. (A) GO term enrichment analysis using the genes with low dispersion. Enriched gene ontology biological process function categories for genes with low allelic dispersion in T-cells day 7 post LCMV infection scRNA dataset (B) Mean expression and proportion of non-zero cells between the stably expressed genes (SEGs), identified in Bl6 × Cast F1 brain organoids dataset, and background, genes matched by expression level and number of non-zero cells (two-sided Wilcoxon rank-sum test) (complementary to Fig 2C). (TIF) S3 Fig. Detecting genes with allelic imbalance using ASPEN. (A) Performance comparison between ASPEN and scDALI using simulated data (complementary to Fig 3C). Line plots showing TPRs calculated at FDR = 0.001 for genes stratified by gene expression and allelic dispersion levels (low dispersion – θ < 0.005, medium – θ ≥ 0.005 & θ < 0.4 and high – θ ≥ 0.4) across groups with varying levels of deviation from the mean AR = 0.5. Only datasets simulated with a mean AR of 0.5 ± 0.2 are shown. (B) ASPEN runtime (top) and memory usage (bottom) for different numbers of cells and genes (calculations were restricted to one core using a 6 CPU Intel Xeon, 64GB RAM machine). (C) Correlation of -log10FDR values from ASPEN mean test ran on the single- ... [1,680 more characters -- open the paper]

## Figure and table captions

A caption is where a result's inputs get named, which is the
`result_traceability` question.

- p7: Table in S2 Appendix). For low-dispersion genes, exemption from shrinkage improved sensitivity by up to 22%. In con­ trast, genes with high allelic dispersion benefited from shrinkage, which enhanced detection accuracy by up to 30%. We benchmarked ASPEN against scDALI [24], a method that models ASE via generalized linear mixed models, and found that ASPEN detected up to ~30% more imbalanced genes across simulated datasets, with no detectable increase in false positives among allelically balanced controls (Fig 3C, S3A Fig). We also compared ASPEN’s method to the binomial test.

## Repository — `github__ewonglab__ASPEN`

### Layout

```
.Rbuildignore  (61 B)
.Rhistory  (23,807 B)
.gitignore  (68 B)
ASPEN.Rproj  (414 B)
DESCRIPTION  (2,413 B)
NAMESPACE  (455 B)
R/
  allelic_imbalance.R  (7,098 B)
  allelic_variation.R  (9,314 B)
  diffASE.R  (17,236 B)
  parameter_estimation.R  (19,306 B)
  utils.R  (18,711 B)
README.md  (2,295 B)
_pkgdown.yml  (152 B)
data/
  Bl6_Cast_a1.rda  (2,360,557 B)
  Bl6_Cast_tot.rda  (3,219,395 B)
docs/
  404.html  (4,279 B)
  articles/
    allelic_imbalance.html  (91,267 B)
    allelic_imbalance_files/
    allelic_variance.html  (70,549 B)
    allelic_variance_files/
    differential_ASE.html  (214,730 B)
    differential_ASE_files/
    dynamic_allelic_changes.html  (88,104 B)
    dynamic_allelic_changes_files/
    index.html  (3,983 B)
  authors.html  (5,511 B)
  bootstrap-toc.css  (1,843 B)
  bootstrap-toc.js  (4,764 B)
  deps/
    bootstrap-5.2.2/
    bootstrap-toc-1.0.1/
    clipboard.js-2.0.11/
    data-deps.txt  (885 B)
    font-awesome-6.4.2/
    headroom-0.11.0/
    jquery-3.6.0/
    search-1.0.0/
  docsearch.css  (11,758 B)
  docsearch.js  (2,018 B)
  index.html  (8,880 B)
  katex-auto.js  (617 B)
  lightswitch.js  (2,505 B)
  link.svg  (810 B)
  pkgdown.css  (7,308 B)
  pkgdown.js  (4,716 B)
  pkgdown.yml  (327 B)
  reference/
    allelicSwitch.html  (8,490 B)
    bb_mean.html  (8,832 B)
    bb_var.html  (9,562 B)
    beta_binom_test.html  (9,137 B)
    calc_mad.html  (5,445 B)
    correct_theta.html  (8,072 B)
    correct_theta_bygroup.html  (8,217 B)
    estim_bbparams.html  (7,909 B)
    estim_bbparams_bygroup.html  (9,601 B)
    estim_delta.html  (7,099 B)
    geBoxplot.html  (5,602 B)
    glob_disp.html  (7,598 B)
    group_mean.html  (8,064 B)
    group_var.html  (8,347 B)
    index.html  (8,459 B)
    make_plotdf_simul.html  (7,177 B)
    makedf.html  (5,986 B)
    plot_MA.html  (6,369 B)
    plot_disp.html  (5,452 B)
    plot_disp_fit_mean.html  (5,733 B)
    plot_disp_fit_theta.html  (5,721 B)
    plot_distr.html  (5,652 B)
    plot_exp_disp.html  (5,704 B)
    plot_glob_params.html  (7,107 B)
    plot_theta_density.html  (5,701 B)
  search.json  (102,468 B)
  sitemap.xml  (2,779 B)
inst/
  extdata/
    Bl6_Cast_cell_annot.xlsx  (261,982 B)
    mm10_genesXY.txt  (18,662 B)
    mm10_imprinted_genes.xlsx  (9,379 B)
    pseudotime_Bl6Cast.xlsx  (149,209 B)
man/
  bb_mean.Rd  (1,845 B)
  bb_var.Rd  (2,069 B)
  calc_mad.Rd  (397 B)
  correct_theta.Rd  (1,280 B)
  estim_bbparams.Rd  (1,399 B)
  estim_delta.Rd  (1,028 B)
  geBoxplot.Rd  (430 B)
  glob_disp.Rd  (1,244 B)
  group_mean.Rd  (1,592 B)
  group_var.Rd  (1,664 B)
  make_plotdf_simul.Rd  (1,044 B)
  makedf.Rd  (554 B)
  plot_MA.Rd  (750 B)
  plot_disp.Rd  (393 B)
  plot_disp_fit_mean.Rd  (500 B)
  plot_disp_fit_theta.Rd  (498 B)
  plot_distr.Rd  (468 B)
  plot_exp_disp.Rd  (516 B)
  plot_glob_params.Rd  (1,140 B)
  plot_theta_density.Rd  (470 B)
vignettes/
  .gitignore  (79 B)
  allelic_imbalance.Rmd  (16,318 B)
  allelic_variance.Rmd  (10,431 B)
  differential_ASE.Rmd  (15,099 B)
```

### README

**`README.md`**

```markdown
# ASPEN

A statistical method to analyze allele-specific expression (ASE) data. ASPEN estimates the mean and dispersion parameters of the beta-binomial distribution from allelic counts.
 Then, it models allelic dispersion as a function of total gene expression and shrinks the estimated dispersion toward the expected values using the Bayesian hierarchical framework. 
            
ASPEN can be used to 
- identify genes with allelic imbalance;
- identify genes with allelic dispersion deviating from the expected for the genes with similar expression levels;
- identify genes with changes in their allelic distribution across the groups;
- identify genes with changes in their allelic variation across the group.

## Installation
```
if(!require(devtools)) install.packages("devtools")
library(devtools)

devtools::install_github("ewonglab/ASPEN")
```

## Quick start
```
library(ASPEN)
#loading reference allele and total count matrices
data("Bl6_Cast_a1")
data("Bl6_Cast_tot")

#estimating beta-binomial distribution parameters
bb_init_params <- estim_bbparams(Cast_B6_a1, Cast_B6_tot, min_cells = 5, cores = 6)

#shrinking dispersion
shrink_pars <- correct_theta(bb_init_params, delta_set = 50, N_set = 30, thetaFilter = 0.001)

#preparing a list of genes that are excluded from the reference allele mapping bias evaluation
load_file <- system.file("extdata", "mm10_genesXY.txt", package = "ASPEN")
genesXY <- read.table(load_file)
load_file <- system.file("extdata", "mm10_imprinted_genes.xlsx", package = "ASPEN")
genesIMPR <- read.xlsx(load_file, colNames = T)
genes2remove <- c(genesXY$V1, genesIMPR$imprinted.genes)

#evaluating reference allele bias
global_estims <- glob_disp(Cast_B6_a1, Cast_B6_tot, genes.excl = genes2remove, min_counts = 5)

bb_mean_res <- bb_mean(Cast_B6_a1, Cast_B6_tot,
                       shrink_pars, min_cells = 5,
                       min_counts = 5, glob_params = global_estims)
```

## Tutorials

For the step-by-step guide on how to use ASPEN, please see [ASPEN tutorial](https://ewonglab.github.io/ASPEN/) 

## Code from the main manuscript

A repository with the code to reproduce analyses from the ASPEN [manuscript](https://www.biorxiv.org/content/10.1101/2025.04.16.649227v1) can be found [here](https://github.com/ewonglab/ASPEN_manuscript/)


```

### Environment manifests

**`DESCRIPTION`**

```
Package: ASPEN
Title: Quantifying allele-specific expression (ASE) in single-cell RNA-seq
Version: 1.2.4
Authors@R: 
    c(person("Veronika", "Petrova", ,"v.petrova@victorchang.edu.au", role = c("aut", "cre"),
           comment = c(ORCID = "YOUR-ORCID-ID")),
      person("Muqing", "Niu", ,"muqing.niu@victorchang.edu.au", role = c("aut"),
           comment = c(ORCID = "YOUR-ORCID-ID")),
      person("Thomas", "Vierbuchen", ,"vierbuct@mskcc.org", role = c("aut"),
           comment = c(ORCID = "YOUR-ORCID-ID")),
      person("Emily", "Wong", ,"e.wong@victorchang.edu.au", role = c("aut"),
           comment = c(ORCID = "YOUR-ORCID-ID")))
Description: A statistical method to analyze allele-specific expression (ASE) data. ASPEN estimates the mean and dispersion parameters of the beta-binomial distribution from allelic counts.
            Then, it models allelic dispersion as a function of total gene expression and shrinks the estimated dispersion toward the expected values using the Bayesian hierarchical framework. 
             ASPEN can be used to (i) identify genes with allelic imbalance (those with mean allelic ratio deviating from the theoretical value of 0.5); 
             (ii) identify genes with allelic dispersion deviating from the expected for the genes with similar expression levels;
            (iii) identify genes with changes in their allelic distribution across the groups; (iv) identify genes with changes in their allelic variation across the group.
License: `use_mit_license()`
Encoding: UTF-8
Roxygen: list(markdown = TRUE)
RoxygenNote: 7.3.2
Imports: doParallel, 
         locfit, 
         ggplot2, 
         ggthemes, 
         ggsci, 
         ggpointdensity, 
         ggExtra, 
         ggrepel, 
         ggpubr, 
         foreach, 
         assertthat, 
         parallel, 
         iterators, 
         zoo, 
         dplyr, 
         data.table, 
         VGAM,
         tidyverse
Depends: doParallel, 
         locfit, 
         ggplot2, 
         ggthemes, 
         ggsci, 
         ggpointdensity, 
         ggExtra, 
         ggrepel, 
         ggpubr, 
         foreach, 
         assertthat, 
         parallel, 
         iterators, 
         zoo, 
         dplyr, 
         data.table, 
         VGAM,
         tidyverse,
         R (>= 2.10)
LazyData: true
Suggests: 
    knitr,
    rmarkdown
VignetteBuilder: knitr
URL: https://ewonglab.github.io/ASPEN/

```

## Repository — `github__ewonglab__ASPEN_manuscript`

### Layout

```
LICENSE  (1,065 B)
README.md  (121 B)
aspen_output/
  README.md  (1 B)
  brain_organoids/
    Bl6Cast/
    README.md  (1 B)
  simulated/
    README.md  (1 B)
    bb_test_res_iter1.rds  (3,514,588 B)
    bb_test_res_iter1_additional.rds  (1,583,344 B)
    bb_test_res_iter2.rds  (3,968,272 B)
    bb_test_res_iter2_additional.rds  (1,586,955 B)
    bb_test_res_iter3.rds  (3,956,025 B)
    bb_test_res_iter3_additional.rds  (1,582,290 B)
    bb_test_res_iter4.rds  (3,968,376 B)
    bb_test_res_iter4_additional.rds  (1,587,422 B)
    bb_test_res_iter5.rds  (3,969,833 B)
    bb_test_res_iter5_additional.rds  (1,588,489 B)
    scdali_hom_pval_iter1.rds  (260,415 B)
    scdali_hom_pval_iter2.rds  (255,374 B)
    scdali_hom_pval_iter3.rds  (255,342 B)
    scdali_hom_pval_iter4.rds  (255,450 B)
    scdali_hom_pval_iter5.rds  (255,330 B)
    simul_pseudot_change_ASPENdyn.rds  (2,007,872 B)
  tcells/
    README.md  (1 B)
    tcells_allelicimb_bulk.xlsx  (6,775,590 B)
    tcells_lcmv_ASPEN.xlsx  (435,656 B)
    tcells_lcmv_ASPEN_pseudobulk.xlsx  (1,623,557 B)
    tcells_lcmv_ASPENdyn.xlsx  (53,636 B)
    tcells_lcmv_ASPENmean.xlsx  (367,321 B)
    tcells_lcmv_ASPENmeanvar_nochrX.xlsx  (376,718 B)
data/
  README.md  (1 B)
  brain_organoids/
    Bl6Cast/
    Bl6Spret/
    README.md  (1 B)
  simulated/
    README.md  (1 B)
    a1_counts_pseudot_hvg2000.rds  (5,137,546 B)
    sim_tot_hvg2000.rds  (6,651,799 B)
    sim_tot_hvg2000_sce.rds  (2,550,883 B)
    tot_counts_pseudot_hvg2000.rds  (2,396,499 B)
  tcells/
    README.md  (1 B)
    merged_tcells_a1_sce.rds  (2,848,671 B)
    merged_tcells_tot_sce.rds  (4,381,761 B)
misc/
  NAP_genes.xlsx  (12,242 B)
  README.md  (1 B)
  SFARI-genes.csv  (135,924 B)
  Some_imprinted_genes.xlsx  (9,379 B)
  cells_pass_filter.xlsx  (1,824,500 B)
  genes_essential_Tcells.xlsx  (48,646 B)
  mm10_genesXY.txt  (21,156 B)
notebooks/
  Figure2.ipynb  (599,554 B)
  Figure3.ipynb  (1,700,534 B)
  Figure4.ipynb  (1,966,314 B)
  Figure5.ipynb  (828,189 B)
  Figure6.ipynb  (895,075 B)
  README.md  (1 B)
```

### README

**`README.md`**

```markdown
# ASPEN_manuscript
This repository includes the code to analyze datasets and to generate the figures for the ASPEN paper

```

**`aspen_output/README.md`**

```markdown


```

### Environment manifests

**None.** No `requirements.txt`, `environment.yml`, `pyproject.toml`,
`DESCRIPTION`, `renv.lock` or `Dockerfile` anywhere in the clone — which
is the `environment_specification` question answered.

