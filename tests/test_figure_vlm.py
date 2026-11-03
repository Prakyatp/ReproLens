"""Corroboration of figure readings against the text channel.

The VLM channel cannot verify itself, so this is the only thing standing between
a plausible invention and the findings list. Tested without touching the API.
"""

from __future__ import annotations

from reprolens.extraction.schema import FigureContents
from reprolens.extraction.vlm import corroborate


def contents(**kwargs) -> FigureContents:
    return FigureContents(figure_type="workflow", **kwargs)


def test_identifier_present_in_text_is_corroborated():
    got, unverified = corroborate(
        contents(accessions_visible=["GSE212945"]),
        "Data are deposited under GSE212945.",
    )
    assert got == ["accessions_visible:GSE212945"]
    assert unverified == []


def test_identifier_absent_from_text_is_flagged_not_dropped():
    # An identifier visible only in a figure may be real. It is reported as
    # unverified rather than discarded -- the audit says what evidence stands
    # behind a finding, it does not throw the weaker kind away.
    got, unverified = corroborate(
        contents(accessions_visible=["GSE999999"]),
        "Data are deposited under GSE212945.",
    )
    assert got == []
    assert unverified == ["accessions_visible:GSE999999"]


def test_comparison_ignores_whitespace_and_case():
    # The model renders what it sees; it does not reproduce the document's
    # typography, so "GENCODE v38" must match "GENCODEv38" across a line break.
    got, unverified = corroborate(
        contents(versions_visible=["GENCODE v38"]),
        "annotated with GENCODE\nv38 throughout",
    )
    assert got == ["versions_visible:GENCODE v38"]
    assert unverified == []


def test_tools_and_versions_are_checked_too():
    got, unverified = corroborate(
        contents(tools_named=["STARsolo", "Invented"], versions_visible=["v2.8.2"]),
        "aligned with STARsolo using SeqKit v2.8.2",
    )
    assert sorted(got) == ["tools_named:STARsolo", "versions_visible:v2.8.2"]
    assert unverified == ["tools_named:Invented"]


def test_empty_reading_produces_nothing_to_check():
    assert corroborate(contents(), "any text") == ([], [])


class TestBackendSeam:
    """Both backends answer the same schema, which is what makes them comparable."""

    def test_known_backends_resolve(self):
        from reprolens.extraction.vlm import get_backend

        assert get_backend("ollama").name == "ollama"
        assert get_backend("anthropic").name == "anthropic"

    def test_unknown_backend_names_the_alternatives(self):
        import pytest

        from reprolens.extraction.vlm import get_backend

        with pytest.raises(ValueError, match="ollama"):
            get_backend("gpt-vision")

    def test_model_override_is_recorded(self):
        # Which model produced a reading is part of the reading: on this channel
        # the answer is not reproducible without it.
        from reprolens.extraction.vlm import get_backend

        assert get_backend("ollama", "minicpm-v:8b").model == "minicpm-v:8b"

    def test_schema_is_expressible_as_json_schema(self):
        # Ollama constrains generation with this; if it stops being expressible,
        # local structured output silently degrades to free text.
        schema = FigureContents.model_json_schema()
        assert schema["type"] == "object"
        assert "accessions_visible" in schema["properties"]

    def test_empty_lists_are_valid(self):
        # The prompt instructs empty over guess, so empty must parse.
        assert FigureContents(figure_type="plot").accessions_visible == []
