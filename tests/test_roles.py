"""Regressions for role classification.

The cases are verbatim from the two papers' availability statements, because
that is where the hard ones are: one paragraph of LocusMasterTE contains the
paper's own deposit and three third-party datasets, and MATES's entire Data
Availability statement is other people's data.

A wrong role here is worse than no role. "own_data" asserts the authors
deposited something; said about a dataset they merely reused, it moves the
blame for a missing resource onto the wrong party.
"""

from __future__ import annotations

from reprolens.discovery.links import Finding, Occurrence, _is_severed_host
from reprolens.discovery.roles import _classify, classify

# --- LocusMasterTE, Data availability, one paragraph ------------------------
DEPOSIT = (
    "Inhouse HCT116 long-read and short-read are deposited at Gene Expression "
    "Omnibus (GEO) [ https://www.ncbi.nlm.nih.gov/geo )] under GSE225377 and "
    "GSE225380 respectively. We analyzed the ADAR-WT-MDA5-5aza sample"
)
REUSE = (
    "under GSE225377 and GSE225380 respectively. We analyzed the "
    "ADAR-WT-MDA5-5aza sample from the accession code GSE145639 [ 23 ]."
)
SG_NEX = (
    "Short-read and ONT RNA sequencing datasets for SG-NEx are available "
    "through their GitHub [ https://github.com/GoekeLab/sg-nex-data ]. "
    "Inhouse HCT116 long-read"
)
OWN_CODE = (
    "The code for LocusMasterTE is accessible through its GitHub repository at "
    "https://github.com/jasonwong-lab/LocusMasterTE . Scripts used to generate"
)

# --- MATES, Data availability ----------------------------------------------
THIRD_PARTY = (
    "the study utilized mRNAs sequenced by singlecell nanopore (GSE212945, "
    "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE212945) as detailed "
    "in Shiau et al. and postnatal mouse brain Pacbio long read data"
)
ACROSS_ET_AL = (
    "acc.cgi?acc=GSE212945) as detailed in Shiau et al. and postnatal mouse "
    "brain Pacbio long read data (GSE158450, https://www.ncbi.nlm.nih.gov/geo/"
    "query/acc.cgi?acc=GSM4800803 for 10x"
)
VENDOR = (
    "The scATAC-seq 10x 5k adult mouse brain cell dataset is available at "
    "https://support.10xgenomics.com/single-cell-atac/datasets/1.2.0/"
    "atac_v1_adult_brain_fresh_5k, and we generated the cell type labels "
    "following the workflow provided in the Signac tutorial"
)


def role_of(kind: str, value: str, context: str, section: str = "data_availability") -> tuple:
    result = _classify(
        kind=kind, value=value, section=section, heading="Data availability", context=context
    )
    return result.role, result.confidence


class TestOneParagraphTwoAnswers:
    def test_deposit_cue_before_the_accession_wins(self):
        # "we analyzed" is 47 characters from GSE225377 and "deposited" is 85,
        # so plain proximity picks the cue belonging to the *next sentence* and
        # reports the authors' own deposit as somebody else's data.
        assert role_of("geo_series", "GSE225377", DEPOSIT) == ("own_data", "stated")

    def test_reuse_cue_in_the_same_sentence_wins(self):
        assert role_of("geo_series", "GSE145639", REUSE) == ("external_data", "stated")

    def test_a_repository_can_be_someone_elses_dataset(self):
        # github.com/GoekeLab/sg-nex-data is a third-party dataset distributed as
        # a repository. The sentence says so even though the identifier does not.
        assert role_of("github", "github.com/GoekeLab/sg-nex-data", SG_NEX) == (
            "external_data",
            "stated",
        )

    def test_the_papers_own_repository_is_analysis_code(self):
        value = "github.com/jasonwong-lab/LocusMasterTE"
        assert role_of("github", value, OWN_CODE) == ("analysis_code", "stated")


class TestAvailabilityIsNotOwnership:
    def test_attribution_to_another_study_is_reuse(self):
        # Every accession in MATES's Data Availability statement is third-party.
        assert role_of("geo_series", "GSE212945", THIRD_PARTY) == ("external_data", "stated")

    def test_et_al_does_not_end_the_sentence(self):
        # Splitting at "al." strands GSE158450 in a window with no cue in it,
        # and the no-cue default then had to guess.
        assert role_of("geo_series", "GSE158450", ACROSS_ET_AL) == ("external_data", "stated")

    def test_no_cue_is_reported_as_unknown_not_as_own_data(self):
        context = "and postnatal mouse brain data (GSE999999, for 10x and for Pacbio)"
        role, confidence = role_of("geo_series", "GSE999999", context)
        assert role == "unclassified"
        assert confidence == "inferred"

    def test_a_vendor_archive_outranks_a_nearby_deposit_cue(self):
        # "we generated" refers to the cell type labels, not to 10x Genomics'
        # dataset, and the cue alone reported a vendor's public data as the
        # authors' own.
        value = "https://support.10xgenomics.com/single-cell-atac/datasets/1.2.0/x"
        assert role_of("url", value, VENDOR)[0] == "external_data"


class TestSectionDecidesTheQuestion:
    def test_a_repository_in_the_reference_list_is_a_dependency(self):
        result = _classify(
            kind="github",
            value="github.com/pysam-developers/pysam",
            section="references",
            heading="References",
            context="pysam, https://github.com/pysam-developers/pysam",
        )
        assert result.role == "software_dependency"

    def test_an_annotation_track_gets_its_own_role(self):
        # Both papers' hard blockers are undocumented RepeatMasker and GENCODE
        # versions, so these are worth separating from software.
        result = _classify(
            kind="url",
            value="https://www.repeatmasker.org/species/hg.html",
            section="methods",
            heading="Methods",
            context="TE reference from https://www.repeatmasker.org/species/hg.html",
        )
        assert result.role == "reference_resource"

    def test_the_running_header_is_boilerplate(self):
        result = _classify(
            kind="doi",
            value="10.1038/s41467-024-53114-7",
            section="page_furniture",
            heading="",
            context="Article https://doi.org/10.1038/s41467-024-53114-7",
        )
        assert result.role == "publisher_boilerplate"
        assert result.confidence == "stated"


class TestStrongestClaimWins:
    def test_data_availability_outranks_pmcs_repeat_of_it(self):
        # LocusMasterTE's statement appears twice in the JATS: once as "Data
        # availability" and once inside "Associated Data".
        finding = Finding(
            value="GSE225377",
            kind="geo_series",
            occurrences=[
                Occurrence(page=15, source="text", context=DEPOSIT, section="associated_data"),
                Occurrence(page=11, source="text", context=DEPOSIT, section="data_availability"),
            ],
        )
        assert classify(finding).role == "own_data"


class TestWeakEvidence:
    def test_the_articles_own_doi_is_not_literature_it_cites(self):
        # MATES prints its DOI in the running header of 21 pages and in the
        # title block of the first. Front matter outranks furniture in the
        # priority order, so this was classified as a citation.
        finding = Finding(
            value="10.1038/s41467-024-53114-7",
            kind="doi",
            occurrences=[
                Occurrence(page=1, source="text", context="Article", section="front_matter"),
                Occurrence(page=2, source="furniture", context="Article", section="page_furniture"),
            ],
        )
        result = classify(finding)
        assert result.role == "publisher_boilerplate"
        assert result.confidence == "stated"

    def test_furniture_does_not_override_a_real_section(self):
        finding = Finding(
            value="10.5281/zenodo.13738122",
            kind="zenodo",
            occurrences=[
                Occurrence(page=2, source="furniture", context="", section="page_furniture"),
                Occurrence(page=20, source="text", context="code at", section="code_availability"),
            ],
        )
        assert classify(finding).role == "analysis_code"


class TestSeveredHosts:
    def test_drops_a_host_cut_off_mid_name(self):
        # MATES prints "https://www. ncbi.nlm.nih.gov/..." with a space inside
        # the line, so the URL pattern matches only the head.
        assert _is_severed_host("https://www")
        assert _is_severed_host("https://www.ncbi")

    def test_keeps_a_real_path_less_host(self):
        assert not _is_severed_host("https://mates.cellcycle.org")
        assert not _is_severed_host("https://portal.gdc.cancer.gov/")

    def test_never_judges_a_url_that_has_a_path(self):
        assert not _is_severed_host("https://whatever.internal/some/path")

    def test_leaves_a_scheme_with_no_authority_alone(self):
        # "mailto:" has no host to be severed. Judging it here dropped MATES's
        # two corresponding-author addresses by the wrong rule, which also left
        # the rule meant to handle them unreachable.
        assert not _is_severed_host("mailto:jun.ding@mcgill.ca")

    def test_a_contact_address_is_boilerplate_not_a_resource(self):
        result = _classify(
            kind="url",
            value="mailto:jun.ding@mcgill.ca",
            section="front_matter",
            heading="",
            context="Correspondence to jun.ding@mcgill.ca",
        )
        assert result.role == "publisher_boilerplate"
        assert result.confidence == "stated"
