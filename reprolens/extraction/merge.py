"""Where the image channel meets the document channel.

The two channels answer the same question from different evidence, and neither
is authoritative. Text can be verified -- a regex match either is or is not in
the document -- while a figure reading cannot, because there is no string to
match it against. So the merge does not pick a winner. It sorts every claim a
figure makes into one of three states and lets the rest of the audit treat them
differently:

* **corroborated** -- the document's own text says the same thing. Two
  independent channels agreeing is the strongest evidence this tool produces,
  and it is the only state allowed to affect the score.
* **figure_only** -- the text is silent. Reported, never scored. A value here
  may be perfectly real; it may also be the model's invention, and on these
  figures that is where the errors concentrate.
* **conflicting** -- both channels describe the same key and disagree about its
  value. This is the state worth building the merge for, because it is the one a
  reader cannot discover by reading either channel alone.

A note on what was measured rather than assumed: on the three papers in hand the
conflict state never fires, and the reason is structural rather than lucky. The
text channel's parameters are command-line flags (``--soloType CB_UMI_Simple``)
and the figures' are statistical thresholds (``FDR = 0.1``); the namespaces do
not overlap, so there is nothing for them to disagree about. The channels turn
out to be complementary rather than redundant on this evidence. The detector
stays because that is a property of three papers, not of the method -- a figure
reading "GENCODE v38" against a methods section saying v41 is exactly the
mislabelling an auditor exists to catch, and it costs nothing to be ready for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from reprolens.extraction.checklist import SOFTWARE_NAMES, Checklist
from reprolens.extraction.schema import FigureContents
from reprolens.extraction.vlm import is_accession_shaped

# Fields carrying claims about how the work was done. ``sample_labels``,
# ``axis_labels`` and ``notes`` are deliberately excluded: the first two describe
# the figure's presentation rather than the method, and ``notes`` is free prose,
# which has no key to corroborate and no value to compare. Leaving prose out is
# what keeps an invented sentence -- "MATES (Mouse Atlas of Transposable
# Elements)", read off MATES figure 2 -- from reaching anything downstream.
MERGED_FIELDS = (
    "workflow_steps",
    "tools_named",
    "versions_visible",
    "parameters_visible",
    "accessions_visible",
)

CORROBORATED = "corroborated"
FIGURE_ONLY = "figure_only"
CONFLICTING = "conflicting"
# A reading that is right about what it saw and wrong about what kind of thing it
# is. ASPEN's figures offer "Meg3" and "Spret" as accessions; both are really in
# the paper's text -- as a gene and a mouse strain -- so corroboration alone
# would confirm them as datasets the paper never deposited. The field is wrong,
# not the reading, which is why this is its own state and not an error.
MISFILED = "misfiled"
# Confirmed by OCR over the page, but absent from the PDF's own text layer.
# A separate state because the witness is different in kind. A figure's label
# lives in the graphic, so the text layer structurally cannot see it -- which
# means "the text does not confirm this" was never evidence against an in-figure
# reading, only evidence that the wrong reader was asked. Two independent models
# over the same pixels is real agreement: Tesseract and qwen2.5vl both read
# "EdgeGatedGraphConv", "SiLU" and "Sum" off ALIGNN's architecture diagrams,
# where the text layer has none of them.
#
# Reported and not scored, deliberately. It establishes that the figure contains
# the text, which is not the same as the paper having documented a method step,
# and the rule throughout is that only what the document itself asserts may move
# a number.
CORROBORATED_BY_OCR = "corroborated_by_ocr"

# "FDR = 0.1", "Log(TPM) < 3", "threshold: 0.05" -- a key and a value, however
# the figure chose to join them.
_ASSIGNMENT = re.compile(r"^(?P<key>[^=<>≥≤:]{1,60}?)\s*[=<>≥≤:]\s*(?P<value>.+)$")

# "STAR 2.7.6a", "GENCODE v38", "DESeq2 1.30.1".
_VERSIONED = re.compile(
    r"^(?P<name>[A-Za-z][\w.+-]*?)[\s_]*(?:v|ver|version)?\.?\s*(?P<version>\d[\w.-]*)$",
    re.I,
)


def _squash(value: str) -> str:
    """The comparison form used throughout: no whitespace, no case.

    Identical to the one ``vlm.corroborate`` uses, and for the same reason -- a
    model renders what it sees rather than reproducing the document's typography.
    """
    return "".join(value.split()).lower()


def _key(value: str) -> str:
    """A parameter or tool name reduced to what two channels can be compared on."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


@dataclass(frozen=True, slots=True)
class Claim:
    """One value a figure asserted, and what the document's text makes of it."""

    figure: str
    field: str
    value: str
    status: str

    def as_dict(self) -> dict:
        return {
            "figure": self.figure,
            "field": self.field,
            "value": self.value,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class Conflict:
    """The same key, asserted differently by each channel."""

    figure: str
    field: str
    key: str
    figure_value: str
    text_value: str

    @property
    def evidence(self) -> str:
        return (
            f"{self.key}: the figure reads {self.figure_value!r}, the text says {self.text_value!r}"
        )

    def as_dict(self) -> dict:
        return {
            "figure": self.figure,
            "field": self.field,
            "key": self.key,
            "figure_value": self.figure_value,
            "text_value": self.text_value,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class Discovery:
    """Software a figure named, the text confirms, and the vocabulary does not know.

    The checklist recognises software from a hand-curated list of 76 names, so it
    is blind to anything not on it however plainly the paper says it. A vision
    model has no such list, which makes this the one thing the image channel
    finds that the document channel cannot: ``Airpart``, named in ASPEN figure 3
    and six times in ASPEN's own text, is absent from the vocabulary and so
    absent from the checklist's denominator.

    Reported as a candidate rather than added automatically. The vocabulary is
    curated by hand because deciding that a capitalised word is a tool and not a
    plot type is a judgement -- the same model also offered ``Dot_plot``,
    ``Bar Chart`` and ``Peak`` as tools -- and this layer should not make it
    alone. Same principle as ``vlm.shape_errors``: surface it, do not decide it.

    Candidates are ordered by how often the text names them, **fewest first**,
    which is the one ranking the evidence supports. A specific tool is mentioned
    a handful of times: ``Airpart`` six, ``scDALI`` ten. A generic word the model
    mistook for a tool is everywhere, because it is ordinary prose -- ``Gene``
    216 times in MATES, ``ARI`` 134, and ``MATES`` itself 269 as the paper's own
    subject. Sorting by rarity puts the real finds at the top without pretending
    to a precision this cannot have: of the thirteen candidates these two papers
    produce, ``Airpart`` (6 mentions), ``Leiden`` (17) and ``UMAP`` (21) are all
    tools the vocabulary was genuinely missing and all three sort into the top
    four, while the generic words sink. Call it a few minutes of a curator's
    reading rather than an automation.
    """

    figure: str
    name: str
    text_mentions: int

    def as_dict(self) -> dict:
        return {"figure": self.figure, "name": self.name, "text_mentions": self.text_mentions}


@dataclass(slots=True)
class Merge:
    """The image channel, reconciled against the document channel."""

    claims: list[Claim] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    discoveries: list[Discovery] = field(default_factory=list)
    read: int = 0

    def by_status(self, status: str) -> list[Claim]:
        return [c for c in self.claims if c.status == status]

    def corroborated_values(self, field_name: str) -> list[str]:
        """Values of one field that both channels assert, deduplicated in order."""
        seen = {
            c.value: None for c in self.claims if c.field == field_name and c.status == CORROBORATED
        }
        return list(seen)

    @property
    def agreement(self) -> float | None:
        """Share of a figure's checkable claims the text confirms.

        ``None`` when nothing was checkable, which is not zero agreement -- it is
        no measurement, and the distinction is the same one the rubric draws
        between a floor of zero and an unassessed criterion.
        """
        checkable = [c for c in self.claims if c.status != MISFILED]
        if not checkable:
            return None
        confirmed = [c for c in checkable if c.status in (CORROBORATED, CORROBORATED_BY_OCR)]
        return len(confirmed) / len(checkable)

    def to_dict(self) -> dict:
        return {
            "figures_read": self.read,
            "summary": {
                "corroborated": len(self.by_status(CORROBORATED)),
                "corroborated_by_ocr": len(self.by_status(CORROBORATED_BY_OCR)),
                "figure_only": len(self.by_status(FIGURE_ONLY)),
                "conflicting": len(self.conflicts),
                "misfiled": len(self.by_status(MISFILED)),
                "agreement": self.agreement,
            },
            "claims": [c.as_dict() for c in self.claims],
            "conflicts": [c.as_dict() for c in self.conflicts],
            "vocabulary_candidates": [d.as_dict() for d in self.discoveries],
        }


def merge(
    readings: list[tuple[str, FigureContents]],
    document_text: str,
    checklist: Checklist,
    ocr_text: str = "",
) -> Merge:
    """Reconcile every figure reading against the document's text and checklist.

    ``ocr_text`` is the optional second witness: the same pages read by OCR
    rather than from the text layer. It is consulted only for values the text
    layer does not have, and agreement there is recorded as its own state so the
    provenance of every claim stays legible.
    """
    haystack = _squash(document_text)
    ocr_haystack = _squash(ocr_text)
    known = {_key(name) for name in SOFTWARE_NAMES}
    text_parameters = {_key(p.flag): p.value for p in checklist.parameters if p.value is not None}
    text_versions = {_key(s.name): s.version for s in checklist.software if s.version is not None}

    result = Merge(read=len(readings))
    candidates: dict[str, Discovery] = {}
    for figure_id, contents in readings:
        for field_name in MERGED_FIELDS:
            for value in getattr(contents, field_name):
                value = value.strip()
                if not value:
                    continue
                conflict = _conflict(figure_id, field_name, value, text_parameters, text_versions)
                if conflict is not None:
                    result.conflicts.append(conflict)
                    result.claims.append(Claim(figure_id, field_name, value, CONFLICTING))
                    continue

                if field_name == "accessions_visible" and not is_accession_shaped(value):
                    result.claims.append(Claim(figure_id, field_name, value, MISFILED))
                    continue

                needle = _squash(value)
                corroborated = needle in haystack
                if corroborated:
                    status = CORROBORATED
                elif ocr_haystack and needle in ocr_haystack:
                    status = CORROBORATED_BY_OCR
                else:
                    status = FIGURE_ONLY
                result.claims.append(Claim(figure_id, field_name, value, status))
                if corroborated and field_name == "tools_named" and _key(value) not in known:
                    candidates.setdefault(
                        _key(value),
                        Discovery(figure_id, value, _mentions(value, document_text)),
                    )

    # One entry per name rather than per figure: a tool drawn into four diagrams
    # is one gap in the vocabulary, and listing it four times only buries the
    # names that appear once.
    result.discoveries = sorted(candidates.values(), key=lambda d: (d.text_mentions, d.name))
    return result


def _conflict(
    figure_id: str,
    field_name: str,
    value: str,
    text_parameters: dict[str, str],
    text_versions: dict[str, str | None],
) -> Conflict | None:
    """Whether this figure value contradicts what the text says about the same key."""
    if field_name == "parameters_visible":
        if (match := _ASSIGNMENT.match(value)) is not None:
            key = _key(match.group("key"))
            stated = text_parameters.get(key)
            figure_value = match.group("value").strip()
            if stated is not None and _key(stated) != _key(figure_value):
                return Conflict(
                    figure_id, field_name, match.group("key").strip(), figure_value, stated
                )
        return None

    if field_name in ("versions_visible", "tools_named"):
        if (match := _VERSIONED.match(value)) is not None:
            key = _key(match.group("name"))
            stated = text_versions.get(key)
            figure_version = match.group("version").strip()
            if stated is not None and _key(stated) != _key(figure_version):
                return Conflict(
                    figure_id, field_name, match.group("name").strip(), figure_version, stated
                )
    return None


def _mentions(value: str, document_text: str) -> int:
    """How often the text names this, for judging whether a candidate is worth adding."""
    return len(re.findall(re.escape(value), document_text, re.I))
