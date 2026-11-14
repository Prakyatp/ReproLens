"""The audit, read by a person.

    uv run streamlit run ui.py

A viewer over what ``audit.py`` already wrote to ``output/<paper>/``. It runs no
extraction of its own, which keeps one rule easy to hold: there is exactly one
place where a finding can be produced, and it is not here. If a number appears
on this page it came out of a JSON file on disk, and the page says which one.

The thing this view exists to get right is the **band**. Every score in this
project is a floor and a ceiling: the floor is what the paper definitely
documents, the ceiling is what it might. A single number would be a lie in
either direction -- it would read as precision the evidence does not support,
and it would hide the distinction the whole tool is built on, which is that a
paper loses points for what it did not say and never for what the reader could
not determine. So nothing here collapses a band, and "not assessed" is drawn as
its own state rather than as a zero.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"

SEVERITY_ORDER = ("hard_blocker", "major", "minor")
SEVERITY_LABEL = {
    "hard_blocker": "hard blocker",
    "major": "major issue",
    "minor": "minor issue",
}
# Blueprint §22. A hard blocker stops a reproduction; a major issue means a
# value has to be guessed; a minor issue costs time.
SEVERITY_COLOR = {"hard_blocker": "#b4232c", "major": "#b8690f", "minor": "#555555"}

CRITERION_LABEL = {
    "data_availability": "Data availability",
    "code_availability": "Code availability",
    "environment_specification": "Environment specification",
    "method_completeness": "Method completeness",
    "parameters_configuration": "Parameters & configuration",
    "execution_instructions": "Execution instructions",
    "result_traceability": "Result traceability",
}

VERDICT_HELP = {
    "satisfied": "every dependency on the path to this result is present",
    "broken": "something on the path is definitely missing",
    "unverified": "something on the path could not be checked",
    "unmapped": "nothing ties this result to code that produces it",
}


def papers() -> list[str]:
    if not OUTPUT.is_dir():
        return []
    return sorted(p.name for p in OUTPUT.iterdir() if (p / "assessment.json").is_file())


def load(paper: str, name: str) -> dict | None:
    path = OUTPUT / paper / f"{name}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def band(floor: int, ceiling: int, total: int, *, height: int = 26) -> str:
    """A floor and a ceiling drawn as one bar, because they are one claim.

    The filled part is the floor -- points the paper has earned outright. The
    hatched part is the gap to the ceiling, which is not partial credit: it is
    the range this reader could not narrow. Drawn differently for that reason,
    rather than as a lighter shade of the same thing.
    """
    total = max(total, 1)
    floor_pct = 100 * floor / total
    gap_pct = 100 * max(0, ceiling - floor) / total
    return f"""
    <div style="display:flex;height:{height}px;width:100%;border-radius:4px;
                overflow:hidden;background:#eceff1;">
      <div style="width:{floor_pct:.2f}%;background:#2f6f4f;"></div>
      <div style="width:{gap_pct:.2f}%;background:repeating-linear-gradient(
                  45deg,#9fb8ab,#9fb8ab 5px,#eceff1 5px,#eceff1 10px);"></div>
    </div>"""


def main() -> None:
    st.set_page_config(page_title="ReproLens", page_icon="🔬", layout="wide")

    available = papers()
    with st.sidebar:
        st.title("ReproLens")
        st.caption("What a reproduction of this paper needs, and what is missing.")

        if not available:
            st.warning("No audits in `output/` yet.")
        paper = st.selectbox("Audited paper", available) if available else None

        st.divider()
        st.subheader("Audit a paper")
        # Only the two directories papers live in. A recursive sweep of data/
        # also offered jarvis's VASP test fixtures and MATES's vendored figure
        # PDF -- eighteen entries, three of them papers.
        sources = sorted(
            str(path.relative_to(ROOT))
            for directory, suffix in (("papers", "*.pdf"), ("xml", "*.xml"))
            for path in (ROOT / "data" / directory).glob(suffix)
        )
        if sources:
            source = st.selectbox("Source document", sources)
            if st.button("Run audit", width="stretch"):
                with st.spinner(f"auditing {source} …"):
                    done = subprocess.run(  # noqa: S603 -- a fixed command, chosen path
                        [sys.executable, str(ROOT / "audit.py"), source, "--out", str(OUTPUT)],
                        capture_output=True,
                        text=True,
                        cwd=ROOT,
                    )
                if done.returncode == 0:
                    st.success("done")
                    st.rerun()
                else:
                    # Surfaced in full rather than summarised: a failed audit is
                    # the one case where the tool's own output is the finding.
                    st.error("the audit failed")
                    st.code((done.stderr or done.stdout)[-3000:])
        else:
            st.caption("No documents under `data/`.")

    if not paper:
        st.info("Audit a paper from the sidebar to begin.")
        return

    assessment = load(paper, "assessment")
    links = load(paper, "links") or {}
    if assessment is None:
        st.error(f"`output/{paper}/assessment.json` is missing.")
        return

    st.title(paper)
    source = links.get("source", "")
    st.caption(
        f"`{source}` · read by {links.get('backend', 'unknown')} · "
        f"{links.get('n_segments', '?')} segment(s) · rubric {assessment['rubric_version']}"
    )

    for warning in links.get("warnings", []):
        # A warning leads, always. "Found nothing" and "could not read it" are
        # different claims, and only one of them is about the paper.
        st.warning(warning)

    _headline(assessment)
    st.divider()

    overview, criteria, issues, resources, graph, provenance = st.tabs(
        ["Overview", "Criteria", "What is missing", "Resources", "Dependencies", "Report"]
    )
    with overview:
        _overview(assessment, links)
    with criteria:
        _criteria(assessment)
    with issues:
        _issues(assessment)
    with resources:
        _resources(load(paper, "checklist") or {}, links)
    with graph:
        _graph(load(paper, "graph") or {})
    with provenance:
        _report(paper)


def _headline(assessment: dict) -> None:
    floor = assessment["score_floor"]
    ceiling = assessment["score_ceiling"]
    assessed = assessment["assessed_points"]

    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"### Readiness **{floor}–{ceiling}** / {assessed}")
        st.markdown(band(floor, ceiling, assessed, height=34), unsafe_allow_html=True)
        st.caption(
            f"**{floor}** points the paper documents outright. The hatched "
            f"**{ceiling - floor}** is not partial credit — it is the range this "
            f"reader could not narrow, and a paper is never penalised for it."
        )
    with right:
        severity = assessment.get("severity", {})
        columns = st.columns(3)
        for column, key in zip(columns, SEVERITY_ORDER, strict=True):
            with column:
                st.markdown(
                    f"<div style='text-align:center'>"
                    f"<div style='font-size:2.1rem;line-height:1;"
                    f"color:{SEVERITY_COLOR[key]};font-weight:600'>"
                    f"{severity.get(key, 0)}</div>"
                    f"<div style='font-size:0.8rem;color:#666'>"
                    f"{SEVERITY_LABEL[key]}s</div></div>",
                    unsafe_allow_html=True,
                )


def _overview(assessment: dict, links: dict) -> None:
    st.subheader("The five questions")
    st.caption("Blueprint §42. Every answer below is a count of things on disk.")

    findings = links.get("findings", [])
    checklist = links.get("checklist", {}).get("summary", {})
    repository = links.get("repository", {})

    rows = [
        (
            "What is required?",
            f"{checklist.get('declared', 0)} software resource(s) the paper declares, "
            f"plus every dataset and input file its repositories name",
        ),
        (
            "What was found?",
            f"{len(findings)} identifier(s) in the document; "
            f"{len(repository.get('checkouts', []))} repository/ies read",
        ),
        (
            "What is missing?",
            f"{sum(assessment.get('severity', {}).values())} issue(s): "
            + ", ".join(
                f"{assessment.get('severity', {}).get(k, 0)} {SEVERITY_LABEL[k]}"
                for k in SEVERITY_ORDER
            ),
        ),
        (
            "Where was each item mentioned?",
            "every finding carries a page, a section and a quote — see Resources and Report",
        ),
        (
            "What to investigate first?",
            "the hard blockers, then the major issues — see *What is missing*",
        ),
    ]
    for question, answer in rows:
        st.markdown(f"**{question}**  \n{answer}")

    unassessed = [c for c in assessment["criteria"] if not c.get("assessed", True)]
    if unassessed:
        st.divider()
        st.subheader("Not assessed")
        st.caption(
            "These are not zeros. Nothing was measured, so nothing is claimed — "
            "reported rather than scored."
        )
        for criterion in unassessed:
            st.markdown(
                f"- **{CRITERION_LABEL.get(criterion['name'], criterion['name'])}** — "
                f"{criterion.get('reason', 'not assessed')}"
            )


def _criteria(assessment: dict) -> None:
    st.caption(
        "Blueprint §21. Each criterion is a band, and the two halves answer "
        "different questions: *what did the paper document* and *what could not "
        "be determined from it*."
    )
    for criterion in assessment["criteria"]:
        name = CRITERION_LABEL.get(criterion["name"], criterion["name"])
        floor, ceiling, weight = criterion["floor"], criterion["ceiling"], criterion["weight"]

        if not criterion.get("assessed", True):
            st.markdown(f"**{name}** · not assessed / {weight}")
            st.caption(criterion.get("reason", ""))
            st.divider()
            continue

        st.markdown(f"**{name}** · {floor}–{ceiling} / {weight}")
        st.markdown(band(floor, ceiling, weight), unsafe_allow_html=True)
        for line in criterion.get("basis", []):
            st.markdown(
                f"<div style='color:#2f6f4f;font-size:0.86rem'>✓ {line}</div>",
                unsafe_allow_html=True,
            )
        for line in criterion.get("undetermined", []):
            st.markdown(
                f"<div style='color:#7a7a7a;font-size:0.86rem'>? {line}</div>",
                unsafe_allow_html=True,
            )
        st.divider()


def _issues(assessment: dict) -> None:
    found = assessment.get("issues", [])
    if not found:
        st.success("No issues raised. That is a finding about the paper, not a default.")
        return

    st.caption("Blueprint §22, worst first. Each line carries the evidence it came from.")
    for key in SEVERITY_ORDER:
        of_kind = [i for i in found if i["severity"] == key]
        if not of_kind:
            continue
        st.markdown(f"#### {len(of_kind)} {SEVERITY_LABEL[key]}{'s' if len(of_kind) > 1 else ''}")
        for issue in of_kind:
            with st.expander(f"**{issue['resource']}** — {issue['kind']}"):
                st.markdown(f"> {issue.get('evidence') or '*no quote recorded*'}")


def _resources(checklist: dict, links: dict) -> None:
    summary = checklist.get("summary", {})
    if summary:
        columns = st.columns(4)
        for column, (label, value) in zip(
            columns,
            [
                ("declared", summary.get("declared", 0)),
                ("pinned to a version", summary.get("pinned", 0)),
                ("named only", summary.get("named_only", 0)),
                ("values stated", summary.get("settings_stated", 0)),
            ],
            strict=True,
        ):
            column.metric(label, value)

    software = [s for s in checklist.get("software", []) if s.get("declared")]
    if software:
        st.subheader("Software the paper declares")
        st.caption("A version is what makes a tool identifiable. Named only ≠ pinned.")
        st.dataframe(
            [
                {
                    "name": s["name"],
                    "kind": s["kind"],
                    "specificity": s["specificity"],
                    "version": s.get("version") or "—",
                    "sections": ", ".join(s.get("sections", [])),
                    "evidence": s.get("evidence", ""),
                }
                for s in software
            ],
            width="stretch",
            hide_index=True,
        )

    settings = checklist.get("settings", [])
    if settings:
        st.subheader("Values the paper states")
        st.caption(
            "A value the paper prints raises the floor. A value only a repository "
            "command carries raises the ceiling — it may be a worked example."
        )
        st.dataframe(
            [
                {"parameter": s["name"], "value": s["value"], "evidence": s["evidence"]}
                for s in settings
            ],
            width="stretch",
            hide_index=True,
        )

    findings = links.get("findings", [])
    if findings:
        st.subheader("Identifiers, by the role the app assigned")
        st.caption(
            "The role is the point: a GSE in a Data availability statement is this "
            "paper's data, and the same GSE in a reference list is a dataset it "
            "merely cites. `stated` means the document said so; `inferred` means "
            "this reader decided, and says why."
        )
        st.dataframe(
            [
                {
                    "identifier": f["value"],
                    "kind": f["kind"],
                    "role": f.get("role", "—"),
                    "how": f.get("role_confidence", "—"),
                    "why": f.get("role_reason", ""),
                    "pages": ", ".join(str(n) for n in f.get("pages", [])[:12]),
                    "sections": ", ".join(f.get("sections", [])),
                    "occurrences": f.get("n_occurrences", 0),
                }
                for f in sorted(findings, key=lambda f: (f.get("role", ""), f["kind"]))
            ],
            width="stretch",
            hide_index=True,
        )


def _graph(graph: dict) -> None:
    if not graph:
        st.info("No dependency graph was written for this paper.")
        return
    if not graph.get("assessable", False):
        st.warning(
            "The graph is not assessable — which is not the same as empty. "
            + " ".join(graph.get("notes", []))
        )

    summary = graph.get("summary", {})
    verdicts = summary.get("verdicts", {})
    st.caption(
        "Blueprint §19. A result is reachable only if everything on its path is, "
        "so the weakest link decides the verdict."
    )
    columns = st.columns(len(verdicts) or 1)
    for column, (verdict, count) in zip(columns, verdicts.items(), strict=False):
        column.metric(verdict, count, help=VERDICT_HELP.get(verdict, ""))

    by_kind = summary.get("by_kind", {})
    if by_kind:
        st.markdown(
            f"{summary.get('nodes', 0)} nodes, {summary.get('edges', 0)} edges — "
            + ", ".join(f"{count} {kind}" for kind, count in by_kind.items())
        )

    paths = graph.get("paths", [])
    if paths:
        st.subheader("Each result, and what it depends on")
        st.dataframe(paths, width="stretch", hide_index=True)

    for note in graph.get("notes", []):
        st.caption(note)


def _report(paper: str) -> None:
    path = OUTPUT / paper / "report.md"
    if not path.is_file():
        st.info("No `report.md` for this paper.")
        return
    st.download_button(
        "Download report.md",
        path.read_text(),
        file_name=f"{paper}-report.md",
        mime="text/markdown",
    )
    st.markdown(path.read_text())


if __name__ == "__main__":
    main()
