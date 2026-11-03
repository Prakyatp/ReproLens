"""Every file in the fetched repositories, classified and measured.

Classification is by name and extension only -- no file is opened to guess what
it is. That keeps this module cheap over a 115 MB checkout and keeps the
judgement inspectable: a reader can check the tables below against the file
listing and get the same answer.

Size is recorded for everything because size is evidence. LocusMasterTE ships
``data/annotation.gtf``, which the demo command takes as its TE annotation, at
1.4 KB and twenty records; the published analysis quantified tens of thousands
of elements. Nothing about the filename says that, and nothing about its
presence in the repository says it either -- only the measurement does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from reprolens.repository.fetch import Checkout

Kind = str  # see _EXTENSIONS and the name tables below

# Never walked. A packed git object store is not part of the published code, and
# compiled caches would double-count every module.
_SKIP_DIRS = frozenset({".git", "__pycache__", ".ipynb_checkpoints", ".mypy_cache", ".DS_Store"})

# Dependency and environment declarations, matched on the whole filename.
_MANIFESTS = frozenset(
    {
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        "pyproject.toml",
        "pipfile",
        "pipfile.lock",
        "poetry.lock",
        "environment.yml",
        "environment.yaml",
        "conda.yml",
        "conda.yaml",
        "dockerfile",
        "description",  # R package metadata
        "renv.lock",
        "install.r",
        "apt.txt",
    }
)

# Files that document how to run the thing, as opposed to doing it.
_DOC_EXTENSIONS = frozenset({".md", ".rst", ".rsd", ".txt", ".adoc"})

_EXTENSIONS: dict[str, Kind] = {
    ".py": "python",
    ".pyx": "python",
    ".pxd": "python",
    ".r": "r",
    ".rmd": "r",
    ".sh": "shell",
    ".bash": "shell",
    ".ipynb": "notebook",
    ".yml": "config",
    ".yaml": "config",
    ".toml": "config",
    ".cfg": "config",
    ".json": "config",
    # Genomic annotations and intervals -- the inputs a pipeline is pointed at.
    ".gtf": "annotation",
    ".gff": "annotation",
    ".gff3": "annotation",
    ".bed": "annotation",
    ".saf": "annotation",
    # Trained parameters, which a paper's results may depend on entirely.
    ".pt": "weights",
    ".pth": "weights",
    ".ckpt": "weights",
    ".safetensors": "weights",
    ".h5": "weights",
    ".bam": "data",
    ".sam": "data",
    ".cram": "data",
    ".fa": "data",
    ".fasta": "data",
    ".fq": "data",
    ".fastq": "data",
    ".tsv": "data",
    ".csv": "data",
    ".npz": "data",
    ".npy": "data",
    ".xlsx": "data",
    ".zip": "data",
    ".c": "compiled",
    ".h": "compiled",
    ".so": "compiled",
}

# A genomic annotation smaller than this is a demo, not a reference. The real
# files are measured in millions of records: a genome-wide RepeatMasker
# annotation of hg38 holds roughly five million, and the smallest plausible
# published TE set is still four orders of magnitude above this line. Set well
# below anything real so that crossing it is unambiguous rather than a judgement
# call about what counts as big.
DEMO_SCALE_RECORDS = 1000

# Enough to count records in an annotation without reading a multi-gigabyte one.
_MAX_COUNT_BYTES = 4 << 20


@dataclass(slots=True)
class RepoFile:
    repo: str  # owner/name, so provenance survives merging several repositories
    path: str  # relative to that repository's root
    size: int
    kind: Kind
    records: int | None = None  # annotations only: non-comment lines

    @property
    def label(self) -> str:
        return f"{self.repo}:{self.path}"

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def demo_scale(self) -> bool:
        return self.records is not None and self.records < DEMO_SCALE_RECORDS


@dataclass(slots=True)
class Inventory:
    files: list[RepoFile] = field(default_factory=list)
    roots: dict[str, Path] = field(default_factory=dict)  # repo slug -> checkout root

    def by_kind(self, *kinds: Kind) -> list[RepoFile]:
        return [f for f in self.files if f.kind in kinds]

    def named(self, *names: str) -> list[RepoFile]:
        wanted = {n.casefold() for n in names}
        return [f for f in self.files if f.name.casefold() in wanted]

    def basenames(self) -> dict[str, list[RepoFile]]:
        index: dict[str, list[RepoFile]] = {}
        for file in self.files:
            index.setdefault(file.name.casefold(), []).append(file)
        return index

    def read(self, file: RepoFile, *, limit: int = _MAX_COUNT_BYTES) -> str:
        """The file's text, or "" when it is not text at all.

        Decoding errors are replaced rather than raised: a repository is
        untrusted input and a stray byte in a README is not a reason for an
        audit to fail.
        """
        root = self.roots.get(file.repo)
        if root is None:
            return ""
        try:
            with (root / file.path).open("rb") as handle:
                return handle.read(limit).decode("utf-8", errors="replace")
        except OSError:
            return ""

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for file in self.files:
            counts[file.kind] = counts.get(file.kind, 0) + 1
        return {
            "repositories": sorted(self.roots),
            "n_files": len(self.files),
            "by_kind": dict(sorted(counts.items(), key=lambda item: -item[1])),
        }


def take(checkouts: list[Checkout]) -> Inventory:
    """One inventory across every repository the paper points at."""
    inventory = Inventory()
    for checkout in checkouts:
        slug = checkout.ref.slug
        inventory.roots[slug] = checkout.root
        for path in sorted(checkout.root.rglob("*")):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(checkout.root).as_posix()
            try:
                size = path.stat().st_size
            except OSError:
                continue
            kind = _classify(relative)
            inventory.files.append(
                RepoFile(
                    repo=slug,
                    path=relative,
                    size=size,
                    kind=kind,
                    records=_records(path) if kind == "annotation" else None,
                )
            )
    return inventory


def _classify(relative: str) -> Kind:
    name = relative.rsplit("/", 1)[-1].casefold()
    if name in _MANIFESTS or (name.startswith("requirements") and name.endswith(".txt")):
        return "manifest"
    suffix = name[name.rfind(".") :] if "." in name else ""
    # A workflow file declares an environment; a config file in the tree does
    # not. Checked before the extension table, which would call both "config".
    if relative.startswith(".github/workflows/") and suffix in (".yml", ".yaml"):
        return "manifest"
    if suffix in _DOC_EXTENSIONS and (
        name.startswith(("readme", "install", "usage", "tutorial", "changelog"))
        or relative.startswith(("doc/", "docs/", "tutorial/", "tutorials/"))
        or suffix in (".md", ".rst", ".rsd")
    ):
        return "docs"
    return _EXTENSIONS.get(suffix, "other")


def _records(path: Path) -> int | None:
    """Non-comment, non-blank lines in an annotation file."""
    try:
        with path.open("rb") as handle:
            blob = handle.read(_MAX_COUNT_BYTES)
    except OSError:
        return None
    if path.stat().st_size > _MAX_COUNT_BYTES:
        # Only ever used to recognize a file that is too small to be real, and a
        # file this large plainly is not. Reporting a count from a truncated read
        # would be a wrong number rather than a missing one.
        return None
    text = blob.decode("utf-8", errors="replace")
    return sum(1 for line in text.splitlines() if line.strip() and not line.startswith("#"))
