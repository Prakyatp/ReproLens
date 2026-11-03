"""``report.md`` -- the five questions blueprint section 42 asks of a report.

    What is required?
    What was found?
    What is missing?
    Where was each item mentioned?
    What should the researcher investigate before starting reproduction?

Those are the section headings, in that order, with one change: the last one is
printed first. A researcher deciding whether to spend a semester on a paper
needs the blockers before the inventory, and burying them under three tables
would be a formatting decision with a cost measured in months.

**This module renders the audit's own JSON and nothing else.** ``render`` takes
the dict ``audit.py`` writes to ``links.json`` -- not the pages, not the
documents, not a model. That is a deliberate constraint rather than a
convenience: it makes the report provably a *view* of the findings, unable to
assert anything the JSON does not already contain, and it means a report can be
regenerated from a saved audit without re-reading the paper. A report that did
its own extraction could disagree with the findings it summarises, and the
disagreement would be invisible.

Three of blueprint section 37's prohibitions are about this file specifically.

* *Do not claim "this paper is reproducible" without actually running it.*
  Nothing here is called reproducible. The report states a readiness band and
  names the distinction in the one place a reader cannot miss it.
* *Do not remove provenance.* Every row carries where it was read -- a section
  and page for the paper, a repository and path for the code.
* *Do not hide uncertainty.* What could not be determined gets its own section
  with its own heading, not a footnote, because an undetermined item is the one
  thing most likely to be mistaken for a finding.
"""

from __future__ import annotations

import re

# What a reader should do about each issue kind, keyed on the phrase the rubric
# assigns. Written as instructions rather than restatements: "software version
# missing: STAR" tells a reader what the audit saw, and "pin STAR before you
# start" tells them what it costs them, which is the question they are asking.
_ACTIONS: dict[str, str] = {
    "required dataset unavailable": (
        "Obtain {resource} at publication scale before starting. The repository's copy is a demo."
    ),
    "essential code absent": (
        "Ask the authors for {resource}. The paper names it and it cannot be retrieved."
    ),
    "the repository does not contain the code required for a reported figure": (
        "Ask the authors for the code behind {resource}, or plan to rewrite it."
    ),
    "a declared resource does not resolve": (
        "Reach {resource} by its accession rather than the printed link, which points elsewhere."
    ),
    "no dependency declaration for a language the repository uses": (
        "Expect to reconstruct the {resource} environment from scratch. Nothing declares it."
    ),
    "version inconsistency between declarations": (
        "Decide which {resource} version is correct before building the environment."
    ),
    "preprocessing unclear": (
        "Find out how {resource} was configured. The code runs it and the paper does not "
        "describe it, so following the methods section builds a different pipeline."
    ),
    "reference genome or annotation unspecified": (
        "Establish which release of {resource} was used. A build name is not a version."
    ),
    "software version missing": "Pin {resource}. The paper names it and never versions it.",
    "critical hyperparameters absent": "Recover a value for {resource}.",
    "referenced file that does not exist": (
        "Supply {resource}. A repository script names it and the repository does not hold it."
    ),
    "a dependency the code imports is declared nowhere": (
        "Install {resource} by hand. The code imports it and no manifest asks for it."
    ),
    "the pinned interpreter is out of support": (
        "Expect build friction: {resource} no longer receives fixes."
    ),
    "undocumented environment variable": (
        "Find out what {resource} should be set to. The code reads it and no document names it."
    ),
    "package version missing": "Pin {resource} if the results depend on it.",
}

# Reading order inside one severity band. The rubric sorts issues by resource,
# which is the right order for a machine and the wrong one for a reader: it
# scatters the five distinct problems through fourteen alphabetised repeats of
# "this tool has no version". The one-off findings come first here.
_KIND_PRIORITY: dict[str, int] = {
    "required dataset unavailable": 0,
    "essential code absent": 0,
    "the repository does not contain the code required for a reported figure": 1,
    "a declared resource does not resolve": 2,
    "no dependency declaration for a language the repository uses": 3,
    "version inconsistency between declarations": 4,
    "referenced file that does not exist": 4,
    "preprocessing unclear": 5,
    "undocumented environment variable": 6,
    "critical hyperparameters absent": 6,
    "the pinned interpreter is out of support": 7,
    "a dependency the code imports is declared nowhere": 7,
    "reference genome or annotation unspecified": 8,
    "software version missing": 9,
    "package version missing": 9,
}
_DEFAULT_PRIORITY = 5

_SEVERITY_HEADINGS = {
    "hard_blocker": "Hard blockers",
    "major": "Major issues",
    "minor": "Minor issues",
}


def render(report: dict) -> str:
    """``report.md`` for one audited paper, from that paper's audit JSON."""
    lines: list[str] = []
    lines += _heading(report)
    lines += _before_you_start(report)
    lines += _required(report)
    lines += _found(report)
    lines += _datasets(report)
    lines += _supplements(report)
    lines += _figures(report)
    lines += _reachability(report)
    lines += _missing(report)
    lines += _undetermined(report)
    lines += _how_it_was_read(report)
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# the band, and what it is not
# --------------------------------------------------------------------------- #


def _heading(report: dict) -> list[str]:
    assessment = report.get("assessment", {})
    floor = assessment.get("score_floor", 0)
    ceiling = assessment.get("score_ceiling", 0)
    total = assessment.get("assessed_points", 0)
    counts = assessment.get("severity", {})

    title = f"# Reproducibility readiness: {report.get('paper_id', 'unknown')}"

    if not total:
        # "0-0 of 0 assessable points" is a nonsense band. Nothing was scored,
        # and the reason belongs above the fold rather than in a warning list.
        reason = next(
            (c.get("reason") for c in assessment.get("criteria", []) if c.get("reason")),
            "nothing could be assessed",
        )
        return [
            title,
            "",
            f"**Not assessed.** {reason[0].upper()}{reason[1:]}.",
            "",
            "No score is reported, because a score would be a verdict on the paper drawn from",
            "an empty reading. What this audit could not do is listed below; nothing in this",
            "report is evidence about the work itself.",
            "",
        ]

    out = [
        title,
        "",
        f"**{floor}-{ceiling} of {total} assessable points** "
        f"(rubric {assessment.get('rubric_version', '?')}), "
        f"{_plural(counts.get('hard_blocker', 0), 'hard blocker')}, "
        f"{counts.get('major', 0)} major and "
        f"{_plural(counts.get('minor', 0), 'minor issue')}.",
        "",
        "This measures how much of what a reproduction needs is *written down*. It is not a",
        "claim that the work reproduces, and it is not a claim that it does not: nothing here",
        "was executed. The range is the uncertainty -- the floor is what the evidence proves,",
        "the ceiling adds back what this audit could not settle either way.",
        "",
    ]
    criteria = assessment.get("criteria", [])
    if criteria:
        out += ["| criterion | points | of |", "|---|---|---:|"]
        for criterion in criteria:
            name = criterion["name"].replace("_", " ")
            if not criterion.get("assessed"):
                out.append(f"| {name} | *not assessed* | {criterion['weight']} |")
                continue
            floor, ceiling = criterion["floor"], criterion["ceiling"]
            band = str(floor) if floor == ceiling else f"{floor}-{ceiling}"
            out.append(f"| {name} | {band} | {criterion['weight']} |")
        out.append("")

    if total < 100:
        unassessed = [c for c in assessment.get("criteria", []) if not c.get("assessed")]
        if unassessed:
            out += [
                f"{len(unassessed)} of the rubric's criteria are **not assessed** rather than "
                f"scored, so the",
                f"total above is out of {total} and not 100. An unassessed criterion is not a",
                'zero; each one is listed under "What could not be determined" with the reason.',
                "",
            ]
    return out


# --------------------------------------------------------------------------- #
# question 5, printed first
# --------------------------------------------------------------------------- #


def _before_you_start(report: dict) -> list[str]:
    issues = report.get("assessment", {}).get("issues", [])
    if not issues:
        return ["## Before you start", "", "No issues were detected.", ""]

    out = ["## Before you start", ""]
    for severity in ("hard_blocker", "major", "minor"):
        group = sorted(
            (issue for issue in issues if issue.get("severity") == severity),
            key=lambda issue: (
                _KIND_PRIORITY.get(issue.get("kind", ""), _DEFAULT_PRIORITY),
                issue.get("resource", "").casefold(),
            ),
        )
        if not group:
            continue
        out += [f"### {_SEVERITY_HEADINGS[severity]} ({len(group)})", ""]
        for issue in group:
            resource = issue.get("resource", "?")
            kind = issue.get("kind", "")
            action = _ACTIONS.get(kind, kind).format(resource=f"`{resource}`")
            out.append(f"- {action}")
            if evidence := issue.get("evidence"):
                # The quote, indented under its instruction. Section 14: a
                # reader has to be able to check the claim, not take it.
                out.append(f"  - *{kind}* — {_quote(evidence)}")
        out.append("")

    out += [
        "Severity here is what the documents show, not what stopped anyone. A tool named",
        "without a version is a major issue by blueprint §22's taxonomy whether or not it",
        "turns out to matter, and which gaps actually block a reproduction is not visible",
        "from a paper. Expect this list to be longer than the one a reproduction attempt",
        "would produce.",
        "",
    ]
    return out


# --------------------------------------------------------------------------- #
# questions 1 and 2, with question 4 in every row
# --------------------------------------------------------------------------- #


def _required(report: dict) -> list[str]:
    out = [
        "## What is required",
        "",
        "Every resource either document presents as needed, with where it was read.",
        "",
        "| need | resource | status | where |",
        "|---|---|---|---|",
    ]
    rows = [
        *_data_rows(report),
        *_code_rows(report),
        *_environment_rows(report),
        *_parameter_rows(report),
    ]
    if not rows:
        return out[:3] + ["Nothing was detected as required.", ""]
    out += [
        f"| {need} | {resource} | {status} | {where} |" for need, resource, status, where in rows
    ]
    out.append("")
    return out


def _data_rows(report: dict) -> list[tuple[str, str, str, str]]:
    rows = []
    for finding in report.get("findings", []):
        role = finding.get("role")
        if role not in ("own_data", "external_data"):
            continue
        label = "data (this paper's)" if role == "own_data" else "data (third-party)"
        rows.append((label, f"`{finding['value']}`", "named", _finding_where(finding)))
    return rows


def _code_rows(report: dict) -> list[tuple[str, str, str, str]]:
    rows = []
    repository = report.get("repository", {})
    read = {entry["repository"]: entry for entry in repository.get("repositories", [])}
    unread = {entry["repository"]: entry for entry in repository.get("not_fetched", [])}

    for finding in report.get("findings", []):
        if finding.get("role") != "analysis_code":
            continue
        value = finding["value"]
        slug = _slug(value)
        if slug in read:
            status = f"read at `{read[slug]['commit'][:10]}`"
        elif slug in unread:
            status = "**not retrievable**"
        else:
            status = "named, not a git host"
        rows.append(("code", f"`{value}`", status, _finding_where(finding)))
    return rows


def _environment_rows(report: dict) -> list[tuple[str, str, str, str]]:
    rows = []
    dependencies = report.get("repository", {}).get("dependencies", {})
    # One row per version, not per file naming it: MATES pins python=3.9 in two
    # different READMEs, and the reader learns nothing from the second.
    seen: set[tuple[str, str, str]] = set()
    for interpreter in dependencies.get("interpreters", []):
        key = (interpreter["ecosystem"], interpreter["version"], interpreter.get("pinning", ""))
        if key in seen:
            continue
        seen.add(key)
        status = {
            "pinned": "pinned",
            "bounded": "lower bound only",
            "unconstrained": "**no version**",
        }.get(interpreter.get("pinning", ""), interpreter.get("pinning", ""))
        if interpreter.get("end_of_life"):
            status += f", out of support since {interpreter['end_of_life']}"
        rows.append(
            (
                "interpreter",
                f"`{interpreter['ecosystem']} {interpreter['version']}`",
                status,
                f"`{interpreter['source']}`",
            )
        )

    summary = dependencies.get("summary", {})
    if summary.get("distinct_packages"):
        pinned = summary.get("distinct_pinned", 0)
        total = summary["distinct_packages"]
        # The manifests the count actually came from. A docs/ copy of a
        # requirements file is a manifest and its packages are excluded from the
        # count, so citing it here would be citing a file the number ignores.
        runtime = [
            path
            for path in dependencies.get("manifest_files", [])
            if not path.partition(":")[2].startswith(("doc/", "docs/"))
        ]
        rows.append(
            (
                "packages",
                f"{total} distinct",
                f"{pinned} resolve to one version",
                ", ".join(f"`{f}`" for f in runtime[:3]) or "—",
            )
        )

    for language in dependencies.get("unmanaged_languages", []):
        rows.append(
            (
                "environment",
                f"{language.upper()} runtime",
                "**nothing declares it**",
                "no manifest in any repository",
            )
        )
    return rows


def _parameter_rows(report: dict) -> list[tuple[str, str, str, str]]:
    rows = []
    for item in report.get("checklist", {}).get("software", []):
        if not item.get("declared") or item.get("kind") != "reference":
            continue
        rows.append(
            (
                "reference data",
                f"`{item['name']}`",
                _specificity(item),
                _checklist_where(item),
            )
        )

    execution = report.get("repository", {}).get("execution", {})
    # One row per file, not per command naming it. This table is a list of what
    # a reader has to gather, and MATES asks for Drosophila_TE.csv from two
    # different tutorials -- which is one file to find, not two.
    listed: set[str] = set()
    for entry in execution.get("inputs", []):
        if entry["path"] in listed:
            continue
        listed.add(entry["path"])
        status = {
            "present": "in the repository",
            "demo_scale": "**demo scale only**",
            "absent": "**absent**",
            "user_supplied": "you must supply it",
        }.get(entry.get("status", ""), entry.get("status", ""))
        rows.append(("input file", f"`{entry['path']}`", status, f"`{entry['named_by']}`"))
    return rows


def _found(report: dict) -> list[str]:
    counts = report.get("by_role", {})
    out = [
        "## What was found",
        "",
        f"{len(report.get('findings', []))} resource identifier(s) across "
        f"{report.get('n_segments', 0)} segment(s), by the role each was assigned:",
        "",
        "| role | stated | inferred |",
        "|---|---:|---:|",
    ]
    for role, split in counts.items():
        out.append(
            f"| {role.replace('_', ' ')} | {split.get('stated', 0)} | {split.get('inferred', 0)} |"
        )
    out.append("")

    repository = report.get("repository", {})
    if repository.get("fetched"):
        inventory = repository.get("inventory", {})
        execution = repository.get("execution", {}).get("summary", {})
        traceability = repository.get("figure_traceability", {})
        out += [
            f"In the code: {inventory.get('n_files', 0)} file(s) across "
            f"{len(inventory.get('repositories', []))} repository(ies), "
            f"{execution.get('with_a_command', 0)} runnable command(s), "
            f"{execution.get('flags_with_a_value', 0)} flag(s) carrying a concrete value.",
            "",
        ]
        if traceability.get("assessable"):
            mapped = ", ".join(
                f"figure {entry['figure']} → `{entry['source']}`"
                for entry in traceability.get("scripts", [])
            )
            out += [f"Result-to-code mapping: {mapped}.", ""]
    return out


# --------------------------------------------------------------------------- #
# question 3
# --------------------------------------------------------------------------- #


def _supplements(report: dict) -> list[str]:
    """What the paper published outside the article, and what that leaves unread.

    Printed even when there is nothing to list, because an empty supplement
    section and an unreadable one mean opposite things and a reader cannot tell
    them apart from silence.
    """
    supplements = report.get("supplements") or {}
    summary = supplements.get("summary", {})
    declared = supplements.get("declared_files") or []
    references = supplements.get("references") or []
    out = ["## What the paper put outside the paper", ""]

    if not supplements:
        out += ["Supplements were not examined.", ""]
        return out

    if supplements.get("inventory") != "declared":
        out += [
            "**No manifest.** This input does not carry a list of the files the paper",
            "published, so which supplements exist could not be established. That is a limit",
            "of the input, not a paper that published none.",
            "",
        ]
    else:
        out += [
            f"- {summary.get('declared', 0)} file(s) declared, "
            f"{summary.get('may_carry_method_detail', 0)} of which could carry method detail",
            "",
        ]

    deferred = [r for r in references if r.get("in_methods")]
    out += [f"### Method detail the paper defers to a supplement ({len(deferred)})", ""]
    if deferred:
        out += [
            "The Methods section itself points at these. Whatever they contain is part of the",
            "method and is **not** covered by anything above: no supplement was read.",
            "",
        ]
        for entry in deferred:
            out.append(
                f"- **{entry['label']}** — cited {_plural(entry['mentions'], 'time')} "
                f"from the Methods section"
            )
    else:
        out.append("- None: the Methods section stands on its own.")
    out.append("")

    if declared:
        out += ["### Declared files", ""]
        for entry in declared:
            size = entry.get("size")
            shown = f"{size / 1e6:.1f} MB" if size else "size not stated"
            mark = "method-bearing" if entry.get("may_carry_method_detail") else "other"
            out.append(
                f"- **{entry['label']}** ({entry['kind']}, {shown}, {mark}) — "
                f"{_quote(entry.get('title') or entry.get('filename') or '', 120)}"
            )
        out += [
            "",
            "None of these were downloaded. The archives gate supplement files against",
            "automated access -- PMC answers with a captcha page and a 200 status, which is",
            "why no reachability claim is made here either.",
            "",
        ]

    other = [r for r in references if not r.get("in_methods")]
    if other:
        out += [
            f"### Also referenced, outside the Methods ({len(other)})",
            "",
            "- " + ", ".join(f"{r['label']} (x{r['mentions']})" for r in other[:14]),
            "",
        ]

    return out


def _datasets(report: dict) -> list[str]:
    """Whether the datasets the paper names are actually in the archives.

    Every other section reports what the paper says. This one reports what a
    third party said back, which is why it states plainly how many were asked
    about: a reader has to be able to tell a confirmed dataset from one nobody
    managed to check.
    """
    resolved = report.get("datasets_resolved") or {}
    entries = resolved.get("entries") or []
    out = ["## Whether the data is actually there", ""]

    if not entries:
        out += [
            "No accession was checked against an archive. Every statement above about a",
            "dataset reports what the paper says, not that the dataset exists.",
            "",
        ]
        return out

    if not resolved.get("attempted", True):
        out += [
            "Lookups were switched off for this run, so nothing below is evidence that a",
            "dataset does or does not exist.",
            "",
        ]

    summary = resolved.get("summary", {})
    out += [
        f"- {summary.get('public', 0)} present · "
        f"{summary.get('not_found', 0)} not in the archive · "
        f"{summary.get('restricted', 0)} controlled access · "
        f"{summary.get('unchecked', 0)} not checked",
        "",
    ]

    absent = [e for e in entries if e["status"] == "not_found"]
    gated = [e for e in entries if e["status"] == "restricted"]
    if absent or gated:
        out += ["### Named but not obtainable", ""]
        for entry in absent:
            out.append(f"- **{entry['accession']}** — {entry['detail']}")
        for entry in gated:
            out.append(f"- **{entry['accession']}** — {entry['detail']}")
        out.append("")

    present = [e for e in entries if e["status"] == "public"]
    if present:
        out += [
            "### Confirmed present",
            "",
            "The archive holds a record under each of these. That the record is the one the",
            "paper meant is a separate question this cannot settle -- a mistyped accession",
            "often resolves to a real dataset belonging to someone else.",
            "",
        ]
        for entry in present:
            label = entry.get("title") or entry.get("detail") or ""
            out.append(f"- `{entry['accession']}` — {_quote(label, 110) if label else 'present'}")
        out.append("")

    unchecked = [e for e in entries if e["status"] == "unchecked"]
    if unchecked:
        out += ["### Not checked", ""]
        for entry in unchecked:
            out.append(f"- `{entry['accession']}` — {entry['detail']}")
        out.append("")

    return out


_FIELD_LABELS = {
    "workflow_steps": "pipeline steps",
    "tools_named": "tools",
    "versions_visible": "versions",
    "parameters_visible": "parameter values",
    "accessions_visible": "accessions",
}


def _figures(report: dict) -> list[str]:
    """What the image channel claimed, and whether the text agrees.

    Its own section rather than merged into "What was found", because the two
    channels do not carry the same weight and a reader has to be able to see
    which is which. A regex match either is or is not in the document; a figure
    reading is a model's account of a picture, and the only checks available are
    the text's agreement and, on these figures, the shape of the value. Printing
    them together would borrow the text channel's credibility for the image
    channel's claims.
    """
    merge = report.get("figure_merge") or {}
    out = ["## What the figures say", ""]

    if not merge:
        out += [
            "No figures were read. Anything stated only inside a figure -- a pipeline",
            "diagram naming the tool chain, a threshold printed on an axis -- is absent",
            "from everything above. This is a gap in the audit, not a finding about the",
            "paper.",
            "",
        ]
        return out

    summary = merge.get("summary", {})
    agreement = summary.get("agreement")
    share = f"{agreement:.0%}" if isinstance(agreement, float) else "not measurable"
    confirmed = summary.get("corroborated", 0)
    total = confirmed + summary.get("figure_only", 0) + summary.get("conflicting", 0)
    misfiled = summary.get("misfiled", 0)
    out += [
        "A vision model read each figure. Unlike a text match, a figure reading cannot",
        "verify itself, so every value is labelled by whether the paper's own text says",
        "the same thing -- and only the corroborated ones affect any score.",
        "",
        f"- {merge.get('figures_read', 0)} figure(s) read, {confirmed} of {total} claims "
        f"confirmed by the text ({share} agreement)",
        "",
    ]
    if misfiled:
        out += [
            f"- {misfiled} value(s) were read correctly but filed under the wrong kind of "
            f"thing, and are excluded from the counts above and from every score",
            "",
        ]

    conflicts = merge.get("conflicts", [])
    out += [f"### Where a figure and the text disagree ({len(conflicts)})", ""]
    if conflicts:
        out += [
            "Read these first. The paper states two different values for the same thing,",
            "so a reproducer following one of them is following the wrong one -- and which",
            "is wrong is a judgement this audit has not made.",
            "",
        ]
        for conflict in conflicts:
            out.append(f"- **{conflict['key']}** — {conflict['evidence']} (`{conflict['figure']}`)")
    else:
        out.append("- None: no figure value contradicts the text.")
    out.append("")

    corroborated: dict[str, list[str]] = {}
    figure_only: dict[str, list[str]] = {}
    misfiled_by_field: dict[str, list[str]] = {}
    buckets = {
        "corroborated": corroborated,
        "figure_only": figure_only,
        "misfiled": misfiled_by_field,
    }
    for claim in merge.get("claims", []):
        bucket = buckets.get(claim["status"])
        if bucket is None:
            continue
        values = bucket.setdefault(claim["field"], [])
        if claim["value"] not in values:
            values.append(claim["value"])

    if corroborated:
        out += ["### Confirmed by the paper's own text", ""]
        for field_name, label in _FIELD_LABELS.items():
            if values := corroborated.get(field_name):
                out.append(
                    f"- **{label}** ({len(values)}): {', '.join(values[:12])}"
                    f"{' …' if len(values) > 12 else ''}"
                )
        out.append("")

    if figure_only:
        out += [
            "### Visible only in a figure — reported, never scored",
            "",
            "The text does not confirm these. Each may be perfectly real; this is also",
            "where a vision model's errors concentrate, so none of them moved a score.",
            "",
        ]
        for field_name, label in _FIELD_LABELS.items():
            if values := figure_only.get(field_name):
                out.append(
                    f"- **{label}** ({len(values)}): {', '.join(values[:12])}"
                    f"{' …' if len(values) > 12 else ''}"
                )
        out.append("")

    if misfiled_by_field:
        out += [
            "### Read correctly, filed wrongly — excluded from every score",
            "",
            "The value is in the paper; the kind of thing the model called it is not what",
            "it is. A gene name offered as a database accession would otherwise enter the",
            "audit as a dataset nobody deposited.",
            "",
        ]
        for field_name, label in _FIELD_LABELS.items():
            if values := misfiled_by_field.get(field_name):
                out.append(
                    f"- **not {label}** ({len(values)}): {', '.join(values[:12])}"
                    f"{' …' if len(values) > 12 else ''}"
                )
        out.append("")

    candidates = merge.get("vocabulary_candidates", [])
    if candidates:
        out += [
            f"### Tool names the software vocabulary does not know ({len(candidates)})",
            "",
            "Named in a figure, confirmed in the text, and absent from the curated list the",
            "checklist matches against -- so the checklist cannot see them at all. Rarest",
            "first, since a specific tool is named a handful of times and a generic word the",
            "model mistook for one is everywhere. Candidates for a human to add, not",
            "additions: deciding a capitalised word is a tool and not a plot type is a",
            "judgement this audit does not make.",
            "",
        ]
        for candidate in candidates:
            out.append(
                f"- `{candidate['name']}` — {candidate['text_mentions']} mention(s) in the text"
            )
        out.append("")

    return out


def _reachability(report: dict) -> list[str]:
    """Which results a reader can actually trace back to what produced them.

    Separate from "What is missing" because it answers a different question.
    That section lists defects; this one says which of the paper's own claims
    each defect stands in front of. A reader deciding whether to attempt a
    reproduction is choosing between results, and a defect with no result
    behind it costs them nothing.
    """
    graph = report.get("dependency_graph") or {}
    out = ["## Can each result be traced to what made it", ""]

    if not graph or not graph.get("assessable"):
        out += [
            "Not assessable: no repository was read, so nothing connects the paper's",
            "results to the code and data that produce them. An unanswered question,",
            "not an empty graph.",
            "",
        ]
        return out

    summary = graph["summary"]
    verdicts = summary["verdicts"]
    out += [
        f"{summary['nodes']} nodes, {summary['edges']} edges. Each of the paper's",
        "figures and each runnable command in the repository was walked outward to",
        "whatever it needs.",
        "",
        f"- **{verdicts['satisfied']} satisfied** -- the walk reached data that is present.",
        f"- **{verdicts['broken']} broken** -- the walk reached something missing or degraded.",
        f"- **{verdicts['unmapped']} unmapped** -- the walk ran out of edges first.",
        "",
    ]

    labels = {node["id"]: node.get("label", node["id"]) for node in graph["nodes"]}
    kinds = {node["id"]: node["kind"] for node in graph["nodes"]}

    broken = [p for p in graph["paths"] if p["verdict"] == "broken"]
    if broken:
        out += ["Broken, with the chain that reaches the break:", ""]
        for path in broken:
            chain = " -> ".join(labels.get(n, n) for n in path["nodes"])
            out += [f"- `{chain}`", f"  {path['reason']}."]
        out += [""]

    unmapped_results = [
        p
        for p in graph["paths"]
        if p["verdict"] == "unmapped" and kinds.get(p["start"]) == "result"
    ]
    if unmapped_results:
        out += [
            f"{_plural(len(unmapped_results), 'result')} could not be traced at all. This is",
            "the honest reading of a gap in the evidence, not a charge against the paper:",
            "the chain breaks because no extractor here connects a figure script to the",
            "data it reads, so what those figures need stays undetermined.",
            "",
        ]
        for path in unmapped_results[:8]:
            out += [f"- **{labels.get(path['start'], path['start'])}** -- {path['reason']}."]
        if len(unmapped_results) > 8:
            out += [f"- ... and {len(unmapped_results) - 8} more."]
        out += [""]

    for note in graph.get("notes", []):
        out += [note, ""]
    return out


def _missing(report: dict) -> list[str]:
    out = ["## What is missing", ""]
    gaps = [
        item
        for item in report.get("checklist", {}).get("software", [])
        if item.get("declared") and item.get("specificity") != "pinned"
    ]
    if gaps:
        out += [
            f"{len(gaps)} tool(s) the paper declares and does not pin down:",
            "",
            "| tool | kind | how it is named | where |",
            "|---|---|---|---|",
        ]
        for item in gaps:
            out.append(
                f"| `{item['name']}` | {item['kind']} | {_specificity(item)} | "
                f"{_checklist_where(item)} |"
            )
        out.append("")

    repository = report.get("repository", {})
    steps = repository.get("undocumented_steps", [])
    if steps:
        out += [
            f"{len(steps)} step(s) the code performs and the paper never names:",
            "",
        ]
        for step in steps:
            out.append(f"- `{step['tool']}` — {_quote(step['evidence'])}")
        out.append("")

    traceability = repository.get("figure_traceability", {})
    if traceability.get("assessable") and traceability.get("uncovered"):
        uncovered = ", ".join(str(n) for n in traceability["uncovered"])
        out += [
            f"Published figure(s) with no generating code in any repository: {uncovered}.",
            "",
        ]

    if len(out) == 2:
        out.append("Nothing was detected as missing.")
        out.append("")
    return out


# --------------------------------------------------------------------------- #
# section 37: do not hide uncertainty
# --------------------------------------------------------------------------- #


def _undetermined(report: dict) -> list[str]:
    assessment = report.get("assessment", {})
    out = [
        "## What could not be determined",
        "",
        "Not findings. Each of these is something this audit was unable to settle, listed so",
        "it cannot be mistaken for an absence in the paper.",
        "",
    ]
    wrote = False
    for criterion in assessment.get("criteria", []):
        if not criterion.get("assessed"):
            out.append(
                f"- **{criterion['name'].replace('_', ' ')}** is not assessed at all: "
                f"{criterion.get('reason', '')}"
            )
            wrote = True
            continue
        for note in criterion.get("undetermined", []):
            out.append(f"- **{criterion['name'].replace('_', ' ')}**: {note}")
            wrote = True

    for warning in report.get("warnings", []):
        out.append(f"- {warning}")
        wrote = True

    if not wrote:
        out.append("- Nothing: every criterion resolved to a single number.")
    out.append("")
    return out


# --------------------------------------------------------------------------- #
# question 4, for the audit itself
# --------------------------------------------------------------------------- #


def _how_it_was_read(report: dict) -> list[str]:
    out = [
        "## How this was read",
        "",
        f"- **Paper**: `{report.get('source', '?')}`, sha256 "
        f"`{report.get('sha256', '')[:16]}`, read by `{report.get('backend', '?')}`",
    ]
    pages = report.get("pages", [])
    ocr = [p["page"] for p in pages if p.get("backend") == "ocr"]
    if ocr:
        out.append(f"- **OCR** was used for segment(s) {', '.join(str(n) for n in ocr)}")
    unreadable = [p["page"] for p in pages if p.get("needs_ocr")]
    if unreadable:
        out.append(
            f"- **Unreadable** segment(s) {', '.join(str(n) for n in unreadable)}: "
            f"absence of a resource there is not evidence of absence"
        )

    repository = report.get("repository", {})
    for entry in repository.get("repositories", []):
        out.append(
            f"- **Code**: `{entry['repository']}` at `{entry['commit'][:10]}` "
            f"(committed {entry.get('committed_at', '?')[:10]}, "
            f"read {entry.get('fetched_at', '?')[:10]})"
        )
    for entry in repository.get("not_fetched", []):
        out.append(f"- **Code NOT read**: `{entry['repository']}` — {entry['reason']}")

    out += [
        f"- **Generated** {report.get('generated_at', '?')}",
        "",
        "The repository is read at the commit above, which is not necessarily its state when",
        "the paper was published.",
        "",
    ]
    return out


# --------------------------------------------------------------------------- #
# provenance helpers
# --------------------------------------------------------------------------- #


# Where a resource is *declared*, in preference order. An availability
# statement beats a body section, which beats the reference list: the same
# repository URL appears in MATES's methods and in its code availability
# statement, and the methods subsection it happens to appear in first says
# nothing about the paper having published its code.
_DECLARING_SECTIONS = ("code_availability", "data_availability", "associated_data")
_NOT_A_DECLARATION = ("page_furniture", "references")


def _finding_where(finding: dict) -> str:
    """The section and page a resource was read from, as section 14 requires.

    Section first, page second. A page number alone is not provenance for this
    project's purposes -- MATES page 20 holds three sections and the role of an
    accession depends entirely on which one it sits in.
    """
    occurrences = finding.get("occurrences", [])
    best = next(
        (o for o in occurrences if o.get("section") in _DECLARING_SECTIONS),
        next(
            (o for o in occurrences if o.get("section") not in _NOT_A_DECLARATION),
            occurrences[0] if occurrences else {},
        ),
    )
    section = (best.get("section_heading") or best.get("section") or "?").replace("_", " ")
    page = best.get("page")
    located = f"{section}, segment {page}" if page else section
    if (source := best.get("source")) and source != "text":
        located += f" ({source})"
    return located


def _checklist_where(item: dict) -> str:
    sections = [s.replace("_", " ") for s in item.get("sections", [])]
    where = ", ".join(sections) or "?"
    if mentions := item.get("mentions"):
        where += f" ({mentions} mention(s))"
    return where


def _specificity(item: dict) -> str:
    specificity = item.get("specificity", "?").replace("_", " ")
    if item.get("version"):
        return f"pinned to {item['version']}"
    if citations := item.get("citations"):
        return f"{specificity} [{', '.join(citations)}]"
    if assembly := item.get("assembly"):
        # Recorded and deliberately not treated as a version: "RepeatMasker for
        # GRCh38" is the exact wording that could not be reproduced from.
        return f"{specificity} (assembly {assembly}, which is not a version)"
    return specificity


# "owner/name:path/to/file" -- evidence the audit constructed, as opposed to a
# window cut out of the paper's running text.
_REPO_LABEL = re.compile(r"^[\w.-]+/[\w.-]+:")

# Shorter than this and a lowercase first word is probably just a lowercase
# first word. The paper-side windows are built at 120 characters either side of
# the match, so a genuine mid-word cut arrives well above this line; "we used
# STAR [32]" arrives well below it and keeps its first word.
_WINDOW_LENGTH = 100


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _quote(text: str, limit: int = 180) -> str:
    """Evidence trimmed to something a reader can read.

    A paper-side quote arrives as a fixed-width window centred on the match, so
    it starts and ends mid-word. Trimming it to a sentence boundary where one is
    near, and to a word boundary otherwise, costs nothing and is the difference
    between a quote and a fragment.

    Evidence this codebase constructed is left alone, recognized by starting
    with a file label, a capital or a digit -- which is a convention the issue
    builders keep for exactly this reason. Without it the rule that drops a
    leading partial word throws away real provenance instead of a fragment.
    """
    text = " ".join(str(text).split())
    if not text:
        return ""
    prefix = ""
    suffix = ""
    if not _REPO_LABEL.match(text) and len(text) > _WINDOW_LENGTH:
        head = text[:80]
        cut = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
        if cut > 0:
            text = text[cut + 2 :]
        elif " " in text and text[0].islower():
            text = text.partition(" ")[2]
            prefix = "…"
        # And the same at the far end: a window is cut mid-word there too, which
        # is where "where K is the num" came from.
        if not text.endswith((".", "!", "?", ")", "]")) and " " in text:
            text = text.rpartition(" ")[0].rstrip(",;:")
            suffix = "…"
    if len(text) > limit:
        text = text[:limit].rpartition(" ")[0].rstrip(",;:")
        suffix = "…"
    return prefix + text.replace("|", "\\|") + suffix


def _slug(value: str) -> str:
    """ "github.com/lab/project" -> "lab/project", to match a checkout's slug."""
    parts = [p for p in value.replace("https://", "").split("/") if p]
    return "/".join(parts[1:3]) if len(parts) >= 3 else value
