"""Guards on the local-model path.

Every case here is a real failure observed running Qwen2.5-VL 7B over MATES's
figures, and all three are silent -- they produce well-formed output that is
wrong, rather than raising.
"""

from __future__ import annotations

from reprolens.extraction.schema import FigureContents
from reprolens.extraction.vlm import shape_errors


def contents(**kwargs) -> FigureContents:
    return FigureContents(figure_type="workflow", **kwargs)


class TestArrayBounds:
    """Ollama compiles this schema into a generation grammar, so an unbounded
    array is a licence to emit an infinite one. Given a dense five-panel figure,
    the model emitted "TE Region" until it hit the token ceiling.
    """

    def test_every_list_field_is_bounded(self):
        schema = FigureContents.model_json_schema()
        arrays = {
            name: spec for name, spec in schema["properties"].items() if spec.get("type") == "array"
        }
        assert arrays, "expected list fields in the schema"
        unbounded = [name for name, spec in arrays.items() if "maxItems" not in spec]
        assert not unbounded, f"unbounded arrays let a local model loop: {unbounded}"

    def test_notes_is_bounded_too(self):
        assert FigureContents.model_json_schema()["properties"]["notes"].get("maxLength")


class TestDeduplication:
    """A bound stops a runaway loop but not a short one; figures legitimately
    repeat labels across panels.
    """

    def test_repeats_collapse_preserving_order(self):
        got = contents(workflow_steps=["FASTQ", "STAR", "FASTQ", "DESeq2"]).deduplicated()
        assert got.workflow_steps == ["FASTQ", "STAR", "DESeq2"]

    def test_whitespace_variants_are_one_value(self):
        got = contents(tools_named=["STARsolo", "STARsolo "]).deduplicated()
        assert got.tools_named == ["STARsolo"]

    def test_leaves_distinct_values_alone(self):
        got = contents(tools_named=["scTE", "SoloTE", "MATES"]).deduplicated()
        assert got.tools_named == ["scTE", "SoloTE", "MATES"]


class TestAccessionShape:
    """The model's dominant error is misfiling, not invention: it read
    "chr13|89384655|89385083" off figure 4 correctly and called it an accession.
    """

    def test_genomic_locus_is_not_an_accession(self):
        errors = shape_errors(contents(accessions_visible=["chr13|89384655|89385083"]))
        assert errors == ["accessions_visible:chr13|89384655|89385083"]

    def test_locus_with_te_family_suffix_is_not_an_accession(self):
        assert shape_errors(contents(accessions_visible=["chr4|139943623|139943728|MamRep434"]))

    def test_real_accessions_pass(self):
        assert shape_errors(contents(accessions_visible=["GSE212945", "SRR12345678"])) == []

    def test_partial_match_is_rejected(self):
        # fullmatch, not search: "GSE212945 and more" must not pass as one
        # accession just because a valid one is embedded in it.
        assert shape_errors(contents(accessions_visible=["see GSE212945 for data"]))

    def test_empty_field_is_not_an_error(self):
        assert shape_errors(contents()) == []
