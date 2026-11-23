"""Text backend: JATS XML, as served for PMC open-access articles.

A second implementation of ``TextBackend``, which is the point: the extractors
downstream were written against ``PageText`` and need no change to consume this.

It is also the better channel when available. JATS carries the document's real
structure -- sections are labelled, so the Data Availability and Code
Availability statements can be addressed directly instead of being recovered by
font-size heuristics over a two-column layout.

What it does not carry is page numbers or bounding boxes. ``PageText.page`` is
therefore a *section* ordinal here, not a page; ``backend`` says which it is.
Provenance from this channel is section-level, and anything needing a page or a
bbox has to come from the PDF.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from reprolens.documents.base import Backend, PageText
from reprolens.documents.sections import SectionMark, classify_heading


class JatsXmlBackend:
    name: Backend = "jats_xml"

    def read(self, path: Path) -> list[PageText]:
        root = _article(ET.parse(path).getroot())
        segments: list[PageText] = []

        for index, (label, element) in enumerate(_segments(root), start=1):
            text = _text_of(element)
            if not text.strip():
                continue
            segments.append(
                PageText(
                    page=index,
                    text=f"{label}\n{text}" if label else text,
                    links=_ext_links(element),
                    has_images=False,  # figures are referenced, not embedded
                    backend=self.name,
                    confidence=None,  # XML is exact
                    # One segment is one section, so its mark sits at offset 0.
                    # The heading is given to us here rather than inferred from
                    # font size, which is the whole advantage of this channel.
                    sections=[
                        SectionMark(
                            offset=0,
                            heading=label,
                            label="front_matter"
                            if element.tag == "front"
                            else classify_heading(label),
                        )
                    ],
                )
            )
        return segments


def _local(tag: str) -> str:
    """An element's name without its namespace, if it carries one."""
    return tag.rpartition("}")[2]


def _article(root: ET.Element) -> ET.Element:
    """The ``<article>`` element, whatever is wrapped around it.

    E-utilities ``efetch`` returns ``<pmc-articleset><article>…`` while the PMC
    open-access packages ship a bare ``<article>``, and this module assumed the
    latter. The assumption held only by accident of how the first XML paper was
    obtained: fed the efetch form it found no front, no body and no back, and
    returned zero segments without raising -- a whole paper reading as empty,
    which is the one failure mode this project exists to prevent. The guard in
    ``base.is_readable`` catches the general case; this handles the common one.
    """
    if _local(root.tag) == "article":
        return root
    for child in root:
        if _local(child.tag) == "article":
            return child
    return root


def _segments(root: ET.Element) -> list[tuple[str, ET.Element]]:
    """Front matter, each top-level body section, then back matter.

    Back matter is included deliberately: in JATS the data- and
    code-availability statements frequently live there rather than in the body,
    and those are the two sections that matter most for this project.
    """
    found: list[tuple[str, ET.Element]] = []

    if (front := root.find("front")) is not None:
        found.append(("Front matter", front))

    body = root.find("body")
    if body is not None:
        top_level = body.findall("sec")
        if top_level:
            for sec in top_level:
                found.extend(_with_nested_statements(_title(sec), sec))
        else:
            found.append(("Body", body))

    if (back := root.find("back")) is not None:
        # The back matter's own sections are split out rather than lumped
        # together, because that is where the statements this project cares
        # about most actually live. Nature and PLOS put "Code availability" in
        # the body; RSC's Digital Discovery puts it in a <sec
        # sec-type="data-availability"> in the back, after the
        # acknowledgements. Emitting <back> as a single "Back matter" segment
        # classifies the lot as "other", and Atomate2's availability statement
        # -- which names its repository, pins it to version 0.0.21 and gives a
        # Zenodo DOI -- vanished into it, scoring the paper 0 of 20 for code
        # availability.
        # JATS does not model back matter as sections throughout: <ack> and
        # <ref-list> are siblings of <sec>, not children of one. Splitting only
        # the <sec> children therefore left the reference list in the
        # remainder, where it was labelled "other" -- 64 of ASPEN's 89 finding
        # occurrences and 149 of Atomate2's 209, which is to say almost all of
        # the cited literature in both papers. LocusMasterTE hid this: PMC
        # wraps its reference list in <sec sec-type="ref-list">, so it split
        # out and classified correctly by title.
        #
        # So each back child is its own segment, keyed by element name rather
        # than by title, because <ref-list> frequently carries no <title> at
        # all and the name is the structural fact the format guarantees.
        unknown: list[ET.Element] = []
        for child in back:
            tag = _local(child.tag)
            if tag == "sec":
                found.extend(_with_nested_statements(_title(child), child))
            elif tag in _BACK_HEADINGS:
                found.append((_title(child) or _BACK_HEADINGS[tag], child))
            else:
                unknown.append(child)

        # Only genuinely unrecognized elements are pooled, in a new element so
        # that no text belongs to two segments at once and a finding in the
        # reference list is not also counted inside an availability statement.
        if unknown:
            remainder = ET.Element("back")
            remainder.extend(unknown)
            found.append(("Back matter", remainder))

    return found


# The back-matter elements JATS names structurally, with the printed heading
# each stands in for when the element itself carries no <title>. The strings are
# chosen so that ``classify_heading`` recognizes them: the label vocabulary and
# the rules that reach it stay in ``sections.py``, and this map says only which
# heading an unlabelled element would have had if the typesetter had printed one.
_BACK_HEADINGS = {
    "ack": "Acknowledgments",
    "ref-list": "References",
    "app-group": "Appendix",
    "app": "Appendix",
    "glossary": "Glossary",
    "notes": "Notes",
    "fn-group": "Footnotes",
    "bio": "Author information",
}


# The labels that name a statement rather than a part of the argument. A
# section carrying one of these is addressed directly by the rubric, so it has
# to be its own segment no matter how deeply the publisher nested it.
_STATEMENT_LABELS = frozenset(
    {
        "data_availability",
        "code_availability",
        "supplementary",
        "reporting_summary",
        "associated_data",
    }
)


def _with_nested_statements(label: str, sec: ET.Element) -> list[tuple[str, ET.Element]]:
    """``sec``, with any statement subsection lifted out of it.

    Splitting only the top-level body sections was the same mistake as
    emitting <back> whole, one level deeper. ASPEN nests its "Availability of
    data and materials" -- a <sec sec-type="data-availability"> -- inside
    Methods, twenty-one subsections down, so the statement naming both of its
    repositories arrived inside a 25,935-character segment labelled "methods".
    Both repositories then read as dependencies rather than the paper's own
    code, neither was cloned, and the paper scored 0 of 20 for code
    availability from this channel while scoring 18 of 20 from its own PDF.

    Ordinary subsections are left where they are, because the heading rules in
    ``sections.py`` are anchored and classify them as "other": "Bayesian
    shrinkage implementation" belongs to Methods and nothing is gained by
    giving it a segment. Only a recognized statement is lifted.
    """
    # A statement nested inside another statement stays where it is. PMC
    # repeats the whole Data availability statement verbatim inside an
    # <sec sec-type="associated-data">, and ``associated_data`` is a separate
    # label precisely so the copy can be told from the original. Lifting the
    # nested copy out would relabel it ``data_availability`` and leave the
    # document stating its accessions twice with equal authority.
    if classify_heading(label) in _STATEMENT_LABELS:
        return [(label, sec)]

    parents = {child: parent for parent in sec.iter() for child in parent}
    statements = [
        element
        for element in sec.iter()
        if element is not sec
        and _local(element.tag) == "sec"
        and classify_heading(_title(element)) in _STATEMENT_LABELS
    ]
    if not statements:
        return [(label, sec)]

    # A lifted statement is removed from its parent so that no text belongs to
    # two segments at once. Only the outermost of a nested pair is lifted; the
    # inner one travels with it, still inside the statement it belongs to.
    outermost = [
        element
        for element in statements
        if not any(other is not element and element in list(other.iter()) for other in statements)
    ]
    for element in outermost:
        parents[element].remove(element)

    return [(label, sec)] + [(_title(element), element) for element in outermost]


def _title(element: ET.Element) -> str:
    for child in element:
        if _local(child.tag) == "title":
            return " ".join("".join(child.itertext()).split())
    return ""


def _text_of(element: ET.Element) -> str:
    return " ".join(part.strip() for part in element.itertext() if part.strip())


# An ``<ext-link>`` href is only a URL when its type says so. For the
# identifier types JATS carries bare, the resolver prefix is added here rather
# than downstream: "30454069" is not an actionable resource and would be
# recorded as a URL by the catch-all pattern, which is how LocusMasterTE's
# reference list produced 99 findings of kind ``url``.
_LINK_RESOLVERS = {
    "pmid": "https://pubmed.ncbi.nlm.nih.gov/{}/",
    "pmcid": "https://www.ncbi.nlm.nih.gov/pmc/articles/{}/",
    "doi": "https://doi.org/{}",
}

# Not a link target at all: JATS stores the whole formatted citation in this
# href ("Bourque G, Burns KH, ... Genome Biol. 2018;19:199."). The citation is
# already in the reference section's text, so nothing is lost by not treating
# the search string as a resource.
_NOT_A_LINK = frozenset({"google-scholar"})


def _ext_links(element: ET.Element) -> list[str]:
    """``<ext-link>`` targets -- the JATS equivalent of a PDF link annotation.

    Same reason to read them separately: the displayed text is often shortened
    while the href holds the resolvable target.
    """
    uris: list[str] = []
    for link in element.iter("ext-link"):
        kind = link.get("ext-link-type") or ""
        if kind in _NOT_A_LINK:
            continue
        for key, value in link.attrib.items():
            if key.endswith("href") and value:
                template = _LINK_RESOLVERS.get(kind)
                uris.append(template.format(value.strip()) if template else value)
    return uris
