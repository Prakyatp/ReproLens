"""The audit as a reader sees it: one dict a front end can render without thinking.

Built from the artifacts ``audit.py`` wrote and nothing else, so a front end
cannot assert anything the audit did not. Every rule about *presentation* that
carries meaning lives here rather than in a template, because two front ends
rendering the same audit must not disagree about it:

- whose link it is. A GEO landing page looks identical whether the paper
  printed it or this tool built it from the accession, so only the label can
  tell a reader which, and the label is decided here.
- a channel that did not run is not a channel that found nothing. The
  per-channel conditions are read from what the audit recorded about its own
  run -- ``attempted``, ``fetched``, a per-figure ``reading`` -- never inferred
  from a count, because zero findings is exactly the ambiguity being resolved.
- the score is never handed over without its coverage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from reprolens.discovery.patterns import archive_url

SEVERITY_ORDER = ("hard_blocker", "major", "minor")
SEVERITY_LABEL = {"hard_blocker": "hard blocker", "major": "major issue", "minor": "minor issue"}

CRITERION_LABEL = {
    "data_availability": "Data availability",
    "code_availability": "Code availability",
    "environment_specification": "Environment specification",
    "parameters_configuration": "Parameters and configuration",
    "method_completeness": "Method completeness",
    "execution_instructions": "Execution instructions",
    "result_traceability": "Result traceability",
}

_IS_A_LINK = {"url", "github", "gitlab", "figshare", "zenodo", "dryad", "doi", "pubmed", "pmc"}
PRESENT_LINK_KINDS = ("github", "gitlab", "zenodo", "figshare", "dryad")

_STATUS_WORDS = {
    "not_found": "the archive has no such record",
    "restricted": "controlled access: an application is required",
}


def build(result_dir: Path) -> dict:
    """Everything a results page shows, from one audit's output directory."""
    links = _load(result_dir / "links.json")
    assessment = _load(result_dir / "assessment.json")
    checklist = _load(result_dir / "checklist.json")
    figures = _load(result_dir / "figures.json", default=[])
    graph = _load(result_dir / "graph.json")
    report = result_dir / "report.md"

    return {
        "paper_id": links.get("paper_id", result_dir.name),
        "generated_at": links.get("generated_at"),
        "headline": headline(assessment),
        "channels": channels(links, figures),
        "warnings": links.get("warnings", []),
        "missing": missing(assessment, links),
        "present": present(links, checklist),
        "criteria": criteria(assessment),
        "figures": figure_cards(figures),
        "supplements": links.get("supplements", {}),
        "graph": graph,
        "report_markdown": report.read_text() if report.is_file() else "",
    }


def _load(path: Path, default=None):
    if not path.is_file():
        return {} if default is None else default
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# The headline


def headline(assessment: dict) -> dict:
    """The score, and the coverage it must never appear without."""
    return {
        "score": assessment.get("score"),
        "coverage": assessment.get("coverage", 0.0),
        "min_coverage": assessment.get("min_coverage", 0.5),
        "floor": assessment.get("score_floor", 0),
        "ceiling": assessment.get("score_ceiling", 0),
        "assessed_points": assessment.get("assessed_points", 0),
        "determined_points": assessment.get("determined_points", 0),
        "severity": {key: assessment.get("severity", {}).get(key, 0) for key in SEVERITY_ORDER},
        "rubric_version": assessment.get("rubric_version", "?"),
    }


# ---------------------------------------------------------------------------
# The channels


def channels(links: dict, figures: list) -> list[dict]:
    """The condition of every channel, stated whether it ran or not."""
    rows: list[dict] = [
        {"name": "text", "ran": True, "text": f"Text read by {links.get('backend', 'unknown')}"}
    ]

    pages = links.get("pages") or []
    ocr_pages = [p for p in pages if p.get("backend") == "ocr"]
    if ocr_pages:
        rows.append(
            {
                "name": "ocr",
                "ran": True,
                "text": f"{len(ocr_pages)} page(s) had no text layer and were read by OCR",
            }
        )

    read = [f for f in figures if f.get("reading")]
    if not figures:
        rows.append({"name": "figures", "ran": False, "text": "No figures extracted"})
    elif read:
        model = read[0]["reading"].get("model", "an unnamed model")
        rows.append(
            {
                "name": "figures",
                "ran": True,
                "text": f"{len(read)} of {len(figures)} figures read by {model}",
            }
        )
    else:
        rows.append(
            {
                "name": "figures",
                "ran": False,
                "text": f"{len(figures)} figures extracted, NONE read",
            }
        )

    supplements = links.get("supplements") or {}
    summary = supplements.get("summary") or {}
    received = summary.get("received", 0)
    if received:
        read_count = summary.get("contents_read", 0)
        rows.append(
            {
                "name": "supplements",
                "ran": read_count > 0,
                "text": f"{read_count} of {received} supplied supplement(s) read",
            }
        )

    repo = links.get("repository") or {}
    fetched = repo.get("repositories") or []
    if repo.get("fetched") and fetched:
        rows.append(
            {"name": "repository", "ran": True, "text": f"{len(fetched)} repository/ies read"}
        )
    elif repo.get("fetched"):
        rows.append({"name": "repository", "ran": False, "text": "No repository was reachable"})
    else:
        rows.append({"name": "repository", "ran": False, "text": "Repositories NOT fetched"})

    datasets = links.get("datasets_resolved") or {}
    counts = datasets.get("summary") or {}
    if not datasets.get("attempted"):
        rows.append({"name": "archives", "ran": False, "text": "Archives NOT asked"})
    else:
        checked = counts.get("checked", 0)
        total = checked + counts.get("unchecked", 0)
        rows.append(
            {
                "name": "archives",
                "ran": checked > 0,
                "text": f"{checked} of {total} datasets checked against an archive",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Whose link it is


def paper_link(finding: dict) -> tuple[str | None, str]:
    """The link the paper itself gave for this item, and how it gave it.

    ``(None, "")`` when the paper gave none, which has to stay distinguishable
    from a link this tool built. MATES writes "(GSE212945,
    https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE212945)" for five of
    its ten accessions and none of those URLs survives as a separate ``url``
    finding, because the accession pattern claims the span first -- so the
    accession's own link is read out of the text around it.
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

    for occurrence in finding.get("occurrences", []):
        found = re.search(
            r"https?://[^\s)\]>,]*" + re.escape(value) + r"[^\s)\]>,]*",
            occurrence.get("context", ""),
            re.I,
        )
        if found:
            return found.group(0), f"printed beside the identifier on {where(occurrence)}"
    return None, ""


def mentions(finding: dict, limit: int = 3) -> list[dict]:
    """Where the paper names this, with running headers filtered out."""
    occurrences = [
        o for o in finding.get("occurrences", []) if o.get("source") != "furniture"
    ] or finding.get("occurrences", [])
    ranked = sorted(
        occurrences,
        key=lambda o: (o.get("section") in ("references", "page_furniture", "front_matter"),),
    )
    return [
        {
            "where": where(o),
            "quote": (o.get("context") or "")[:300],
            "document": o.get("document", ""),
        }
        for o in ranked[:limit]
    ]


def where(occurrence: dict) -> str:
    """``page 20, Data availability`` -- or ``S2 Appendix, page 3`` for a supplement."""
    section = occurrence.get("section_heading") or occurrence.get("section", "")
    place = f"page {occurrence.get('page', '?')}"
    if document := occurrence.get("document"):
        place = f"{document}, {place}"
    return place + (f", {section}" if section and section != "front_matter" else "")


def item(
    title: str, note: str, finding: dict | None, *, lookup: str | None = None, quote: str = ""
) -> dict:
    """One row of the two panels: what it is, the link, and where it was said."""
    row: dict = {
        "title": title,
        "note": note,
        "paper_link": None,
        "paper_link_how": "",
        "lookup": None,
        "mentions": [],
        "quote": quote[:400],
    }
    if finding is not None:
        url, how = paper_link(finding)
        row["paper_link"] = url
        row["paper_link_how"] = how
        row["mentions"] = mentions(finding)
        # Clickable, but never presented as the paper's own citation; the
        # front end must keep the label, because the link itself cannot carry
        # the distinction.
        row["lookup"] = lookup
    return row


# ---------------------------------------------------------------------------
# The two panels


def _by_value(links: dict) -> dict[str, dict]:
    return {str(f.get("value", "")): f for f in links.get("findings", [])}


def _dataset_entries(links: dict) -> list[dict]:
    return links.get("datasets_resolved", {}).get("entries", [])


def missing(assessment: dict, links: dict) -> dict:
    findings = _by_value(links)
    resolution = links.get("datasets_resolved", {})
    entries = _dataset_entries(links)

    absent = [e for e in entries if e.get("status") in ("not_found", "restricted")]
    datasets = [
        item(
            f"{e['accession']}",
            e.get("detail", ""),
            findings.get(e["accession"]),
            lookup=archive_url(e.get("kind", ""), e["accession"]),
        )
        | {"status": e["status"], "status_text": _STATUS_WORDS.get(e["status"], e["status"])}
        for e in absent
    ]

    issues = assessment.get("issues", [])
    groups = []
    for key in SEVERITY_ORDER:
        of_kind = [i for i in issues if i["severity"] == key]
        if not of_kind:
            continue
        groups.append(
            {
                "severity": key,
                "label": SEVERITY_LABEL[key],
                "items": [
                    item(
                        str(i.get("resource", "")),
                        i.get("kind", ""),
                        findings.get(str(i.get("resource", ""))),
                        quote=i.get("evidence", ""),
                    )
                    for i in of_kind
                ],
            }
        )

    return {
        "count": len(absent) + len(issues),
        "datasets_not_looked_up": not resolution.get("attempted", False),
        "resolution_notes": resolution.get("notes", []),
        "datasets": datasets,
        "issues": groups,
    }


def present(links: dict, checklist: dict) -> dict:
    findings = _by_value(links)
    all_findings = links.get("findings", [])

    public = [e for e in _dataset_entries(links) if e.get("status") == "public"]
    datasets = [
        item(
            e["accession"],
            e.get("title") or e.get("detail", ""),
            findings.get(e["accession"]),
            lookup=archive_url(e.get("kind", ""), e["accession"]),
        )
        for e in public
    ]
    repositories = [
        item(str(f["value"]), "", f) for f in all_findings if f.get("kind") in ("github", "gitlab")
    ]
    archives = [
        item(str(f["value"]), "", f)
        for f in all_findings
        if f.get("kind") in ("zenodo", "figshare", "dryad")
    ]
    pinned = [
        {
            "name": s["name"],
            "version": s["version"],
            "kind": s.get("kind", ""),
            "where": ", ".join(s.get("sections", [])),
            "evidence": s.get("evidence", ""),
        }
        for s in checklist.get("software", [])
        if s.get("declared") and s.get("version")
    ]
    settings = [
        {"name": s["name"], "value": s["value"], "evidence": s.get("evidence", "")}
        for s in checklist.get("settings", [])
    ]
    return {
        "count": len(datasets) + len(repositories) + len(archives) + len(pinned) + len(settings),
        "datasets": datasets,
        "repositories": repositories,
        "archives": archives,
        "pinned_software": pinned,
        "settings": settings,
    }


# ---------------------------------------------------------------------------
# Criteria and figures


def criteria(assessment: dict) -> list[dict]:
    rows = []
    for c in assessment.get("criteria", []):
        settled = c["floor"] + c["weight"] - c["ceiling"]
        rows.append(
            {
                "name": c["name"],
                "label": CRITERION_LABEL.get(c["name"], c["name"]),
                "weight": c["weight"],
                "floor": c["floor"],
                "ceiling": c["ceiling"],
                "assessed": c.get("assessed", True),
                "reason": c.get("reason", ""),
                "settled": settled,
                "basis": c.get("basis", []),
                "undetermined": c.get("undetermined", []),
            }
        )
    return rows


def figure_cards(figures: list) -> list[dict]:
    cards = []
    for f in figures:
        reading = f.get("reading") or {}
        contents = reading.get("contents") or {}
        cards.append(
            {
                "figure_id": f.get("figure_id"),
                "label": f.get("label"),
                "page": f.get("page"),
                "document": f.get("document", ""),
                "caption": (f.get("caption") or "")[:400],
                "image": Path(f["image"]).name if f.get("image") else None,
                "read": bool(reading),
                "model": reading.get("model"),
                "figure_type": contents.get("figure_type"),
                "workflow_steps": contents.get("workflow_steps", []),
                "tools_named": contents.get("tools_named", []),
                "corroborated": reading.get("corroborated", []),
                "unverified": reading.get("vlm_only_unverified", []),
                "misfiled": reading.get("not_accession_shaped", []),
            }
        )
    return cards
