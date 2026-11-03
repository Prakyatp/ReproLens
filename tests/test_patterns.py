"""Identifier patterns, including the normalizations that have to run first."""

from __future__ import annotations

from reprolens.discovery.links import extract
from reprolens.discovery.patterns import normalize, normalize_with_offsets
from reprolens.documents.base import PageText
from reprolens.extraction.checklist import find_names


def findings(text: str, links: list[str] | None = None) -> dict[str, set[str]]:
    page = PageText(page=1, text=text, links=links or [])
    out: dict[str, set[str]] = {}
    for finding in extract([page]):
        out.setdefault(finding.kind, set()).add(finding.value)
    return out


class TestNormalization:
    def test_rejoins_hyphenated_line_break(self):
        assert "LocusMasterTE" in normalize("LocusMas-\nterTE")

    def test_folds_unicode_dashes_to_ascii(self):
        assert normalize("GSE–123") == "GSE-123"

    def test_strips_soft_hyphen_and_nbsp(self):
        assert normalize("GSE­212945") == "GSE212945"
        assert normalize("a b") == "a b"


class TestAccessions:
    def test_finds_geo_series(self):
        assert findings("deposited under GSE212945.")["geo_series"] == {"GSE212945"}

    def test_tolerates_typeset_space_inside_accession(self):
        assert findings("under GSE 212945 and")["geo_series"] == {"GSE212945"}

    def test_distinguishes_series_from_sample(self):
        got = findings("GSE158450 contains GSM4800803")
        assert got["geo_series"] == {"GSE158450"}
        assert got["geo_sample"] == {"GSM4800803"}

    def test_finds_bioproject_and_sra(self):
        got = findings("PRJNA123456 with runs SRR12345678")
        assert got["bioproject"] == {"PRJNA123456"}
        assert got["sra_run"] == {"SRR12345678"}


class TestRepositoriesAndDois:
    def test_finds_github_without_scheme(self):
        got = findings("code at github.com/mcgilldinglab/MATES.")
        assert got["github"] == {"github.com/mcgilldinglab/MATES"}

    def test_strips_trailing_sentence_punctuation_from_doi(self):
        assert findings("see 10.1038/s41467-024-53114-7.")["doi"] == {"10.1038/s41467-024-53114-7"}

    def test_does_not_double_report_url_and_repo(self):
        # A repo URL is one finding, not both a `github` and a `url`.
        got = findings("at https://github.com/org/repo for details")
        assert got.get("url") is None
        assert got["github"] == {"github.com/org/repo"}

    def test_reads_identifiers_out_of_link_annotations(self):
        # Journals truncate the displayed URL while the annotation keeps the
        # full target, so the annotation channel is not a duplicate.
        got = findings(
            "see the repository",
            links=["https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE225377"],
        )
        assert got["geo_series"] == {"GSE225377"}


class TestLigatures:
    """A PDF text layer hands back "fi" as one character.

    MATES carries 514 of U+FB01 and 42 of U+FB02, so before these expanded, the
    word "quantification" appeared in its normalized text zero times out of 177
    and every vocabulary term containing fi, fl or ff was unmatchable. The
    failure is silent in the worst way: the audit reports that the paper never
    mentioned the tool.
    """

    def test_each_ligature_expands_to_its_letters(self):
        assert normalize("quanti\ufb01cation") == "quantification"
        assert normalize("Next\ufb02ow") == "Nextflow"
        assert normalize("Cu\ufb00links") == "Cufflinks"
        assert normalize("di\ufb03cult") == "difficult"
        assert normalize("sha\ufb04e") == "shaffle"

    def test_a_vocabulary_term_survives_the_typesetter(self):
        # Nextflow and TensorFlow are both in the software vocabulary and both
        # carry an fl. A Nature-family PDF would have hidden either one.
        for name in ("Nextflow", "TensorFlow", "clusterProfiler"):
            typeset = name.replace("fl", "\ufb02").replace("fi", "\ufb01")
            assert find_names(normalize(typeset)) == find_names(name)

    def test_an_offset_still_lands_on_the_ligature_in_the_original(self):
        # Expansion is the one normalization step that makes the string longer,
        # so it drifts offsets the opposite way from dehyphenation. A match
        # position has to map back onto the single source character.
        text = "we used Next\ufb02ow then GSE212945"
        normalized, offsets = normalize_with_offsets(text)
        position = normalized.index("GSE212945")
        assert text[offsets[position] : offsets[position] + 9] == "GSE212945"

    def test_expansion_does_not_disturb_the_plain_normalizer(self):
        for sample in ["quanti\ufb01cation", "a\ufb01b", "no ligature here", ""]:
            assert normalize_with_offsets(sample)[0] == normalize(sample)
