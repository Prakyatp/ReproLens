"""What a figure script reads, which is the edge the dependency graph lacked.

The graph could reach a figure's script and stop there. ``execution.inputs``
attributes an input to the file that names it, and that file is a shell script
in the pipeline, never the script that draws the figure -- so every result in
every audited paper came back ``unmapped``, and the verdict ``satisfied`` was
unreachable in practice.

Reading the figure scripts themselves closes it, and the two papers that ship
figure code do it in two different ways, both of which this module has to
handle:

    LocusMasterTE  fig1.R reads six Figshare URLs, no local paths at all
    ASPEN          Figure4.ipynb reads ./misc/NAP_genes.xlsx, a repo path

The distinction is not cosmetic. A repository path can be checked against the
clone and answered now; a remote URL cannot be answered without fetching it,
and this module does not fetch. Collapsing the two would mean either calling
unverified remote data "present" or calling deposited data "missing", and both
are worse than reporting the state accurately.

A basename that exists elsewhere in the repository is reported as ``moved``
rather than ``absent``, because the two call for different work and the
distinction turned up a real defect on the first paper it ran against: ASPEN's
Figure3.ipynb reads ``./data/misc/cells_pass_filter.xlsx``, which is not there,
while ``misc/cells_pass_filter.xlsx`` is -- 1.8 MB of it. The notebook as
published fails on a fresh clone, and the fix is one path segment.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from reprolens.repository import inventory as inventory_read

PRESENT = "present"
MOVED = "moved"
ABSENT = "absent"
REMOTE = "remote"
CONSTRUCTED = "constructed"

# The reader calls worth following, across the languages the benchmark papers
# publish figure code in. Deliberately a list of named readers rather than "any
# string that looks like a path": a column name, a plot title and a regex all
# look like paths often enough to bury the real references.
# Dots are escaped: an unescaped ``read.csv`` also matches ``read_csv``, and
# more usefully it matches ``readxcsv``, which is how a sloppy alternation
# quietly widens into "any identifier".
_READERS = (
    # R
    r"read\.(?:delim|csv2?|table|tsv|xlsx?)|readRDS|readxl::read_excel|"
    r"openxlsx::read\.xlsx|read_excel|readr::read_[a-z_]+|read_[a-z_]+|"
    r"fread|load|scan"
    # Python
    r"|pd\.read_[a-z_]+|np\.load(?:txt)?|np\.genfromtxt|open|loadmat|"
    r"nib\.load|sc\.read[a-z_]*|anndata\.read[a-z_]*"
)
# Two call shapes, because real figure code uses both and the first one alone
# found 3 of ASPEN's references out of 20. ``_EXACT`` is a quoted path that is
# the whole first argument; ``_PARTIAL`` is a quoted filename anywhere in the
# argument list, which is what ``read.xlsx(paste0(res_dir, "counts.xlsx"))``
# leaves behind once the directory has become a variable.
_EXACT = re.compile(
    r"(?:" + _READERS + r")\s*\(\s*(?P<quote>[\"'])(?P<target>[^\"'\n]{3,300})(?P=quote)"
)
_PARTIAL = re.compile(r"(?:" + _READERS + r")\s*\((?P<args>[^\n]{0,300})")
_QUOTED = re.compile(r"""(?P<quote>["'])(?P<target>[^"'\n]{3,300})(?P=quote)""")

# A reference has to look like a file or a URL. Without this, ``open("w")`` and
# ``read.csv(text = "a,b")`` arrive as data dependencies.
_LOOKS_REMOTE = re.compile(r"^(?:https?|ftp)://", re.IGNORECASE)
_LOOKS_LIKE_PATH = re.compile(r"[/\\]|\.[A-Za-z0-9]{1,6}$")


@dataclass(slots=True)
class DataRef:
    """One thing a script reads, and whether it is there."""

    target: str  # exactly as written in the script
    kind: str  # "repo_path" | "remote"
    status: str
    named_by: str  # the script's inventory label, repo:path
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class DataRefs:
    refs: list[DataRef] = field(default_factory=list)
    # False when no script was read at all, so an empty list cannot be mistaken
    # for a script that reads nothing.
    assessable: bool = True
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for ref in self.refs:
            counts[ref.status] = counts.get(ref.status, 0) + 1
        return {
            "assessable": self.assessable,
            "references": len(self.refs),
            "by_status": dict(sorted(counts.items())),
        }

    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "references": [ref.as_dict() for ref in self.refs],
            "notes": self.notes,
        }


def _source(inventory: inventory_read.Inventory, file: inventory_read.RepoFile) -> str:
    """A file's text, with a notebook flattened to its code cells.

    A notebook read as raw JSON matches nothing useful: the reader call is
    inside a ``source`` array, split across list elements at every newline.
    """
    text = inventory.read(file)
    if not file.path.endswith(".ipynb"):
        return text
    try:
        notebook = json.loads(text)
    except (ValueError, TypeError):
        return text
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
        if cell.get("cell_type") == "code"
    )


def read(
    inventory: inventory_read.Inventory,
    scripts: list[tuple[int, str]],
) -> DataRefs:
    """The data each figure script reads, resolved against the clone.

    ``scripts`` is ``FigureCoverage.scripts`` -- (figure number, inventory
    label) pairs -- so this reads only the files already identified as
    producing a published figure, rather than every script in the repository.
    """
    result = DataRefs()
    wanted = {label for _, label in scripts}
    by_label = {f.label: f for f in inventory.files if f.label in wanted}

    if not by_label:
        result.assessable = False
        result.notes.append(
            "No figure-generating script was read, so what the paper's results are "
            "made from is undetermined rather than absent."
        )
        return result

    index = inventory.basenames()
    for label, file in sorted(by_label.items()):
        for target, complete in _targets(_source(inventory, file)).items():
            result.refs.append(_classify(target, label, file.repo, index, complete))
    return result


def _targets(source: str) -> dict[str, bool]:
    """Each reader argument that looks like a file or URL -> was it complete.

    ``True`` means the quoted string was the whole first argument, so it is the
    path as the script will use it. ``False`` means it was one piece of a
    constructed path and only the filename is known, which changes what can
    honestly be concluded when the file is not found.
    """
    seen: dict[str, bool] = {}
    for match in _EXACT.finditer(source):
        target = match.group("target").strip()
        if _LOOKS_REMOTE.match(target) or _LOOKS_LIKE_PATH.search(target):
            seen[target] = True
    for match in _PARTIAL.finditer(source):
        for quoted in _QUOTED.finditer(match.group("args")):
            target = quoted.group("target").strip()
            if target in seen:
                continue
            if _LOOKS_REMOTE.match(target) or _LOOKS_LIKE_PATH.search(target):
                seen[target] = False
    return seen


def _classify(
    target: str,
    named_by: str,
    repo: str,
    index: dict[str, list[inventory_read.RepoFile]],
    complete: bool = True,
) -> DataRef:
    if _LOOKS_REMOTE.match(target):
        host = target.split("/")[2] if "//" in target else ""
        return DataRef(
            target=target,
            kind="remote",
            status=REMOTE,
            named_by=named_by,
            # Said plainly, because a remote reference is the one case where
            # this module knows what the script needs and cannot say whether
            # it is obtainable.
            detail=f"deposited at {host}; not fetched, so whether it resolves is unchecked",
        )

    normalized = target.lstrip("./").replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1].casefold()
    candidates = [f for f in index.get(basename, []) if f.repo == repo]

    for candidate in candidates:
        if candidate.path == normalized:
            return DataRef(
                target=target,
                kind="repo_path",
                status=PRESENT,
                named_by=named_by,
                detail=candidate.label,
            )
    if candidates:
        where = ", ".join(sorted(c.path for c in candidates)[:3])
        if not complete:
            # The directory came from a variable, so this is where the file is
            # and not evidence that the script looks in the wrong place.
            return DataRef(
                target=target,
                kind="repo_path",
                status=PRESENT,
                named_by=named_by,
                detail=f"{where} (the directory came from a variable)",
            )
        return DataRef(
            target=target,
            kind="repo_path",
            status=MOVED,
            named_by=named_by,
            detail=f"not at this path; a file of that name is at {where}",
        )
    if not complete:
        # Not a defect. A figure notebook reading its pipeline's own output is
        # behaving correctly, and this project cannot tell that case from a
        # genuinely missing input without running the pipeline -- so it says
        # which it cannot tell rather than picking one.
        return DataRef(
            target=target,
            kind="repo_path",
            status=CONSTRUCTED,
            named_by=named_by,
            detail=(
                "the directory came from a variable and no file of this name is in the "
                "repository, so it is produced by an earlier step or supplied by the user"
            ),
        )
    return DataRef(
        target=target,
        kind="repo_path",
        status=ABSENT,
        named_by=named_by,
        detail="no file of that name anywhere in the repository",
    )
