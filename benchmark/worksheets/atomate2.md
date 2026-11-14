# Tier-2 annotation worksheet — `atomate2`

Source: `data/xml/atomate2.xml` · 11 segment(s) · generated 2026-11-14

> **This worksheet contains no findings.** Everything below is the paper's own
> text or the repository's own files, quoted verbatim with provenance. It
> deliberately carries no score, no severity, no resource verdict and no
> extracted identifier, because this record is the ground truth ReproLens is
> graded against: if the app's answers reached the annotator, the agreement
> number would be measuring the app against itself. Read the quotes and
> decide. Where the quotes are not enough, open the paper.

Fill in `benchmark/papers/atomate2.json`, then:

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

    Front matter
    Digit Discov Digit Discov 1126 rscsd 9918351186906676 DD Digital Discovery 2635-098X pmc-is-collection-domain yes pmc-collection-title Royal Society of Chemistry PMC12210224 PMC12210224.1 12210224 122

## Where the paper's own sections are

| page | label | heading as printed |
| --- | --- | --- |
| 1 | `front_matter` | Front matter |
| 2 | `background` | Introduction |
| 3 | `other` | Atomate2 design philosophy and overview |
| 4 | `other` | Calculators |
| 5 | `other` | Workflows |
| 6 | `conclusions` | Conclusions and future work |
| 7 | `author_contributions` | Author contributions |
| 8 | `declarations` | Conflicts of interest |
| 9 | `acknowledgments` | Acknowledgments |
| 10 | `data_availability` | Data availability |
| 11 | `references` | References |

## Availability statements, verbatim

### `data_availability` — page 10

> Data availability Data availability The code for atomate2 can be found at https://github.com/materialsproject/atomate2 and the documentation for it can be found at https://materialsproject.github.io/atomate2/ . The version of the code employed for this study is version 0.0.21. The Zenodo DOI corresponding to the code is https://doi.org/10.5281/zenodo.10677080 . The CECAM workshop resources can be found on https://www.cecam.org/workshop-details/automated-ab-initio-workflows-with-jobflow-and-atomate2-1276 , https://lhumos.org/collection/0/680bb4d7e4b0f0d2028027ce , https://lhumos.org/collection/0/680bb4d3e4b0f0d2028027c9 , https://lhumos.org/collection/0/680bb4d0e4b0f0d2028027c5 , https://lhumos.org/collection/0/680bb4c7e4b0f0d2028027c1 . The community support for atomate2 can obtained at https://matsci.org/c/atomate/atomat2/55 and via the Issues section of the atomate2 GitHub repository. There is no separate dataset to declare.

## Figure and table captions

A caption is where a result's inputs get named, which is the
`result_traceability` question.

None recognised.

## Repository — `github__materialsproject__atomate2`

### Layout

```
.codecov.yml  (205 B)
.gitattributes  (207 B)
.gitignore  (866 B)
.pre-commit-config.yaml  (1,484 B)
ADMIN.md  (364 B)
CHANGELOG.md  (59,761 B)
CODE_OF_CONDUCT.md  (2,844 B)
CONTRIBUTING.md  (3,022 B)
LICENSE  (2,419 B)
README.md  (9,959 B)
applications/
  __init__.py  (312 B)
  mof.py  (15,395 B)
citation.cff  (6,490 B)
docs/
  _static/
    MgO-bandstructure.png  (92,463 B)
    MgO-dos.png  (93,093 B)
    custom.css  (1,487 B)
    docs_store_Si_relax.json  (31,443 B)
    example_flow.png  (369,725 B)
    fonts/
    index_api.svg  (3,519 B)
    index_contribute.svg  (2,528 B)
    index_support.svg  (1,052 B)
    index_user_guide.svg  (6,429 B)
    orcid.svg  (1,472 B)
  _templates/
    autosummary/
  about/
    changelog.md  (36 B)
    contributing.md  (39 B)
    contributors.md  (4,942 B)
    license.md  (2,510 B)
  conf.py  (5,956 B)
  dev/
    abinit_tests.md  (7,297 B)
    dev_install.md  (1,825 B)
    forcefields.md  (3,344 B)
    input_set_update_logic.png  (38,788 B)
    input_sets.md  (9,265 B)
    input_sets.png  (70,050 B)
    vasp_tests.md  (14,784 B)
    workflow_tutorial.md  (6,982 B)
  index.md  (1,880 B)
  reference/
    index.rst  (320 B)
  user/
    addons.md  (1,993 B)
    atomate-1-vs-2.md  (2,038 B)
    codes/
    docs_schemas_emmet.md  (21,581 B)
    execution.md  (4,515 B)
    fireworks.md  (2,111 B)
    index.md  (80 B)
    install.md  (20,743 B)
    jobflow-remote.md  (1,500 B)
    key_concepts_overview.md  (15,553 B)
    running-workflows.md  (5,889 B)
pyproject.toml  (9,784 B)
src/
  atomate2/
    __init__.py  (195 B)
    _version.py  (74 B)
    abinit/
    aims/
    amset/
    ase/
    cli/
    common/
    cp2k/
    forcefields/
    jdftx/
    lammps/
    lobster/
    openff/
    openmm/
    py.typed  (0 B)
    qchem/
    settings.py  (13,001 B)
    torchsim/
    utils/
    vasp/
tests/
  .pytest-split-durations  (32,519 B)
  abinit/
    __init__.py  (0 B)
    conftest.py  (11,503 B)
    flows/
    jobs/
    sets/
    test_powerups.py  (3,870 B)
  aims/
    __init__.py  (1,003 B)
    conftest.py  (8,807 B)
    species_dir/
    test_files/
    test_flows/
    test_makers/
    test_parsers/
  amset/
    test_files.py  (989 B)
  ase/
    conftest.py  (1,261 B)
    flows/
    test_jobs.py  (6,141 B)
    test_md.py  (7,415 B)
    test_neb.py  (3,490 B)
    test_utils.py  (4,555 B)
  common/
    jobs/
    schemas/
    test_files.py  (1,822 B)
    test_jobs.py  (2,997 B)
    test_settings.py  (2,477 B)
    test_utils.py  (605 B)
  conftest.py  (4,223 B)
  cp2k/
    __init__.py  (0 B)
    conftest.py  (7,187 B)
    jobs/
    schemas/
    sets/
    test_drones.py  (1,304 B)
    test_files.py  (4,887 B)
    test_powerups.py  (4,949 B)
  forcefields/
    conftest.py  (3,250 B)
    flows/
    test_jobs.py  (35,269 B)
    test_mace_field.py  (2,920 B)
    test_md.py  (13,803 B)
    test_neb.py  (3,740 B)
    test_schemas.py  (1,469 B)
    test_utils.py  (3,089 B)
  jdftx/
    __init__.py  (0 B)
    conftest.py  (5,647 B)
    jobs/
    schemas/
    sets/
  lammps/
    __init__.py  (0 B)
    conftest.py  (6,477 B)
    test_flows.py  (1,831 B)
    test_jobs.py  (3,856 B)
    test_schemas.py  (2,007 B)
    test_sets.py  (1,882 B)
  lobster/
    __init__.py  (0 B)
    test_files.py  (886 B)
  openff_md/
    __init__.py  (0 B)
    conftest.py  (2,892 B)
    test_core.py  (2,352 B)
    test_utils.py  (9,814 B)
  openmm_md/
    __init__.py  (0 B)
    conftest.py  (3,508 B)
    flows/
    jobs/
    test_utils.py  (4,025 B)
  qchem/
    conftest.py  (7,963 B)
    flows/
    freq.qin.gz  (300 B)
    jobs/
    opt.qin.gz  (312 B)
    sets/
    sp.qin.gz  (360 B)
    test_drones.py  (495 B)
    test_files.py  (1,168 B)
    test_run.py  (1,201 B)
    test_sets.py  (3,812 B)
  test_data/
    abinit/
    aims/
    common/
    cp2k/
    forcefields/
    jdftx/
    lammps/
    lobster/
    molecules/
    openff/
    openmm/
    qchem/
    qha/
    schemas/
    structures/
    symmetry_structures/
    vasp/
  torchsim/
    __init__.py  (0 B)
    conftest.py  (818 B)
    flows/
    test_core.py  (16,522 B)
  vasp/
    conftest.py  (3,536 B)
    flows/
    jobs/
    lobster/
    schemas/
    test_drones.py  (219 B)
    test_files.py  (1,565 B)
    test_powerups.py  (2,970 B)
    test_run.py  (284 B)
    test_sets.py  (12,298 B)
tutorials/
  __init__.py  (17 B)
  blob_storage.ipynb  (7,105 B)
  cte_workflow.ipynb  (29,779 B)
  force_fields/
    __init__.py  (34 B)
    phonon_workflow.ipynb  (4,885 B)
  grueneisen_workflow.ipynb  (9,599 B)
  hiphive_workflow.ipynb  (17,108 B)
  lammps_workflow.ipynb  (12,825 B)
  lobster_workflow.ipynb  (5,214 B)
  materials_project_workflows.ipynb  (18,588 B)
  mock_aims.py  (1,040 B)
  mock_lobster.py  (1,088 B)
  mock_vasp.py  (1,028 B)
  openmm_tutorial.ipynb  (15,749 B)
  pheasy_workflow.ipynb  (8,312 B)
  phonon_workflow.ipynb  (6,559 B)
  phonon_workflow_aims.ipynb  (9,637 B)
  qha_workflow.ipynb  (13,369 B)
  torchsim_tutorial.ipynb  (27,210 B)
  tutorials.md  (630 B)
```

### README

**`README.md`**

```markdown
# atomate2

[![tests](https://img.shields.io/github/actions/workflow/status/materialsproject/atomate2/testing.yml?branch=main&label=tests)](https://github.com/materialsproject/atomate2/actions?query=workflow%3Atesting)
[![code coverage](https://img.shields.io/codecov/c/gh/materialsproject/atomate2)](https://codecov.io/gh/materialsproject/atomate2)
[![pypi version](https://img.shields.io/pypi/v/atomate2?color=blue)](https://pypi.org/project/atomate2)
![supported python versions](https://img.shields.io/pypi/pyversions/atomate2)
[![Zenodo](https://img.shields.io/badge/DOI-10.5281/zenodo.10677080-blue?logo=Zenodo&logoColor=white)](https://doi.org/10.5281/zenodo.15603088)
[![This project supports Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg?logo=python&logoColor=white)](https://python.org/downloads)
[![PyPI](https://img.shields.io/pypi/dm/atomate2.svg?maxAge=2592000)](https://pypi.python.org/pypi/atomate2)

[Documentation][docs] | [PyPI][pypi] | [GitHub][github]

Atomate2 is a free, open-source software for performing complex materials science
workflows using simple Python functions. Features of atomate2 include

- It is built on open-source libraries: [pymatgen], [custodian], [jobflow], and
  [jobflow-remote] or [FireWorks].
- A library of "standard" workflows to compute a wide variety of desired materials
  properties.
- The ability scale from a single material, to 100 materials, or 100,000 materials.
- Easy routes to modifying and chaining workflows together.
- It can build large databases of output properties that you can query, analyze, and
  share in a systematic way.
- It automatically keeps meticulous records of jobs, their directories, runtime
  parameters, and more.

## Workflows

Some of the workflows available in atomate2 are:

- electronic band structures
- elastic, dielectric, and piezoelectric tensors
- one-shot electron-phonon interactions
- electronic transport using [AMSET]
- phonons using [phonopy]
- defect formation energy diagrams
- [Lobster] bonding analysis with [lobsterpy]

It is easy to customise and compose any of the above workflows.

## Quick start

Workflows in atomate2 are written using the [jobflow] library. Workflows are generated using
`Maker` objects which have a consistent API for modifying input settings and chaining
workflows together. Below, we demonstrate how to run a band structure workflow
(see the [documentation][RelaxBandStructure] for more details). In total, 4 VASP
calculations will be performed:

1. A structural optimisation.
2. A self-consistent static calculation on the relaxed geometry.
3. A non-self-consistent calculation on a uniform k-point mesh (for the density of
   states).
4. A non-self-consistent calculation on a high symmetry k-point path (for the line mode
   band structure).

```py
from atomate2.vasp.flows.core import RelaxBandStructureMaker
from jobflow import run_locally
from pymatgen.core import Structure

# construct a rock salt MgO structure
mgo_structure = Structure(
    lattice=[[0, 2.13, 2.13], [2.13, 0, 2.13], [2.13, 2.13, 0]],
    species=["Mg", "O"],
    coords=[[0, 0, 0], [0.5, 0.5, 0.5]],
)

# make a band structure flow to optimise the structure and obtain the band structure
bandstructure_flow = RelaxBandStructureMaker().make(mgo_structure)

# run the flow
run_locally(bandstructure_flow, create_folders=True)
```

Before the above code can run successfully, you'll need to

- tell pymatgen where to [find your pseudopotential files](https://pymatgen.org/installation.html#potcar-setup)
- tell atomate2 where to find your VASP binary
- (optionally) prepare an external database to store the job output

See the [installation] steps for details how to set all of this up.

In this example, we execute the workflow immediately. In many cases, you might want
to perform calculations on several materials simultaneously. To achieve this, all
atomate2 workflows can be run using the [jobflow-remote] or [FireWorks] software. See the
[jobflow-remote-specific documentation][atomate2-jobflow-remote] or [fireworks-specific documentation][atomate2_fireworks] for more details.

## Installation

Atomate2 is a Python 3.12+ library and can be installed using pip. Full installation
and configuration instructions are provided in the [installation tutorial][installation].

## Tutorials

The documentation includes comprehensive tutorials and reference information to get you
started:

- [Introduction to running workflows][running-workflows]
- [Using atomate2 with FireWorks][atomate2_fireworks]
- [Overview of key concepts][key-concepts]
- [List of VASP workflows][vasp_workflows]
- [Executable tutorials for different workflows][tutorials]

In March 2025, the first dedicated school on atomate2 (including the workflow language jobflow and the workflow manager jobflow-remote) took place, and one can access the video material here:

- [Jobflow and Jobflow-remote][videotutorial1]
- [atomate2][videotutorial2]
- [Advanced Workflows in atomate2: Part 1][videotutorial3]
- [Advanced Workflows in atomate2: Part 2][videotutorial4]

## Need help?

Ask questions about atomate2 on the [atomate2 support forum][help-forum].
If you've found an issue with atomate2, please submit a bug report on [GitHub Issues][issues].

## What’s new?

Track changes to atomate2 through the [changelog][changelog].

## Contributing

We greatly appreciate any contributions in the form of a pull request.
Additional information on contributing to atomate2 can be found [here][contributing].
We maintain a list of all contributors [here][contributors].

## License

Atomate2 is released under a modified BSD license; the full text is available [here][license].

## Acknowledgements

The development of atomate2 has benefited from many people across several research groups.
A full list of contributors is available [here][contributors].

## Citing atomate2

If you use atomate2, please cite the [following article](https://doi.org/10.1039/D5DD00019J):

```bib
@article{ganose2025_atomate
... [3,957 more characters]
```

**`tests/test_data/forcefields/nep/README.md`**

```markdown
The NEP model used for the tests is licensed under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode) and
downloaded from https://doi.org/10.5281/zenodo.10081677. Also cite the original work if you use this
specific model : https://arxiv.org/abs/2311.04732

```

### Environment manifests

**`pyproject.toml`**

```
[build-system]
requires = ["setuptools >= 42, < 85", "versioningit >= 1,< 4", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "atomate2"
description = "atomate2 is a library of materials science workflows"
readme = "README.md"
keywords = ["automated", "dft", "high-throughput", "vasp", "workflow"]
license = "BSD-3-Clause-LBNL"
authors = [{ name = "Alex Ganose", email = "alexganose@gmail.com" }]
dynamic = ["version"]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Information Technology",
    "Intended Audience :: Science/Research",
    "Intended Audience :: System Administrators",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Other/Nonlisted Topic",
    "Topic :: Scientific/Engineering",
]
requires-python = ">=3.12"
dependencies = [
    "PyYAML",
    "click",
    "custodian>=2024.4.18",
    "emmet-core>=0.87.3",
    "jobflow>=0.1.11",
    "monty>=2024.12.10",
    "numpy",
    "pydantic-settings>=2.0.3",
    "pydantic>=2.0.1",
    "pymatgen>=2024.11.13",
    "pymatgen-core>=2026.5.18",
    "pymongo<=4.19.0",
]

[project.optional-dependencies]
abinit = [
    "abipy>=0.9.3",
    "netCDF4>=1.7.4"
]
aims = ["pymatgen-io-aims>=0.0.5", "pymatgen>=2025.10.7"]
amset = ["amset>=0.4.15", "pydash"]
cclib = ["cclib>=1.8.1"]
mp = ["mp-api>=0.37.5"]
# phonopy 4.x changed force-constants/primitive-axis handling, breaking the
# phonon.save -> phonopy.load round-trip used by the Grüneisen workflow
# ("Force constants shape disagrees with crystal structure setting").
phonons = ["phonopy>=4.7.1,<5", "seekpath>=2.0.0"]
# pheasy itself is in the pheasy dependency group
pheasy = ["atomate2[phonons]", "hiphive==1.5", "numpy<=2.2"]
# phono3py computes the mode Grueneisen tensors in the thermal expansion workflow
phono3py = ["atomate2[phonons]", "phono3py>=4.7"]
hiphive = ["hiphive==1.5", "trainstation>=1.0", "atomate2[phonons]"]
lobster = ["ijson>=3.2.2", "lobsterpy>=0.6.0"]
defects = [
    "dscribe>=1.2.0",
    "pymatgen-analysis-defects>=2024.5.11",
    "python-ulid>=2.7",
]

ase = ["ase>=3.26.0"]
ase-ext = ["tblite>=0.3.0; platform_system=='Linux'"]
forcefields-demo = ["chgnet>=0.3.8","atomate2[ase]"]

torchsim = [
    "torch-sim-atomistic[symmetry]==0.6.2; python_version >= '3.12'"
]

# TorchSim's optional model backends pin to minimum versions to avoid the backend
# from being absent. We also have to keep mace separate from the generic group
# to avoid conflicts with e3nn versions. Note that the groups are different
# from the ones used for the forcefields backend.

# ALWAYS REMEMBER to update `.github/workflows/testing.yml` to reflect the
# current set of torchsim dependency groups.
torchsim-mace = [
    "torch-sim-atomistic[mace,symmetry]==0.6.2; python_version >= '3.12'"
]
# mattersim can be added to torchsim-generic once they clean their dependencies
torchsi
... [6,783 more characters]
```

