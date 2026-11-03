#!/usr/bin/env python3
"""ReproLens -- the app. Paper in, resources out.

    python audit.py data/papers/mates.pdf --out output/

This command is the product's one stable surface. It gains extractors over time
(the resource checklist, blockers, the readiness score, report.md) without its
invocation changing.

It must never read anything under ``benchmark/``. The ground-truth records state
their findings in prose, so letting them reach the app's input would silently
invalidate every score measured afterward. Grading lives in ``check.py``.

Three channels run over a paper, and they are not tiers of one ladder:

* text   -- the PDF's text layer, falling back to OCR per page where there is
            none. One of the two wins per page.
* images -- a VLM over extracted figures. Independent, and runs even when the
            text layer is perfect, because pipeline diagrams and panel labels
            hold information no text extractor can reach.
* code   -- the repositories the paper points at, cloned and read. Three of the
            rubric's seven criteria are questions about code, and the paper is
            not the document that answers them.

Each channel can fail, and a failed channel is never reported as an empty one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from reprolens.discovery import links, roles
from reprolens.discovery import resolve as accession_resolve
from reprolens.documents import crosscheck as ocr_crosscheck
from reprolens.documents import figures as figure_extract
from reprolens.documents import supplements as supplement_scan
from reprolens.documents import tables as table_scan
from reprolens.documents.base import PageText, TextBackend, is_readable
from reprolens.documents.figures import figure_numbers
from reprolens.documents.jats_xml import JatsXmlBackend
from reprolens.documents.ocr import OcrBackend
from reprolens.documents.pdf_text import PdfTextBackend
from reprolens.extraction import checklist as checklist_build
from reprolens.extraction.checklist import Checklist
from reprolens.extraction.merge import Merge
from reprolens.extraction.merge import merge as merge_channels
from reprolens.graph import build as graph_build
from reprolens.reporting.markdown import render
from reprolens.repository import analysis as repo_analysis
from reprolens.repository import fetch as repo_fetch
from reprolens.scoring.rubric import assess


def pick_backend(path: Path) -> TextBackend:
    """Choose a reader from the file type. One line per supported input."""
    if path.suffix.lower() in {".xml", ".nxml"}:
        return JatsXmlBackend()
    return PdfTextBackend()


def read_text(path: Path, *, use_ocr: bool) -> tuple[list[PageText], list[str]]:
    """The text channel: text layer first, OCR only for pages it cannot serve."""
    pages = pick_backend(path).read(path)

    if not is_readable(pages):
        # Not "this paper says little" -- this reader failed. Everything below
        # runs anyway, because a partial reading is still worth reporting, but
        # the assessment refuses to score and this warning leads the report.
        total = sum(page.char_count for page in pages)
        return pages, [
            f"THE DOCUMENT WAS NOT READ: {len(pages)} segment(s) and {total} characters "
            f"came out of {path.name}. A real paper runs to tens of thousands. Nothing "
            f"below is evidence about the paper, and every rubric criterion is reported "
            f"as not assessed rather than scored."
        ]

    unreadable = [p.page for p in pages if p.needs_ocr]
    if not unreadable:
        return pages, []

    listed = ", ".join(str(n) for n in unreadable)
    if not use_ocr:
        return pages, [
            f"{len(unreadable)} of {len(pages)} pages have no usable text layer "
            f"(pages {listed}) and OCR is disabled. Findings are INCOMPLETE: "
            f"absence of a resource on these pages is not evidence of absence."
        ]

    recovered = {p.page: p for p in OcrBackend().read(path, pages=unreadable)}
    merged = [recovered.get(p.page, p) for p in pages]
    low = [f"p{n}" for n, p in recovered.items() if (p.confidence or 0) < 0.80]
    notes = [f"pages {listed} had no text layer and were read by OCR (approximate)."]
    if low:
        notes.append(f"low OCR confidence on {', '.join(low)} -- identifiers there may be wrong.")
    return merged, notes


def read_figures(path: Path, out_dir: Path, *, use_vlm: bool) -> tuple[list[dict], list[str]]:
    """The image channel. Figures are extracted regardless; the VLM is optional."""
    if path.suffix.lower() not in {".pdf"}:
        return [], ["figure extraction needs a PDF; skipped for this input."]

    found = figure_extract.extract(path, out_dir / "figures")
    records = [
        {
            "figure_id": f.figure_id,
            "label": f.label,
            "page": f.page,
            "bbox": [round(v, 1) for v in f.bbox],
            "caption": f.caption,
            "image": str(f.image_path),
            "reading": None,
        }
        for f in found
    ]
    if not use_vlm:
        return records, [
            f"{len(records)} figures extracted but not read: no VLM run. "
            f"Anything visible only in a figure is NOT represented in the findings."
        ]
    return records, []


def run_vlm(
    records: list[dict],
    found: list,
    document_text: str,
    checklist: Checklist,
    backend_name: str,
    model: str | None,
    ocr_text: str = "",
) -> tuple[list[str], Merge]:
    """Read each figure, then reconcile what it claims against the text channel."""
    from reprolens.extraction import vlm
    from reprolens.llm.cache import ResponseCache

    backend = vlm.get_backend(backend_name, model)
    cache = ResponseCache()
    by_id = {f.figure_id: f for f in found}
    unverified_total: list[str] = []
    malformed_total: list[str] = []
    readings: list[tuple[str, object]] = []

    for record in records:
        contents = vlm.read_figure(by_id[record["figure_id"]], backend, cache)
        corroborated, unverified = vlm.corroborate(contents, document_text)
        malformed = vlm.shape_errors(contents)
        record["reading"] = {
            "backend": backend.name,
            "model": backend.model,
            "prompt_version": vlm.PROMPT_VERSION,
            "contents": contents.model_dump(),
            "corroborated": corroborated,
            "vlm_only_unverified": unverified,
            "not_accession_shaped": malformed,
        }
        unverified_total += unverified
        malformed_total += malformed
        readings.append((record["figure_id"], contents))

    cache.close()
    merged = merge_channels(readings, document_text, checklist, ocr_text)

    notes: list[str] = []
    if unverified_total:
        notes.append(
            f"{len(unverified_total)} identifier(s) appear only in figures and are "
            f"NOT confirmed by the document text: {', '.join(unverified_total[:6])}"
            f"{' ...' if len(unverified_total) > 6 else ''}"
        )
    if malformed_total:
        notes.append(
            f"{len(malformed_total)} value(s) reported as accessions are not "
            f"accession-shaped and were not counted as datasets: "
            f"{', '.join(malformed_total[:4])}"
            f"{' ...' if len(malformed_total) > 4 else ''}"
        )
    for conflict in merged.conflicts:
        notes.append(
            f"CONFLICT: the paper's figure and its text disagree -- {conflict.evidence} "
            f"({conflict.figure}). Neither channel is assumed right."
        )
    if merged.discoveries:
        names = ", ".join(f"{d.name} ({d.text_mentions})" for d in merged.discoveries[:5])
        notes.append(
            f"{len(merged.discoveries)} tool name(s) read off a figure and confirmed in the "
            f"text are absent from the software vocabulary, so the checklist cannot see "
            f"them; rarest first, with text mentions: {names}"
        )
    return notes, merged


def cross_check_text(
    path: Path, pages: list[PageText], *, enabled: bool
) -> tuple[ocr_crosscheck.CrossCheck, list[str], str]:
    """Read every page a second time with OCR and compare the two accounts.

    Off by default, and the reason is measured rather than assumed: OCR costs
    about 340 times what reading the text layer costs, and on a clean
    born-digital PDF every disagreement it turns up is one of its own errors.
    It earns its keep where the text layer is suspect -- a scanned page, or an
    accepted manuscript whose font encoding mangles what it reports.
    """
    blank = ocr_crosscheck.CrossCheck(attempted=False)
    if not enabled:
        return blank, [], ""
    if path.suffix.lower() != ".pdf":
        return blank, ["the OCR cross-check needs page images, which this input lacks."], ""
    try:
        ocr_pages = OcrBackend().read(path)
    except Exception as error:  # tesseract missing, rasterization failure
        return (
            blank,
            [
                f"the OCR cross-check did not run ({type(error).__name__}: {error}). "
                f"Nothing below is evidence that the text layer is sound."
            ],
            "",
        )
    result = ocr_crosscheck.compare(pages, ocr_pages)
    return result, list(result.notes), "\n".join(page.text for page in ocr_pages)


def read_datasets(
    findings, *, use_network: bool
) -> tuple[accession_resolve.Resolutions, list[str]]:
    """Ask each archive whether the datasets the paper names are actually there.

    Only the accessions the paper presents as its own data or as data it reuses.
    A reference list can name dozens belonging to other people's papers, and
    resolving those would audit the field rather than the paper.
    """
    wanted = [
        (finding.kind, finding.value)
        for finding in findings
        if finding.kind in accession_resolve.RESOLVABLE
        and roles.classify(finding).role in ("own_data", "external_data")
    ]
    if not wanted:
        return accession_resolve.Resolutions(attempted=use_network), []
    resolutions = accession_resolve.resolve_all(wanted, allow_network=use_network)
    return resolutions, list(resolutions.notes)


def read_repositories(
    findings: list[links.Finding],
    pages: list[PageText],
    checklist: checklist_build.Checklist,
    cache: Path,
    *,
    use_repo: bool,
) -> tuple[repo_analysis.RepoAnalysis, list[str]]:
    """The code channel: the repositories this paper presents as its own.

    Which repositories to fetch is decided by the role classifier, not by the
    pattern that matched. A paper cites the repository of every tool it uses --
    LocusMasterTE's reference list alone names several -- and cloning those would
    audit the field rather than the paper.
    """
    refs = repo_fetch.resolve_refs(
        [
            (finding.kind, finding.value)
            for finding in findings
            if roles.classify(finding).role == "analysis_code"
        ]
    )
    if not refs:
        return repo_analysis.RepoAnalysis(), [
            "no repository is named as this paper's own code, so the three "
            "code-dependent criteria are not assessed. This is a finding about the "
            "paper only if a repository really is absent, which is why it is "
            "reported as unassessed rather than scored."
        ]

    results = repo_fetch.fetch_all(refs, cache, allow_network=use_repo)
    analysis = repo_analysis.analyze(
        results,
        paper_figures=figure_numbers("\n".join(p.text for p in pages)),
        paper_software={s.name for s in checklist.software if s.declared},
    )

    notes: list[str] = []
    for entry in analysis.unfetched:
        notes.append(
            f"{entry['repository']} was named by the paper and NOT read ({entry['reason']}). "
            f"Nothing below is evidence about its contents."
        )
    if analysis.unfetched and not analysis.checkouts:
        notes.append(
            "no repository was read, so method completeness, execution instructions and "
            "result traceability are not assessed and the total is out of 65, not 100."
        )
    stale = [c for c in analysis.checkouts if c["served_from_cache"]]
    if stale:
        notes.append(
            f"{len(stale)} repository(ies) were read from the local cache, at the commit "
            f"recorded in repo.json rather than the current one. Delete the cache "
            f"directory to refresh."
        )
    return analysis, notes


def audit(
    path: Path,
    out_dir: Path,
    *,
    use_ocr: bool = True,
    use_vlm: bool = True,
    use_repo: bool = True,
    use_resolve: bool = True,
    cross_check_ocr: bool = False,
    repo_cache: Path = Path("data/repos"),
    vlm_backend: str = "ollama",
    vlm_model: str | None = None,
) -> dict:
    paper_id = path.stem
    paper_out = out_dir / paper_id
    paper_out.mkdir(parents=True, exist_ok=True)

    pages, warnings = read_text(path, use_ocr=use_ocr)
    findings = links.extract(pages)
    checklist = checklist_build.build(pages)

    # The cross-check runs ahead of the image channel, not after it, because its
    # OCR text is the second witness the figure merge consults. A figure's
    # labels live in the graphic, so the text layer cannot see them, and its
    # silence was never evidence against an in-figure reading -- only evidence
    # that the wrong reader had been asked.
    crosscheck, crosscheck_warnings, ocr_text = cross_check_text(
        path, pages, enabled=cross_check_ocr
    )
    warnings += crosscheck_warnings

    # The image channel runs BEFORE scoring, because its corroborated readings
    # are evidence the rubric consults. It used to run after, which is why a
    # channel that worked contributed nothing to any score for weeks.
    figure_records, figure_warnings = read_figures(path, paper_out, use_vlm=use_vlm)
    warnings += figure_warnings

    merged: Merge | None = None
    if use_vlm and figure_records:
        found = figure_extract.extract(path, paper_out / "figures")
        try:
            vlm_warnings, merged = run_vlm(
                figure_records,
                found,
                "\n".join(p.text for p in pages),
                checklist,
                vlm_backend,
                vlm_model,
                ocr_text,
            )
            warnings += vlm_warnings
        except Exception as error:  # model unavailable, credentials, network
            warnings.append(
                f"figures extracted but NOT read via {vlm_backend} "
                f"({type(error).__name__}). Anything visible only in a figure is absent "
                f"from the findings below. Detail: {error}"
            )

    repo, repo_warnings = read_repositories(
        findings, pages, checklist, repo_cache, use_repo=use_repo
    )
    warnings += repo_warnings

    resolutions, resolve_warnings = read_datasets(findings, use_network=use_resolve)
    warnings += resolve_warnings

    supplements = supplement_scan.collect(path, pages)
    warnings += supplements.notes

    tables = table_scan.extract(path)
    warnings += tables.notes
    table_agreement = table_scan.agreement(tables, "\n".join(p.text for p in pages))
    if (share := table_agreement["share_echoed"]) is not None:
        warnings.append(
            f"{table_agreement['named_values_echoed_in_prose']} of "
            f"{table_agreement['named_values']} named values in the tables also appear in "
            f"the prose ({share:.0%}). A table's numbers are expected to be unique to it; "
            f"its names are not."
        )

    # Built from the records above rather than from another pass over the
    # repository, so the graph and the report cannot disagree about one paper.
    dependency_graph = graph_build.build(repo.to_dict(), resolutions=resolutions.to_dict())
    warnings += dependency_graph.notes

    assessment = assess(pages, findings, checklist, repo, merged, resolutions, supplements)

    report = {
        "paper_id": paper_id,
        "source": str(path),
        "sha256": _sha256(path),
        "backend": pages[0].backend if pages else "none",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_segments": len(pages),
        "warnings": warnings,
        "pages": [
            {
                "page": p.page,
                "backend": p.backend,
                "char_count": p.char_count,
                "confidence": p.confidence,
                "has_images": p.has_images,
                "needs_ocr": p.needs_ocr,
                "n_link_annotations": len(p.links),
            }
            for p in pages
        ],
        "sections": _section_outline(pages),
        "findings": [f.to_dict() | roles.classify(f).as_dict() for f in findings],
        "by_role": _role_counts(findings),
        "checklist": checklist.to_dict(),
        "repository": repo.to_dict(),
        "datasets_resolved": resolutions.to_dict(),
        "supplements": supplements.to_dict(),
        "ocr_crosscheck": crosscheck.to_dict(),
        "tables": tables.to_dict() | {"agreement_with_prose": table_agreement},
        "figure_merge": merged.to_dict() if merged is not None else {},
        "dependency_graph": dependency_graph.to_dict(),
        "assessment": assessment.to_dict(),
    }

    (paper_out / "links.json").write_text(json.dumps(report, indent=2) + "\n")
    (paper_out / "repo.json").write_text(json.dumps(repo.to_dict(), indent=2) + "\n")
    (paper_out / "figures.json").write_text(json.dumps(figure_records, indent=2) + "\n")
    (paper_out / "checklist.json").write_text(json.dumps(checklist.to_dict(), indent=2) + "\n")
    (paper_out / "assessment.json").write_text(json.dumps(assessment.to_dict(), indent=2) + "\n")
    (paper_out / "graph.json").write_text(json.dumps(dependency_graph.to_dict(), indent=2) + "\n")
    # Rendered from the report dict above and nothing else, so report.md cannot
    # assert anything links.json does not already contain.
    (paper_out / "report.md").write_text(render(report))
    return report | {"n_figures": len(figure_records)}


def _section_outline(pages: list[PageText]) -> list[dict]:
    """The document structure as the app recovered it, for provenance.

    Written out because every role below is justified by a section, so the
    section detection has to be inspectable rather than implicit.
    """
    return [
        {"page": page.page, "heading": mark.heading, "label": mark.label, "level": mark.level}
        for page in pages
        for mark in page.sections
    ]


def _role_counts(findings: list[links.Finding]) -> dict:
    counts: dict[str, dict[str, int]] = {}
    for finding in findings:
        classification = roles.classify(finding)
        bucket = counts.setdefault(classification.role, {"stated": 0, "inferred": 0})
        bucket[classification.confidence] += 1
    return dict(sorted(counts.items(), key=lambda item: -sum(item[1].values())))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a paper for reproducibility resources.")
    parser.add_argument("paper", type=Path, help="path to the paper (PDF, or JATS XML)")
    parser.add_argument("--out", type=Path, default=Path("output"), help="output directory")
    parser.add_argument("--no-ocr", action="store_true", help="skip the OCR fallback")
    parser.add_argument(
        "--cross-check-ocr",
        action="store_true",
        help="read every page with OCR as well and compare it to the text layer "
        "(roughly 340x the cost of the text layer alone)",
    )
    parser.add_argument(
        "--no-resolve",
        action="store_true",
        help="do not ask any archive whether the named datasets exist",
    )
    parser.add_argument(
        "--no-vlm", action="store_true", help="extract figures but do not read them"
    )
    parser.add_argument(
        "--no-repo",
        action="store_true",
        help="do not clone repositories; use only what is already cached",
    )
    parser.add_argument(
        "--repo-cache", type=Path, default=Path("data/repos"), help="where clones are kept"
    )
    parser.add_argument(
        "--vlm", default="ollama", choices=["ollama", "anthropic"], help="vision backend"
    )
    parser.add_argument("--vlm-model", help="override the backend's default model")
    args = parser.parse_args()

    if not args.paper.is_file():
        parser.error(f"no such file: {args.paper}")

    report = audit(
        args.paper,
        args.out,
        use_ocr=not args.no_ocr,
        use_vlm=not args.no_vlm,
        use_repo=not args.no_repo,
        use_resolve=not args.no_resolve,
        cross_check_ocr=args.cross_check_ocr,
        repo_cache=args.repo_cache,
        vlm_backend=args.vlm,
        vlm_model=args.vlm_model,
    )

    for warning in report["warnings"]:
        print(f"WARNING: {warning}\n")

    print(
        f"{report['paper_id']}: {report['n_segments']} segments ({report['backend']}), "
        f"{len(report['findings'])} resources, {report['n_figures']} figures"
    )

    # Only worth saying about a document that was actually read. On one that was
    # not, "no data availability statement found" is a claim about the paper
    # drawn from an empty reading -- the same mistake, one layer up.
    if report["assessment"]["assessed_points"]:
        sections = {entry["label"] for entry in report["sections"]}
        for required in ("data_availability", "code_availability"):
            if required not in sections:
                print(f"  ! no {required.replace('_', ' ')} statement found")

    print("\n  by role                 stated  inferred")
    for role, counts in report["by_role"].items():
        print(f"  {role:<22} {counts['stated']:>6}  {counts['inferred']:>8}")

    summary = report["checklist"]["summary"]
    print(
        f"\n  software declared       {summary['declared']:>6}"
        f"\n    pinned to a version   {summary['pinned']:>6}"
        f"\n    named only            {summary['named_only']:>6}"
        f"\n    deferred to a ref     {summary['deferred_to_citation']:>6}"
        f"\n  flags named             {summary['flags_named']:>6}"
        f"  ({summary['flags_with_a_value']} with a value)"
        f"\n  commands given          {summary['commands_given']:>6}"
    )

    repo = report["repository"]
    if repo["fetched"]:
        inventory = repo["inventory"]
        dependencies = repo["dependencies"]["summary"]
        execution = repo["execution"]["summary"]
        traceability = repo["figure_traceability"]
        absent = execution["inputs_absent"] + execution["inputs_demo_scale"]
        print(
            f"\n  repositories read        {len(repo['repositories']):>6}"
            f"  ({inventory['n_files']} files)"
            f"\n    packages declared     {dependencies['distinct_packages']:>6}"
            f"  ({dependencies['distinct_pinned']} resolve to one version)"
            f"\n    version conflicts     {dependencies['conflicts']:>6}"
            f"\n    undeclared imports    {dependencies['undeclared_imports']:>6}"
            f"\n    runnable commands     {execution['with_a_command']:>6}"
            f"  ({execution['flags_with_a_value']} flags carry a value)"
            f"\n    inputs not present    {absent:>6}"
            f"  ({execution['inputs_demo_scale']} present only at demo scale)"
            f"\n    undocumented steps    {len(repo['undocumented_steps']):>6}"
        )
        if traceability["assessable"]:
            print(
                f"    figures with code     {len(traceability['covered']):>6}"
                f" of {len(traceability['paper_figures'])}"
            )
    for entry in repo["not_fetched"]:
        print(f"  ! {entry['repository']} not read: {entry['reason']}")

    verdict = report["assessment"]
    severity = verdict["severity"]
    print(
        f"\n  readiness {verdict['score_floor']}-{verdict['score_ceiling']}"
        f" of {verdict['assessed_points']} assessable points"
        f"  (rubric {verdict['rubric_version']})"
    )
    for criterion in verdict["criteria"]:
        if criterion["assessed"]:
            print(
                f"    {criterion['name']:<28}"
                f" {criterion['floor']:>3}-{criterion['ceiling']:<3} / {criterion['weight']}"
            )
        else:
            print(f"    {criterion['name']:<28}  not assessed: {criterion['reason']}")
    print(
        f"    issues: {severity['hard_blocker']} hard,"
        f" {severity['major']} major, {severity['minor']} minor"
    )

    written = args.out / report["paper_id"]
    print(f"\nwrote {written}/  -- start with {written / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
