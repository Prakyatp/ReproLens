"""Ask the registry whether a named dataset is actually there.

Every criterion before this one scores what a paper *says*. This one is the
first that leaves the document: a data-availability statement naming
``GSE212945`` earns its points for being specific, and until now nothing checked
that the accession resolves to anything. A paper can name a dataset that was
never deposited, or deposited and withdrawn, or mistyped, and the audit would
report full marks for data availability either way.

Three design points, each the result of probing the registry rather than
assuming:

**Counting search hits is not an existence test.** The obvious call --
``esearch`` with the accession in the ``[ACCN]`` field, then read ``count`` --
does not mean what it looks like. ``GSE84465[ACCN]`` matches 3591 records and
``GSE1[ACCN]`` matches 40, because the field search falls back to something
broader. For GEO the sound test is to construct the record's UID, ask
``esummary`` for exactly that record, and compare the accession it returns:
one call, no fuzziness, and it also hands back the title.

**The UID is derivable.** A GEO UID is the record-type digit followed by the
accession's digits padded to eight: ``GSE212945`` is ``200212945``,
``GSM4800803`` is ``304800803``, ``GPL24247`` is ``100024247``. Verified against
five real accessions and three absent ones.

**Existence is not identity.** This is the limit worth stating plainly, because
it is easy to oversell. ``GSE11495`` resolves -- it is a real series about
granulosa and theca cell transcription in chicken ovary, and it appears in a
transposable-element paper's findings only because it is a truncation of
``GSE114952``. The registry confirms the accession is real; it cannot confirm it
is the dataset the paper meant. So this module reports the title alongside the
status and leaves that judgement to a reader, who can see at a glance that a
chicken ovary study does not belong in this paper.

Nothing here downloads data. These are metadata lookups, and a dataset's size is
exactly why: confirming that something is obtainable must not require obtaining
it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

PUBLIC = "public"
NOT_FOUND = "not_found"
RESTRICTED = "restricted"
UNCHECKED = "unchecked"

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

# NCBI asks for a tool name on every call and allows three requests a second
# without an API key. The tool name is sent; an email address is not. NCBI
# accepts one and it would make a rate-limit complaint easier to trace, but it
# is the user's address and this is an unrelated third party, so it is opt-in
# through NCBI_EMAIL rather than compiled in.
TOOL = "reprolens"
MIN_INTERVAL = 0.35
TIMEOUT = 10.0

# How many lookups one audit will make. A paper's reference list can name
# dozens of accessions that belong to other people's papers, and resolving all
# of them would audit the field rather than the paper. The cache makes a repeat
# run free, so this bounds a first run only.
DEFAULT_BUDGET = 60

# The record-type digit that opens a GEO UID.
_GEO_PREFIX = {"geo_series": "2", "geo_sample": "3", "geo_platform": "1"}

# Kinds resolvable by a field search, with the Entrez database that holds them.
_SEARCHABLE = {
    "sra_run": "sra",
    "sra_experiment": "sra",
    "sra_study": "sra",
    "bioproject": "bioproject",
    "biosample": "biosample",
    "ena_run": "sra",
    "ena_study": "sra",
}

# Controlled-access archives. An accession here resolving is not the same as the
# data being obtainable: dbGaP requires an approved data-access request, which
# can take months and can be refused. Reporting that as "public" would be the
# single most misleading thing this module could say.
_CONTROLLED = {"dbgap"}

RESOLVABLE = frozenset(_GEO_PREFIX) | frozenset(_SEARCHABLE) | _CONTROLLED


@dataclass(frozen=True, slots=True)
class Resolution:
    """What a registry said about one accession."""

    accession: str
    kind: str
    status: str
    title: str = ""
    detail: str = ""

    @property
    def confirmed(self) -> bool:
        return self.status in (PUBLIC, RESTRICTED)

    @property
    def answered(self) -> bool:
        """Whether a registry actually replied, either way.

        ``unchecked`` is not a verdict about the paper, and the distinction
        matters more than the result: a lookup that did not happen must never
        read as a dataset that is not there.
        """
        return self.status != UNCHECKED

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Resolutions:
    entries: list[Resolution] = field(default_factory=list)
    attempted: bool = True
    notes: list[str] = field(default_factory=list)

    def by_status(self, status: str) -> list[Resolution]:
        return [e for e in self.entries if e.status == status]

    @property
    def missing(self) -> list[Resolution]:
        return self.by_status(NOT_FOUND)

    def to_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "summary": {
                "checked": len([e for e in self.entries if e.answered]),
                "public": len(self.by_status(PUBLIC)),
                "restricted": len(self.by_status(RESTRICTED)),
                "not_found": len(self.by_status(NOT_FOUND)),
                "unchecked": len(self.by_status(UNCHECKED)),
            },
            "notes": self.notes,
            "entries": [e.as_dict() for e in self.entries],
        }


class Cache:
    """A flat JSON file of past answers, keyed by accession.

    Deliberately plain and readable. The registry's answer about a published
    accession changes rarely, and when it does the file can be inspected or
    deleted by hand -- which matters for a result a reader may want to
    challenge.
    """

    def __init__(self, path: Path = Path(".cache/accessions.json")):
        self.path = path
        self._data: dict[str, dict] = {}
        if path.is_file():
            try:
                self._data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def get(self, accession: str) -> Resolution | None:
        hit = self._data.get(accession)
        # An unchecked result is a failure to ask, not an answer, so it is never
        # cached as one: the next run should try again.
        if hit is None or hit.get("status") == UNCHECKED:
            return None
        return Resolution(**hit)

    def put(self, resolution: Resolution) -> None:
        if resolution.status == UNCHECKED:
            return
        self._data[resolution.accession] = resolution.as_dict()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True) + "\n")
        except OSError:
            pass


def resolve_all(
    accessions: list[tuple[str, str]],
    *,
    allow_network: bool = True,
    cache: Cache | None = None,
    budget: int = DEFAULT_BUDGET,
) -> Resolutions:
    """Resolve ``(kind, accession)`` pairs, cheapest path first.

    With ``allow_network`` false nothing is asked and every entry comes back
    ``unchecked`` with ``attempted`` false. That pairing is deliberate and was
    learned the hard way on the repository channel: an audit told not to use the
    network once produced a hard blocker for code it had been told not to fetch.
    A switch the operator turned off is not a finding about the paper.
    """
    wanted = _unique(accessions)
    result = Resolutions(attempted=allow_network)

    if not allow_network:
        result.entries = [
            Resolution(acc, kind, UNCHECKED, detail="lookups disabled for this run")
            for kind, acc in wanted
        ]
        if wanted:
            result.notes.append(
                f"{len(wanted)} accession(s) were NOT looked up: resolution is switched off "
                f"for this run. Nothing below is evidence that a dataset does or does not "
                f"exist."
            )
        return result

    store = cache if cache is not None else Cache()
    spent = 0
    last = 0.0

    for kind, accession in wanted:
        if kind not in RESOLVABLE:
            result.entries.append(
                Resolution(accession, kind, UNCHECKED, detail=f"no registry known for {kind}")
            )
            continue
        if (hit := store.get(accession)) is not None:
            result.entries.append(hit)
            continue
        if spent >= budget:
            result.entries.append(
                Resolution(accession, kind, UNCHECKED, detail="lookup budget for this run spent")
            )
            continue

        last = _throttle(last)
        resolution = _lookup(kind, accession)
        spent += 1
        store.put(resolution)
        result.entries.append(resolution)

    store.save()

    unchecked = result.by_status(UNCHECKED)
    if unchecked:
        result.notes.append(
            f"{len(unchecked)} accession(s) could not be checked "
            f"({unchecked[0].detail}). Not evidence either way."
        )
    for missing in result.missing:
        result.notes.append(
            f"{missing.accession} is named by the paper and the registry does not have it: "
            f"{missing.detail}"
        )
    return result


def _unique(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: dict[str, tuple[str, str]] = {}
    for kind, accession in pairs:
        seen.setdefault(accession.strip().upper(), (kind, accession.strip().upper()))
    return list(seen.values())


def _throttle(last: float) -> float:
    gap = time.monotonic() - last
    if last and gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    return time.monotonic()


def _lookup(kind: str, accession: str) -> Resolution:
    if kind in _CONTROLLED:
        # Not looked up at all: dbGaP's public endpoint says only that a study
        # id exists, and "exists" is the part nobody needed to know. What a
        # reproducer needs is that the data is behind an access request, and
        # that is true of every phs accession by definition.
        return Resolution(
            accession,
            kind,
            RESTRICTED,
            detail="controlled access: obtaining this requires an approved data-access "
            "request, which can take months and can be refused",
        )
    try:
        if kind in _GEO_PREFIX:
            return _geo(kind, accession)
        return _searchable(kind, accession)
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        return Resolution(
            accession, kind, UNCHECKED, detail=f"registry unreachable ({type(error).__name__})"
        )
    except (json.JSONDecodeError, KeyError, ValueError) as error:
        return Resolution(
            accession, kind, UNCHECKED, detail=f"registry replied unusably ({type(error).__name__})"
        )


def _geo(kind: str, accession: str) -> Resolution:
    digits = accession[3:]
    if not digits.isdigit() or len(digits) > 8:
        return Resolution(
            accession, kind, UNCHECKED, detail="accession is not shaped like a GEO record"
        )
    uid = _GEO_PREFIX[kind] + digits.zfill(8)
    payload = _get("esummary.fcgi", {"db": "gds", "id": uid})
    record = payload.get("result", {}).get(uid) or {}
    if record.get("accession") == accession:
        return Resolution(accession, kind, PUBLIC, title=str(record.get("title") or "").strip())
    return Resolution(
        accession, kind, NOT_FOUND, detail=f"GEO has no record {uid} for this accession"
    )


def _searchable(kind: str, accession: str) -> Resolution:
    db = _SEARCHABLE[kind]
    payload = _get("esearch.fcgi", {"db": db, "term": f"{accession}[ACCN]"})
    count = int(payload.get("esearchresult", {}).get("count", 0))
    if count:
        return Resolution(accession, kind, PUBLIC, detail=f"{db} has this accession")
    return Resolution(accession, kind, NOT_FOUND, detail=f"{db} returned no record")


def _get(endpoint: str, params: dict[str, str]) -> dict:
    import os

    query = dict(params, retmode="json", tool=TOOL)
    if email := os.environ.get("NCBI_EMAIL"):
        query["email"] = email
    url = f"{EUTILS}{endpoint}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": f"{TOOL}/0.1"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))
