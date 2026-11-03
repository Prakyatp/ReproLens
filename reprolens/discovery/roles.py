"""What each resource is *for*, which is not the same question as what it is.

The identifier tells you the kind; it does not tell you the role. ``GSE225377``
and ``GSE145639`` are both GEO series, both printed in the same Data
Availability paragraph of the same paper, and they mean opposite things:

    Inhouse HCT116 long-read and short-read are deposited at Gene Expression
    Omnibus (GEO) [...] under GSE225377 and GSE225380 respectively. We analyzed
    the ADAR-WT-MDA5-5aza sample from the accession code GSE145639 [23].

The first two are the paper's own deposit, so their absence would be the
authors' failure. The third is someone else's dataset the work depends on, so
its absence is a dependency risk. An audit that reports "5 datasets found"
without that split has not said anything useful.

**Presence in a Data Availability statement does not mean the data is the
paper's own.** This was worth checking rather than assuming, and the assumption
was wrong: every one of the six GEO accessions in MATES's Data Availability
statement belongs to another study -- "as detailed in Shiau et al.", "published
by Zhu et al.", "is described in Darmanis et al.". MATES deposited no data of
its own. A paper whose availability statement is entirely third-party is a
specific and reportable reproducibility condition, and a rule keyed on the
section alone would have recorded the exact opposite.

So the section decides the *question* and the sentence decides the *answer*: the
nearest deposit-or-reuse cue to the identifier wins, since one paragraph holds
both. Every classification carries the phrase it was decided by, and says
whether that came from the paper (``stated``) or from us (``inferred``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from reprolens.documents.sections import SectionLabel

Role = Literal[
    "own_data",  # a dataset this paper deposited
    "external_data",  # a dataset from elsewhere that the work depends on
    "analysis_code",  # code or scripts for this paper's analysis
    "software_dependency",  # a tool the method uses
    "reference_resource",  # genome build or annotation track
    "cited_literature",  # a paper
    "publisher_boilerplate",  # journal, licence, ORCID, running header
    "unclassified",  # said plainly, rather than guessed at
]

Confidence = Literal["stated", "inferred"]

# Lower binds tighter. Where a value appears in several sections, the strongest
# claim about it wins: an availability statement is the paper telling us what a
# resource is for, while a reference-list appearance is barely a claim at all.
_SECTION_PRIORITY: dict[SectionLabel, int] = {
    "data_availability": 0,
    "code_availability": 0,
    "associated_data": 1,  # PMC's verbatim repeat of the availability statement
    "methods": 2,
    "results": 3,
    "supplementary": 4,
    "abstract": 5,
    "background": 5,
    "discussion": 5,
    "conclusions": 5,
    "reporting_summary": 5,
    "acknowledgments": 6,
    "funding": 6,
    "author_contributions": 6,
    "declarations": 6,
    "references": 7,
    "front_matter": 8,
    "other": 8,
    "page_furniture": 9,
}

_AVAILABILITY = ("data_availability", "code_availability", "associated_data")

_DATASET_KINDS = frozenset(
    {
        "geo_series",
        "geo_sample",
        "geo_platform",
        "sra_run",
        "sra_experiment",
        "sra_study",
        "bioproject",
        "biosample",
        "ena_run",
        "ena_study",
        "dbgap",
    }
)
_CODE_KINDS = frozenset({"github", "gitlab"})
_ARCHIVE_KINDS = frozenset({"zenodo", "figshare", "dryad"})  # hold data or code
_LITERATURE_KINDS = frozenset({"doi", "arxiv", "pubmed", "pmc"})

# The paper deposited it.
_DEPOSIT_CUES = (
    "deposited",
    "inhouse",
    "in-house",
    "in house",
    "generated in this study",
    "generated for this study",
    "newly generated",
    "we generated",
    "this study generated",
    "reported in this paper",
    "provided with this paper",
    "have been submitted",
    "we have deposited",
)

# The paper took it from somewhere else.
_REUSE_CUES = (
    "downloaded from",
    "download from",
    "retrieved from",
    "obtained from",
    "sourced from",
    "published by",
    "detailed in",
    "described in",
    "available through their",
    "publicly available",
    "previously published",
    "can be found on",
    "we analyzed",
    "we analysed",
    "from the accession",
    "et al.",
)

# Domains that answer the role question on their own. Kept small and specific:
# a guess from a domain is weaker evidence than a sentence, and is marked so.
_DOMAIN_ROLES: tuple[tuple[str, Role], ...] = (
    # journal infrastructure -- never a research resource
    ("nature.com", "publisher_boilerplate"),
    ("springer.com", "publisher_boilerplate"),
    ("springernature.com", "publisher_boilerplate"),
    ("biomedcentral.com", "publisher_boilerplate"),
    ("creativecommons.org", "publisher_boilerplate"),
    ("orcid.org", "publisher_boilerplate"),
    ("crossmark.crossref.org", "publisher_boilerplate"),
    ("doi.org", "publisher_boilerplate"),
    ("researchgate.net", "publisher_boilerplate"),
    # genome builds and annotation tracks -- the versions both benchmark papers
    # fail to pin, so worth naming as its own role rather than lumping in with
    # software
    ("repeatmasker.org", "reference_resource"),
    ("gencodegenes.org", "reference_resource"),
    ("genome.ucsc.edu", "reference_resource"),
    ("hgdownload", "reference_resource"),
    ("ensembl.org", "reference_resource"),
    ("gtrnadb", "reference_resource"),
    # data archives
    ("portal.gdc.cancer.gov", "external_data"),
    ("encodeproject.org", "external_data"),
    ("gdc-hub", "external_data"),
    ("xenabrowser.net", "external_data"),
    ("ega-archive.org", "external_data"),
    ("support.10xgenomics.com", "external_data"),
    ("ebi.ac.uk/arrayexpress", "external_data"),
    # software distribution and tool homepages
    ("bioconductor.org", "software_dependency"),
    ("pypi.org", "software_dependency"),
    ("cran.r-project.org", "software_dependency"),
    ("anaconda.org", "software_dependency"),
    ("bioconda", "software_dependency"),
    ("galaxyproject.org", "software_dependency"),
    ("stuartlab.org", "software_dependency"),
    ("satijalab.org", "software_dependency"),
    ("broadinstitute.org", "software_dependency"),
)

_MAILTO = re.compile(r"^mailto:", re.I)

# A cue in the next sentence is not describing this identifier.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s")

# ...but a period is not always a sentence end, and in this genre the exception
# is the common case. "as detailed in Shiau et al. and postnatal mouse brain
# Pacbio long read data (GSE158450, ...)" is one sentence; splitting it at
# "al." strands GSE158450 in a window with no cue in it at all.
_ABBREVIATIONS = (
    "et al.",
    "e.g.",
    "i.e.",
    "cf.",
    "fig.",
    "figs.",
    "vs.",
    "no.",
    "ref.",
    "refs.",
    "etc.",
    "approx.",
)
_INITIAL = re.compile(r"(?:^|\s)\w\.$")


@dataclass(slots=True)
class Classification:
    role: Role
    confidence: Confidence
    reason: str

    def as_dict(self) -> dict:
        return {"role": self.role, "role_confidence": self.confidence, "role_reason": self.reason}


# Sections that make no claim about what a resource is for.
_WEAK_SECTIONS = frozenset({"front_matter", "page_furniture", "other"})


def classify(finding) -> Classification:
    """Assign a role to one finding, from its strongest-claiming occurrence."""
    sections = {occurrence.section for occurrence in finding.occurrences}

    # Checked ahead of the priority ordering below, which would otherwise prefer
    # a front-matter occurrence over a furniture one and so classify the
    # article's own DOI -- printed in MATES's running header on 21 pages and in
    # its title block on the first -- as literature this paper cites.
    if "page_furniture" in sections and sections <= _WEAK_SECTIONS:
        return Classification(
            "publisher_boilerplate",
            "stated",
            "printed in the running header or footer, and nowhere more specific",
        )

    occurrence = min(
        finding.occurrences,
        key=lambda o: (_SECTION_PRIORITY.get(o.section, 8), o.page),
    )
    return _classify(
        kind=finding.kind,
        value=finding.value,
        section=occurrence.section,
        heading=occurrence.section_heading,
        context=occurrence.context,
    )


def _classify(
    *, kind: str, value: str, section: SectionLabel, heading: str, context: str
) -> Classification:
    where = heading or section.replace("_", " ")

    if section == "page_furniture":
        return Classification(
            "publisher_boilerplate", "stated", "printed in the running header or footer"
        )

    if kind in _LITERATURE_KINDS:
        if section == "references":
            return Classification("cited_literature", "stated", "listed in the reference section")
        return Classification("cited_literature", "inferred", f"literature identifier, in {where}")

    if _MAILTO.match(value):
        return Classification(
            "publisher_boilerplate", "stated", "a contact address, not a resource"
        )

    domain_role = _domain_role(value)

    # The publisher's own domains are boilerplate wherever they appear.
    if domain_role == "publisher_boilerplate":
        return Classification(domain_role, "inferred", f"a publisher or licence domain, in {where}")

    if section in _AVAILABILITY:
        return _from_availability(kind, value, section, where, context, domain_role)

    if domain_role is not None:
        return Classification(domain_role, "inferred", f"recognized domain, cited in {where}")

    if kind in _DATASET_KINDS:
        return Classification("external_data", "inferred", f"an accession cited in {where}")

    if kind in _CODE_KINDS or kind in _ARCHIVE_KINDS:
        return Classification("software_dependency", "inferred", f"a repository cited in {where}")

    return Classification("unclassified", "inferred", f"a bare URL in {where}, role not determined")


def _from_availability(
    kind: str,
    value: str,
    section: SectionLabel,
    where: str,
    context: str,
    domain_role: Role | None,
) -> Classification:
    """Decide own-vs-external inside an availability statement, by the sentence.

    One paragraph routinely holds both, so "which cue is present" is not enough
    -- it has to be which cue is *nearest* the identifier.
    """
    cue = _nearest_cue(context, value)
    quoted = f'"{cue[1]}"' if cue else None

    # A recognized third-party archive outranks the sentence. MATES reads
    # "... is available at https://support.10xgenomics.com/..., and we generated
    # the cell type labels following the workflow ..." -- "we generated" is the
    # nearest deposit cue and it refers to the labels, not to 10x Genomics'
    # dataset, so the cue alone reported a vendor's public data as the authors'.
    if domain_role == "external_data":
        agrees = cue is not None and cue[0] == "reuse"
        return Classification(
            "external_data",
            "stated" if agrees else "inferred",
            f"{quoted}, in {where}" if agrees else f"a third-party data archive, in {where}",
        )

    # Zenodo, Figshare and Dryad hold data or code indifferently, so the kind
    # cannot settle it -- but a Code availability heading can, and does.
    if section == "code_availability" and (kind in _CODE_KINDS or kind in _ARCHIVE_KINDS):
        if cue and cue[0] == "reuse":
            return Classification("external_data", "stated", f"{quoted}, in {where}")
        return Classification("analysis_code", "stated", f"named in {where}")

    if kind in _DATASET_KINDS or kind in _ARCHIVE_KINDS:
        if cue and cue[0] == "reuse":
            return Classification("external_data", "stated", f"{quoted}, in {where}")
        if cue and cue[0] == "deposit":
            return Classification("own_data", "stated", f"{quoted}, in {where}")
        # Deliberately not "own_data". Presence in an availability statement
        # says the paper means you to have the dataset, not that the paper made
        # it, and defaulting the other way invented three deposits for MATES --
        # which deposited nothing. Unknown is reportable; wrong is not.
        return Classification(
            "unclassified", "inferred", f"in {where}, with no deposit or reuse wording nearby"
        )

    if kind in _CODE_KINDS:
        if cue and cue[0] == "reuse":
            # github.com/GoekeLab/sg-nex-data is a third-party *dataset* that
            # happens to be distributed as a repository; the sentence says so.
            return Classification("external_data", "stated", f"{quoted}, in {where}")
        return Classification("analysis_code", "stated", f"named in {where}")

    if domain_role is not None:
        return Classification(domain_role, "inferred", f"recognized domain, named in {where}")

    if section == "code_availability":
        return Classification("analysis_code", "stated", f"named in {where}")

    if cue and cue[0] == "reuse":
        return Classification("external_data", "stated", f"{quoted}, in {where}")
    return Classification("unclassified", "inferred", f"a bare URL in {where}, role not determined")


def _nearest_cue(context: str, value: str) -> tuple[str, str] | None:
    """The deposit/reuse cue governing this identifier, with the phrase matched.

    Scoped to the identifier's own sentence, and preferring a cue that precedes
    it. Both rules are load-bearing, and plain proximity gets this wrong::

        ... are deposited at Gene Expression Omnibus (GEO) [...] under
        GSE225377 and GSE225380 respectively. We analyzed the ADAR-WT ...

    "we analyzed" is 47 characters from GSE225377 and "deposited" is 85, so the
    nearest cue is the one belonging to the *next sentence*, and the paper's own
    deposit gets reported as somebody else's data. The sentence break is the
    signal that says the second cue is not talking about this accession.
    """
    lowered = context.casefold()
    needle = value.casefold()
    anchor = lowered.find(needle)
    located = anchor >= 0
    if not located:
        anchor, span = len(lowered) // 2, 0
    else:
        span = len(needle)

    start, end = 0, len(lowered)
    for break_ in _sentence_breaks(lowered):
        if break_ <= anchor:
            start = break_
        elif break_ >= anchor + span:
            end = break_
            break

    # Where the value could not be located in the context there is no "before"
    # or "after" to prefer, and splitting on a guessed midpoint discards any cue
    # that straddles it -- which is every cue in a short context.
    before: tuple[int, int, str, str] | None = None
    after: tuple[int, int, str, str] | None = None
    for cue_kind, phrases in (("deposit", _DEPOSIT_CUES), ("reuse", _REUSE_CUES)):
        for phrase in phrases:
            position = lowered.find(phrase, start, end)
            while position >= 0:
                if not located:
                    candidate = (abs(position - anchor), -len(phrase), cue_kind, phrase)
                    if before is None or candidate < before:
                        before = candidate
                elif position + len(phrase) <= anchor:
                    # Nearer wins; on a tie the longer phrase is more specific
                    # than a catch-all like "et al.".
                    candidate = (anchor - position, -len(phrase), cue_kind, phrase)
                    if before is None or candidate < before:
                        before = candidate
                elif position >= anchor + span:
                    candidate = (position - anchor, -len(phrase), cue_kind, phrase)
                    if after is None or candidate < after:
                        after = candidate
                position = lowered.find(phrase, position + 1, end)

    chosen = before or after
    return (chosen[2], chosen[3]) if chosen else None


def _sentence_breaks(lowered: str):
    """Offsets just past each real sentence end, skipping abbreviations."""
    for match in _SENTENCE_BREAK.finditer(lowered):
        prefix = lowered[: match.start()]
        if any(prefix.endswith(abbreviation) for abbreviation in _ABBREVIATIONS):
            continue
        if _INITIAL.search(prefix):  # an author initial, "Wang R. et al"
            continue
        yield match.end()


def _domain_role(value: str) -> Role | None:
    lowered = value.casefold()
    for needle, role in _DOMAIN_ROLES:
        if needle in lowered:
            return role
    return None
