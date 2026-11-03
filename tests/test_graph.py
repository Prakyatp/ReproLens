"""The dependency graph, and the three verdicts it is allowed to reach.

The graph exists to answer a question the flat missing-dependency list cannot:
not "what is wrong with this repository" but "which of the paper's own results
does each defect stand in front of". Its value therefore rests entirely on the
verdicts being honest, which is what these tests pin.
"""

from __future__ import annotations

from reprolens.graph.build import BROKEN, SATISFIED, UNMAPPED, build


def repo(**overrides) -> dict:
    """A minimal fetched repository record, in the shape ``repo.json`` has."""
    base = {
        "fetched": True,
        "repositories": [{"repository": "lab/tool"}],
        "execution": {"entry_points": [], "inputs": [], "tools_called": []},
        "figure_traceability": {"paper_figures": [], "scripts": []},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = base[key] | value
        else:
            base[key] = value
    return base


def entry(name: str, command: str = "run") -> dict:
    return {
        "kind": "shell_script",
        "name": name,
        "command": command,
        "source": f"lab/tool:{name}",
    }


def verdicts(graph) -> dict[str, str]:
    return {p.start: p.verdict for p in graph.reachability(("result", "entry_point"))}


class TestUnassessable:
    """No repository read is a question left open, not a graph with no edges."""

    def test_an_unfetched_repository_is_not_assessable(self):
        graph = build({"fetched": False})
        assert graph.assessable is False
        assert graph.nodes == {}

    def test_it_says_so_rather_than_reporting_an_empty_graph(self):
        graph = build({})
        assert graph.notes
        assert "unanswered question" in " ".join(graph.notes)


class TestBrokenPaths:
    """The verdict the benchmark can check."""

    def test_a_demo_scale_input_breaks_the_path(self):
        # This is LocusMasterTE's Tier-1 hard blocker, which the annotators
        # spent months discovering: the shipped annotation.gtf is a demo, the
        # real one was never released. The graph has to reach it by walking,
        # not by being told.
        graph = build(
            repo(
                execution={
                    "entry_points": [entry("run_sample.sh")],
                    "inputs": [
                        {
                            "path": "annotation.gtf",
                            "status": "demo_scale",
                            "named_by": "lab/tool:run_sample.sh",
                            "detail": "",
                        }
                    ],
                    "tools_called": [],
                }
            )
        )
        paths = {p.start: p for p in graph.reachability(("entry_point",))}
        (path,) = paths.values()
        assert path.verdict == BROKEN
        assert "demo_scale" in path.reason

    def test_an_absent_input_breaks_the_path(self):
        graph = build(
            repo(
                execution={
                    "entry_points": [entry("realignUnmapped.sh")],
                    "inputs": [
                        {
                            "path": "sample.bam",
                            "status": "absent",
                            "named_by": "lab/tool:realignUnmapped.sh",
                            "detail": "",
                        }
                    ],
                    "tools_called": [],
                }
            )
        )
        assert BROKEN in verdicts(graph).values()

    def test_a_user_supplied_input_is_not_a_break(self):
        # A pipeline that asks for your own FASTQ is behaving correctly.
        # Scoring that as a defect would penalize every tool in the field.
        graph = build(
            repo(
                execution={
                    "entry_points": [entry("align.sh")],
                    "inputs": [
                        {
                            "path": "reads_R1.fastq.gz",
                            "status": "user_supplied",
                            "named_by": "lab/tool:align.sh",
                            "detail": "",
                        }
                    ],
                    "tools_called": [],
                }
            )
        )
        assert BROKEN not in verdicts(graph).values()

    def test_a_break_outranks_an_unmapped_sibling_path(self):
        # One dead end must not hide a known defect reachable another way.
        graph = build(
            repo(
                execution={
                    "entry_points": [entry("run.sh")],
                    "inputs": [
                        {
                            "path": "annotation.gtf",
                            "status": "demo_scale",
                            "named_by": "lab/tool:run.sh",
                            "detail": "",
                        }
                    ],
                    "tools_called": [{"tool": "samtools", "source": "lab/tool:run.sh"}],
                }
            )
        )
        assert BROKEN in verdicts(graph).values()


class TestSatisfiedRequiresData:
    """``satisfied`` means data was checked, never that a tool was named.

    The first draft accepted a tool as a terminal, and every satisfied verdict
    it produced on real papers terminated on one: ASPEN's Figure 2 read as
    reproducible because a notebook mentions clusterProfiler. The clearest case
    against it was LocusMasterTE, whose satisfied path ended at
    ``featureCounts`` -- which the benchmark records as required and never
    named by the paper at all. Nothing in this project checks that a tool is
    installable at a usable version.
    """

    def test_reaching_a_tool_is_unmapped_not_satisfied(self):
        graph = build(
            repo(
                execution={
                    "entry_points": [entry("Figure2.ipynb")],
                    "inputs": [],
                    "tools_called": [
                        {"tool": "clusterProfiler", "source": "lab/tool:Figure2.ipynb"}
                    ],
                }
            )
        )
        (path,) = graph.reachability(("entry_point",))
        assert path.verdict == UNMAPPED
        assert "installable" in path.reason

    def test_reaching_a_present_input_is_satisfied(self):
        # Proves the verdict is reachable rather than dead code: it happens not
        # to occur on any of the five papers audited so far.
        graph = build(
            repo(
                execution={
                    "entry_points": [entry("run.sh")],
                    "inputs": [
                        {
                            "path": "sample_sorted.bam",
                            "status": "present",
                            "named_by": "lab/tool:run.sh",
                            "detail": "",
                        }
                    ],
                    "tools_called": [],
                }
            )
        )
        (path,) = graph.reachability(("entry_point",))
        assert path.verdict == SATISFIED
        assert "sample_sorted.bam" in path.reason


class TestResultsAndScripts:
    def test_a_figure_with_no_script_says_so_distinctly(self):
        graph = build(repo(figure_traceability={"paper_figures": [1, 2], "scripts": []}))
        paths = {p.start: p for p in graph.reachability(("result",))}
        assert all(p.verdict == UNMAPPED for p in paths.values())
        assert all("no edge leaves result" in p.reason for p in paths.values())

    def test_a_figure_with_a_script_but_no_inputs_blames_the_script(self):
        # The distinction matters to a reader: "no code was found for this
        # figure" and "the code was found but what it reads is unknown" are
        # different states of the evidence.
        graph = build(
            repo(
                figure_traceability={
                    "paper_figures": [1],
                    "scripts": [{"figure": 1, "source": "lab/paper:fig1.R"}],
                }
            )
        )
        (path,) = graph.reachability(("result",))
        assert path.verdict == UNMAPPED
        assert "fig1.R" in path.reason


class TestUnconnectedDatasets:
    """Accessions arrive with no inbound edge, and are listed anyway."""

    def test_datasets_are_present_as_unconnected_nodes(self):
        graph = build(
            repo(),
            resolutions={"accessions": [{"accession": "GSE225377", "status": "public"}]},
        )
        assert any(n.kind == "dataset" for n in graph.nodes.values())
        assert not graph.edges or all(e.target != "dataset:GSE225377" for e in graph.edges)

    def test_the_disconnection_is_stated_rather_than_implied(self):
        graph = build(
            repo(),
            resolutions={"accessions": [{"accession": "GSE225377", "status": "public"}]},
        )
        assert any("no dataset is connected" in note for note in graph.notes)


class TestSerialization:
    def test_the_dict_carries_the_verdict_tally(self):
        graph = build(
            repo(
                execution={
                    "entry_points": [entry("run.sh")],
                    "inputs": [
                        {
                            "path": "annotation.gtf",
                            "status": "demo_scale",
                            "named_by": "lab/tool:run.sh",
                            "detail": "",
                        }
                    ],
                    "tools_called": [],
                }
            )
        )
        record = graph.to_dict()
        assert record["summary"]["verdicts"][BROKEN] == 1
        assert record["summary"]["nodes"] == len(record["nodes"])
        assert record["summary"]["edges"] == len(record["edges"])

    def test_an_edge_is_never_emitted_for_a_node_that_does_not_exist(self):
        graph = build(
            repo(
                execution={
                    "entry_points": [entry("run.sh")],
                    "inputs": [],
                    "tools_called": [{"tool": "samtools", "source": "lab/other:absent.sh"}],
                }
            )
        )
        ids = {n["id"] for n in graph.to_dict()["nodes"]}
        for edge in graph.to_dict()["edges"]:
            assert edge["source"] in ids and edge["target"] in ids
