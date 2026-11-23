"""Gather the raw material a Tier-2 annotation needs, and nothing else.

The benchmark is two papers against a target of twenty, and that is the binding
constraint on every agreement number this project reports. The two Tier-1
records took five months each, so the remaining eighteen have to be Tier-2
cold reads. ``benchmark/README.md`` puts a Tier-2 record at about an hour, and
most of that hour is not judgement -- it is finding the availability statement
in a thirty-page PDF, listing what is in the repository, and locating the
environment manifest. This script does that part.

What it will not do is form an opinion. The annotator's record is the ground
truth the app is graded against, so anything this script puts in front of them
that came from the app makes that grade circular: the benchmark would agree
with the tool by construction, and the agreement number would be measuring
nothing. So the worksheet carries the paper's own words and the repository's
own files, quoted verbatim with provenance, and never a score, a severity, a
resource verdict, or an extracted identifier.

That rule is enforced rather than promised. This module may not import the
extraction layer or call anything that scores, and
``tests/test_prep_benchmark.py`` asserts it by reading this file, the same way
``tests/test_no_benchmark_leak.py`` asserts the app never reads the benchmark.

The one exception is ``WEIGHTS``, which is imported deliberately: it is the
criterion names and their point values, not a judgement about any paper, and
``benchmark/README.md`` requires the worksheet's weights to come from the app
so that the two cannot drift apart. ``assess`` and the checklist builder are
the things that must stay out, and they do.

    uv run python scripts/prep_benchmark.py data/papers/alignn.pdf \
        --repo data/repos/github__usnistgov__alignn
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reprolens.documents.jats_xml import JatsXmlBackend
from reprolens.documents.pdf_text import PdfTextBackend
from reprolens.documents.sections import resolve
from reprolens.scoring.rubric import WEIGHTS

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "benchmark" / "tier2-template.json"
RECORDS = ROOT / "benchmark" / "papers"
WORKSHEETS = ROOT / "benchmark" / "worksheets"

# The sections whose text a reproducer has to read in full, quoted verbatim so
# the annotator reads one paragraph instead of thirty pages. Quoting the
# paper's own words is raw material; listing the identifiers the app found in
# them would be the app's answer to a question the record is supposed to settle.
VERBATIM = (
    "data_availability",
    "code_availability",
    "associated_data",
    "supplementary",
)

# How much of each is quoted. The availability statement is a paragraph and is
# quoted whole; the supplementary section is ASPEN's entire supporting-
# information list, 6,000 characters of S-figure captions that would bury the
# four lines above it. Either way the cut is announced, because a quote trimmed
# silently is a quote the annotator will read as complete.
LIMITS = {"supplementary": 1800}

# Files whose entire content is the answer to "what environment does this
# need", small enough to quote and useless in summary.
MANIFESTS = (
    "requirements.txt",
    "environment.yml",
    "environment.yaml",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "poetry.lock",
    "DESCRIPTION",
    "renv.lock",
    "Dockerfile",
    "docker-compose.yml",
    "conda.yaml",
)

READMES = ("README.md", "README.rst", "README.txt", "README", "readme.md")

# Directories that are never part of what a reproducer has to understand.
SKIP_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "node_modules",
    ".ipynb_checkpoints",
    "egg-info",
}

_LIMIT = 6000


def read_pages(path: Path):
    backend = JatsXmlBackend() if path.suffix.lower() == ".xml" else PdfTextBackend()
    return backend.read(path)


def section_map(pages) -> list[tuple[int, str, str]]:
    """Every heading the document declares, with the page it sits on."""
    return [
        (page.page, mark.label, mark.heading.strip())
        for page in pages
        for mark in page.sections
        if mark.heading.strip()
    ]


def verbatim_sections(pages) -> list[tuple[str, int, str]]:
    """The availability statements, quoted whole.

    A section is a character offset rather than a page, because one page can
    carry three of them -- so the text runs from its own heading to whichever
    heading comes next, which may be on a later page.
    """
    marks = [
        (page.page, mark.offset, mark)
        for page in pages
        for mark in page.sections
        if mark.label in VERBATIM
    ]
    by_page = {page.page: page for page in pages}
    starts = sorted((page.page, mark.offset) for page in pages for mark in page.sections)
    out = []
    for page_no, offset, mark in sorted(marks):
        following = [s for s in starts if s > (page_no, offset)]
        end = len(by_page[page_no].text)
        if following and following[0][0] == page_no:
            end = following[0][1]
        body = " ".join(by_page[page_no].text[offset:end].split())
        if not body:
            continue
        limit = LIMITS.get(mark.label, _LIMIT)
        if len(body) > limit:
            body = body[:limit] + f" ... [{len(body) - limit:,} more characters -- open the paper]"
        out.append((mark.label, page_no, body))
    return out


_OPENS_A_CAPTION = ("fig.", "figure ", "table ", "supplementary fig", "supplementary table")


def captions(pages) -> list[tuple[int, str]]:
    """Figure and table captions, which is where a result's inputs get named.

    Continuation lines are followed, because a caption is typeset over several
    of them and the first line alone is where the naming has not happened yet:
    ALIGNN's Figure 1 cut at the line break reads "undirected crystal graph
    representation and corresponding line", losing every term the
    ``result_traceability`` question is about.
    """
    out = []
    for page in pages:
        lines = [line.strip() for line in page.text.splitlines()]
        for index, line in enumerate(lines):
            if not line.lower().startswith(_OPENS_A_CAPTION) or len(line) <= 25:
                continue
            body = [line]
            for following in lines[index + 1 : index + 6]:
                if not following or following.lower().startswith(_OPENS_A_CAPTION):
                    break
                body.append(following)
                if following.endswith("."):
                    break
            out.append((page.page, " ".join(" ".join(body).split())[:600]))
    return out


def tree(root: Path, *, depth: int = 3) -> list[str]:
    """The repository's own layout, walked directly.

    Deliberately not the app's ``Inventory``: that classifies each file by kind
    and flags demo-scale data, which are judgements about the repository. This
    is a listing.
    """
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        parts = relative.parts
        if any(p in SKIP_DIRS or p.endswith(".egg-info") for p in parts):
            continue
        if len(parts) > depth:
            continue
        if path.is_dir():
            lines.append(f"{'  ' * (len(parts) - 1)}{parts[-1]}/")
        else:
            size = path.stat().st_size
            lines.append(f"{'  ' * (len(parts) - 1)}{parts[-1]}  ({size:,} B)")
    return lines


def find_files(root: Path, names: tuple[str, ...]) -> list[Path]:
    found = []
    for path in sorted(root.rglob("*")):
        if any(p in SKIP_DIRS for p in path.relative_to(root).parts):
            continue
        if path.is_file() and path.name in names:
            found.append(path)
    return found


def quote_file(path: Path, root: Path, *, limit: int = _LIMIT) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # pragma: no cover -- a clone that cannot be read
        return f"(could not be read: {exc})"
    clipped = text[:limit]
    suffix = "" if len(text) <= limit else f"\n... [{len(text) - limit:,} more characters]"
    return clipped + suffix


def skeleton(paper_id: str, repos: list[str]) -> dict:
    """The template with only the mechanically certain fields filled in.

    The title is deliberately NOT one of them. A journal typesets it over two
    lines, so taking the first long line of page 1 gives "Atomistic Line Graph
    Neural Network for Improved Materials Property" -- which is wrong, and
    worse, looks filled in. The worksheet quotes the front matter verbatim
    instead, so the real title is a copy away and a blank stays visibly blank.
    """
    record = json.loads(TEMPLATE.read_text())
    record["paper_id"] = paper_id
    if repos:
        record["github"] = repos[0] if len(repos) == 1 else repos
    record["annotation_provenance"]["annotation_date"] = date.today().isoformat()
    return record


def worksheet(paper_id: str, source: Path, pages, repo_paths: list[Path]) -> str:
    out: list[str] = []
    w = out.append

    w(f"# Tier-2 annotation worksheet — `{paper_id}`")
    w("")
    w(f"Source: `{source}` · {len(pages)} segment(s) · generated {date.today().isoformat()}")
    w("")
    w("> **This worksheet contains no findings.** Everything below is the paper's own")
    w("> text or the repository's own files, quoted verbatim with provenance. It")
    w("> deliberately carries no score, no severity, no resource verdict and no")
    w("> extracted identifier, because this record is the ground truth ReproLens is")
    w("> graded against: if the app's answers reached the annotator, the agreement")
    w("> number would be measuring the app against itself. Read the quotes and")
    w("> decide. Where the quotes are not enough, open the paper.")
    w("")
    w("Fill in `benchmark/papers/" + paper_id + ".json`, then:")
    w("")
    w("```bash")
    w("uv run python check.py --validate-only")
    w("```")
    w("")

    w("## The seven questions")
    w("")
    w("Score what the paper **documents**, before anyone tries to run it. A cold read")
    w("cannot honestly fill `verified_reproduction` — leave it out rather than guess.")
    w("")
    w("| criterion | weight | your score | why |")
    w("| --- | --- | --- | --- |")
    for name, weight in WEIGHTS.items():
        w(f"| {name} | {weight} | | |")
    w("")
    w("Severity vocabulary for `blockers`: `hard` (reproduction impossible without")
    w("it), `major` (must be guessed), `minor` (costs time). Not `hard_blocker` —")
    w("that is the app's word, and a record using it vanishes from the comparison.")
    w("")

    w("## Front matter, verbatim")
    w("")
    w("`title` and `citation` are copied from here. They are not pre-filled: a")
    w("journal sets a title over two lines, so taking the first one gives a")
    w("plausible-looking wrong answer, and a blank field is honest where a")
    w("truncated one is not.")
    w("")
    if pages:
        for line in pages[0].text.splitlines()[:18]:
            stripped = " ".join(line.split())
            if stripped:
                w(f"    {stripped[:200]}")
    w("")

    w("## Where the paper's own sections are")
    w("")
    headings = section_map(pages)
    if headings:
        w("| page | label | heading as printed |")
        w("| --- | --- | --- |")
        for page_no, label, heading in headings:
            w(f"| {page_no} | `{label}` | {heading[:120]} |")
    else:
        w("No headings were recognised in this document. Everything below is partial,")
        w("and the availability statements have to be found by hand.")
    w("")

    w("## Availability statements, verbatim")
    w("")
    quotes = verbatim_sections(pages)
    if quotes:
        for label, page_no, body in quotes:
            w(f"### `{label}` — page {page_no}")
            w("")
            w("> " + body.replace("\n", " "))
            w("")
    else:
        w("**None found.** That is itself worth recording: a paper with no availability")
        w("statement is a different case from one whose statement this reader missed, so")
        w("check the PDF before concluding the first.")
        w("")

    w("## Figure and table captions")
    w("")
    w("A caption is where a result's inputs get named, which is the")
    w("`result_traceability` question.")
    w("")
    found_captions = captions(pages)
    if found_captions:
        for page_no, caption in found_captions[:40]:
            w(f"- p{page_no}: {caption}")
        if len(found_captions) > 40:
            w(f"- ... and {len(found_captions) - 40} more")
    else:
        w("None recognised.")
    w("")

    if not repo_paths:
        w("## Repository")
        w("")
        w("**No repository was supplied.** Three of the seven criteria —")
        w("`method_completeness`, `execution_instructions`, `result_traceability` —")
        w("are mostly answered by the repository, so a record scored without one")
        w("should say so in `scoring_rubric_v0.1.notes`.")
        w("")
        return "\n".join(out) + "\n"

    for repo in repo_paths:
        w(f"## Repository — `{repo.name}`")
        w("")
        w("### Layout")
        w("")
        w("```")
        out.extend(tree(repo))
        w("```")
        w("")

        readmes = find_files(repo, READMES)
        w("### README")
        w("")
        if readmes:
            for path in readmes[:2]:
                w(f"**`{path.relative_to(repo)}`**")
                w("")
                w("```markdown")
                w(quote_file(path, repo))
                w("```")
                w("")
        else:
            w("**No README.** That is the `execution_instructions` question answered.")
            w("")

        manifests = find_files(repo, MANIFESTS)
        w("### Environment manifests")
        w("")
        if manifests:
            for path in manifests[:6]:
                w(f"**`{path.relative_to(repo)}`**")
                w("")
                w("```")
                w(quote_file(path, repo, limit=3000))
                w("```")
                w("")
            if len(manifests) > 6:
                w(f"... and {len(manifests) - 6} more manifest file(s).")
                w("")
        else:
            w("**None.** No `requirements.txt`, `environment.yml`, `pyproject.toml`,")
            w("`DESCRIPTION`, `renv.lock` or `Dockerfile` anywhere in the clone — which")
            w("is the `environment_specification` question answered.")
            w("")

    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gather the raw material for a Tier-2 benchmark annotation."
    )
    parser.add_argument("paper", type=Path, help="the paper (PDF or JATS XML)")
    parser.add_argument("--id", help="paper_id; defaults to the filename stem")
    parser.add_argument(
        "--repo",
        type=Path,
        action="append",
        default=[],
        help="a cached clone to describe; repeatable",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="a repository URL for the record's github field; repeatable",
    )
    parser.add_argument(
        "--force", action="store_true", help="overwrite an existing record skeleton"
    )
    args = parser.parse_args()

    if not args.paper.is_file():
        print(f"no such paper: {args.paper}", file=sys.stderr)
        return 2

    paper_id = args.id or args.paper.stem
    record_path = RECORDS / f"{paper_id}.json"
    if record_path.exists() and not args.force:
        # Refusing is the whole point: a finished annotation is months of
        # someone's judgement and this script would replace it with blanks.
        print(
            f"{record_path.relative_to(ROOT)} already exists -- refusing to overwrite "
            f"an annotation with a blank skeleton. Pass --force if you mean it.",
            file=sys.stderr,
        )
        return 1

    missing = [r for r in args.repo if not r.is_dir()]
    if missing:
        print(f"no such clone(s): {', '.join(str(m) for m in missing)}", file=sys.stderr)
        return 2

    pages = read_pages(args.paper)
    resolve(pages)  # sections are attached to pages by the backend; fail loudly if not

    WORKSHEETS.mkdir(parents=True, exist_ok=True)
    sheet = WORKSHEETS / f"{paper_id}.md"
    sheet.write_text(worksheet(paper_id, args.paper, pages, args.repo))

    record_path.write_text(json.dumps(skeleton(paper_id, args.url), indent=2) + "\n")

    print(f"wrote {sheet.relative_to(ROOT)}")
    print(f"wrote {record_path.relative_to(ROOT)}  (a blank skeleton -- fill it in)")
    print()
    print("The worksheet carries no findings by design. Read it, decide, then:")
    print("    uv run python check.py --validate-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
