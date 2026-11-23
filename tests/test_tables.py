"""Regressions for table extraction from PDF geometry.

Every case is from ALIGNN, the one paper in the corpus with real tables. The
two that cost a pass each are the column-gap measurement and the grid
terminator; both looked right and both silently misread the page.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reprolens.documents.tables import (
    PROSE_WORDS,
    Table,
    Tables,
    _cells,
    _grid_below,
    _is_prose,
    agreement,
    extract,
)

PDF = Path("data/papers/alignn.pdf")
have_pdf = pytest.mark.skipif(not PDF.is_file(), reason="ALIGNN PDF not present")


def word(x0: float, x1: float, text: str) -> tuple[float, float, str]:
    return (x0, x1, text)


class TestColumnSplitting:
    def test_a_gutter_splits_a_row_into_cells(self):
        row = [word(70, 110, "Bandgap"), word(200, 215, "eV"), word(300, 330, "0.99")]
        assert _cells(row) == ["Bandgap", "eV", "0.99"]

    def test_words_of_one_cell_stay_together(self):
        # The space inside "Formation energy" is a few points; a gutter is tens.
        row = [word(70, 120, "Formation"), word(124, 160, "energy"), word(300, 330, "0.86")]
        assert _cells(row) == ["Formation energy", "0.86"]

    def test_the_gap_is_measured_between_words_not_between_their_starts(self):
        # The mistake that reported tables on all 27 pages of a paper that has
        # them on four: comparing start positions makes every long word look
        # like a column break.
        row = [word(70, 190, "hyperparameters"), word(196, 220, "were")]
        assert _cells(row) == ["hyperparameters were"]


class TestGridTermination:
    def test_a_wrapped_cell_does_not_end_the_grid(self):
        rows = [
            (0.0, ["Table 3: caption"]),
            (10.0, ["Property", "Units", "MAD"]),
            (20.0, ["MAE"]),
            (30.0, ["eV(atom)-1"]),
            (40.0, ["Bandgap", "eV", "0.99"]),
        ]
        grid = _grid_below(rows, 0)
        assert len(grid) == 2
        assert grid[-1] == ["Bandgap", "eV", "0.99"]

    def test_two_stacked_wrapped_cells_do_not_end_it_either(self):
        # Counting consecutive single-cell rows looked equivalent and was not:
        # ALIGNN's Table 3 stacks a wrapped heading above a wrapped unit, so a
        # tolerance of two terminated it after the header -- one row of fifteen.
        rows = [
            (0.0, ["Table 3: caption"]),
            (10.0, ["Property", "Units"]),
            (20.0, ["MAE"]),
            (30.0, ["eV(atom)-1"]),
            (40.0, ["Formation"]),
            (50.0, ["Bandgap", "eV"]),
        ]
        assert len(_grid_below(rows, 0)) == 2

    def test_prose_resuming_ends_the_grid(self):
        rows = [
            (0.0, ["Table 1: caption"]),
            (10.0, ["a", "b"]),
            (20.0, ["These hyperparameters were selected through a combination of"]),
            (30.0, ["c", "d"]),
        ]
        assert _grid_below(rows, 0) == [["a", "b"]]

    def test_the_prose_threshold_is_a_word_count(self):
        assert _is_prose(["one two three four five six"])
        assert not _is_prose(["MAE"])
        assert not _is_prose(["eV(atom)-1"])
        assert PROSE_WORDS >= 4


class TestAgreementWithProse:
    def test_numbers_are_not_counted_as_names(self):
        # A table exists to carry values the prose does not repeat, so scoring
        # its numbers against the text would report correct behaviour as
        # disagreement.
        result = Tables(found=[Table("Table 1", "c", 1, [["0.86", "0.14"], ["26.06", "eV"]])])
        assert agreement(result, "no numbers here")["named_values"] <= 1

    def test_a_name_the_prose_repeats_is_counted_as_echoed(self):
        result = Tables(found=[Table("Table 1", "c", 1, [["CGCNN", "SchNet"]])])
        out = agreement(result, "we compare against CGCNN and SchNet throughout")
        assert out["named_values"] == 2
        assert out["named_values_echoed_in_prose"] == 2
        assert out["share_echoed"] == 1.0

    def test_no_names_gives_no_measurement_rather_than_zero(self):
        assert agreement(Tables(), "anything")["share_echoed"] is None


class TestOnTheRealPaper:
    @have_pdf
    def test_every_caption_resolves_to_a_grid(self):
        result = extract(PDF)
        assert result.unparsed == []
        assert len(result.found) == 5

    @have_pdf
    def test_a_known_row_is_read_correctly(self):
        table = next(t for t in extract(PDF).found if t.label == "Table 3")
        rows = [" ".join(r) for r in table.rows]
        assert any(r.startswith("Bandgap eV 0.99") for r in rows)
        assert table.columns == 7

    @have_pdf
    def test_a_non_pdf_input_says_why_rather_than_reporting_none(self):
        result = extract(Path("data/xml/locusmasterte.xml"))
        assert result.found == []
        assert any("needs page geometry" in n for n in result.notes)
