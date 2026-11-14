"""ReproLens — drop a paper in, get what a reproduction of it needs.

    uv run streamlit run ui.py

One page. A paper goes in; the audit runs; the result comes out. Nothing is
kept: the upload and its output live in a temporary directory for the length of
the session, so the page carries no library of papers and no state from the last
visitor.

It runs no extraction of its own. Every number here came out of a JSON file that
``audit.py`` wrote, which keeps one rule easy to hold: there is exactly one
place a finding can be produced, and this is not it.

The thing this view exists to get right is the **band**. Every score in this
project is a floor and a ceiling: the floor is what the paper definitely
documents, the ceiling what it might. A single number would read as precision
the evidence does not support and would hide the distinction the whole tool is
built on -- that a paper loses points for what it did not say and never for what
the reader could not determine. So nothing here collapses a band, and "not
assessed" is drawn as its own state rather than as a zero.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import streamlit as st

from reprolens.discovery.patterns import archive_url

ROOT = Path(__file__).resolve().parent

# Where the current paper's audit lives, for this session only.
RESULT = "result_dir"
NAME = "paper_name"
WORKDIR = "work_dir"

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


def load(name: str) -> dict:
    """One artifact of the current audit, or ``{}`` if it was not written."""
    directory = st.session_state.get(RESULT)
    if not directory:
        return {}
    path = Path(directory) / f"{name}.json"
    return json.loads(path.read_text()) if path.is_file() else {}


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


def find_result(out: Path) -> Path | None:
    """The directory ``audit.py`` wrote its artifacts into.

    It names that directory after the document's stem rather than anything the
    caller chose, so the caller has to look. A directory without
    ``assessment.json`` is not a result: the audit can write a partial reading
    and still refuse to score it, and showing that as a result would present
    "could not be read" as "nothing was found".
    """
    if not out.is_dir():
        return None
    produced = sorted(path for path in out.iterdir() if (path / "assessment.json").is_file())
    return produced[0] if produced else None


def _process(upload) -> None:
    """Audit one uploaded document in a directory of its own.

    The upload goes into its own empty directory and is passed to ``audit.py``
    by path. Nothing in it is ever executed -- Python is parsed with ``ast`` and
    everything else is read as text -- and nothing is kept: the whole working
    directory is removed when the next paper is dropped.

    Archive lookups are left ON. With them off every dataset comes back
    "unchecked", and a page whose job is to say what is *not available* cannot
    make that claim without asking the archive. Figure reading is left off: it
    needs a vision backend that may not be running, and a missing backend
    should not fail an audit.
    """
    _discard()
    workdir = Path(tempfile.mkdtemp(prefix="reprolens-"))
    incoming = workdir / "incoming"
    incoming.mkdir()
    source = incoming / Path(upload.name).name
    source.write_bytes(upload.getbuffer())
    out = workdir / "out"

    with st.status(f"Reading {upload.name} …", expanded=True) as status:
        st.write("extracting text, links and figures")
        st.write("cloning the repositories the paper points at")
        st.write("asking the archives whether each dataset is there")
        done = subprocess.run(  # noqa: S603 -- fixed argv, path written by us
            [sys.executable, str(ROOT / "audit.py"), str(source), "--out", str(out), "--no-vlm"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if done.returncode != 0:
            # In full rather than summarised: a failed audit is the one case
            # where the tool's own output is the finding.
            status.update(label="The audit failed", state="error")
            st.code((done.stderr or done.stdout)[-4000:])
            shutil.rmtree(workdir, ignore_errors=True)
            return
        status.update(label=f"Audited {upload.name}", state="complete")

    produced = find_result(out)
    if produced is None:
        st.error("The audit wrote no assessment. Nothing below would be evidence.")
        shutil.rmtree(workdir, ignore_errors=True)
        return

    st.session_state[WORKDIR] = str(workdir)
    st.session_state[RESULT] = str(produced)
    st.session_state[NAME] = upload.name
    st.rerun()


def _discard() -> None:
    """Forget the current paper, and take its files with it."""
    workdir = st.session_state.pop(WORKDIR, None)
    if workdir:
        shutil.rmtree(workdir, ignore_errors=True)
    st.session_state.pop(RESULT, None)
    st.session_state.pop(NAME, None)


def _landing() -> None:
    """The whole product before a paper arrives: one place to drop one."""
    st.markdown("<div style='height:7vh'></div>", unsafe_allow_html=True)
    left, middle, right = st.columns([1, 2, 1])
    with middle:
        st.markdown(
            "<h1 style='text-align:center;margin-bottom:0'>ReproLens</h1>"
            "<p style='text-align:center;color:#666;font-size:1.05rem;margin-top:0.4rem'>"
            "Drop a paper in. Find out what reproducing it would need, "
            "and what the paper never says.</p>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:1.5vh'></div>", unsafe_allow_html=True)

        upload = st.file_uploader(
            "Drop a paper here",
            type=["pdf", "xml"],
            help="A journal PDF, or a JATS XML full text.",
        )
        if upload is not None:
            _process(upload)

        st.markdown(
            "<p style='text-align:center;color:#888;font-size:0.82rem;margin-top:1.2rem'>"
            "Nothing is stored. The paper and its audit are deleted when you leave "
            "or drop another.<br>Nothing in a fetched repository is ever executed."
            "</p>",
            unsafe_allow_html=True,
        )


def main() -> None:
    st.set_page_config(page_title="ReproLens", page_icon="\U0001f52c", layout="wide")
    if st.session_state.get(RESULT):
        _results()
    else:
        _landing()


def _results() -> None:
    assessment = load("assessment")
    links = load("links")
    checklist = load("checklist")

    heading, action = st.columns([5, 1])
    with heading:
        st.markdown(f"## {st.session_state.get(NAME, 'Result')}")
        st.caption(
            f"read by {links.get('backend', 'unknown')} \u00b7 "
            f"{links.get('n_segments', '?')} segment(s) \u00b7 "
            f"rubric {assessment.get('rubric_version', '?')}"
        )
    with action:
        st.markdown("<div style='height:1.4rem'></div>", unsafe_allow_html=True)
        if st.button("Another paper", width="stretch"):
            _discard()
            st.rerun()

    for warning in links.get("warnings", []):
        # A warning leads, always. "Found nothing" and "could not read it" are
        # different claims, and only one of them is about the paper.
        st.warning(warning)

    _headline(assessment)
    st.divider()

    missing, present, criteria, graph, report = st.tabs(
        [
            f"\u26a0 Not available ({_count_missing(assessment, links)})",
            f"\u2713 Present ({_count_present(assessment, links, checklist)})",
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
        _graph(load("graph"))
    with report:
        _report()


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


def _report() -> None:
    directory = st.session_state.get(RESULT)
    path = Path(directory) / "report.md" if directory else None
    if path is None or not path.is_file():
        st.info("No full report was written for this paper.")
        return
    text = path.read_text()
    st.download_button(
        "Download report.md",
        text,
        file_name=f"{Path(st.session_state.get(NAME, 'paper')).stem}-report.md",
        mime="text/markdown",
    )
    st.markdown(text)


if __name__ == "__main__":
    main()
