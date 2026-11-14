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
import re
import subprocess
import sys
from pathlib import Path

import streamlit as st

from reprolens.discovery.patterns import archive_url

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


# Identifier kinds whose value already *is* the link the paper printed. A
# "github.com/owner/name" finding is a URL with the scheme left off by the
# typesetter, not a bare name that needs looking up.
_IS_A_LINK = {"url", "github", "gitlab", "figshare", "zenodo", "dryad", "doi", "pubmed", "pmc"}


def paper_link(finding: dict) -> tuple[str | None, str]:
    """The link the paper itself gave for this item, and how it gave it.

    ``(None, "")`` when the paper gave none, which is the common case and has
    to stay distinguishable from a link this tool built. Measured across the
    five papers: not one of them prints a URL for any of its accessions. They
    name "GSE164978" and leave the reader to find it. So the archive lookup
    offered beside this is always labelled as constructed, because presenting
    it as the paper's citation would be reporting something the paper did not
    say -- in a tool whose entire job is telling those two apart.
    """
    value = str(finding.get("value", "")).strip()
    kind = finding.get("kind", "")
    if not value:
        return None, ""

    from_annotation = any(o.get("source") == "annotation" for o in finding.get("occurrences", []))
    how = "an embedded hyperlink" if from_annotation else "printed in the text"

    if value.startswith(("http://", "https://")):
        return value, how
    if kind in _IS_A_LINK and "/" in value and not value.startswith("10."):
        return f"https://{value}", how
    if kind in _IS_A_LINK and value.startswith("10."):
        return f"https://doi.org/{value}", how

    # An accession's own link, read out of the text around it. This is where it
    # actually lives: MATES's Data availability statement writes "(GSE212945,
    # https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE212945)" for 5 of
    # its 10 accessions, and none of those URLs survives as a separate `url`
    # finding -- the accession pattern claims the span first. Comparing the
    # accession list against the url list therefore says no paper links
    # anything, which is how this was missed the first time.
    for occurrence in finding.get("occurrences", []):
        found = re.search(
            r"https?://[^\s)\]>,]*" + re.escape(value) + r"[^\s)\]>,]*",
            occurrence.get("context", ""),
            re.I,
        )
        if found:
            return found.group(
                0
            ), f"printed beside the identifier on page {occurrence.get('page', '?')}"
    return None, ""


def mentions(finding: dict, limit: int = 3) -> list[dict]:
    """Where the paper names this, worst-provenance-first filtered out.

    Running headers are dropped: a DOI printed in the footer of all 22 pages is
    not the paper referencing it, and showing that as the mention would bury
    the one occurrence in the Data availability statement that matters.
    """
    occurrences = [
        o for o in finding.get("occurrences", []) if o.get("source") != "furniture"
    ] or finding.get("occurrences", [])
    ranked = sorted(
        occurrences,
        key=lambda o: (o.get("section") in ("references", "page_furniture", "front_matter"),),
    )
    return ranked[:limit]


def _where(occurrence: dict) -> str:
    section = occurrence.get("section_heading") or occurrence.get("section", "")
    return f"page {occurrence.get('page', '?')}" + (f", {section}" if section else "")


def _item(
    title: str,
    note: str,
    finding: dict | None,
    *,
    lookup: str | None = None,
    quote: str = "",
) -> None:
    """One row of the two panels: what it is, the link, and where it was said."""
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if note:
            st.caption(note)

        if finding is not None:
            url, how = paper_link(finding)
            if url:
                st.markdown(f"🔗 [{url}]({url}) — {how}")
            else:
                st.markdown("🔗 **the paper gives no link for this**, only the identifier.")
            if lookup:
                # Clickable, but never presented as the paper's own citation.
                # The label carries the distinction, because the link itself
                # cannot: a GEO landing page looks identical whether the paper
                # linked it or this tool built it from the accession.
                st.markdown(
                    f"🔎 [look it up]({lookup}) — built from the identifier, "
                    f"not a link the paper gave"
                )

            for occurrence in mentions(finding):
                st.markdown(
                    f"<div style='font-size:0.84rem;color:#444'>"
                    f"<b>{_where(occurrence)}</b> — “{occurrence.get('context', '')[:300]}”"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        elif quote:
            st.markdown(
                f"<div style='font-size:0.84rem;color:#444'>“{quote[:400]}”</div>",
                unsafe_allow_html=True,
            )


def _run(source: str) -> None:
    """Run the audit on one document, surfacing its own failure verbatim.

    Resolution is left ON. With lookups disabled every dataset comes back
    "unchecked", and this page's whole job is to say what is *not available* --
    a claim that cannot be made without asking the archive. Figure reading is
    left off, because it needs a vision backend that may not be running, and a
    missing backend should not fail an audit.
    """
    with st.spinner(f"auditing {source} \u2026 this takes a minute"):
        done = subprocess.run(  # noqa: S603 -- fixed argv, path chosen from disk
            [sys.executable, str(ROOT / "audit.py"), source, "--out", str(OUTPUT), "--no-vlm"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
    if done.returncode == 0:
        st.success("done")
        st.rerun()
    else:
        # In full rather than summarised: a failed audit is the one case where
        # the tool's own output is the finding.
        st.error("the audit failed")
        st.code((done.stderr or done.stdout)[-3000:])


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

        uploaded = st.file_uploader("Upload a paper", type=["pdf", "xml"])
        if uploaded is not None:
            # Saved under data/ rather than a temp directory, so the audit stays
            # reproducible from the repo: a report whose source document has
            # been deleted cannot be re-checked.
            folder = "xml" if uploaded.name.lower().endswith(".xml") else "papers"
            target = ROOT / "data" / folder / uploaded.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(uploaded.getbuffer())
            if st.button(f"Audit {uploaded.name}", type="primary", width="stretch"):
                _run(str(target.relative_to(ROOT)))

        # Only the two directories papers live in. A recursive sweep of data/
        # also offered jarvis's VASP test fixtures and MATES's vendored figure
        # PDF -- eighteen entries, three of them papers.
        sources = sorted(
            str(path.relative_to(ROOT))
            for directory, suffix in (("papers", "*.pdf"), ("xml", "*.xml"))
            for path in (ROOT / "data" / directory).glob(suffix)
        )
        if sources:
            st.caption("or audit one already in `data/`")
            source = st.selectbox("Source document", sources, label_visibility="collapsed")
            if st.button("Run audit", width="stretch"):
                _run(source)

        st.caption(
            "Archive lookups are on, so a dataset can be reported as missing "
            "rather than merely unchecked."
        )

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

    checklist = load(paper, "checklist") or {}
    missing, present, criteria, graph, provenance = st.tabs(
        [
            f"⚠ Not available ({_count_missing(assessment, links)})",
            f"✓ Present ({_count_present(assessment, links, checklist)})",
            "Score detail",
            "Dependencies",
            "Full report",
        ]
    )
    with missing:
        _missing(assessment, links)
    with present:
        _present(links, checklist)
    with criteria:
        _criteria(assessment)
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


def _by_value(links: dict) -> dict[str, dict]:
    return {str(f.get("value", "")): f for f in links.get("findings", [])}


def _dataset_entries(links: dict) -> list[dict]:
    return links.get("datasets_resolved", {}).get("entries", [])


def _count_missing(assessment: dict, links: dict) -> int:
    absent = [e for e in _dataset_entries(links) if e.get("status") in ("not_found", "restricted")]
    return len(absent) + len(assessment.get("issues", []))


# Every kind of thing the Present panel renders. The number on the tab has to be
# the number of things in it: atomate2 pins no version and deposits no dataset,
# so an earlier version labelled its tab "Present (0)" above a panel listing six
# repositories.
_PRESENT_LINK_KINDS = ("github", "gitlab", "zenodo", "figshare", "dryad")


def _count_present(assessment: dict, links: dict, checklist: dict) -> int:
    public = [e for e in _dataset_entries(links) if e.get("status") == "public"]
    linked = [f for f in links.get("findings", []) if f.get("kind") in _PRESENT_LINK_KINDS]
    pinned = [s for s in checklist.get("software", []) if s.get("declared") and s.get("version")]
    return len(public) + len(linked) + len(pinned) + len(checklist.get("settings", []))


def _missing(assessment: dict, links: dict) -> None:
    st.caption(
        "Everything a reproduction needs that this paper does not supply — each with "
        "the link the paper gave, where it gave one, and the place in the paper that "
        "named it."
    )

    findings = _by_value(links)
    resolution = links.get("datasets_resolved", {})
    entries = _dataset_entries(links)

    if not resolution.get("attempted", False):
        # The distinction the whole tool turns on: nothing was asked, so nothing
        # is known. An "unchecked" dataset is not an available one.
        st.warning(
            "**Datasets were not looked up on this run**, so nothing below says whether "
            "a dataset actually exists. " + " ".join(resolution.get("notes", []))
        )

    absent = [e for e in entries if e.get("status") in ("not_found", "restricted")]
    if absent:
        st.subheader(f"Datasets that are not there ({len(absent)})")
        for entry in absent:
            accession = entry["accession"]
            status = {
                "not_found": "the archive has no such record",
                "restricted": "controlled access — an application is required",
            }.get(entry["status"], entry["status"])
            _item(
                f"{accession} — {status}",
                entry.get("detail", ""),
                findings.get(accession),
                lookup=archive_url(entry.get("kind", ""), accession),
            )

    issues = assessment.get("issues", [])
    for key in SEVERITY_ORDER:
        of_kind = [i for i in issues if i["severity"] == key]
        if not of_kind:
            continue
        st.subheader(f"{len(of_kind)} {SEVERITY_LABEL[key]}{'s' if len(of_kind) > 1 else ''}")
        for issue in of_kind:
            resource = str(issue.get("resource", ""))
            _item(
                f"{resource} — {issue.get('kind', '')}",
                "",
                findings.get(resource),
                quote=issue.get("evidence", ""),
            )

    if not absent and not issues:
        st.success(
            "Nothing was flagged. That is a finding about the paper, not a default — "
            "see *Score detail* for what was checked."
        )


def _present(links: dict, checklist: dict) -> None:
    st.caption("What the paper does supply, with the link it gave and where it said so.")
    findings = _by_value(links)

    public = [e for e in _dataset_entries(links) if e.get("status") == "public"]
    if public:
        st.subheader(f"Datasets confirmed in the archive ({len(public)})")
        for entry in public:
            accession = entry["accession"]
            _item(
                f"{accession} — {entry.get('title') or 'public'}",
                entry.get("detail", ""),
                findings.get(accession),
                lookup=archive_url(entry.get("kind", ""), accession),
            )

    repositories = [f for f in links.get("findings", []) if f.get("kind") in ("github", "gitlab")]
    if repositories:
        st.subheader(f"Code repositories the paper points at ({len(repositories)})")
        for finding in repositories:
            _item(str(finding["value"]), "", finding)

    archives = [
        f for f in links.get("findings", []) if f.get("kind") in ("zenodo", "figshare", "dryad")
    ]
    if archives:
        st.subheader(f"Archived data and artifacts ({len(archives)})")
        for finding in archives:
            _item(str(finding["value"]), "", finding)

    pinned = [s for s in checklist.get("software", []) if s.get("declared") and s.get("version")]
    if pinned:
        st.subheader(f"Software pinned to a version ({len(pinned)})")
        st.dataframe(
            [
                {
                    "name": s["name"],
                    "version": s["version"],
                    "kind": s["kind"],
                    "where": ", ".join(s.get("sections", [])),
                    "evidence": s.get("evidence", ""),
                }
                for s in pinned
            ],
            width="stretch",
            hide_index=True,
        )

    settings = checklist.get("settings", [])
    if settings:
        st.subheader(f"Parameter values the paper states ({len(settings)})")
        st.dataframe(
            [
                {"parameter": s["name"], "value": s["value"], "evidence": s["evidence"]}
                for s in settings
            ],
            width="stretch",
            hide_index=True,
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
