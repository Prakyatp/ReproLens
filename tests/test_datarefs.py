"""What a figure script reads, which is the edge that made ``satisfied`` reachable.

Before this extractor, ``execution.inputs`` attributed every input to the file
that *names* it -- a pipeline shell script, never the script that draws the
figure -- so all five audited papers returned ``unmapped`` for every result and
the verdict ``satisfied`` could not occur.

The two papers that ship figure code do it two different ways, and both are
pinned here: LocusMasterTE's R scripts read Figshare URLs with no local path at
all, ASPEN's notebooks read repository paths, mostly assembled from a variable.
"""

from __future__ import annotations

import json

from reprolens.repository import datarefs
from reprolens.repository.fetch import Checkout, RepoRef
from reprolens.repository.inventory import take


def checkout(root, slug: str = "lab/paper") -> Checkout:
    owner, _, name = slug.partition("/")
    return Checkout(
        ref=RepoRef("github", owner, name),
        root=root,
        commit="0" * 40,
        committed_at="2026-01-01T00:00:00Z",
        fetched_at="2026-01-01T00:00:00Z",
        reused=True,
    )


def inventory_of(tmp_path, files: dict[str, str]):
    root = tmp_path / "repo"
    for path, body in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return take([checkout(root)])


def notebook(*sources: str) -> str:
    return json.dumps(
        {"cells": [{"cell_type": "code", "source": [s]} for s in sources]},
    )


def refs_for(tmp_path, files: dict[str, str], script: str):
    inventory = inventory_of(tmp_path, files)
    return datarefs.read(inventory, [(1, f"lab/paper:{script}")]).refs


class TestNotAssessable:
    def test_no_figure_script_is_undetermined_not_empty(self, tmp_path):
        inventory = inventory_of(tmp_path, {"README.md": "# nothing"})
        result = datarefs.read(inventory, [])
        assert result.assessable is False
        assert "undetermined rather than absent" in " ".join(result.notes)


class TestRemoteReferences:
    """LocusMasterTE's shape: the data is deposited, not in the repository."""

    def test_a_figshare_url_is_remote_and_not_a_defect(self, tmp_path):
        refs = refs_for(
            tmp_path,
            {
                "fig1.R": (
                    'short_read <- read.delim("https://figshare.com/ndownloader/'
                    'files/52072676", comment.char="#")\n'
                )
            },
            "fig1.R",
        )
        (ref,) = refs
        assert ref.kind == "remote"
        assert ref.status == datarefs.REMOTE
        assert "figshare.com" in ref.detail
        # The point of the status: it says what is unknown, rather than
        # claiming the data is missing or claiming it is fine.
        assert "unchecked" in ref.detail


class TestRepositoryPaths:
    """ASPEN's shape: real paths, resolvable against the clone now."""

    def test_a_path_that_resolves_is_present(self, tmp_path):
        refs = refs_for(
            tmp_path,
            {
                "misc/NAP_genes.xlsx": "x",
                "Figure4.ipynb": notebook('NAPgenes <- read.xlsx("./misc/NAP_genes.xlsx")'),
            },
            "Figure4.ipynb",
        )
        (ref,) = refs
        assert ref.status == datarefs.PRESENT

    def test_a_wrong_path_is_moved_and_says_where_the_file_is(self, tmp_path):
        # The real defect this distinction found: ASPEN's Figure3.ipynb reads
        # ./data/misc/cells_pass_filter.xlsx, which is not there, while
        # misc/cells_pass_filter.xlsx is -- 1.8 MB of it. The notebook fails on
        # a fresh clone and the fix is one path segment. Reporting that as
        # "absent" would send a reader looking for data that is already there.
        refs = refs_for(
            tmp_path,
            {
                "misc/cells_pass_filter.xlsx": "x",
                "Figure3.ipynb": notebook(
                    'annot <- read.xlsx("./data/misc/cells_pass_filter.xlsx", sheet = 1)'
                ),
            },
            "Figure3.ipynb",
        )
        (ref,) = refs
        assert ref.status == datarefs.MOVED
        assert "misc/cells_pass_filter.xlsx" in ref.detail

    def test_a_path_with_no_such_file_anywhere_is_absent(self, tmp_path):
        refs = refs_for(
            tmp_path,
            {"fig2.R": 'counts <- read.csv("./data/counts_that_do_not_exist.csv")'},
            "fig2.R",
        )
        (ref,) = refs
        assert ref.status == datarefs.ABSENT


class TestConstructedPaths:
    """``read.xlsx(paste0(res_dir, "counts.xlsx"))`` -- the dominant real shape.

    Matching only a quoted path that is the whole first argument found 3 of
    ASPEN's 20 references. Most of its reads build the directory from a
    variable and leave only the filename quoted.
    """

    def test_a_constructed_path_whose_basename_exists_is_present(self, tmp_path):
        refs = refs_for(
            tmp_path,
            {
                "aspen_output/tcells/counts.xlsx": "x",
                "Figure2.ipynb": notebook('res <- read.xlsx(paste0(res_dir, "counts.xlsx"))'),
            },
            "Figure2.ipynb",
        )
        (ref,) = refs
        assert ref.status == datarefs.PRESENT
        assert "came from a variable" in ref.detail

    def test_a_constructed_path_with_no_match_is_constructed_not_absent(self, tmp_path):
        # A figure notebook reading its own pipeline's output looks exactly
        # like this. Calling it a defect would be wrong; calling it present
        # would be worse.
        refs = refs_for(
            tmp_path,
            {"Figure5.ipynb": notebook('a1 <- read.csv(paste0(dir, "Bl6_Cast_a1.csv"))')},
            "Figure5.ipynb",
        )
        (ref,) = refs
        assert ref.status == datarefs.CONSTRUCTED
        assert "earlier step or supplied by the user" in ref.detail


class TestWhatIsNotAReference:
    def test_a_non_path_string_argument_is_ignored(self, tmp_path):
        # Without this guard, open("w") and read.csv(text = "a,b") arrive as
        # data dependencies.
        refs = refs_for(
            tmp_path,
            {"fig1.py": 'handle = open("w")\nrows = read_csv("a,b,c")\n'},
            "fig1.py",
        )
        assert refs == []

    def test_readxcsv_does_not_match_read_dot_csv(self, tmp_path):
        # An unescaped dot in the reader alternation makes ``read.csv`` match
        # any identifier of that shape, which is how a tidy-looking regex
        # quietly widens into "anything".
        refs = refs_for(
            tmp_path,
            {"fig1.py": 'rows = readxcsv("./data/real.csv")'},
            "fig1.py",
        )
        assert refs == []

    def test_a_notebook_is_read_as_code_cells_not_raw_json(self, tmp_path):
        # Raw JSON matches nothing useful: the reader call sits inside a
        # "source" array, split at every newline across list elements.
        files = {
            "misc/x.csv": "a",
            "Figure1.ipynb": json.dumps(
                {
                    "cells": [
                        {"cell_type": "markdown", "source": ['read.csv("./misc/ignored.csv")']},
                        {"cell_type": "code", "source": ['d <- read.csv("./misc/x.csv")']},
                    ]
                }
            ),
        }
        refs = refs_for(tmp_path, files, "Figure1.ipynb")
        assert [r.target for r in refs] == ["./misc/x.csv"]


class TestSerialization:
    def test_the_summary_counts_by_status(self, tmp_path):
        inventory = inventory_of(
            tmp_path,
            {
                "misc/here.csv": "a",
                "fig1.R": (
                    'a <- read.csv("./misc/here.csv")\n'
                    'b <- read.csv("./misc/gone.csv")\n'
                    'c <- read.delim("https://figshare.com/ndownloader/files/1")\n'
                ),
            },
        )
        record = datarefs.read(inventory, [(1, "lab/paper:fig1.R")]).to_dict()
        assert record["summary"]["references"] == 3
        assert record["summary"]["by_status"] == {"absent": 1, "present": 1, "remote": 1}
