"""Regressions for text assembly. Each case here was a real bug found on the
two benchmark papers, and each one is silent -- it corrupts an identifier
without raising anything.
"""

from __future__ import annotations

from reprolens.documents.pdf_text import _render
from reprolens.documents.textrepair import rejoin_broken_urls


def span(text: str, *, superscript: bool = False, size: float = 8.22) -> dict:
    return {"text": text, "flags": 5 if superscript else 4, "size": size}


def rendered(*spans: dict) -> str:
    return _render(list(spans))[0]


class TestCitationMarkers:
    def test_drops_superscript_reference_number(self):
        # MATES p20: "github.com/mcgilldinglab/MATES" + sup "90" -> ".../MATES90"
        url = "github.com/mcgilldinglab/MATES"
        assert rendered(span(url), span("90", superscript=True)) == url

    def test_drops_superscript_range_and_list(self):
        assert rendered(span("AdamW"), span("4,5", superscript=True)) == "AdamW"
        assert rendered(span("AdamW"), span("7-9", superscript=True)) == "AdamW"

    def test_keeps_non_superscript_digits(self):
        # A repository may legitimately end in digits (scNanoGPS2, MATES2).
        assert rendered(span("MATES"), span("90")) == "MATES90"

    def test_keeps_superscript_that_is_not_a_number(self):
        # A footnote dagger is content, not a citation marker.
        assert rendered(span("the 1"), span("st", superscript=True)) == "the 1st"
        assert rendered(span("author"), span("\u2020", superscript=True)) == "author\u2020"

    def test_a_name_ending_in_a_digit_still_takes_a_marker(self):
        # The reason the rule cannot be "it follows a digit". All three are
        # citations in their papers: QM9 in ALIGNN, CD74 and Aldh18a1 in MATES.
        for name in ("QM9", "CD74", "Aldh18a1"):
            assert rendered(span(f"and {name}"), span("46", superscript=True)) == f"and {name}"


class TestExponents:
    """The other kind of superscript, and 65 of them across the three PDFs.

    Dropping every digit-shaped superscript deleted the exponent from every
    p-value and every scientific-notation number in all three papers: ASPEN
    reported "p < 2.22 x 10" for 2.22e-16, MATES has eight more of the same
    shape, and ALIGNN's weight decay of 1e-5 read as a weight decay of 10.
    """

    def test_a_negative_exponent_survives(self):
        assert rendered(span("p < 2.22 \u00d7 10"), span("\u201316", superscript=True)) == (
            "p < 2.22 \u00d7 10^-16"
        )
        assert rendered(span("of 10"), span("-5", superscript=True)) == "of 10^-5"

    def test_a_positive_exponent_survives_on_a_bare_number(self):
        assert rendered(span("10"), span("21 ", superscript=True)) == "10^21 "

    def test_a_negative_exponent_survives_on_a_unit(self):
        # ALIGNN writes "10**21 Vm**-2". The unit's exponent follows a letter,
        # so the leading sign is the only thing that identifies it.
        assert rendered(span("Vm"), span("-2", superscript=True)) == "Vm^-2"

    def test_the_trailing_space_is_kept_as_a_separator(self):
        assert rendered(span("10"), span("21 ", superscript=True), span("Vm")) == "10^21 Vm"


class TestUrlRejoining:
    def test_joins_break_after_mid_url_character(self):
        # MATES p20: the query string wraps right before its accession.
        lines = ["dataset (GSE114952, https://www.ncbi.nlm.nih.gov/", "geo/query/acc.cgi?acc=X"]
        assert "nih.gov/geo/query" in rejoin_broken_urls(lines)

    def test_joins_break_before_character_that_cannot_start_a_word(self):
        lines = ["available at https://www", ".ncbi.nlm.nih.gov/geo/"]
        assert "https://www.ncbi.nlm.nih.gov/geo/" in rejoin_broken_urls(lines)

    def test_does_not_glue_running_header_onto_title(self):
        # MATES p1. Line geometry gets this wrong: the DOI line defines the
        # block's right edge, so it trivially "fills" the column.
        lines = ["https://doi.org/10.1038/s41467-024-53114-7", "MATES: a deep learning-based model"]
        assert "53114-7MATES" not in rejoin_broken_urls(lines)

    def test_does_not_glue_completed_url_onto_next_sentence(self):
        lines = ["Code is at https://github.com/org/repo", "The results show that"]
        joined = rejoin_broken_urls(lines)
        assert "repoThe" not in joined

    def test_does_not_glue_reference_number_onto_a_doi(self):
        # Found via OCR of MATES p22: the running-header DOI ends a line and the
        # reference list's next entry opens with "67.". Both are digits, so the
        # continuation rule alone accepts it and invents "...53114-767".
        lines = ["https://doi.org/10.1038/s41467-024-53114-7", "67. Winkler, A. M., et al."]
        assert "53114-767" not in rejoin_broken_urls(lines)

    def test_still_joins_a_genuine_numeric_continuation(self):
        # The same shape, but the digits continue a path rather than open a list.
        lines = ["Nat. Biotechnol. https://doi.org/10.", "1038/s41587-023-01767-y (2023)."]
        assert "10.1038/s41587-023-01767-y" in rejoin_broken_urls(lines)

    def test_leaves_hyphenated_prose_alone(self):
        lines = ["we used a two-", "column layout"]
        assert rejoin_broken_urls(lines) == "we used a two-\ncolumn layout"


class TestTheThreeEncodings:
    """One normal form out of three ways publishers set the same number.

    A reader comparing two p-values should not have to know which publisher
    raised which span. All three shapes below are real: ALIGNN, MATES and
    ASPEN respectively, and the middle two were both dropping their digits.
    """

    def test_sign_and_digits_in_one_raised_span(self):
        assert rendered(span("of 10"), span("-5", superscript=True)) == "of 10^-5"

    def test_sign_and_digits_in_two_raised_spans(self):
        # MATES p4: "P < 1 x 10" then raised "−" then raised "6". The second
        # span is attached to a sign rather than to a number, which is what
        # dropped it.
        assert rendered(
            span("P < 1 × 10"),
            span("−", superscript=True),
            span("6", superscript=True),
        ) == "P < 1 × 10^-6"

    def test_sign_as_an_ordinary_glyph_and_digits_raised(self):
        # ASPEN p2 sets the minus as a ⁻ glyph in an unraised span and raises
        # only "16". The sign is normalised rather than left beside the caret.
        assert rendered(
            span("p < 2.22 × 10 ⁻"), span("16", superscript=True)
        ) == "p < 2.22 × 10^-16"

    def test_a_citation_marker_after_a_sign_is_still_a_marker(self):
        # The sign-stripping must not turn a hyphenated name into a number.
        assert rendered(span("Aldh18a1-"), span("57", superscript=True)) == "Aldh18a1-"

    def test_a_bare_plus_on_a_cell_marker_is_not_an_exponent(self):
        # ASPEN writes "CD8+ T cells" with the plus raised, twice. A sign with
        # no digits is a power only where it is attached to a number, so this
        # one is kept as the phenotype it is rather than opening an exponent.
        assert rendered(span("in CD8"), span("+", superscript=True)) == "in CD8+"

    def test_a_split_citation_range_is_still_dropped(self):
        # MATES writes "heterogeneity" + raised "1" + raised "–" + raised "3"
        # for references 1 to 3. Nothing here is attached to a number.
        assert rendered(
            span("heterogeneity"),
            span("1", superscript=True),
            span("–", superscript=True),
            span("3", superscript=True),
        ) == "heterogeneity"
