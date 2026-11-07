"""The dependency graph, and the reachability question it exists to answer.

Blueprint §27 lists "determine missing dependencies" and "generate dependency
graph" as separate goals, and the separation is the point. The flat list is
already built: ``repo.json`` says 41 imports are undeclared and that
``annotation.gtf`` is present only at demo scale. What it cannot say is *which
result that blocks*. A reader deciding whether to attempt a reproduction does
not need a longer list of defects; they need to know that Figure 1 is
unreachable and why.

So the graph is not a drawing. It is a reachability computation over nodes this
project already extracts, and its output is one verdict per result:

    satisfied   every requirement on every path to it is accounted for
    broken      a path reaches a requirement that is missing or degraded
    unmapped    a path runs out of edges before reaching any requirement

``unmapped`` carries the project's fail-closed rule into the graph, and it is
the verdict that does most of the work. Measured over the five audited papers,
no script the repository provides also names the data it reads: LocusMasterTE's
``fig1.R`` draws Figure 1, ``run_sample.sh`` reads ``annotation.gtf``, and
nothing connects the two. A graph that scored that as ``satisfied`` would be
claiming the figure's inputs are fine; one that scored it ``broken`` would be
inventing a defect. It is neither -- the edge does not exist -- and saying so is
the only honest answer available.

NetworkX is named in the blueprint's study list (§30, "Fourth") and is not used
here. The graph is a few hundred typed edges and the traversal is a breadth
-first walk; a dependency earns its place by doing something the standard
library cannot, and for this it would not.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

NodeKind = Literal[
    "result",  # a figure or table the paper asserts
    "script",  # repository code that produces one
    "entry_point",  # a runnable command
    "input",  # a file a command reads
    "dataset",  # an accession the input might come from
    "tool",  # external software a command calls
    "repository",
]

EdgeKind = Literal[
    "generated_by",  # result -> script
    "provides",  # repository -> entry_point | script
    "reads",  # script | entry_point -> input
    "calls",  # script | entry_point -> tool
    "supplied_by",  # input -> dataset
]

SATISFIED = "satisfied"
BROKEN = "broken"
UNVERIFIED = "unverified"
UNMAPPED = "unmapped"

Verdict = Literal["satisfied", "broken", "unverified", "unmapped"]

# An input's status, as ``repository.execution`` reports it, mapped to whether
# a path through that input is usable. ``demo_scale`` is a break rather than a
# warning on the strength of the benchmark: LocusMasterTE ships
# ``annotation.gtf`` at demo scale, the annotators spent months discovering the
# real one was never released, and they recorded it as a hard blocker. A file
# that exists at the wrong scale is not a file you can reproduce with.
_INPUT_BREAKS = {
    "absent": "named but not present in the repository",
    "demo_scale": "present only at demo scale",
    # The script looks in the wrong place. Reported separately from ``absent``
    # because the two call for different work, and because the distinction
    # found a real defect: ASPEN's Figure3.ipynb reads
    # ./data/misc/cells_pass_filter.xlsx, which is not there, while
    # misc/cells_pass_filter.xlsx is. The notebook fails on a fresh clone and
    # the fix is one path segment.
    "moved": "read from a path it is not at",
}
# Located but not checkable here. ``remote`` is deposited data this module does
# not fetch; ``constructed`` is a path assembled from a variable, where only
# the filename is known and nothing of that name is in the repository -- a
# figure notebook reading its own pipeline's output looks exactly like this, so
# calling it a defect would be wrong and calling it present would be worse.
_INPUT_UNVERIFIED = {
    "remote": "deposited remotely and never fetched, so whether it resolves is unchecked",
    "constructed": "named only by filename, so whether it exists is undetermined",
}
# ``user_supplied`` is deliberately not a break. A pipeline that asks for your
# own FASTQ is behaving correctly, and calling that a defect would penalize
# every tool in the field.
_INPUT_OK = frozenset({"present", "user_supplied"})


@dataclass(frozen=True, slots=True)
class Node:
    kind: NodeKind
    id: str
    label: str = ""
    # Why this node is or is not usable, when that is known. Empty means the
    # question does not apply to this kind of node, never that the answer is
    # "fine" -- an unknown status is reported by the absence of an edge.
    status: str = ""
    detail: str = ""

    def as_dict(self) -> dict:
        record = {"kind": self.kind, "id": self.id, "label": self.label or self.id}
        if self.status:
            record["status"] = self.status
        if self.detail:
            record["detail"] = self.detail
        return record


@dataclass(frozen=True, slots=True)
class Edge:
    kind: EdgeKind
    source: str
    target: str
    evidence: str = ""

    def as_dict(self) -> dict:
        record = {"kind": self.kind, "source": self.source, "target": self.target}
        if self.evidence:
            record["evidence"] = self.evidence
        return record


@dataclass(slots=True)
class Path:
    """One walk from a starting node to wherever it ended, and why it ended."""

    start: str
    verdict: Verdict
    nodes: list[str]
    reason: str

    def as_dict(self) -> dict:
        return {
            "start": self.start,
            "verdict": self.verdict,
            "nodes": self.nodes,
            "reason": self.reason,
        }


@dataclass(slots=True)
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    # False when there was no repository to walk. A graph with no edges because
    # nothing was fetched must not read like a paper whose code has no
    # dependencies.
    assessable: bool = True
    notes: list[str] = field(default_factory=list)

    def add(self, node: Node) -> str:
        # First writer wins: a node named by two sources keeps the status the
        # more specific one gave it.
        self.nodes.setdefault(node.id, node)
        return node.id

    def link(self, kind: EdgeKind, source: str, target: str, evidence: str = "") -> None:
        if source in self.nodes and target in self.nodes:
            self.edges.append(Edge(kind, source, target, evidence))

    def out(self, node_id: str) -> list[Edge]:
        return [edge for edge in self.edges if edge.source == node_id]

    # -- reachability ------------------------------------------------------
    def walk(self, start: str) -> Path:
        """Breadth-first from ``start``, stopping at the first real answer.

        A break outranks an unmapped tail: if any path from this node reaches a
        missing requirement, the node is broken whether or not its other paths
        peter out. The reverse would let one dead end hide a known defect.
        """
        if start not in self.nodes:
            return Path(start, UNMAPPED, [], "not in the graph")

        seen = {start}
        queue: deque[list[str]] = deque([[start]])
        terminals: list[list[str]] = []

        while queue:
            trail = queue.popleft()
            node = self.nodes[trail[-1]]
            if node.status in _INPUT_BREAKS:
                return Path(start, BROKEN, trail, f"{node.label} is {_INPUT_BREAKS[node.status]}")
            onward = [e for e in self.out(trail[-1]) if e.target not in seen]
            if not onward:
                terminals.append(trail)
                continue
            for edge in onward:
                seen.add(edge.target)
                queue.append([*trail, edge.target])

        # Nothing broken. The weakest link decides what is left: a result is
        # satisfied only when *every* path from it lands on data that was
        # actually checked. Reporting the strongest path instead would say
        # ASPEN's Figure 5 is satisfied because three of its five inputs are
        # present, while the other two are paths assembled from a variable that
        # nothing in the repository matches -- the same over-claim as accepting
        # a tool name, reached a different way.
        for trail in terminals:
            node = self.nodes[trail[-1]]
            if node.status in _INPUT_UNVERIFIED:
                return Path(
                    start,
                    UNVERIFIED,
                    trail,
                    f"{node.label} is {_INPUT_UNVERIFIED[node.status]}",
                )

        # Whether reaching the end of a path is reassuring depends entirely on
        # what the walk actually reached.
        #
        # Only an input whose status was checked earns ``satisfied``. Reaching
        # a *tool* does not, and the first draft of this walk accepted it:
        # every satisfied verdict it produced terminated on a tool name, so
        # ASPEN's Figure 2 read as reproducible because a notebook mentions
        # clusterProfiler. Nothing in this project checks that a tool is
        # installable at a usable version. The clearest case against it is
        # LocusMasterTE, where the satisfied path ended at ``featureCounts`` --
        # which the benchmark records as required and never named by the paper
        # at all.
        for trail in terminals:
            node = self.nodes[trail[-1]]
            if node.kind in ("input", "dataset") and node.status in _INPUT_OK:
                return Path(start, SATISFIED, trail, f"{node.label} is {node.status or 'present'}")
        deepest = max(terminals, key=len) if terminals else [start]
        last = self.nodes[deepest[-1]]
        if last.kind == "tool":
            return Path(
                start,
                UNMAPPED,
                deepest,
                f"reaches {last.label!r} but no data, and whether that tool is "
                f"installable at a usable version is never checked",
            )
        return Path(
            start,
            UNMAPPED,
            deepest,
            f"no edge leaves {last.kind} {last.label!r}, so what it needs is undetermined",
        )

    def reachability(self, kinds: Iterable[NodeKind] = ("result",)) -> list[Path]:
        wanted = set(kinds)
        return [self.walk(n.id) for n in self.nodes.values() if n.kind in wanted]

    def to_dict(self) -> dict:
        paths = self.reachability(("result", "entry_point"))
        tally: dict[str, int] = {SATISFIED: 0, BROKEN: 0, UNVERIFIED: 0, UNMAPPED: 0}
        for path in paths:
            tally[path.verdict] += 1
        by_kind: dict[str, int] = {}
        for node in self.nodes.values():
            by_kind[node.kind] = by_kind.get(node.kind, 0) + 1
        return {
            "assessable": self.assessable,
            "summary": {
                "nodes": len(self.nodes),
                "edges": len(self.edges),
                "by_kind": by_kind,
                "verdicts": tally,
            },
            "nodes": [n.as_dict() for n in self.nodes.values()],
            "edges": [e.as_dict() for e in self.edges],
            "paths": [p.as_dict() for p in paths],
            "notes": self.notes,
        }


def _key(kind: str, value: str) -> str:
    return f"{kind}:{value}"


def build(repo: dict, *, resolutions: dict | None = None) -> Graph:
    """Assemble the graph from the records ``audit.py`` has already produced.

    Deliberately a pure function over dictionaries rather than another pass
    over the repository: every edge here is a relation some earlier extractor
    already found, and re-deriving them would let the graph and the report
    disagree about the same paper.
    """
    graph = Graph()

    if not repo or not repo.get("fetched"):
        graph.assessable = False
        graph.notes.append(
            "No repository was read, so nothing connects the paper's results to what "
            "producing them requires. This is an unanswered question, not an empty graph."
        )
        return graph

    for checkout in repo.get("repositories", []):
        graph.add(Node("repository", _key("repo", checkout["repository"]), checkout["repository"]))

    execution = repo.get("execution", {}) or {}
    traceability = repo.get("figure_traceability", {}) or {}

    # -- results, and the scripts that make them ---------------------------
    scripts_for: dict[int, list[str]] = {}
    for entry in traceability.get("scripts", []):
        scripts_for.setdefault(entry["figure"], []).append(entry["source"])

    for figure in traceability.get("paper_figures", []):
        result = graph.add(Node("result", _key("figure", str(figure)), f"Figure {figure}"))
        for source in scripts_for.get(figure, []):
            script = graph.add(Node("script", _key("script", source), source))
            graph.link("generated_by", result, script)

    # -- what each figure script reads -------------------------------------
    # The edge the graph was missing. ``execution.inputs`` attributes an input
    # to the file that names it, and that file is a pipeline shell script, never
    # the script that draws the figure -- so before this every result in every
    # paper returned ``unmapped`` and ``satisfied`` was unreachable in practice.
    for ref in (repo.get("figure_data", {}) or {}).get("references", []):
        script = _key("script", ref["named_by"])
        if script not in graph.nodes:
            continue
        node = graph.add(
            Node(
                "input" if ref["kind"] == "repo_path" else "dataset",
                _key("data", ref["target"]),
                ref["target"],
                status=ref["status"],
                detail=ref.get("detail", ""),
            )
        )
        graph.link("reads", script, node, evidence=ref.get("detail", ""))

    # -- entry points, and what they read and call -------------------------
    for point in execution.get("entry_points", []):
        node = graph.add(
            Node(
                "entry_point",
                _key("entry", point["source"] + "::" + point["name"]),
                point["name"],
                detail=point.get("command", ""),
            )
        )
        graph.link("provides", _key("repo", point["source"].split(":", 1)[0]), node)

    # An input is attributed to the file that names it, which is the only
    # attribution the extractor records. That file is often a shell script
    # rather than the figure script, which is exactly why so many result paths
    # come back unmapped rather than satisfied.
    by_source: dict[str, list[str]] = {}
    for node in graph.nodes.values():
        if node.kind in ("entry_point", "script"):
            by_source.setdefault(node.label, []).append(node.id)
            by_source.setdefault(node.detail, []).append(node.id)

    for item in execution.get("inputs", []):
        status = item.get("status", "")
        node = graph.add(
            Node(
                "input",
                _key("input", item["path"]),
                item["path"],
                status=status if status in _INPUT_BREAKS or status in _INPUT_OK else "",
                detail=item.get("detail", ""),
            )
        )
        named_by = item.get("named_by", "")
        owners = [
            owner.id
            for owner in graph.nodes.values()
            if owner.kind in ("entry_point", "script")
            and named_by
            and named_by.endswith(owner.label)
        ]
        for owner in owners or []:
            graph.link("reads", owner, node, evidence=named_by)
        if not owners and named_by:
            # Fail closed rather than drop it: an input nothing claims is still
            # a requirement, so it hangs off the repository that named it.
            graph.link("reads", _key("repo", named_by.split(":", 1)[0]), node, evidence=named_by)

    for call in execution.get("tools_called", []):
        node = graph.add(Node("tool", _key("tool", call["tool"]), call["tool"]))
        source = call.get("source", "")
        owners = [
            owner.id
            for owner in graph.nodes.values()
            if owner.kind in ("entry_point", "script") and source and source.endswith(owner.label)
        ]
        for owner in owners:
            graph.link("calls", owner, node, evidence=call.get("evidence", ""))

    # -- datasets ----------------------------------------------------------
    # No extractor maps a file path to the accession it came from, so these
    # arrive as nodes with no inbound edge. Present rather than omitted,
    # because the gap between "the paper deposited GSE225377" and "a script
    # reads it" is a real finding about the paper.
    for record in (resolutions or {}).get("accessions", []):
        graph.add(
            Node(
                "dataset",
                _key("dataset", record["accession"]),
                record["accession"],
                status=record.get("status", ""),
            )
        )

    if any(n.kind == "dataset" for n in graph.nodes.values()):
        graph.notes.append(
            "No script in the repository names the accession it reads, so no dataset is "
            "connected to the code that consumes it. The accessions are listed as "
            "unconnected nodes rather than left out."
        )
    return graph
