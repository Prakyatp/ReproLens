"""Regressions for the repository channel.

Every case here comes from one of the two benchmark repositories, and most of
them are bugs the first implementation had. The recurring theme is that the
repository is a second document making claims about the same work, so almost
every useful finding is a *disagreement* -- between two manifests, between a
command and the files beside it, or between the code and the paper -- and
disagreements are exactly what a reader of either document alone cannot see.
"""

from __future__ import annotations

from pathlib import Path

from reprolens.documents.figures import figure_numbers
from reprolens.repository import analysis, execution, inventory, manifests
from reprolens.repository.fetch import Checkout, FetchResult, RepoRef, resolve_refs


def checkout(tmp_path: Path, files: dict[str, str], *, slug: str = "lab/project") -> Checkout:
    owner, name = slug.split("/")
    root = tmp_path / name
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return Checkout(
        ref=RepoRef("github", owner, name),
        root=root,
        commit="0" * 40,
        committed_at="2025-01-01T00:00:00+00:00",
        fetched_at="2026-10-26T00:00:00+00:00",
        reused=False,
    )


def read_all(tmp_path: Path, files: dict[str, str]):
    found = inventory.take([checkout(tmp_path, files)])
    return found, manifests.read(found), execution.read(found)


class TestResolvingReferences:
    def test_only_git_hosts_become_repositories(self):
        refs = resolve_refs(
            [
                ("github", "github.com/mcgilldinglab/MATES"),
                ("url", "https://mates.cellcycle.org"),
                ("zenodo", "10.5281/zenodo.13738122"),
            ]
        )
        assert [r.slug for r in refs] == ["mcgilldinglab/MATES"]

    def test_a_url_into_a_repository_still_names_the_repository(self):
        refs = resolve_refs([("github", "github.com/lab/project/tree/main/scripts")])
        assert [r.slug for r in refs] == ["lab/project"]

    def test_the_same_repository_written_two_ways_is_one(self):
        refs = resolve_refs(
            [
                ("github", "https://github.com/lab/project.git"),
                ("github", "github.com/lab/project"),
            ]
        )
        assert len(refs) == 1
        assert refs[0].url == "https://github.com/lab/project.git"


class TestInventory:
    def test_a_demo_annotation_is_measured_not_just_listed(self, tmp_path):
        # LocusMasterTE's run_sample.sh takes data/annotation.gtf, which holds
        # twenty records. Nothing about the filename or its presence says that.
        records = "\n".join(
            f"chr1\thg38_rmsk\texon\t{i}\t{i + 100}\t.\t+\t.\tgene_id" for i in range(20)
        )
        found, _, _ = read_all(tmp_path, {"data/annotation.gtf": f"# header\n{records}\n"})
        annotation = found.by_kind("annotation")[0]
        assert annotation.records == 20
        assert annotation.demo_scale

    def test_a_workflow_file_is_a_manifest_and_a_config_file_is_not(self, tmp_path):
        found, _, _ = read_all(
            tmp_path, {".github/workflows/ci.yml": "on: push", "params.yml": "alpha: 1"}
        )
        kinds = {f.path: f.kind for f in found.files}
        assert kinds[".github/workflows/ci.yml"] == "manifest"
        assert kinds["params.yml"] == "config"


class TestDependencyDeclarations:
    def test_two_manifests_pinning_one_package_differently_is_a_conflict(self, tmp_path):
        # MATES: requirements.txt says torch==2.0.1, setup.py says torch==2.0.0.
        # Blueprint section 16 names this class, and neither file alone has it.
        _, found, _ = read_all(
            tmp_path,
            {
                "requirements.txt": "torch==2.0.1\nnumpy==1.25.2\n",
                "setup.py": 'setup(name="x", install_requires=["torch==2.0.0"])',
            },
        )
        assert [c.name for c in found.conflicts] == ["torch"]
        conflict = found.conflicts[0]
        assert {conflict.left_constraint, conflict.right_constraint} == {"==2.0.1", "==2.0.0"}

    def test_a_docs_requirements_copy_does_not_own_the_conflict(self, tmp_path):
        # MATES keeps a second copy under docs/ for Read the Docs. Attributing
        # the project's torch version to a documentation file is true and
        # useless, so the shallowest declaration is reported first.
        _, found, _ = read_all(
            tmp_path,
            {
                "requirements.txt": "torch==2.0.1\n",
                "docs/requirements.txt": "torch==2.0.1\nsphinx>=5.0\n",
                "setup.py": 'setup(install_requires=["torch==2.0.0"])',
            },
        )
        assert found.conflicts[0].left_source.endswith(":requirements.txt")
        # ...and the sphinx entry is not counted as a project dependency.
        assert "sphinx" not in {d.name for d in found.runtime}

    def test_one_package_declared_twice_counts_by_its_tightest_constraint(self, tmp_path):
        # LocusMasterTE asks for numpy>=1.16.3 in setup.py and numpy=1.16.3 in
        # its README. That is one dependency with a resolvable version, not one
        # good declaration and one bad one.
        _, found, _ = read_all(
            tmp_path,
            {
                "setup.py": 'setup(install_requires=["numpy>=1.16.3"])',
                "README.md": "```\nconda create -n env python=3.6 numpy=1.16.3\n```\n",
            },
        )
        assert found.distinct_pinning() == {"numpy": "pinned"}

    def test_a_lower_bound_is_not_a_pin(self, tmp_path):
        _, found, _ = read_all(tmp_path, {"setup.py": 'setup(install_requires=["numpy>=1.16.3"])'})
        assert found.distinct_pinning() == {"numpy": "bounded"}

    def test_a_readme_conda_line_declares_the_interpreter_but_not_installably(self, tmp_path):
        _, found, _ = read_all(
            tmp_path, {"README.md": "```\nconda create -n env python=3.6 future\n```\n"}
        )
        interpreter = found.interpreters[0]
        assert (interpreter.version, interpreter.pinning) == ("3.6", "pinned")
        assert interpreter.prose_only
        # And the pin is to an interpreter that is out of support.
        assert interpreter.end_of_life == "2021-12-23"

    def test_a_lower_bound_on_python_reports_no_end_of_life(self, tmp_path):
        # ">=3.8" says the project runs on supported versions too, which is a
        # different claim from "this project requires 3.8".
        _, found, _ = read_all(
            tmp_path, {"pyproject.toml": '[project]\nname = "x"\nrequires-python = ">=3.8"\n'}
        )
        assert found.interpreters[0].end_of_life is None

    def test_setup_py_is_parsed_and_never_executed(self, tmp_path):
        # LocusMasterTE's setup.py reads environment variables and cythonizes an
        # extension at import time. Importing it to read install_requires would
        # run all of that.
        _, found, _ = read_all(
            tmp_path,
            {
                "setup.py": (
                    "from os import environ\n"
                    "raise SystemExit('this must never run')\n"
                    'setup(install_requires=["pysam>=0.15.2"])\n'
                )
            },
        )
        assert [d.name for d in found.runtime] == ["pysam"]


class TestWhatTheCodeUsesVersusWhatIsDeclared:
    def test_an_r_library_call_is_a_use_not_a_declaration(self, tmp_path):
        # Recording library() as a dependency was the first thing tried, and it
        # hid the finding that matters: it made R look like a managed
        # environment because something had named every package. Nothing had
        # declared one.
        _, found, _ = read_all(
            tmp_path,
            {
                "setup.py": 'setup(install_requires=["numpy==1.0"])',
                "preprocessing.R": 'library("tidyverse")\nlibrary(optparse)\n',
            },
        )
        assert found.unmanaged_languages == ["r"]
        assert {u.name for u in found.undeclared_imports} == {"tidyverse", "optparse"}

    def test_a_package_name_held_in_a_variable_is_not_a_dependency(self, tmp_path):
        # fig5.R: ref_genome <- "BSgenome..." then library(ref_genome, ...).
        _, found, _ = read_all(
            tmp_path,
            {
                "fig5.R": (
                    'library(BSgenome)\nref_genome <- "BSgenome.Hsapiens"\nlibrary(ref_genome)\n'
                )
            },
        )
        assert {u.name for u in found.undeclared_imports} == {"BSgenome"}

    def test_a_declaration_in_one_ecosystem_does_not_cover_another(self, tmp_path):
        _, found, _ = read_all(
            tmp_path,
            {
                "requirements.txt": "reshape==1.0\n",
                "DESCRIPTION": "Imports: ggplot2\n",
                "fig1.R": "library(reshape)\n",
            },
        )
        assert [u.name for u in found.undeclared_imports] == ["reshape"]

    def test_an_import_whose_distribution_has_another_name_is_declared(self, tmp_path):
        _, found, _ = read_all(
            tmp_path,
            {
                "requirements.txt": "scikit-learn==1.0.2\nfuture==0.18\n",
                "model.py": "import sklearn\nfrom past.builtins import xrange\n",
            },
        )
        assert found.undeclared_imports == []

    def test_a_repository_does_not_depend_on_itself(self, tmp_path):
        _, found, _ = read_all(
            tmp_path,
            {
                "requirements.txt": "numpy==1.0\n",
                "MATES/__init__.py": "",
                "MATES/main.py": "from MATES.scripts import helper\nimport numpy\n",
                "MATES/scripts/__init__.py": "",
                "MATES/scripts/helper.py": "",
            },
        )
        assert found.undeclared_imports == []


class TestExecution:
    def test_a_one_line_fence_does_not_swallow_the_next_paragraph(self, tmp_path):
        # The fence regex used to require a newline after the language tag, so
        # it skipped this opening fence and paired its closing one with the next
        # block's -- reading four paragraphs as code and reporting a sentence
        # about Telescope as a command.
        readme = (
            "## Testing\n"
            "```bash run_sample.sh```\n\n"
            "LocusMasterTE was built upon Telescope. Arguments are elaborated.\n\n"
            "```\nsome text\n```\n"
        )
        _, _, found = read_all(tmp_path, {"README.md": readme, "run_sample.sh": "echo hi\n"})
        commands = [e.command for e in found.entry_points if e.kind == "documented"]
        assert commands == ["bash run_sample.sh"]

    def test_a_redirect_target_is_an_output_not_a_missing_input(self, tmp_path):
        # "minimap2 -ax splice $fa $fq > processed.sam" was reported as a file
        # the repository is missing.
        _, _, found = read_all(
            tmp_path, {"run.sh": "minimap2 -ax splice $fa $fq > processed.sam\n"}
        )
        assert found.inputs == []

    def test_a_wrapped_command_keeps_all_its_flags(self, tmp_path):
        # Reading the continuation lines separately kept two flags of twenty.
        readme = (
            "```\nSTAR --runThreadN 20 \\\n"
            "  --outFilterMultimapNmax 100 \\\n"
            "  --alignEndsType EndToEnd\n```\n"
        )
        _, _, found = read_all(tmp_path, {"README.md": readme})
        assert {f.flag: f.value for f in found.flags} == {
            "--runThreadN": "20",
            "--outFilterMultimapNmax": "100",
            "--alignEndsType": "EndToEnd",
        }

    def test_a_recognized_tool_named_in_prose_is_not_a_command(self, tmp_path):
        # "htseq and intervaltree appear to yield identical results" sits in a
        # fenced block in LocusMasterTE's README. A tool is admitted here for
        # its flags, so a line carrying none of them adds nothing.
        _, _, found = read_all(
            tmp_path, {"README.md": "```\nhtseq and intervaltree appear to yield identical\n```\n"}
        )
        assert [e for e in found.entry_points if e.kind == "documented"] == []

    def test_a_variable_in_a_commented_out_block_is_not_read(self, tmp_path):
        # MATES keeps a disabled conda preamble, which reported three
        # undocumented environment variables that nothing ever reads.
        _, _, found = read_all(
            tmp_path, {"run.sh": "# CONDA_ENV=x\n# echo $CONDA_BASE\necho $REAL_VAR\n"}
        )
        assert [v.name for v in found.env_vars] == ["REAL_VAR"]

    def test_an_input_the_repository_holds_at_demo_scale_is_not_simply_present(self, tmp_path):
        records = "\n".join(f"chr1\trmsk\texon\t{i}\t{i + 9}" for i in range(20))
        _, _, found = read_all(
            tmp_path,
            {
                "data/run_sample.sh": "tool assign sample.bam annotation.gtf\n",
                "data/annotation.gtf": records,
                "data/sample.bam": "x",
            },
        )
        statuses = {i.path: i.status for i in found.inputs}
        assert statuses == {"sample.bam": "present", "annotation.gtf": "demo_scale"}

    def test_a_placeholder_in_a_documentation_example_is_not_a_missing_file(self, tmp_path):
        # "bash wrapper.sh hg38.fasta ..." -- no repository ships a human
        # genome, and reporting one as absent would be false.
        _, _, found = read_all(
            tmp_path,
            {"README.md": "```\nbash wrapper.sh hg38.fasta reads.fastq\n```\n", "wrapper.sh": "\n"},
        )
        assert {i.status for i in found.inputs} == {"user_supplied"}
        assert found.missing_inputs == []

    def test_a_console_script_is_read_from_the_packaging(self, tmp_path):
        _, _, found = read_all(
            tmp_path,
            {"setup.py": 'setup(entry_points={"console_scripts": ["Tool=Tool.__main__:main"]})'},
        )
        assert [(e.kind, e.name) for e in found.entry_points] == [("console_script", "Tool")]

    def test_a_notebooks_stored_output_is_not_read_as_a_command(self, tmp_path):
        # An output cell holds whatever the run printed, including other files.
        notebook = (
            '{"cells": [{"cell_type": "code", "source": ["import MATES\\n"],'
            ' "outputs": [{"text": ["aligned with bowtie2\\n"]}]}]}'
        )
        _, _, found = read_all(tmp_path, {"pipeline.ipynb": notebook})
        assert "bowtie2" not in {t.tool for t in found.tools_called}


class TestComparingTheRepositoryWithThePaper:
    def test_a_published_figure_with_no_script_is_found(self, tmp_path):
        # LocusMasterTE_paper holds fig1, fig3, fig4 and fig5. The paper has
        # five main figures.
        files = {f"Figures_Rscripts/fig{n}.R": "library(ggplot2)\n" for n in (1, 3, 4, 5)}
        found = analysis.analyze(
            [FetchResult(ref=RepoRef("github", "lab", "p"), checkout=checkout(tmp_path, files))],
            paper_figures=[1, 2, 3, 4, 5],
            paper_software=set(),
        )
        assert found.figures.assessable
        assert found.figures.covered == [1, 3, 4, 5]
        assert found.figures.uncovered == [2]

    def test_no_figure_named_file_is_undetermined_rather_than_uncovered(self, tmp_path):
        # MATES generates its figures from pipeline steps named for what they
        # compute. That is not evidence that the figures have no code.
        found = analysis.analyze(
            [
                FetchResult(
                    ref=RepoRef("github", "lab", "p"),
                    checkout=checkout(tmp_path, {"MATES/train_model.py": "import torch\n"}),
                )
            ],
            paper_figures=[1, 2, 3],
            paper_software=set(),
        )
        assert not found.figures.assessable

    def test_a_tool_the_repository_runs_and_the_paper_omits_is_reported(self, tmp_path):
        # Pychopper is step one of LocusMasterTE's own preprocessing wrapper and
        # the string appears nowhere in the paper.
        wrapper = "pychopper -r report.pdf $fq out.fq\nminimap2 -ax splice $fa out.fq\n"
        found = analysis.analyze(
            [
                FetchResult(
                    ref=RepoRef("github", "lab", "p"),
                    checkout=checkout(tmp_path, {"wrapper.sh": wrapper}),
                )
            ],
            paper_figures=[],
            paper_software={"minimap2"},
        )
        assert [s.tool for s in found.undocumented_steps] == ["Pychopper"]
        assert "wrapper.sh" in found.undocumented_steps[0].evidence

    def test_a_library_the_paper_omits_is_not_an_undocumented_step(self, tmp_path):
        # A methods section that does not name every imported package is a
        # normal methods section. Before this filter the comparison reported
        # conda, PyTorch and Ensembl around the one real finding.
        found = analysis.analyze(
            [
                FetchResult(
                    ref=RepoRef("github", "lab", "p"),
                    checkout=checkout(tmp_path, {"README.md": "Install with conda; uses PyTorch."}),
                )
            ],
            paper_figures=[],
            paper_software=set(),
        )
        assert found.undocumented_steps == []

    def test_nothing_fetched_is_not_a_repository_full_of_nothing(self):
        found = analysis.analyze(
            [FetchResult(ref=RepoRef("github", "lab", "p"), reason="git clone failed: not found")],
            paper_figures=[1],
            paper_software=set(),
        )
        assert not found.fetched
        assert found.unfetched[0]["reason"].startswith("git clone failed")


class TestFigureNumbers:
    def test_a_panel_letter_does_not_hide_the_figure(self):
        # "Fig. 1b" is how a paper cites its own figures, and a trailing word
        # boundary after the digit never matches it.
        assert figure_numbers("as shown in Fig. 1b and Figure 3") == [1, 3]

    def test_a_supplementary_figure_is_not_a_main_figure(self):
        assert figure_numbers("Additional file 1: Fig. S5A shows") == []

    def test_figures_are_deduplicated_and_ordered(self):
        assert figure_numbers("Fig. 3, Figs. 1-2, figure 3 again") == [1, 2, 3]


class TestCacheLayout:
    def test_a_relative_cache_directory_still_resolves(self, tmp_path, monkeypatch):
        # git resolves a relative clone target against the cwd it is given, so
        # a relative cache directory sent the first fresh clone to
        # data/repos/data/repos/<name>. The checkout then could not read its own
        # commit and recorded it as "unknown" -- a wrong provenance record
        # rather than a crash, and invisible on the cached path.
        from reprolens.repository.fetch import RepoRef, fetch

        monkeypatch.chdir(tmp_path)
        cached = tmp_path / "cache" / "github__lab__project" / ".git"
        cached.mkdir(parents=True)
        result = fetch(RepoRef("github", "lab", "project"), Path("cache"), allow_network=False)
        assert result.checkout is not None
        assert result.checkout.root.is_absolute()
        assert result.checkout.reused

    def test_an_uncached_repository_is_not_invented_when_offline(self, tmp_path):
        from reprolens.repository.fetch import RepoRef, fetch

        result = fetch(RepoRef("github", "lab", "project"), tmp_path, allow_network=False)
        assert result.checkout is None
        assert "cache" in result.reason


class TestAnRPackageIsAlsoARepository:
    """ASPEN's case: a published, installable R package with a worked example.

    Reading only the Python shapes -- a shell script, a console_scripts entry --
    found no entry point and no parameters in it, and scored a well-documented
    package 0 of 10 for execution instructions. That was a statement about the
    reader, not about the package.
    """

    NAMESPACE = (
        "# Generated by roxygen2: do not edit by hand\n\n"
        "export(estim_bbparams)\n"
        "export(correct_theta)\n"
        "exportMethods(show)\n"
    )
    README = (
        "## Installation\n"
        "```\n"
        'if(!require(devtools)) install.packages("devtools")\n'
        'devtools::install_github("lab/project")\n'
        "```\n"
        "## Quick start\n"
        "```\n"
        "library(project)\n"
        "bb_init <- estim_bbparams(counts, totals, min_cells = 5, cores = 6)\n"
        "shrunk <- correct_theta(bb_init, delta_set = 50, thetaFilter = 0.001)\n"
        "```\n"
    )

    def read(self, tmp_path):
        return read_all(
            tmp_path,
            {
                "NAMESPACE": self.NAMESPACE,
                "DESCRIPTION": "Package: project\nImports: stats, methods\n",
                "README.md": self.README,
                "R/parameter_estimation.R": "estim_bbparams <- function(a, b) { a }\n",
            },
        )

    def test_namespace_exports_are_entry_points(self, tmp_path):
        _, _, found = self.read(tmp_path)
        exports = [e for e in found.entry_points if e.kind == "r_export"]
        assert {e.name for e in exports} == {"estim_bbparams", "correct_theta", "show"}
        # Named surface, not an invocation: what you run is the documented call.
        assert all(e.command == "" for e in exports)

    def test_a_documented_call_to_an_export_is_a_command(self, tmp_path):
        # The head token of "bb_init <- estim_bbparams(...)" is a variable, so a
        # rule that keys on the first word of the line finds nothing.
        _, _, found = self.read(tmp_path)
        commands = [e.command for e in found.entry_points if e.kind == "documented"]
        assert any("estim_bbparams(counts, totals" in c for c in commands)
        assert any("correct_theta(bb_init" in c for c in commands)

    def test_the_install_and_load_lines_are_commands(self, tmp_path):
        _, _, found = self.read(tmp_path)
        commands = " ".join(e.command for e in found.entry_points if e.kind == "documented")
        assert "install_github" in commands
        assert "library(project)" in commands

    def test_r_named_arguments_are_read_as_parameters(self, tmp_path):
        # The same evidence as a shell flag: a parameter of the analysis,
        # written down with a value.
        _, _, found = self.read(tmp_path)
        valued = {f.flag: f.value for f in found.flags if f.value}
        assert valued == {
            "min_cells": "5",
            "cores": "6",
            "delta_set": "50",
            "thetaFilter": "0.001",
        }

    def test_an_argument_passing_a_variable_carries_no_value(self, tmp_path):
        # "genes.excl = genes2remove" documents that a parameter is passed, not
        # what it was set to -- the same rule as a shell flag whose value is $VAR.
        call = "est <- glob_disp(a, b, genes.excl = genes2remove, min_counts = 5)"
        _, _, found = read_all(
            tmp_path,
            {
                "NAMESPACE": "export(glob_disp)\n",
                "README.md": f"```\n{call}\n```\n",
            },
        )
        by_flag = {f.flag: f.value for f in found.flags}
        assert by_flag["min_counts"] == "5"
        assert by_flag["genes.excl"] is None

    def test_a_python_repository_is_unaffected(self, tmp_path):
        # No NAMESPACE, so the R path contributes nothing and the shell and
        # console-script rules are the only ones in play.
        _, _, found = read_all(
            tmp_path,
            {
                "setup.py": 'setup(entry_points={"console_scripts": ["tool=tool.__main__:main"]})',
                "run.sh": "tool assign input.bam\n",
            },
        )
        assert {e.kind for e in found.entry_points} == {"console_script", "shell_script"}
