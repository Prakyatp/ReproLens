"""Regressions for text assembly. Each case here was a real bug found on the
two benchmark papers, and each one is silent -- it corrupts an identifier
without raising anything.
"""

from __future__ import annotations

from reprolens.documents.pdf_text import _is_citation_marker
from reprolens.documents.textrepair import rejoin_broken_urls


def span(text: str, *, superscript: bool = False, size: float = 8.22) -> dict:
    return {"text": text, "flags": 5 if superscript else 4, "size": size}


class TestCitationMarkers:
    def test_drops_superscript_reference_number(self):
        # MATES p20: "github.com/mcgilldinglab/MATES" + sup "90" -> ".../MATES90"
        assert _is_citation_marker(span("90", superscript=True))

    def test_drops_superscript_range_and_list(self):
        assert _is_citation_marker(span("4,5", superscript=True))
        assert _is_citation_marker(span("7-9", superscript=True))

    def test_keeps_non_superscript_digits(self):
        # A repository may legitimately end in digits (scNanoGPS2, MATES2).
        assert not _is_citation_marker(span("90"))

    def test_keeps_superscript_that_is_not_a_number(self):
        # Exponents and footnote daggers are content, not citation markers.
        assert not _is_citation_marker(span("st", superscript=True))
        assert not _is_citation_marker(span("†", superscript=True))


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
