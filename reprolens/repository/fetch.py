"""Resolve the repositories a paper names, and get a local copy of each.

A third channel alongside text and images, and the one that answers the
questions the paper structurally cannot. Three of the rubric's seven criteria --
method completeness, execution instructions, result traceability -- are about
what the code does, and a paper is not the right document to ask.

Two rules shape this module.

**A repository that was not fetched is not a repository with nothing in it.**
Every failure returns a reason, and the caller keeps the affected criteria
unassessed rather than scoring them zero. This is the same fail-closed rule the
OCR path follows, for the same reason: in a tool whose output is "what is
missing", an unread input that reads as an empty one is the worst available bug.

**Nothing in a checkout is ever executed.** A fetched repository is untrusted
input, so it is only ever read and parsed -- Python through ``ast``, which
evaluates nothing, and everything else as text. There is no step anywhere in
this package that runs a script, imports a module, installs a dependency or
builds an extension. Actually executing a pipeline is blueprint section 23, a
later phase, and it belongs in a container rather than here.

A paper's repositories are analysed together rather than one at a time. That is
not a convenience: LocusMasterTE publishes the method in one repository and the
figure scripts in another, so judging either alone reaches the wrong verdict
twice -- the method looks untraceable and the figures look unrunnable.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# A shallow clone of a large repository is still a download. MATES ships 55 MB
# of 10x barcode whitelists, so this is generous on purpose.
CLONE_TIMEOUT = 300

_SLUG = re.compile(r"(github|gitlab)\.com/([A-Za-z0-9][\w.-]*)/([\w.-]+)", re.I)

# Path segments that mean the URL points inside a repository rather than at one.
# "github.com/owner/name/tree/main/scripts" names a directory; the repository is
# still owner/name, which the pattern above already captured.
_NOT_A_REPO_NAME = frozenset({"blob", "tree", "releases", "issues", "wiki", "raw"})


@dataclass(frozen=True, slots=True)
class RepoRef:
    """A repository named by the paper, normalized to host/owner/name."""

    host: str  # "github" | "gitlab"
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def url(self) -> str:
        return f"https://{self.host}.com/{self.slug}.git"

    @property
    def cache_name(self) -> str:
        return f"{self.host}__{self.owner}__{self.name}"


@dataclass(slots=True)
class Checkout:
    """A local copy of one repository, pinned to the commit that was read."""

    ref: RepoRef
    root: Path
    commit: str
    committed_at: str  # ISO 8601, from the commit itself
    fetched_at: str
    reused: bool  # served from the cache rather than cloned now

    def to_dict(self) -> dict:
        return {
            "repository": self.ref.slug,
            "url": self.ref.url,
            "commit": self.commit,
            "committed_at": self.committed_at,
            "fetched_at": self.fetched_at,
            "served_from_cache": self.reused,
        }


@dataclass(slots=True)
class FetchResult:
    ref: RepoRef
    checkout: Checkout | None = None
    reason: str = ""  # why not, when there is no checkout
    # Whether a fetch was tried at all. "Tried and failed" is a fact about the
    # repository; "never tried" is a fact about how this audit was run, and
    # scoring the two the same way would charge the paper for a --no-repo flag.
    attempted: bool = True


def resolve_refs(values: list[tuple[str, str]]) -> list[RepoRef]:
    """(kind, value) pairs from the findings, as deduplicated repository refs.

    Takes the kind alongside the value so the caller decides what counts as the
    paper's own code -- a repository in the reference list is a citation, and
    cloning every tool a paper cites would measure the field rather than the
    paper.
    """
    refs: list[RepoRef] = []
    seen: set[RepoRef] = set()
    for kind, value in values:
        if kind not in ("github", "gitlab"):
            continue
        match = _SLUG.search(value)
        if not match:
            continue
        host, owner, name = match.group(1).lower(), match.group(2), match.group(3)
        name = name.removesuffix(".git").rstrip(".,;)")
        if not name or name.casefold() in _NOT_A_REPO_NAME:
            continue
        ref = RepoRef(host=host, owner=owner, name=name)
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def fetch(ref: RepoRef, cache_root: Path, *, allow_network: bool = True) -> FetchResult:
    """A local copy of one repository, from the cache when there is one.

    A cached checkout is reused rather than refreshed. An audit has to be
    repeatable -- re-running it a week later should not quietly change the
    findings because the authors pushed a commit -- so the commit actually read
    is recorded on the result and a refresh is an explicit act (delete the
    cache directory).
    """
    # Absolute, because the clone runs with ``cwd`` set and git resolves a
    # relative target against it. With a relative cache directory the first
    # fresh clone landed in data/repos/data/repos/<name>, which then failed to
    # read its own commit and reported it as "unknown" -- a wrong provenance
    # record rather than a crash, and only visible on the uncached path.
    root = (cache_root / ref.cache_name).resolve()
    if (root / ".git").is_dir():
        commit, committed_at = _commit(root)
        return FetchResult(
            ref=ref,
            checkout=Checkout(
                ref=ref,
                root=root,
                commit=commit,
                committed_at=committed_at,
                fetched_at=_mtime(root / ".git"),
                reused=True,
            ),
        )

    if not allow_network:
        return FetchResult(
            ref=ref,
            reason="not in the local cache and fetching is disabled",
            attempted=False,
        )

    root.parent.mkdir(parents=True, exist_ok=True)
    completed = _git(
        [
            # Hooks live in .git/hooks and are not transferred by a clone, so
            # this is belt and braces rather than the real guarantee. The real
            # guarantee is that nothing in this package executes a checkout.
            "-c",
            "core.hooksPath=/dev/null",
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--quiet",
            ref.url,
            str(root),
        ],
        cwd=root.parent,
    )
    if completed is None:
        return FetchResult(ref=ref, reason=f"git clone timed out after {CLONE_TIMEOUT}s")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        return FetchResult(
            ref=ref,
            reason=f"git clone failed: {detail[-1] if detail else f'exit {completed.returncode}'}",
        )

    commit, committed_at = _commit(root)
    return FetchResult(
        ref=ref,
        checkout=Checkout(
            ref=ref,
            root=root,
            commit=commit,
            committed_at=committed_at,
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            reused=False,
        ),
    )


def fetch_all(
    refs: list[RepoRef], cache_root: Path, *, allow_network: bool = True
) -> list[FetchResult]:
    return [fetch(ref, cache_root, allow_network=allow_network) for ref in refs]


def _commit(root: Path) -> tuple[str, str]:
    completed = _git(["log", "-1", "--format=%H%n%cI"], cwd=root)
    if completed is None or completed.returncode != 0:
        return "unknown", "unknown"
    lines = completed.stdout.splitlines()
    return (lines[0] if lines else "unknown", lines[1] if len(lines) > 1 else "unknown")


def _git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str] | None:
    """Run one git command with credential prompting disabled.

    Without ``GIT_TERMINAL_PROMPT=0`` a private or misspelled repository makes
    git sit waiting for a username, which in a batch audit is indistinguishable
    from a hang.
    """
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT,
            # A minimal environment with the caller's PATH. Hard-coding a PATH
            # here finds git on this machine and not on one that installs it
            # somewhere else.
            env={"GIT_TERMINAL_PROMPT": "0", "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
    except subprocess.TimeoutExpired:
        return None
    except OSError:
        return None


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")
