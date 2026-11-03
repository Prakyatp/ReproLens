"""Regressions for the required-resource checklist.

The cases come from MATES and LocusMasterTE. The through-line is that the
obvious implementation is biased the wrong way: anchoring on version strings
finds the tools a paper already documented and misses every tool it did not,
which is exactly backwards for an audit.
"""

from __future__ import annotations

from reprolens.documents.base import PageText
from reprolens.documents.sections import SectionMark, classify_heading
from reprolens.extraction.checklist import build, find_names


def page(text: str, *, heading: str = "Methods", number: int = 1) -> PageText:
    return PageText(
        page=number,
        text=f"{heading}\n{text}",
        sections=[SectionMark(offset=0, heading=heading, label=classify_heading(heading))],
    )


def item(checklist, name: str):
    return next((s for s in checklist.software if s.name == name), None)


class TestSpecificityNotInventory:
    def test_a_tool_named_repeatedly_without_a_version_is_a_gap(self):
        # MATES names STARsolo six times and never versions it. Its documented
        # major blocker is the alignment configuration.
        text = (
            "reads were realigned using STARsolo with the given option. "
            "The simulated reads were aligned using STARsolo. "
            "Reads were aligned using STARsolo for each sample."
        )
        found = item(build([page(text)]), "STARsolo")
        assert found.specificity == "named_only"
        assert found.mentions == 3
        assert found.declared

    def test_any_mention_with_a_version_pins_the_tool(self):
        # Velocyto is named bare three times in MATES before the one mention
        # that gives 0.17. Judging on the first mention reports a documented
        # tool as a gap.
        text = (
            "using Velocyto, the number of unspliced reads is identified. "
            "Since Velocyto does not provide detailed information. "
            "Counts were produced with Velocyto (version 0.17) throughout."
        )
        found = item(build([page(text)]), "Velocyto")
        assert found.specificity == "pinned"
        assert found.version == "0.17"

    def test_a_version_several_words_later_still_counts(self):
        # LocusMasterTE: "Gencode annotation of the hg38 version 42 Basic GTF".
        text = (
            "We obtained the coding gene Gencode annotation of the hg38 version 42 Basic GTF file."
        )
        found = item(build([page(text)]), "GENCODE")
        assert found.specificity == "pinned"
        assert found.version == "42"
        assert found.assembly == "hg38"

    def test_a_version_in_the_next_sentence_is_not_attributed(self):
        text = (
            "The reads were aligned using STARsolo. We then ran SeqKit version 2.8.2 on the output."
        )
        assert item(build([page(text)]), "STARsolo").specificity == "named_only"


class TestAssemblyIsNotAVersion:
    def test_a_genome_build_does_not_pin_an_annotation_source(self):
        # The exact wording of LocusMasterTE's hard blocker. Naming GRCh38 fixes
        # the coordinate system; the RepeatMasker track version is what was
        # needed and never given.
        text = "The GTF file for TE quantification was created using RepeatMasker for GRCh38."
        found = item(build([page(text)]), "RepeatMasker")
        assert found.specificity == "named_only"
        assert found.assembly == "GRCh38"
        assert found.version is None


class TestSplitNames:
    def test_typesetting_may_split_a_name(self):
        # MATES p20: "sourced from the Repeat Masker website" -- the mention
        # that matters most is the one an exact-name match misses.
        text = "The TE reference data was sourced from the Repeat Masker website."
        assert item(build([page(text)]), "RepeatMasker") is not None

    def test_a_shorter_name_does_not_claim_a_longer_ones_span(self):
        checklist = build([page("aligned using STARsolo for all samples.")])
        assert item(checklist, "STARsolo") is not None
        assert item(checklist, "STAR") is None


class TestFalsePositives:
    def test_r_squared_is_not_the_r_language(self):
        # Both papers report correlations as R-squared, which reaches the text
        # as "R 2" once the superscript is handled. A bare "R <digit>" matched
        # the statistic nine times in LocusMasterTE.
        text = "Spearman R 2 = 0.202 and the pseudo-bulk R 2 reached 0.9276 across runs."
        assert item(build([page(text)]), "R") is None

    def test_the_r_language_is_still_found_when_named(self):
        text = "Cosine similarity tests used the lsa R package to compare all groups."
        assert item(build([page(text)]), "R") is not None

    def test_a_name_only_in_the_reference_list_is_not_declared(self):
        checklist = build([page("Li H. samtools: a tool.", heading="References")])
        assert item(checklist, "samtools").declared is False


class TestParametersAndCommands:
    def test_a_flag_named_without_a_value_is_recorded(self):
        # MATES names --outFilterMultimapNmax and never says what it was set
        # to. The multi-mapper threshold is what the quantification turns on.
        text = "realigning them using STARsolo with the '--outFilterMultimapNmax' option."
        checklist = build([page(text)])
        assert [(p.flag, p.value) for p in checklist.parameters] == [
            ("--outFilterMultimapNmax", None)
        ]

    def test_a_quoted_flag_alone_is_not_a_command(self):
        text = "aligned with the '--outFilterMultimapNmax' option."
        assert build([page(text)]).commands == []

    def test_a_program_with_arguments_is_a_command(self):
        text = "identified with the command 'velocyto run -b path_to_bam annotation.gtf --dump p1'."
        commands = build([page(text)]).commands
        assert len(commands) == 1
        assert commands[0].command.startswith("velocyto run")


class TestCitationDeferral:
    def test_a_name_followed_by_a_reference_is_deferred_not_merely_named(self):
        text = "The GTF file was created using RepeatMasker [ 27 ] for GRCh38."
        found = item(build([page(text)]), "RepeatMasker")
        assert found.specificity == "deferred_to_citation"
        assert found.citations == ["27"]

    def test_evidence_comes_from_the_cited_mention(self):
        # The quote and the reference number have to describe the same mention,
        # or the record sends somebody to the wrong paper.
        text = (
            "mutational profiles were illustrated for all groups. "
            "Cosine similarity used the lsa R package [ 42 ] against TCGA-COAD."
        )
        found = item(build([page(text)]), "R")
        assert found.citations == ["42"]
        assert "[ 42 ]" in found.evidence


class TestGraderVocabulary:
    def test_find_names_reads_ground_truth_prose(self):
        prose = (
            "Exact STARsolo alignment command/flags; RepeatMasker annotation version; "
            "GENCODE annotation version"
        )
        assert set(find_names(prose)) >= {"STARsolo", "RepeatMasker", "GENCODE"}


class TestTheVocabularyCeiling:
    """What a fixed name list costs, measured on a paper it was not built for.

    On ASPEN the module knew 3 of the 8 tools the paper names, and the five it
    missed were all Bioconductor packages pinned to an exact version. The error
    runs the opposite way from the benchmark papers: there a missing name hides a
    gap, here it hides good practice.
    """

    def test_the_five_bioconductor_packages_aspen_names_are_found(self):
        text = (
            "Normalisation used scater (v1.28.0) and scuttle (v1.10.2). Counting used "
            "Rsubread (v2.4.3). Allelic testing used scDALI (v0.1.0), and enrichment "
            "analysis was performed in clusterProfiler (v4.8.3)."
        )
        assert find_names(text) == ["Rsubread", "clusterProfiler", "scDALI", "scater", "scuttle"]

    def test_a_parenthesised_version_pins_the_tool(self):
        # A third version format: MATES writes "v2.8.2", LocusMasterTE writes
        # "version 42", PLOS writes "scater (v1.28.0)".
        checklist = build([page("Counts were normalised with scater (v1.28.0) per batch.")])
        found = item(checklist, "scater")
        assert found.specificity == "pinned"
        assert found.version == "1.28.0"

    def test_a_bioconductor_package_named_bare_is_still_a_gap(self):
        checklist = build([page("Enrichment was performed in clusterProfiler.")])
        found = item(checklist, "clusterProfiler")
        assert found.specificity == "named_only"
        assert found in checklist.gaps()

    def test_the_additions_do_not_fire_on_ordinary_prose(self):
        # "scater" and "scuttle" are rare words, but the guard is worth pinning:
        # a vocabulary entry that matches running text turns every paper in the
        # field into a false positive.
        assert find_names("Reads were scattered across the scaffold and rescued.") == []
