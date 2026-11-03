"""Regressions for the text/figure merge.

The conflict detector is the part that cannot be validated on the papers in
hand: all three keep their command-line flags in the text and their statistical
thresholds in the figures, so the two channels never describe the same key and
there is nothing to disagree about. These cases are therefore the only evidence
that the state works at all, and they are written from the mislabelling an
auditor actually exists to catch -- a figure saying one annotation version while
the methods section says another.
"""

from __future__ import annotations

from reprolens.extraction.checklist import Checklist, Parameter, Software
from reprolens.extraction.merge import (
    CONFLICTING,
    CORROBORATED,
    CORROBORATED_BY_OCR,
    FIGURE_ONLY,
    MISFILED,
    merge,
)
from reprolens.extraction.schema import FigureContents


def contents(**fields) -> FigureContents:
    return FigureContents.model_validate({"figure_type": "workflow"} | fields)


def checklist(parameters=(), software=()) -> Checklist:
    return Checklist(software=list(software), parameters=list(parameters), commands=[])


def pinned(name: str, version: str) -> Software:
    return Software(
        name=name,
        kind="pipeline",
        specificity="pinned",
        version=version,
        sections=["methods"],
    )


class TestTheThreeStates:
    def test_a_value_the_text_repeats_is_corroborated(self):
        result = merge(
            [("fig1", contents(tools_named=["STAR"]))],
            "We aligned reads with STAR.",
            checklist(),
        )
        assert [c.status for c in result.claims] == [CORROBORATED]

    def test_a_value_the_text_never_mentions_is_figure_only(self):
        result = merge(
            [("fig1", contents(tools_named=["Bowtie2"]))],
            "We aligned reads with STAR.",
            checklist(),
        )
        assert [c.status for c in result.claims] == [FIGURE_ONLY]
        assert result.conflicts == []

    def test_typography_does_not_decide_corroboration(self):
        # A model renders what it sees; the document may hyphenate or wrap it.
        result = merge(
            [("fig1", contents(workflow_steps=["Multi-Layer Perceptron"]))],
            "a multi-layer   perceptron was trained",
            checklist(),
        )
        assert result.claims[0].status == CORROBORATED

    def test_prose_fields_are_never_merged(self):
        # MATES figure 2's notes field invented "MATES (Mouse Atlas of
        # Transposable Elements)". Prose has no key to corroborate and no value
        # to compare, so it must not reach the merge at all.
        result = merge(
            [
                (
                    "fig1",
                    contents(
                        notes="MATES (Mouse Atlas of Transposable Elements)",
                        axis_labels=["log2 fold change"],
                        sample_labels=["MEL1"],
                    ),
                )
            ],
            "",
            checklist(),
        )
        assert result.claims == []


class TestConflicts:
    """The state the merge exists for, and the one no real paper here exercises."""

    def test_a_version_the_figure_and_text_disagree_about(self):
        result = merge(
            [("fig1", contents(versions_visible=["GENCODE v38"]))],
            "annotations from GENCODE v41",
            checklist(software=[pinned("GENCODE", "41")]),
        )
        assert len(result.conflicts) == 1
        conflict = result.conflicts[0]
        assert conflict.key == "GENCODE"
        assert conflict.figure_value == "38"
        assert conflict.text_value == "41"
        assert "the figure reads '38'" in conflict.evidence
        assert [c.status for c in result.claims] == [CONFLICTING]

    def test_a_parameter_the_figure_and_text_disagree_about(self):
        result = merge(
            [("fig1", contents(parameters_visible=["FDR = 0.1"]))],
            "controlling the FDR",
            checklist(parameters=[Parameter(flag="FDR", value="0.05", evidence="")]),
        )
        assert len(result.conflicts) == 1
        assert result.conflicts[0].figure_value == "0.1"
        assert result.conflicts[0].text_value == "0.05"

    def test_agreement_on_the_same_key_is_not_a_conflict(self):
        result = merge(
            [("fig1", contents(versions_visible=["GENCODE v41"]))],
            "annotations from GENCODE v41",
            checklist(software=[pinned("GENCODE", "41")]),
        )
        assert result.conflicts == []
        assert result.claims[0].status == CORROBORATED

    def test_a_key_the_text_never_pins_down_is_not_a_conflict(self):
        # Silence is not disagreement. The paper naming no version cannot
        # contradict a figure that shows one.
        result = merge(
            [("fig1", contents(versions_visible=["GENCODE v38"]))],
            "annotations from GENCODE",
            checklist(
                software=[
                    Software(
                        name="GENCODE",
                        kind="annotation",
                        specificity="named_only",
                        sections=["methods"],
                    )
                ]
            ),
        )
        assert result.conflicts == []

    def test_a_flag_written_with_or_without_dashes_is_the_same_key(self):
        result = merge(
            [("fig1", contents(parameters_visible=["outFilterMultimapNmax = 10"]))],
            "",
            checklist(
                parameters=[Parameter(flag="--outFilterMultimapNmax", value="1", evidence="")]
            ),
        )
        assert len(result.conflicts) == 1
        assert result.conflicts[0].text_value == "1"

    def test_the_disjoint_namespaces_that_produced_no_conflicts_in_practice(self):
        # Exactly the real case: the text holds STAR flags, the figure holds a
        # statistical threshold, and they share no key. Zero conflicts here is
        # the correct answer, not a detector that failed to fire.
        result = merge(
            [("fig1", contents(parameters_visible=["FDR = 0.1"]))],
            "significance was assessed at FDR = 0.1 throughout",
            checklist(
                parameters=[Parameter(flag="--soloType", value="CB_UMI_Simple", evidence="")]
            ),
        )
        assert result.conflicts == []
        assert result.claims[0].status == CORROBORATED


class TestVocabularyCandidates:
    def test_a_tool_the_text_confirms_but_the_vocabulary_lacks_is_surfaced(self):
        result = merge(
            [("fig3", contents(tools_named=["Airpart"]))],
            "we compared against Airpart and scDALI",
            checklist(),
        )
        assert [d.name for d in result.discoveries] == ["Airpart"]

    def test_a_tool_already_in_the_vocabulary_is_not_a_candidate(self):
        result = merge(
            [("fig3", contents(tools_named=["STAR"]))],
            "aligned with STAR",
            checklist(),
        )
        assert result.discoveries == []

    def test_an_uncorroborated_name_is_never_a_candidate(self):
        # The vocabulary must not grow on the strength of one unverifiable
        # reading; that is how an invented tool becomes a permanent pattern.
        result = merge(
            [("fig3", contents(tools_named=["Airpart"]))],
            "no mention of it anywhere",
            checklist(),
        )
        assert result.discoveries == []
        assert result.claims[0].status == FIGURE_ONLY

    def test_one_entry_per_name_however_many_figures_name_it(self):
        reading = contents(tools_named=["Airpart"])
        result = merge(
            [("fig1", reading), ("fig2", reading), ("fig3", reading)],
            "Airpart",
            checklist(),
        )
        assert [d.name for d in result.discoveries] == ["Airpart"]

    def test_candidates_are_ordered_rarest_first(self):
        result = merge(
            [("fig1", contents(tools_named=["Airpart", "Gene"]))],
            "Airpart " + ("Gene " * 20),
            checklist(),
        )
        assert [d.name for d in result.discoveries] == ["Airpart", "Gene"]
        assert result.discoveries[0].text_mentions < result.discoveries[1].text_mentions


class TestAgreement:
    def test_nothing_checkable_is_no_measurement_rather_than_zero(self):
        result = merge([("fig1", contents())], "some text", checklist())
        assert result.agreement is None

    def test_agreement_is_the_corroborated_share(self):
        result = merge(
            [("fig1", contents(tools_named=["STAR", "Bowtie2"]))],
            "aligned with STAR",
            checklist(),
        )
        assert result.agreement == 0.5

    def test_corroborated_values_are_deduplicated_in_order(self):
        reading = contents(workflow_steps=["Alignment", "Clustering", "Alignment"])
        result = merge([("fig1", reading)], "Alignment then Clustering", checklist())
        assert result.corroborated_values("workflow_steps") == ["Alignment", "Clustering"]

    def test_the_summary_counts_every_state(self):
        result = merge(
            [("fig1", contents(tools_named=["STAR", "Bowtie2"], versions_visible=["GENCODE v38"]))],
            "aligned with STAR using GENCODE",
            checklist(software=[pinned("GENCODE", "41")]),
        )
        summary = result.to_dict()["summary"]
        assert summary == {
            "corroborated": 1,
            "corroborated_by_ocr": 0,
            "figure_only": 1,
            "conflicting": 1,
            "misfiled": 0,
            "agreement": summary["agreement"],
        }
        assert result.to_dict()["figures_read"] == 1


class TestMisfiledValues:
    """Right about the value, wrong about what kind of thing it is.

    The state exists because corroboration alone gets this case backwards. Every
    one of these really is in the paper's text, so text agreement promotes it --
    and a gene name confirmed as a database accession is a dataset the paper
    never deposited, asserted by the audit with two channels behind it.
    """

    def test_a_gene_name_offered_as_an_accession_is_misfiled_not_corroborated(self):
        result = merge(
            [("fig5", contents(accessions_visible=["Meg3"]))],
            "imprinted expression of Meg3 was measured",
            checklist(),
        )
        assert [c.status for c in result.claims] == [MISFILED]

    def test_a_genomic_locus_offered_as_an_accession_is_misfiled(self):
        # MATES figure 4, read correctly: that is exactly how these papers write
        # a transposable-element locus.
        result = merge(
            [("fig4", contents(accessions_visible=["chr13|89384655|89385083"]))],
            "chr13|89384655|89385083",
            checklist(),
        )
        assert [c.status for c in result.claims] == [MISFILED]

    def test_a_real_accession_still_corroborates(self):
        result = merge(
            [("fig1", contents(accessions_visible=["GSE212945"]))],
            "data are available under GSE212945",
            checklist(),
        )
        assert [c.status for c in result.claims] == [CORROBORATED]

    def test_only_the_accession_field_is_shape_checked(self):
        # A pipeline step is prose and has no shape to fail.
        result = merge(
            [("fig1", contents(workflow_steps=["Meg3"]))],
            "Meg3",
            checklist(),
        )
        assert [c.status for c in result.claims] == [CORROBORATED]

    def test_a_misfiled_value_is_not_counted_against_agreement(self):
        # Agreement measures whether the text confirms what the figure said. A
        # value excluded before that question is asked is no measurement, and
        # counting it as a failure would make a correct reading look like a
        # disagreement between the channels.
        result = merge(
            [("fig1", contents(accessions_visible=["Meg3", "GSE212945"]))],
            "Meg3 and GSE212945",
            checklist(),
        )
        assert result.agreement == 1.0
        assert result.to_dict()["summary"]["misfiled"] == 1


class TestOcrAsASecondWitness:
    """The text layer cannot see inside a figure, so its silence proves nothing.

    Found on ALIGNN. Its architecture diagrams are labelled
    "EdgeGatedGraphConv", "SiLU" and "Sum"; the PDF's text layer contains none
    of those strings, so every one was filed as figure_only and discarded. OCR
    over the same pages reads all three. Two different models over the same
    pixels is real agreement, and treating the text layer's silence as evidence
    against an in-figure reading was asking the wrong reader.
    """

    def test_a_value_only_ocr_confirms_gets_its_own_state(self):
        result = merge(
            [("fig2", contents(tools_named=["EdgeGatedGraphConv"]))],
            "the model uses gated convolutions",
            checklist(),
            ocr_text="Node features EdgeGatedGraphConv SiLU Sum",
        )
        assert [c.status for c in result.claims] == [CORROBORATED_BY_OCR]

    def test_the_text_layer_still_wins_when_it_has_the_value(self):
        # Provenance has to stay legible: a value the document itself asserts is
        # stronger evidence than one only a second reading of the pixels has.
        result = merge(
            [("fig2", contents(tools_named=["SiLU"]))],
            "we use the SiLU activation",
            checklist(),
            ocr_text="SiLU",
        )
        assert [c.status for c in result.claims] == [CORROBORATED]

    def test_a_value_neither_reader_confirms_is_still_figure_only(self):
        result = merge(
            [("fig2", contents(tools_named=["Bowtie2"]))],
            "nothing like it here",
            checklist(),
            ocr_text="nor here",
        )
        assert [c.status for c in result.claims] == [FIGURE_ONLY]

    def test_without_ocr_text_nothing_changes(self):
        # The cross-check is opt-in and costly, so the default path must behave
        # exactly as it did before this state existed.
        without = merge([("fig2", contents(tools_named=["SiLU"]))], "no mention", checklist())
        assert [c.status for c in without.claims] == [FIGURE_ONLY]

    def test_an_ocr_confirmed_value_counts_toward_agreement(self):
        result = merge(
            [("fig2", contents(tools_named=["SiLU", "Nonexistent"]))],
            "",
            checklist(),
            ocr_text="SiLU",
        )
        assert result.agreement == 0.5
        assert result.to_dict()["summary"]["corroborated_by_ocr"] == 1
