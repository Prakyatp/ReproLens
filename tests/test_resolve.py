"""Regressions for dataset resolution.

This is the first part of the audit that leaves the document, so it is also the
first that can be wrong in a new way: by reporting silence from a registry as
absence in a paper. Most of what follows is about keeping those apart.

The network is never touched here. ``_get`` is replaced with canned payloads
taken from real NCBI replies, which is the only way to test the paths that
matter -- an absent accession, an unreachable registry -- without depending on
them happening.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from reprolens.discovery import resolve
from reprolens.discovery.resolve import (
    NOT_FOUND,
    PUBLIC,
    RESTRICTED,
    UNCHECKED,
    Cache,
    Resolution,
    resolve_all,
)

# A real esummary reply for GSE212945, trimmed to the fields used.
GSE_PRESENT = {
    "result": {"200212945": {"accession": "GSE212945", "title": "High throughput single cell"}}
}
# What the registry returns for a UID that does not exist: the envelope is
# there, the record is not. Reading this as success is the obvious bug.
GSE_ABSENT = {"result": {"uids": []}}


@pytest.fixture
def no_cache(tmp_path):
    return Cache(tmp_path / "accessions.json")


def canned(payload, record=None):
    def _get(endpoint, params):
        record.append((endpoint, params)) if record is not None else None
        return payload

    return _get


class TestTheGeoUid:
    """The accession-to-UID rule, verified against five real records.

    A GEO UID is the record-type digit then the accession's digits padded to
    eight. Getting the padding wrong is silent: the lookup returns an empty
    record and the accession reads as absent.
    """

    @pytest.mark.parametrize(
        ("accession", "kind", "uid"),
        [
            ("GSE212945", "geo_series", "200212945"),
            ("GSE11495", "geo_series", "200011495"),
            ("GSE1", "geo_series", "200000001"),
            ("GSM4800803", "geo_sample", "304800803"),
            ("GPL24247", "geo_platform", "100024247"),
        ],
    )
    def test_uid_is_the_type_digit_then_eight_padded_digits(
        self, accession, kind, uid, monkeypatch
    ):
        seen = []
        monkeypatch.setattr(
            resolve,
            "_get",
            canned({"result": {uid: {"accession": accession, "title": "t"}}}, seen),
        )
        out = resolve._lookup(kind, accession)
        assert out.status == PUBLIC
        assert seen[0][1]["id"] == uid

    def test_an_accession_too_long_to_be_a_record_is_unchecked_not_absent(self, monkeypatch):
        # Nine digits cannot be padded into a UID, so no lookup is possible.
        # Calling that "absent" claims the registry answered when it was never
        # asked. Eight digits is still askable, and its empty reply really is
        # an answer -- the test below holds that line.
        def never(endpoint, params):
            raise AssertionError("an unaskable accession must not be looked up")

        monkeypatch.setattr(resolve, "_get", never)
        out = resolve._lookup("geo_series", "GSE123456789")
        assert out.status == UNCHECKED
        assert "not shaped like a GEO record" in out.detail

    def test_the_longest_askable_accession_is_still_asked(self, monkeypatch):
        monkeypatch.setattr(resolve, "_get", canned(GSE_ABSENT))
        out = resolve._lookup("geo_series", "GSE99999999")
        assert out.status == NOT_FOUND, "eight digits fits a UID, so the reply is an answer"


class TestWhatTheRegistrySaid:
    def test_a_matching_accession_is_public_and_carries_its_title(self, monkeypatch):
        monkeypatch.setattr(resolve, "_get", canned(GSE_PRESENT))
        out = resolve._lookup("geo_series", "GSE212945")
        assert out.status == PUBLIC
        assert out.title == "High throughput single cell"
        assert out.confirmed and out.answered

    def test_an_empty_record_is_not_found(self, monkeypatch):
        monkeypatch.setattr(resolve, "_get", canned(GSE_ABSENT))
        out = resolve._lookup("geo_series", "GSE999998")
        assert out.status == NOT_FOUND
        assert out.answered and not out.confirmed

    def test_a_record_whose_accession_differs_is_not_a_match(self, monkeypatch):
        # The reason this compares accessions instead of counting hits: a field
        # search for GSE84465 matches 3591 records, and GSE1 matches 40.
        monkeypatch.setattr(
            resolve,
            "_get",
            canned({"result": {"200212945": {"accession": "GSE999999", "title": "other"}}}),
        )
        assert resolve._lookup("geo_series", "GSE212945").status == NOT_FOUND

    def test_a_searchable_kind_uses_the_hit_count(self, monkeypatch):
        monkeypatch.setattr(resolve, "_get", canned({"esearchresult": {"count": "1"}}))
        assert resolve._lookup("sra_run", "SRR13450127").status == PUBLIC
        monkeypatch.setattr(resolve, "_get", canned({"esearchresult": {"count": "0"}}))
        assert resolve._lookup("sra_run", "SRR99999999999").status == NOT_FOUND


class TestSilenceIsNotAbsence:
    """The distinction the whole module exists to preserve."""

    def test_an_unreachable_registry_is_unchecked(self, monkeypatch):
        def boom(endpoint, params):
            raise urllib.error.URLError("no route to host")

        monkeypatch.setattr(resolve, "_get", boom)
        out = resolve._lookup("geo_series", "GSE212945")
        assert out.status == UNCHECKED
        assert not out.answered
        assert "unreachable" in out.detail

    def test_an_unusable_reply_is_unchecked(self, monkeypatch):
        def garbage(endpoint, params):
            raise json.JSONDecodeError("nope", "", 0)

        monkeypatch.setattr(resolve, "_get", garbage)
        assert resolve._lookup("geo_series", "GSE212945").status == UNCHECKED

    def test_a_kind_with_no_registry_is_unchecked(self, no_cache):
        out = resolve_all([("zenodo", "10.5281/zenodo.123")], cache=no_cache)
        assert [e.status for e in out.entries] == [UNCHECKED]
        assert "no registry known" in out.entries[0].detail

    def test_switching_lookups_off_marks_the_run_not_the_paper(self):
        out = resolve_all([("geo_series", "GSE212945")], allow_network=False)
        assert out.attempted is False
        assert [e.status for e in out.entries] == [UNCHECKED]
        assert out.missing == []
        assert "switched off" in out.notes[0]

    def test_a_spent_budget_is_unchecked_rather_than_absent(self, monkeypatch, no_cache):
        monkeypatch.setattr(resolve, "_get", canned(GSE_PRESENT))
        out = resolve_all(
            [("geo_series", "GSE212945"), ("geo_series", "GSE11495")],
            cache=no_cache,
            budget=1,
        )
        statuses = [e.status for e in out.entries]
        assert statuses.count(UNCHECKED) == 1
        assert "budget" in [e.detail for e in out.entries if e.status == UNCHECKED][0]


class TestControlledAccess:
    def test_a_dbgap_accession_is_restricted_without_asking_anyone(self, monkeypatch):
        def never(endpoint, params):
            raise AssertionError("dbGaP must not be looked up")

        monkeypatch.setattr(resolve, "_get", never)
        out = resolve._lookup("dbgap", "phs000424")
        assert out.status == RESTRICTED
        assert out.confirmed and out.answered
        assert "approved data-access request" in out.detail


class TestTheCache:
    def test_an_answer_survives_a_second_run(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(resolve, "_get", canned(GSE_PRESENT, calls))
        path = tmp_path / "a.json"
        resolve_all([("geo_series", "GSE212945")], cache=Cache(path))
        assert len(calls) == 1
        resolve_all([("geo_series", "GSE212945")], cache=Cache(path))
        assert len(calls) == 1, "a cached answer was looked up again"

    def test_a_failure_is_never_cached_as_an_answer(self, tmp_path, monkeypatch):
        # Caching "unchecked" would turn one bad network moment into a
        # permanent gap in every later audit of that paper.
        def boom(endpoint, params):
            raise urllib.error.URLError("down")

        monkeypatch.setattr(resolve, "_get", boom)
        path = tmp_path / "a.json"
        resolve_all([("geo_series", "GSE212945")], cache=Cache(path))
        monkeypatch.setattr(resolve, "_get", canned(GSE_PRESENT))
        out = resolve_all([("geo_series", "GSE212945")], cache=Cache(path))
        assert out.entries[0].status == PUBLIC

    def test_a_corrupt_cache_file_is_ignored_rather_than_fatal(self, tmp_path):
        path = tmp_path / "a.json"
        path.write_text("{not json")
        assert Cache(path).get("GSE212945") is None


class TestNormalization:
    def test_the_same_accession_is_looked_up_once_however_it_was_written(self, monkeypatch):
        calls = []
        monkeypatch.setattr(resolve, "_get", canned(GSE_PRESENT, calls))
        out = resolve_all(
            [
                ("geo_series", "gse212945"),
                ("geo_series", "GSE212945 "),
                ("geo_series", "GSE212945"),
            ],
            cache=Cache(_tmp()),
        )
        assert len(out.entries) == 1
        assert len(calls) == 1


def _tmp():
    import tempfile
    from pathlib import Path

    return Path(tempfile.mkdtemp()) / "a.json"


class TestTheSummary:
    def test_counts_every_state(self):
        out = resolve.Resolutions(
            entries=[
                Resolution("GSE1", "geo_series", PUBLIC),
                Resolution("GSE2", "geo_series", NOT_FOUND),
                Resolution("phs1", "dbgap", RESTRICTED),
                Resolution("GSE3", "geo_series", UNCHECKED),
            ]
        )
        assert out.to_dict()["summary"] == {
            "checked": 3,
            "public": 1,
            "restricted": 1,
            "not_found": 1,
            "unchecked": 1,
        }
        assert [e.accession for e in out.missing] == ["GSE2"]
