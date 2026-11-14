#!/usr/bin/env python3
"""ReproLens -- the grader. Scores the app's output against hand-annotated truth.

    python check.py --out output/

This file is the ONLY place allowed to read ``benchmark/``. The ground-truth
records state their findings in prose -- "RepeatMasker and GENCODE versions were
never specified" is literally the conclusion the app is supposed to reach on its
own -- so if that text ever reached the app's input, every number measured
afterward would be meaningless and nothing would visibly break. Keeping the
import on this side of the line makes that impossible rather than merely
discouraged.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from reprolens.extraction.checklist import find_names
from reprolens.scoring.rubric import WEIGHTS

BENCHMARK = Path("benchmark/papers")
TEMPLATE = Path("benchmark/tier2-template.json")

# A placeholder left in a ground-truth record, e.g. mates.json's github field.
_UNRESOLVED = re.compile(r"not confirmed|TODO", re.I)


def normalize_repo(value: str) -> str:
    """Compare repository references by host+path, ignoring scheme and case."""
    value = value.strip().rstrip("/")
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    return value.removesuffix(".git").lower()


# The record and the app use different words for the same severities, and the gap
# is a trap for an annotator rather than a bug in either. The app's issues carry
# ``severity="hard_blocker"`` and ``report.md`` prints that phrase, so writing it
# into a record is the natural mistake -- and it silently drops the blocker from
# ``blockers_side_by_side``, which filters on "hard". Naming the right word in a
# message costs nothing; discovering it after annotating twenty papers does not.
SEVERITIES = ("hard", "major", "minor")
_APP_SEVERITY = {"hard_blocker": "hard", "hard blocker": "hard"}

# ``severity_summary``'s keys, which are a third spelling again.
_SUMMARY_KEYS = {"hard": "hard_blockers", "major": "major_issues", "minor": "minor_issues"}


def validate_record(paper_id: str, record: dict) -> list[str]:
    """Mechanical problems in one ground-truth record, as sentences naming the fix.

    Worth having before the benchmark grows rather than after. Every number this
    grader prints is a comparison against one of these records, so a record that
    is merely well-formed JSON can still make the app look wrong -- or, worse,
    look right. Nothing here second-guesses an annotator's judgement: these are
    the mistakes that produce a silently wrong comparison rather than an error.
    """
    problems: list[str] = []

    stated = record.get("paper_id")
    if stated != paper_id:
        problems.append(f"paper_id is {stated!r} but the file is named {paper_id}.json")

    for field in ("title", "citation", "github"):
        if not str(record.get(field, "")).strip():
            problems.append(f"{field} is missing or empty")

    if not isinstance(record.get("data_accessions"), list):
        problems.append("data_accessions must be a list, one prose entry per dataset")

    tier = record.get("annotation_provenance", {}).get("tier")
    if tier not in (1, 2):
        problems.append(f"annotation_provenance.tier is {tier!r}; expected 1 or 2")

    return (
        problems
        + _validate_template_leftovers(record)
        + _validate_blockers(record)
        + _validate_rubric(record)
    )


def _validate_template_leftovers(record: dict) -> list[str]:
    """Fields still carrying the template's own placeholder text.

    ``scripts/prep_benchmark.py`` writes a blank skeleton per paper, and a blank
    skeleton validated clean: every structural rule above is satisfied by
    placeholder prose, a rubric of seven zeros that correctly totals zero, and
    one template blocker that the summary correctly counts. So a paper whose
    annotation had not been started would have been graded against as though it
    had, and the comparison would have looked entirely normal -- the precise
    failure the rest of this validator exists to prevent, arriving through the
    tooling meant to make annotating faster.

    Compared against the template rather than a copied list of phrases, so the
    two cannot drift: editing the template cannot leave a stale rule behind.
    """
    if not TEMPLATE.is_file():  # pragma: no cover -- the template is in the repo
        return []
    template = json.loads(TEMPLATE.read_text())
    problems: list[str] = []

    for field in ("title", "citation", "github", "data_accessions"):
        if field in record and record[field] == template.get(field):
            problems.append(
                f"{field} is still the template's placeholder text; "
                f"fill it in from benchmark/worksheets/{record.get('paper_id', '<id>')}.md"
            )

    blockers = record.get("blockers")
    if blockers and blockers == template.get("blockers"):
        problems.append(
            "blockers is still the template's example blocker, so every severity "
            "comparison for this paper would be against placeholder prose"
        )

    rubric = record.get("scoring_rubric_v0.1", {})
    if rubric and rubric == template.get("scoring_rubric_v0.1"):
        problems.append(
            "scoring_rubric_v0.1 is still the template's seven zeros; a record scored "
            "0 is indistinguishable from a record nobody has scored yet"
        )

    provenance = record.get("annotation_provenance", {})
    if provenance.get("annotators") == template.get("annotation_provenance", {}).get("annotators"):
        problems.append("annotation_provenance.annotators is still ['Your Name']")

    return problems


def _validate_blockers(record: dict) -> list[str]:
    """Blocker severities, and whether the summary still counts what it summarises."""
    problems: list[str] = []
    tally = dict.fromkeys(SEVERITIES, 0)
    counted = True

    for index, blocker in enumerate(record.get("blockers", [])):
        severity = str(blocker.get("severity", ""))
        if severity in _APP_SEVERITY:
            problems.append(
                f"blockers[{index}].severity is {severity!r}, which is the app's word for "
                f"it; a record says {_APP_SEVERITY[severity]!r}"
            )
            counted = False
        elif severity not in SEVERITIES:
            problems.append(
                f"blockers[{index}].severity is {severity!r}; expected one of "
                f"{', '.join(SEVERITIES)}"
            )
            counted = False
        else:
            tally[severity] += 1
        if not str(blocker.get("description", "")).strip():
            problems.append(f"blockers[{index}] has no description")

    summary = record.get("severity_summary")
    if summary is None:
        problems.append("severity_summary is missing; the grader compares its counts directly")
        return problems

    for severity, key in _SUMMARY_KEYS.items():
        if (stated := summary.get(key)) is None:
            problems.append(f"severity_summary.{key} is missing")
        elif counted and stated != tally[severity]:
            # Only meaningful once every severity parsed: a rejected spelling
            # leaves the tally short, and reporting that as a count mismatch
            # would blame the summary for a problem already named above.
            problems.append(
                f"severity_summary.{key} says {stated} but the blockers list holds "
                f"{tally[severity]} of severity {severity!r}"
            )
    return problems


def _validate_rubric(record: dict) -> list[str]:
    """The hand-assigned score: all seven criteria, each in range, and adding up.

    ``total`` is what ``grade_rubric`` compares the app's band against, so a
    total that does not equal its own parts makes every criterion row in the
    output unfalsifiable.
    """
    problems: list[str] = []
    rubric = record.get("scoring_rubric_v0.1")
    if not rubric:
        return [
            "scoring_rubric_v0.1 is missing; without it there is no hand-assigned score "
            "for the app's band to be compared against"
        ]

    subtotal = 0
    complete = True
    for name, weight in WEIGHTS.items():
        score = rubric.get(name)
        if score is None:
            problems.append(f"scoring_rubric_v0.1.{name} is missing (weight {weight})")
            complete = False
        elif not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= weight:
            problems.append(
                f"scoring_rubric_v0.1.{name} is {score!r}; expected an integer 0-{weight}"
            )
            complete = False
        else:
            subtotal += score

    for name in sorted(set(rubric) - set(WEIGHTS) - {"total", "notes"}):
        problems.append(f"scoring_rubric_v0.1.{name} is not one of the rubric's criteria")

    total = rubric.get("total")
    if total is None:
        problems.append("scoring_rubric_v0.1.total is missing")
    elif complete and total != subtotal:
        problems.append(
            f"scoring_rubric_v0.1.total says {total} but the seven criteria sum to {subtotal}"
        )

    readiness = record.get("readiness_score")
    if readiness is not None and total is not None and readiness != total:
        problems.append(f"readiness_score is {readiness} but scoring_rubric_v0.1.total is {total}")
    return problems


def expected_resources(record: dict) -> tuple[set[str], set[str], list[str]]:
    """(accessions, repos, skipped) declared by one ground-truth record.

    ``data_accessions`` entries are prose -- "GSE225377 (long-read ONT, HCT116)"
    -- so the identifier is pulled out rather than matched whole.
    """
    accessions: set[str] = set()
    for entry in record.get("data_accessions", []):
        accessions.update(re.findall(r"\b(?:GSE|GSM|SRR|SRX|PRJNA|SAMN|ERR)\d+\b", entry.upper()))

    repos: set[str] = set()
    skipped: list[str] = []
    # One string or a list of them. ALIGNN points at two repositories (alignn
    # and jarvis) and ASPEN at two (the package and the manuscript), and a
    # record that could hold only the first would understate what a reproducer
    # has to obtain -- and silently, since recall would still read 100%.
    declared = record.get("github", "")
    for github in declared if isinstance(declared, list) else [declared]:
        github = str(github)
        if github and not _UNRESOLVED.search(github):
            repos.add(normalize_repo(github))
        elif github:
            skipped.append("github (ground truth is an unresolved placeholder)")

    return accessions, repos, skipped


def expected_gaps(record: dict) -> list[str]:
    """Resources a ground-truth record says could not be recovered.

    Read out of the record's own prose -- the parameters it lists as required
    but unavailable, plus every blocker description -- rather than from a
    separate hand-kept list, so the two cannot drift apart.
    """
    parameters = record.get("resource_requirements", {}).get("parameters", {})
    prose = " ".join(
        [
            str(parameters.get("required", "")),
            str(parameters.get("notes", "")),
            *(str(blocker.get("description", "")) for blocker in record.get("blockers", [])),
        ]
    )
    return find_names(prose)


def grade_checklist(record: dict, report: dict) -> list[tuple[str, str, str]]:
    """Whether the checklist flagged each resource the lab could not recover."""
    software = {item["name"]: item for item in report.get("checklist", {}).get("software", [])}
    rows: list[tuple[str, str, str]] = []
    for name in expected_gaps(record):
        item = software.get(name)
        if item is None or not item.get("declared"):
            # The second gap class, and the one the text cannot show. MATES
            # needs a gene annotation and the string "GENCODE" appears nowhere
            # in it, so no reading of the paper recovers this.
            rows.append((name, "not-in-paper", "required, but the paper never names it"))
        elif item["specificity"] == "pinned":
            rows.append((name, "DISAGREES", f"checklist reports it pinned to v{item['version']}"))
        else:
            detail = item["specificity"].replace("_", " ")
            if item.get("citations"):
                detail += f" {item['citations']}"
            rows.append((name, "flagged", f"{detail}, {item['mentions']} mention(s)"))
    return rows


def grade_rubric(record: dict, report: dict) -> list[tuple[str, str, str]]:
    """App score band against the hand-assigned sub-score, per criterion.

    Reported as a delta rather than a pass/fail. The two numbers measure
    different things: the record was scored by people who attempted the
    reproduction, and the app has only read the paper, so a divergence is
    information about which evidence each one had rather than an error.
    """
    human = record.get("scoring_rubric_v0.1", {})
    rows: list[tuple[str, str, str]] = []
    for criterion in report.get("assessment", {}).get("criteria", []):
        name = criterion["name"]
        if name not in human:
            continue
        theirs = human[name]
        if not criterion["assessed"]:
            rows.append((name, "not assessed", f"human {theirs}/{criterion['weight']}"))
            continue
        floor, ceiling = criterion["floor"], criterion["ceiling"]
        band = f"app {floor}-{ceiling}, human {theirs}"
        if floor <= theirs <= ceiling:
            rows.append((name, "agrees", band))
        else:
            delta = floor - theirs if theirs < floor else theirs - ceiling
            rows.append((name, f"off by {delta}", band))
    return rows


def grade_severity(record: dict, report: dict) -> list[tuple[str, int, int]]:
    """App issue counts against the record's own severity summary."""
    human = record.get("severity_summary", {})
    app = report.get("assessment", {}).get("severity", {})
    return [
        ("hard blockers", app.get("hard_blocker", 0), human.get("hard_blockers", 0)),
        ("major issues", app.get("major", 0), human.get("major_issues", 0)),
        ("minor issues", app.get("minor", 0), human.get("minor_issues", 0)),
    ]


def blockers_side_by_side(record: dict, report: dict) -> list[tuple[str, str, str]]:
    """The app's hard blockers beside the ones the annotators recorded.

    Printed rather than scored. Deciding whether "annotation.gtf is present only
    at demo scale" is the same blocker as "the exact TE annotation GTF used for
    the published figure was never released" is a judgement about meaning, and
    automating it here would turn a readable comparison into a number whose
    basis no one can check. The counts are compared in ``grade_severity``; this
    is for reading the two accounts next to each other.
    """
    app = [
        (issue["resource"], issue["evidence"])
        for issue in report.get("assessment", {}).get("issues", [])
        if issue["severity"] == "hard_blocker"
    ]
    human = [
        b.get("description", "") for b in record.get("blockers", []) if b.get("severity") == "hard"
    ]
    rows: list[tuple[str, str, str]] = []
    for index in range(max(len(app), len(human))):
        resource, evidence = app[index] if index < len(app) else ("-", "")
        rows.append((resource, evidence, human[index] if index < len(human) else "-"))
    return rows


def grade(paper_id: str, out_dir: Path) -> dict | None:
    record_path = BENCHMARK / f"{paper_id}.json"
    report_path = out_dir / paper_id / "links.json"
    if not report_path.is_file():
        return None

    record = json.loads(record_path.read_text())
    report = json.loads(report_path.read_text())

    want_accessions, want_repos, skipped = expected_resources(record)

    got_accessions = {
        f["value"].upper()
        for f in report["findings"]
        if f["kind"].startswith(("geo_", "sra_", "bioproject", "biosample", "ena_"))
    }
    got_repos = {
        normalize_repo(f["value"]) for f in report["findings"] if f["kind"] in {"github", "gitlab"}
    }

    want = want_accessions | want_repos
    got = got_accessions | got_repos

    # The app's own role for each value, so "extra" can be read rather than just
    # counted. A ground-truth record lists the resources its annotators judged
    # central; a paper legitimately points at many more, and until these were
    # grouped by role there was no way to tell a third-party dataset the work
    # depends on from a tool cited in the reference list.
    roles: dict[str, tuple[str, str, str]] = {}
    for finding in report["findings"]:
        key = (
            normalize_repo(finding["value"])
            if finding["kind"] in {"github", "gitlab"}
            else finding["value"].upper()
        )
        roles[key] = (
            finding.get("role", "unclassified"),
            finding.get("role_confidence", "inferred"),
            finding.get("role_reason", ""),
        )

    extra_by_role: dict[str, list[tuple[str, str, str]]] = {}
    for value in sorted(got - want):
        role, confidence, reason = roles.get(value, ("unknown", "inferred", ""))
        extra_by_role.setdefault(role, []).append((value, confidence, reason))

    return {
        "paper_id": paper_id,
        "found": sorted(want & got),
        "missed": sorted(want - got),
        "extra": sorted(got - want),
        "extra_by_role": extra_by_role,
        "found_roles": {value: roles.get(value, ("unknown",))[0] for value in sorted(want & got)},
        "skipped": skipped,
        "recall": len(want & got) / len(want) if want else None,
        "warnings": report.get("warnings", []),
        "sections": sorted({entry["label"] for entry in report.get("sections", [])}),
        "checklist": grade_checklist(record, report),
        "rubric": grade_rubric(record, report),
        "severity": grade_severity(record, report),
        "checklist_summary": report.get("checklist", {}).get("summary", {}),
        "repository": report.get("repository", {}),
        "blockers": blockers_side_by_side(record, report),
        "human_total": record.get("scoring_rubric_v0.1", {}).get("total"),
    }


def report_assessment(result: dict) -> str:
    agreeing = len([row for row in result["rubric"] if row[1] == "agrees"])
    scored = len([row for row in result["rubric"] if row[1] != "not assessed"])
    return f"{agreeing}/{scored} criteria agree"


def read_records() -> tuple[list[str], dict[str, list[str]]]:
    """Every ground-truth record's id, and the problems found in each.

    Validation runs on every invocation rather than behind the flag, because a
    record only has to be wrong once to make a grading run that looks entirely
    normal. The flag exists for the other direction: checking a freshly written
    record before there is any app output to grade it against.
    """
    papers: list[str] = []
    problems: dict[str, list[str]] = {}
    for path in sorted(BENCHMARK.glob("*.json")):
        papers.append(path.stem)
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            problems[path.stem] = [f"not valid JSON: {error}"]
            continue
        if found := validate_record(path.stem, record):
            problems[path.stem] = found
    return papers, problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade ReproLens output against ground truth.")
    parser.add_argument("--out", type=Path, default=Path("output"))
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="check the ground-truth records for mechanical errors and stop, without grading",
    )
    args = parser.parse_args()

    papers, problems = read_records()
    if problems:
        print("ground-truth records with problems:")
        for paper_id, found in sorted(problems.items()):
            print(f"  {paper_id}.json")
            for problem in found:
                print(f"      ! {problem}")
        print()
    elif args.validate_only:
        print(f"{len(papers)} ground-truth record(s) validate clean.")

    if args.validate_only:
        return 1 if problems else 0

    # A record that failed validation is not graded. Every number below is a
    # comparison against ground truth, so comparing against a record known to
    # be wrong produces a confident, normal-looking, meaningless result -- and
    # a blank skeleton from scripts/prep_benchmark.py is exactly that record.
    gradable = [pid for pid in papers if pid not in problems]
    if problems:
        print(
            f"not graded: {', '.join(sorted(problems))} -- "
            f"the problems above have to be fixed first.\n"
        )
    results = [r for pid in gradable if (r := grade(pid, args.out))]

    if not results:
        print("No app output to grade. Run audit.py first.")
        return 1

    for result in results:
        print(f"\n{'=' * 68}\n{result['paper_id']}   recall {result['recall']:.0%}\n{'=' * 68}")
        for warning in result["warnings"]:
            print(f"  ! {warning}")
        print(f"  found   ({len(result['found'])}):")
        for value in result["found"]:
            print(f"      {value:<44} -> {result['found_roles'].get(value, '?')}")
        print(f"  MISSED  ({len(result['missed'])}): {', '.join(result['missed']) or '-'}")
        for note in result["skipped"]:
            print(f"  skipped: {note}")

        for required in ("data_availability", "code_availability"):
            if required not in result["sections"]:
                print(f"  ! no {required.replace('_', ' ')} statement detected")

        repo = result["repository"]
        if repo.get("fetched"):
            traceability = repo["figure_traceability"]
            print("\n  repository channel:")
            for entry in repo["repositories"]:
                print(f"      read {entry['repository']}@{entry['commit'][:10]}")
            for entry in repo["not_fetched"]:
                print(f"      ! {entry['repository']} NOT read: {entry['reason']}")
            note = "" if traceability["assessable"] else "  (undetermined: nothing named for one)"
            print(
                f"      figures with generating code: "
                f"{len(traceability['covered'])} of {len(traceability['paper_figures'])}{note}"
            )
            for step in repo["undocumented_steps"]:
                print(f"      runs but unnamed in the paper: {step['tool']}")
        elif repo:
            print("\n  repository channel: nothing read")

        if result["blockers"]:
            print("\n  hard blockers -- app beside the annotators':")
            for resource, evidence, human in result["blockers"]:
                print(f"      app   {resource}: {evidence[:96]}")
                print(f"      human {human[:120]}")

        if result["rubric"]:
            verdict = report_assessment(result)
            print(f"\n  rubric {verdict} -- app band vs the hand-assigned score:")
            for name, status, detail in result["rubric"]:
                print(f"      {status:<13} {name:<28} {detail}")
            print("  severity:")
            for label, app_count, human_count in result["severity"]:
                print(f"      {label:<16} app {app_count:>3}   human {human_count:>3}")

        if result["checklist"]:
            summary = result["checklist_summary"]
            print(
                f"\n  checklist: {summary.get('pinned', 0)} of {summary.get('declared', 0)}"
                f" declared tools pinned to a version;"
                f" {summary.get('flags_with_a_value', 0)} of {summary.get('flags_named', 0)}"
                f" named flags carry a value"
            )
            for name, status, detail in result["checklist"]:
                print(f"      {status:<13} {name:<18} {detail}")

        print(f"\n  extra ({len(result['extra'])}) -- by the role the app assigned:")
        for role, rows in sorted(result["extra_by_role"].items()):
            print(f"      {role} ({len(rows)})")
            for value, confidence, reason in rows:
                print(f"        {value:<42} {confidence:<9} {reason}")

    graded = [r for r in results if r["recall"] is not None]
    if graded:
        overall = sum(r["recall"] for r in graded) / len(graded)
        print(f"\n{'=' * 68}\nmean recall across {len(graded)} paper(s): {overall:.0%}")

    missing = [p for p in papers if not (args.out / p / "links.json").is_file()]
    if missing:
        print(f"not yet audited: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
