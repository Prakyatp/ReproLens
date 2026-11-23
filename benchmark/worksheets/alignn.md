# Tier-2 annotation worksheet — `alignn`

Source: `data/papers/alignn.pdf` · 27 segment(s) · generated 2026-11-14

> **This worksheet contains no findings.** Everything below is the paper's own
> text or the repository's own files, quoted verbatim with provenance. It
> deliberately carries no score, no severity, no resource verdict and no
> extracted identifier, because this record is the ground truth ReproLens is
> graded against: if the app's answers reached the annotator, the agreement
> number would be measuring the app against itself. Read the quotes and
> decide. Where the quotes are not enough, open the paper.

Fill in `benchmark/papers/alignn.json`, then:

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

    1
    Atomistic Line Graph Neural Network for Improved Materials Property
    Predictions
    Kamal Choudhary1,2,3,*, Brian DeCost1,*
    1 Materials Measurement Laboratory, National Institute of Standards and Technology, Gaithersburg, MD, 20899,
    USA.
    2 Theiss Research, La Jolla, California, 92037, USA.
    3 DeepMaterials LLC, Silver Spring, MD, 20906, USA.
    * These authors contributed equally to this work
    Abstract:
    Graph neural networks (GNN) have been shown to provide substantial performance improvements
    for atomistic material representation and modeling compared with descriptor-based machine
    learning models. While most existing GNN models for atomistic predictions are based on atomic
    distance information, they do not explicitly incorporate bond angles, which are critical for
    distinguishing many atomic structures. Furthermore, many material properties are known to be
    sensitive to slight changes in bond angles. We present an Atomistic Line Graph Neural Network
    (ALIGNN), a GNN architecture that performs message passing on both the interatomic bond graph
    and its line graph corresponding to bond angles. We demonstrate that angle information can be

## Where the paper's own sections are

| page | label | heading as printed |
| --- | --- | --- |
| 2 | `background` | Introduction |
| 3 | `results` | Results and discussion |
| 3 | `other` | A. Atomistic graph representation |
| 4 | `other` | B. Atomistic line graph representation |
| 5 | `other` | C. Edge gated graph convolution |
| 6 | `other` | D. ALIGNN update |
| 7 | `other` | E. Overall model architecture and training |
| 7 | `other` | Parameter Value ALIGNN layers |
| 8 | `other` | F. Model performance |
| 12 | `other` | Property Units MAD CFID CGCNN ALIGNN MAD: |
| 12 | `other` | MAE |
| 14 | `other` | Model Threshold ALIGNN |
| 15 | `other` | Target Units SchNet MEGNet DimeNet++ ALIGNN |
| 15 | `other` | G. Model analysis |
| 21 | `methods` | Methods |
| 21 | `other` | A: JARVIS-DFT dataset |
| 22 | `other` | B. ALIGNN model implementation and training |
| 23 | `acknowledgments` | Acknowledgements: |
| 23 | `code_availability` | Code availability: |
| 23 | `author_contributions` | Contributions: |
| 23 | `declarations` | Competing interests: |
| 23 | `data_availability` | Data availability: |
| 24 | `references` | References: |
| 27 | `other` | Figure captions: |

## Availability statements, verbatim

### `code_availability` — page 23

> Code availability: The code and full model and training configurations used in this work are available on GitHub at https://github.com/usnistgov/alignn, along with general tooling at https://github.com/usnistgov/jarvis .

### `data_availability` — page 23

> Data availability: All data used in this work is available at Figshare link https://figshare.com/collections/ALIGNN_data/5429274. During the training these datasets are accessed using JARVIS-Tools’s figshare module.

## Figure and table captions

A caption is where a result's inputs get named, which is the
`result_traceability` question.

- p5: Figure 1: Schematic showing undirected crystal graph representation and corresponding line graph construction for a SiO4 polyhedron. For simplicity, only Si-O bonds are illustrated. The ALIGNN convolution layer alternates between message passing on the bond graph (left) and its line graph (or bond adjacency graph, right).
- p7: Figure 2: Schematic of the ALIGNN layer structure. The ALIGNN layer first performs edge- gated graph convolution on the line graph to update pair and triplet features. The newly updated pair features are propagated to the edges of the direct graph and further updated with the atom features in a second edge-gated graph convolution applied to the direct graph.
- p7: Table 1: ALIGNN model configuration used for both solid state and molecular machine learning models.
- p9: Table 2: Test set performance on the Materials Project dataset. Predictions on test set are shown in parity plots in Supplementary Figure S1 and Supplementary Figure S2.
- p12: Table 3: Regression model performances on JARVIS-DFT dataset for 29 properties using CFID, CGCNN and ALIGNN models on 55722 materials. Predictions on test set are shown in
- p12: Supplementary Figure S3 to Supplementary Figure S31. Property Units MAD CFID CGCNN ALIGNN MAD: MAE Formation energy eV(atom)^-1
- p14: Table 4: Classification task ROC AUC performance on JARVIS-DFT dataset for ALIGNN models. The ROC curve plots for these models are provided in Supplementary Fig. S32 to
- p15: Table 5: Regression model performances on QM9 dataset for 11 properties using ALIGNN. These models were trained with same parameters as solid-state databases but for 1000 epochs.
- p15: Table 1 for JARVIS-DFT OptB88vdW formation energies and bandgaps respectively. We find that without any graph convolution layers the MAE for the formation energy and bandgap are 1248.5 % and 453.6 % higher than the default model. Adding even a single ALIGNN or GCN
- p16: Figure 6 shows in detail the tradeoff between the performance benefit of including ALIGNN layers and their computational overhead relative to GCN layers. Per-epoch timing for each configuration is reported in Supplementary Table 2. All GCN-only configurations (annotated with the number of GCN layers) are on the low-computation portion of the pareto frontier, but the high-accuracy portion of the pareto frontier is dominated by ALIGNN/GCN combinations with at least two ALIGNN updates. The ALIGNN-2/GCN-2 configuration obtains peak performance (again,
- p17: Figure 3: ALIGNN layer study performance tradeoff, JARVIS-DFT formation energy target. This layer ablation study clearly demonstrates that inclusion of bond angle information and propagation of bond and pair features through the node updates improves the generalization ability of atomistic GCN models. This is satisfying from a materials science perspective, as interatomic bonding theory clearly motivates the notion that inclusion of bond angles should improve accuracy of the model.
- p17: Supplementary Table 3, we observe that the marginal performance from increasing the hidden features saturates at 256 for both properties. Supplementary Table 4 shows that the number of edge input features is optimal at 80 for formation energy model, while for the bandgap model performance saturates at 40. Similarly, embedding features are optimized at 64 for formation
- p18: Supplementary Table 6. We observe that the default node attributes have the lowest MAE. Next, we study time taken per epoch of several models for QM9 and JARVIS-DFT formation energy dataset in Supplementary Table 7. To help facilitate fair comparison, we train all models with the same computational resources using the reference implementations and configurations reported in the literature. We note that the timing code for the reference implementations of different methods may include differing amounts of overhead. For example, the ALIGNN timings
- p19: Figure 3 indicates that switching from the default configuration of 4 layers each of ALIGNN and GCN updates to 2 layers each could offer a speedup of ~1.5x with negligible reduction in accuracy.
- p19: Supplementary Table 9) targets. We perform the cross-validation splitting procedure by merging the standard JARVIS-DFT train and validation sets and randomly sampling without replacement Ntrain training samples and 5000 validation samples. The learning curve study shows no sign of diminishing marginal returns for additional data up to the full size of the JARVIS-DFT dataset.
- p20: Figure 4: learning curve for JARVIS-DFT formation energy regression target. Blue markers indicate validation set MAE scores for individual cross-validation iterates. Error bars indicate the mean cross-validation MAE +/- one standard error of the mean.
- p22: Supplementary Table 10. The random search results indicate that model performance is most highly sensitive to the learning rate, weight decay, and convolution layer width, and beyond a relatively low threshold is insensitive to the sizes of the initial feature embedding layers.
- p27: Figure 1: Schematic showing undirected crystal graph representation and corresponding line graph construction for a SiO4 polyhedron. For simplicity, only Si-O bonds are illustrated. The ALIGNN convolution layer alternates between message passing on the bond graph (left) and its line graph (or bond adjacency graph, right).
- p27: Figure 2: Schematic of the ALIGNN layer structure. The ALIGNN layer first performs edge- gated graph convolution on the line graph to update pair and triplet features. The newly updated pair features are propagated to the edges of the direct graph and further updated with the atom features in a second edge-gated graph convolution applied to the direct graph.
- p27: Figure 3: ALIGNN layer study performance tradeoff, JARVIS-DFT formation energy target.
- p27: Figure 4: learning curve for JARVIS-DFT formation energy regression target. Blue markers indicate validation set MAE scores for individual cross-validation iterates. Error bars indicate the mean cross-validation MAE +/- one standard error of the mean.

## Repository — `github__usnistgov__alignn`

### Layout

```
.gitignore  (1,825 B)
.pre-commit-config.yaml  (1,030 B)
LICENSE.rst  (1,878 B)
README.md  (35,640 B)
alignn/
  __init__.py  (48 B)
  cli.py  (1,872 B)
  config.py  (5,075 B)
  data.py  (17,493 B)
  dataset.py  (4,924 B)
  examples/
    sample_data/
    sample_data_ff/
    sample_data_ff_additional/
    sample_data_ff_feats/
    sample_data_multi_prop/
  ff/
    __init__.py  (31 B)
    all_models_alignn.json  (4,439 B)
    all_models_alignn_atomwise.json  (1,957 B)
    calculators.py  (17,547 B)
    ff.py  (47,410 B)
  graphs.py  (38,565 B)
  lmdb_dataset.py  (8,201 B)
  models/
    __init__.py  (402 B)
    alignn.py  (11,405 B)
    alignn_atomwise.py  (25,363 B)
    ealignn_atomwise.py  (15,398 B)
    utils.py  (13,108 B)
  pretrained.py  (14,832 B)
  profiler.py  (2,452 B)
  run_alignn_ff.py  (7,857 B)
  scripts/
    __init__.py  (27 B)
    alignn_evac.py  (4,124 B)
    all_train_cgcnn.py  (1,586 B)
    compare_cfid.py  (3,359 B)
    cubic_mat_relax.py  (1,437 B)
    data_1.json  (29,566 B)
    dataset_props.json  (1,015 B)
    defect.py  (2,188 B)
    early_stopping_checker.py  (1,442 B)
    ev_curve.py  (5,445 B)
    ev_curve_comp.py  (1,593 B)
    final_model.py  (1,340 B)
    graph_viz.py  (382 B)
    make_test_split_cross_pred.py  (1,923 B)
    plot_ff_results.py  (4,270 B)
    plot_phonons_ff.py  (2,022 B)
    predict.py  (1,192 B)
    predict_db.py  (2,283 B)
    predict_db_all.py  (4,631 B)
    train_all_hmof.py  (1,315 B)
    train_all_hpov.py  (1,297 B)
    train_all_jv.py  (1,725 B)
    train_all_jv_class.py  (1,751 B)
    train_all_jv_dal.py  (1,737 B)
    train_all_mp.py  (1,376 B)
    train_all_oqmd.py  (1,413 B)
    train_all_pdbbind.py  (1,242 B)
    train_all_qetb.py  (1,427 B)
    train_all_qm9_jctc.py  (1,336 B)
    train_all_qmof.py  (1,411 B)
    train_cgcnn_repo.py  (1,924 B)
    train_edos_pdos.py  (1,235 B)
    train_megnet.py  (4,257 B)
  tests/
    test_alignn_ff.py  (4,598 B)
    test_eprop.py  (4,725 B)
    test_force_reduction.py  (8,358 B)
    test_prop.py  (7,038 B)
  tex/
    MP.PNG  (20,849 B)
    alignn2.png  (173,284 B)
    alignn2.tex  (5,007 B)
    animation.gif  (338,408 B)
    hMOF.PNG  (53,499 B)
    jalignn.PNG  (158,495 B)
    jv.PNG  (103,768 B)
    jv2.PNG  (88,556 B)
    jvclass.PNG  (62,036 B)
    qm9.PNG  (65,291 B)
    schematic_lg.jpg  (77,978 B)
  train.py  (36,014 B)
  train_alignn.py  (14,547 B)
  train_props.py  (5,816 B)
  utils.py  (4,573 B)
environment.yml  (9,295 B)
pyproject.toml  (295 B)
setup.py  (1,557 B)
```

### README

**`README.md`**

```markdown
![alt text](https://github.com/usnistgov/alignn/actions/workflows/main.yml/badge.svg)
[![codecov](https://codecov.io/gh/usnistgov/alignn/branch/main/graph/badge.svg?token=S5X4OYC80V)](https://codecov.io/gh/usnistgov/alignn)
[![PyPI version](https://badge.fury.io/py/alignn.svg)](https://badge.fury.io/py/alignn)
![GitHub tag (latest by date)](https://img.shields.io/github/v/tag/usnistgov/alignn)
![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/usnistgov/alignn)
![GitHub commit activity](https://img.shields.io/github/commit-activity/y/usnistgov/alignn)
[![Downloads](https://pepy.tech/badge/alignn)](https://pepy.tech/project/alignn)
<!--
[![PWC](https://img.shields.io/endpoint.svg?url=https://paperswithcode.com/badge/atomistic-line-graph-neural-network-for/formation-energy-on-materials-project)](https://paperswithcode.com/sota/formation-energy-on-materials-project?p=atomistic-line-graph-neural-network-for)
[![PWC](https://img.shields.io/endpoint.svg?url=https://paperswithcode.com/badge/atomistic-line-graph-neural-network-for/band-gap-on-materials-project)](https://paperswithcode.com/sota/band-gap-on-materials-project?p=atomistic-line-graph-neural-network-for)
[![PWC](https://img.shields.io/endpoint.svg?url=https://paperswithcode.com/badge/atomistic-line-graph-neural-network-for/formation-energy-on-qm9)](https://paperswithcode.com/sota/formation-energy-on-qm9?p=atomistic-line-graph-neural-network-for)
[![PWC](https://img.shields.io/endpoint.svg?url=https://paperswithcode.com/badge/atomistic-line-graph-neural-network-for/formation-energy-on-jarvis-dft-formation)](https://paperswithcode.com/sota/formation-energy-on-jarvis-dft-formation?p=atomistic-line-graph-neural-network-for)
[![PWC](https://img.shields.io/endpoint.svg?url=https://paperswithcode.com/badge/atomistic-line-graph-neural-network-for/band-gap-on-jarvis-dft)](https://paperswithcode.com/sota/band-gap-on-jarvis-dft?p=atomistic-line-graph-neural-network-for)
-->

# Table of Contents
* [Introduction](#intro)
* [Installation](#install)
* [Examples](#example)
* [Pre-trained models](#pretrained)
* [JARVIS-ALIGNN webapp](#webapp)
* [ALIGNN-FF & ASE Calculator](#alignnff)
* [Peformances on a few datasets](#performances)
* [Useful notes](#notes)
* [References](#refs)
* [How to contribute](#contrib)
* [Correspondence](#corres)
* [Funding support](#fund)

<a name="intro"></a>
# ALIGNN & ALIGNN-FF (Introduction)
The Atomistic Line Graph Neural Network (https://www.nature.com/articles/s41524-021-00650-1)  introduces a new graph convolution layer that explicitly models both two and three body interactions in atomistic systems. This is achieved by composing two edge-gated graph convolution layers, the first applied to the atomistic line graph *L(g)* (representing triplet interactions) and the second applied to the atomistic bond graph *g* (representing pair interactions).

Atomisitic line graph neural network-based FF (ALIGNN-FF) (https://pubs.rsc.org/en/content/articlehtml/2023/dd/d2dd00096b ) can be used to model both structurally and chemically diverse systems with any combination of 89 elements from the periodic table, specially for structural optimization. To train the ALIGNN-FF model, we have used the JARVIS-DFT dataset which contains around 75000 materials and 4 million energy-force entries, out of which 307113 are used in the training. These models can be further finetuned, or new models can be developed from scratch on a new dataset.



![ALIGNN layer schematic](https://github.com/usnistgov/alignn/blob/develop/alignn/tex/schematic_lg.jpg)

<a name="install"></a>
Installation
-------------------------
First create a conda environment:
Install miniconda environment from https://conda.io/miniconda.html
Based on your system requirements, you'll get a file something like 'Miniconda3-latest-XYZ'.

Now,

```
bash Miniconda3-latest-Linux-x86_64.sh (for linux)
bash Miniconda3-latest-MacOSX-x86_64.sh (for Mac)
```
Download 32/64 bit python 3.10 miniconda exe and install (for windows)

#### Method 1 (conda based installation, recommended) 

Now, let's make a conda environment, say "my_alignn", choose other name as you like::
```
conda create --name my_alignn python=3.10 -y
conda activate my_alignn
conda install dgl=2.1.0 pytorch torchvision torchaudio pytorch-cuda -c pytorch -c nvidia
conda install alignn -y
```



#### Method 2 (GitHub based installation)

You can laso install a development version of alignn by cloning the repository and installing in place with pip:

```
conda create --name my_alignn python=3.10 -y
conda activate my_alignn
conda install dgl=2.1.0 pytorch torchvision torchaudio pytorch-cuda -c pytorch -c nvidia
git clone https://github.com/usnistgov/alignn
cd alignn
python -m pip install -e .
```


#### Method 3 (using pypi):

As an alternate method, ALIGNN can also be installed using `pip`. Note, we have received several messages regarding dgl installation issues. You can look into dgl installation [here](https://www.dgl.ai/pages/start.html). Example for PyTorch 2.1+CUDA 12.1+Pip(Stable)+Windows:
```
pip install  -q dgl -f https://data.dgl.ai/wheels/torch-2.1/cu121/repo.html
pip install alignn
```

With no GPU/CUDA:
```
pip install -q dgl -f https://data.dgl.ai/wheels/torch-2.1/repo.html
pip install alignn
```

You can find out installation examples in Google Colab notebooks below

<a name="example"></a>
Examples
---------


| Notebooks                                                                                                                                      | Google&nbsp;Colab                                                                                                                                        | Descriptions                                                                                                                                                                                                                                                                                  
... [29,618 more characters]
```

### Environment manifests

**`environment.yml`**

```
name: my_alignn
channels:
  - conda-forge
  - defaults
dependencies:
  - _libgcc_mutex=0.1=conda_forge
  - _openmp_mutex=4.5=2_gnu
  - alsa-lib=1.2.11=hd590300_1
  - archspec=0.2.2=pyhd8ed1ab_0
  - attr=2.5.1=h166bdaf_1
  - babel=2.14.0=pyhd8ed1ab_0
  - boltons=23.1.1=pyhd8ed1ab_0
  - brotli=1.1.0=hd590300_1
  - brotli-bin=1.1.0=hd590300_1
  - brotli-python=1.1.0=py310hc6cd4ac_1
  - bzip2=1.0.8=hd590300_5
  - c-ares=1.24.0=hd590300_0
  - ca-certificates=2024.2.2=hbcca054_0
  - cached-property=1.5.2=hd8ed1ab_1
  - cached_property=1.5.2=pyha770c72_1
  - cairo=1.18.0=h3faef2a_0
  - certifi=2024.2.2=pyhd8ed1ab_0
  - cffi=1.16.0=py310h2fee648_0
  - charset-normalizer=3.3.2=pyhd8ed1ab_0
  - click=8.1.7=unix_pyh707e725_0
  - codecov=2.1.13=pyhd8ed1ab_0
  - colorama=0.4.6=pyhd8ed1ab_0
  - conda=23.11.0=py310hff52083_1
  - conda-libmamba-solver=23.12.0=pyhd8ed1ab_0
  - conda-package-handling=2.2.0=pyh38be061_0
  - conda-package-streaming=0.9.0=pyhd8ed1ab_0
  - contourpy=1.2.0=py310hd41b1e2_0
  - coverage=7.4.4=py310h2372a71_0
  - cycler=0.12.1=pyhd8ed1ab_0
  - dbus=1.13.6=h5008d03_3
  - distro=1.8.0=pyhd8ed1ab_0
  - exceptiongroup=1.2.0=pyhd8ed1ab_2
  - expat=2.6.2=h59595ed_0
  - fmt=10.1.1=h00ab1b0_1
  - font-ttf-dejavu-sans-mono=2.37=hab24e00_0
  - font-ttf-inconsolata=3.000=h77eed37_0
  - font-ttf-source-code-pro=2.038=h77eed37_0
  - font-ttf-ubuntu=0.83=h77eed37_1
  - fontconfig=2.14.2=h14ed4e7_0
  - fonts-conda-ecosystem=1=0
  - fonts-conda-forge=1=0
  - fonttools=4.50.0=py310h2372a71_0
  - freetype=2.12.1=h267a509_2
  - gettext=0.21.1=h27087fc_0
  - ghp-import=2.1.0=pyhd8ed1ab_0
  - glib=2.80.0=hf2295e7_0
  - glib-tools=2.80.0=hde27a5a_0
  - graphite2=1.3.13=h58526e2_1001
  - gst-plugins-base=1.22.9=h8e1006c_0
  - gstreamer=1.22.9=h98fc4e7_0
  - h5py=3.10.0=nompi_py310h65828d5_101
  - harfbuzz=8.3.0=h3d44ed6_0
  - hdf5=1.14.3=nompi_h4f84152_100
  - icu=73.2=h59595ed_0
  - idna=3.6=pyhd8ed1ab_0
  - importlib-metadata=7.1.0=pyha770c72_0
  - iniconfig=2.0.0=pyhd8ed1ab_0
  - jarvis-tools=2024.3.24=pyhd8ed1ab_0
  - jinja2=3.1.3=pyhd8ed1ab_0
  - joblib=1.3.2=pyhd8ed1ab_0
  - jsonpatch=1.33=pyhd8ed1ab_0
  - jsonpointer=2.4=py310hff52083_3
  - keyutils=1.6.1=h166bdaf_0
  - kiwisolver=1.4.5=py310hd41b1e2_1
  - krb5=1.21.2=h659d440_0
  - lame=3.100=h166bdaf_1003
  - lcms2=2.16=hb7c19ff_0
  - ld_impl_linux-64=2.40=h41732ed_0
  - lerc=4.0.0=h27087fc_0
  - libaec=1.1.3=h59595ed_0
  - libarchive=3.7.2=h2aa1ff5_1
  - libblas=3.9.0=21_linux64_openblas
  - libbrotlicommon=1.1.0=hd590300_1
  - libbrotlidec=1.1.0=hd590300_1
  - libbrotlienc=1.1.0=hd590300_1
  - libcap=2.69=h0f662aa_0
  - libcblas=3.9.0=21_linux64_openblas
  - libclang=15.0.7=default_hb11cfb5_4
  - libclang13=15.0.7=default_ha2b6cf4_4
  - libcups=2.3.3=h4637d8d_4
  - libcurl=8.5.0=hca28451_0
  - libdeflate=1.19=hd590300_0
  - libedit=3.1.20191231=he28a2e2_2
  - libev=4.33=hd590300_2
  - libevent=2.1.12=hf998b51_1
  - libexpat=2.6.2=h59595ed_0
  - libffi=3.4.2=h7f98852_5
  - libflac=1.4.3=h59595ed_0
  -
... [6,295 more characters]
```

**`pyproject.toml`**

```
[build-system]
requires = ["setuptools >= 40.6.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.isort]
multi_line_output = 3
include_trailing_comma = true
force_grid_wrap = 0
use_parentheses = true
ensure_newline_before_comments = true
line_length = 79

[tool.black]
line_length = 79

```

**`setup.py`**

```
"""ALIGNN: Atomistic LIne Graph Neural Network.

https://jarvis.nist.gov.
"""

import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="alignn",
    version="2025.4.1",
    author="Kamal Choudhary, Brian DeCost",
    author_email="kamal.choudhary@nist.gov",
    description="alignn",
    install_requires=[
        "numpy<2.0",
        # "numpy>=1.19.5,<2.0.0",
        "scipy>=1.6.1",
        "jarvis-tools>=2021.07.19",
        "torch<=2.2.1",
        "mpmath<=1.3.0",
        "dgl<=1.1.1",
        "spglib>=2.0.2",
        "scikit-learn>=0.22.2",
        "matplotlib>=3.4.1",
        "tqdm>=4.60.0",
        "pandas>=1.2.3",
        "pydantic>=1.8.1",
        "pydantic-settings",
        "flake8>=3.9.1",
        "pycodestyle>=2.7.0",
        "pydocstyle>=6.0.0",
        "pyparsing>=2.2.1,<3",
        "ase",
        "lmdb",
    ],
    scripts=[
        "alignn/pretrained.py",
        "alignn/train_alignn.py",
        "alignn/run_alignn_ff.py",
    ],
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/usnistgov/alignn",
    packages=setuptools.find_packages(),
    package_data={
        "alignn.ff": [
            "all_models_alignn.json",
            "all_models_alignn_atomwise.json",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
)

```

