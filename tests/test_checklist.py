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


class TestTheMaterialsScienceVocabulary:
    """A second field, and the collisions that a second field creates.

    The vocabulary was computational biology only, and the cost was measurable:
    ALIGNN named 1 tool and Atomate2 named 1, against ASPEN's 16. Both papers
    were then scored as though they had declared almost nothing. These cases are
    the names that could not simply be added.
    """

    def test_the_materials_names_are_found(self):
        text = (
            "Band gaps were computed with VASP and post-processed with BoltzTraP. "
            "Training data came from JARVIS-DFT and the Materials Project, and the "
            "baselines were CGCNN, SchNet, MEGNet and DimeNet++ in DGL."
        )
        assert set(find_names(text)) >= {
            "VASP",
            "BoltzTraP",
            "JARVIS-DFT",
            "Materials Project",
            "CGCNN",
            "SchNet",
            "MEGNet",
            "DimeNet++",
            "DGL",
        }

    def test_ase_alone_is_allele_specific_expression(self):
        # The one collision that crosses the two fields. ASPEN writes "variations
        # in ASE across continuous trajectories", 12 occurrences, and it means
        # allele-specific expression. So the Atomic Simulation Environment is
        # matched only where a paper spells it out or introduces the
        # abbreviation, which Atomate2 does: "Atomic Simulation Environment (ASE)".
        assert find_names("a linear mixed model to detect variations in ASE across cells") == []
        assert find_names("built on the Atomic Simulation Environment (ASE) and pymatgen") == [
            "pymatgen",
            "Atomic Simulation Environment",
        ]

    def test_dimenet_keeps_its_plusses(self):
        # "DimeNet++ " ends on a non-word character followed by a space, so a
        # trailing \b never matches and the generated pattern found nothing.
        # The two entries also have to not both fire, the same span-claiming
        # rule that keeps "STAR" out of "STARsolo".
        checklist = build([page("DimeNet++ was trained for 300 epochs.")])
        assert [s.name for s in checklist.software] == ["DimeNet++"]
        assert [s.name for s in build([page("DimeNet used radial bases.")]).software] == ["DimeNet"]

    def test_the_names_that_collide_with_prose_were_left_out(self):
        # Each of these is real materials software and each was dropped after
        # measuring it: GAP is also "band gap" (5 hits in ALIGNN, 14 in
        # Atomate2), SCAN is also an exchange-correlation functional and a verb,
        # MP is also an author's initials in LocusMasterTE's reference list, and
        # NOMAD appears in Atomate2 only as an author affiliation.
        text = (
            "the band gap value converged within the GW framework; functionals "
            "like PBE or SCAN are required; we scan the Materials project (MP) "
            "records; the NOMAD Laboratory, Fritz-Haber-Institut"
        )
        assert find_names(text) == ["Materials Project"]

    def test_a_database_named_without_a_version_is_its_own_gap(self):
        # Severity equal to an unspecified reference genome, for the same
        # reason -- a growing collection returns a different set of records each
        # time it is queried -- but worded for something queried rather than
        # aligned against.
        checklist = build([page("Formation energies were taken from JARVIS-DFT.")])
        found = item(checklist, "JARVIS-DFT")
        assert found.kind == "database"
        assert found.specificity == "named_only"
        assert found in checklist.gaps()


class TestTheValuesAPaperStatesItself:
    def test_a_flattened_hyperparameter_table_is_read(self):
        # The text layer gives ALIGNN's two-column "Parameter Value" table as
        # one run, so the separator between a name and its value is a bare
        # space. Requiring punctuation would lose the one paper of the five that
        # documents its training configuration in full.
        text = (
            "Parameter Value ALIGNN layers 4 GCN layers 4 Edge input features 80 "
            "Triplet input features 40 Embedding features 64 Hidden features 256 "
            "Normalization Batch normalization Batch size 64 Learning rate 0.001"
        )
        found = {(s.name, s.value) for s in build([page(text)]).settings}
        assert ("ALIGNN layers", "4") in found
        assert ("Hidden features", "256") in found
        assert ("Batch size", "64") in found
        assert ("Learning rate", "0.001") in found

    def test_an_exponent_is_kept_whole(self):
        # "10^-5" opens with a digit run, so a value pattern that tries a plain
        # number first captures "10" and reports a weight decay four thousand
        # times its real size. The exponent alternative has to come first.
        text = "trained using the AdamW optimizer with normalized weight decay of 10^-5"
        assert [(s.name, s.value) for s in build([page(text)]).settings] == [
            ("weight decay", "10^-5")
        ]

    def test_every_threshold_is_its_own_value(self):
        # ASPEN states four different FDR thresholds and each one configures a
        # different analysis. Keyed on the name alone, the paper would look as
        # though it had documented one.
        text = "enriched at FDR < 0.1, imbalanced at FDR = 0.001, and dynamic at FDR < 0.05"
        assert [s.value for s in build([page(text)]).settings if s.name == "FDR"] == [
            "0.001",
            "0.05",
            "0.1",
        ]

    def test_a_percentage_is_measured_rather_than_configured(self):
        # ASPEN writes "the resolution of 20-38% of total sequencing reads",
        # which is an outcome. Its real "resolution = 0.9" is Seurat's
        # FindClusters setting and is unaffected by the guard.
        measured = "this strategy enabled the resolution of 20-38% of total reads"
        assert build([page(measured)]).settings == []
        configured = "implemented in the FindClusters function (resolution = 0.9)"
        assert [s.value for s in build([page(configured)]).settings] == ["0.9"]

    def test_a_name_is_reported_without_its_joining_word(self):
        # The separator is matched inside the name's span so the value's
        # position is known, which otherwise leaves the label "threshold of".
        text = "a threshold of 0.45 was selected to assign the group"
        assert [s.name for s in build([page(text)]).settings] == ["threshold"]

    def test_the_open_form_is_not_used(self):
        # A rule of "a name, a separator, a number" returns 188-401 matches per
        # paper across the five, and the most frequent captures are DOIs,
        # author names and table cross-references. The vocabulary is closed, so
        # none of these is a stated parameter.
        text = (
            "Wang Ruohan, Zheng Yumin. Nature 2024 doi 10.1038/s41467. "
            "Additional file 13 and Supplementary Table 6 report CD8 T-cells day 7."
        )
        assert build([page(text)]).settings == []
