"""Regressions for ``report.md``.

Three of blueprint section 37's prohibitions are about this file, and two of
them are the kind a renderer breaks quietly: dropping provenance from a row, and
omitting an undetermined item because there is no number to put in the column.
Both are tested here rather than left to review.

The renderer reads the audit's own JSON and nothing else, which is what makes
these tests cheap: a report is built from a dict, with no paper, no repository
and no network.
"""

from __future__ import annotations

from reprolens.reporting.markdown import render


def report(**overrides) -> dict:
    """A minimal audit report, shaped exactly as ``audit.py`` writes it."""
    base = {
        "paper_id": "paper",
        "source": "data/papers/paper.pdf",
        "sha256": "abc123def456789a",
        "backend": "pdf_text",
        "generated_at": "2026-10-27T00:00:00+00:00",
        "n_segments": 20,
        "warnings": [],
        "pages": [],
        "findings": [],
        "by_role": {},
        "checklist": {"software": [], "parameters": [], "commands": []},
        "repository": {"fetched": False, "repositories": [], "not_fetched": []},
        "assessment": {
            "rubric_version": "v0.1",
            "assessed_points": 65,
            "score_floor": 32,
            "score_ceiling": 56,
            "severity": {"hard_blocker": 0, "major": 1, "minor": 0},
            "criteria": [],
            "issues": [],
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = base[key] | value
        else:
            base[key] = value
    return base


def issue(severity: str, kind: str, resource: str, evidence: str) -> dict:
    return {"severity": severity, "kind": kind, "resource": resource, "evidence": evidence}


def criterion(name: str, floor: int, ceiling: int, weight: int, **extra) -> dict:
    return {
        "name": name,
        "weight": weight,
        "floor": floor,
        "ceiling": ceiling,
        "assessed": True,
        "reason": "",
        "basis": [],
        "undetermined": [],
    } | extra


class TestTheThingsSection37Forbids:
    def test_the_report_never_calls_a_paper_reproducible(self):
        # "Do not claim 'this paper is reproducible' without actually running
        # it." Nothing here runs anything, so the word has no business in the
        # output at all.
        text = render(report()).casefold()
        assert "is reproducible" not in text
        assert "reproducible" not in text.replace("reproducibility", "")

    def test_the_band_is_explained_as_uncertainty_not_as_a_range_of_quality(self):
        text = render(report())
        assert "32-56 of 65" in text
        assert "nothing here" in text and "was executed" in text

    def test_every_issue_carries_the_evidence_for_it(self):
        text = render(
            report(
                assessment={
                    "issues": [
                        issue("major", "software version missing", "STAR", "we used STAR [32]")
                    ]
                }
            )
        )
        assert "Pin `STAR`" in text
        assert "we used STAR [32]" in text

    def test_an_unassessed_criterion_is_listed_with_its_reason(self):
        # The quiet failure mode: a criterion with no number is easy to omit
        # from a table, and then a reader cannot tell it from a zero.
        text = render(
            report(
                assessment={
                    "assessed_points": 65,
                    "criteria": [
                        criterion(
                            "result_traceability",
                            0,
                            10,
                            10,
                            assessed=False,
                            reason="needs figure-generating code",
                        )
                    ],
                }
            )
        )
        assert "*not assessed*" in text
        assert "An unassessed criterion is not a" in text
        assert "needs figure-generating code" in text

    def test_an_undetermined_note_survives_into_its_own_section(self):
        text = render(
            report(
                assessment={
                    "criteria": [
                        criterion(
                            "data_availability",
                            14,
                            18,
                            20,
                            undetermined=["2 resources could not be resolved to a role"],
                        )
                    ]
                }
            )
        )
        body = text.split("## What could not be determined")[1]
        assert "2 resources could not be resolved to a role" in body

    def test_a_warning_from_any_channel_reaches_the_reader(self):
        text = render(report(warnings=["pages 7, 8 had no text layer and were read by OCR"]))
        body = text.split("## What could not be determined")[1]
        assert "read by OCR" in body


class TestProvenance:
    def test_a_resource_row_names_its_section_before_its_page(self):
        # A page number alone is not provenance here: MATES page 20 holds three
        # sections and the role of an accession depends on which one it is in.
        finding = {
            "value": "GSE225377",
            "kind": "geo_series",
            "role": "own_data",
            "occurrences": [
                {
                    "page": 20,
                    "source": "text",
                    "section": "data_availability",
                    "section_heading": "Data availability",
                    "context": "deposited under GSE225377",
                }
            ],
        }
        text = render(report(findings=[finding]))
        assert (
            "| data (this paper's) | `GSE225377` | named | Data availability, segment 20 |" in text
        )

    def test_a_reference_list_mention_is_not_the_provenance_of_choice(self):
        # The same value can appear in the reference list and in a methods
        # section; quoting the reference list would describe someone else's work.
        finding = {
            "value": "GSE84465",
            "kind": "geo_series",
            "role": "external_data",
            "occurrences": [
                {"page": 22, "source": "text", "section": "references", "section_heading": ""},
                {
                    "page": 15,
                    "source": "text",
                    "section": "methods",
                    "section_heading": "Methods",
                },
            ],
        }
        text = render(report(findings=[finding]))
        assert "Methods, segment 15" in text
        assert "references, segment 22" not in text

    def test_the_commit_actually_read_is_recorded(self):
        text = render(
            report(
                repository={
                    "fetched": True,
                    "repositories": [
                        {
                            "repository": "lab/project",
                            "commit": "1f01192e36aaaaaa",
                            "committed_at": "2025-05-12T09:05:45-05:00",
                            "fetched_at": "2026-10-26T00:00:00+00:00",
                            "served_from_cache": True,
                        }
                    ],
                    "not_fetched": [],
                    "inventory": {"n_files": 32, "repositories": ["lab/project"]},
                    "execution": {"summary": {}, "inputs": []},
                    "dependencies": {"summary": {}, "interpreters": [], "manifest_files": []},
                    "figure_traceability": {"assessable": False},
                    "undocumented_steps": [],
                }
            )
        )
        assert "`lab/project` at `1f01192e36`" in text
        assert "not necessarily its state when" in text

    def test_a_repository_that_was_not_read_says_so(self):
        text = render(
            report(
                repository={
                    "fetched": False,
                    "repositories": [],
                    "not_fetched": [
                        {
                            "repository": "lab/project",
                            "url": "https://github.com/lab/project.git",
                            "reason": "git clone failed: not found",
                            "attempted": True,
                        }
                    ],
                }
            )
        )
        assert "**Code NOT read**: `lab/project` — git clone failed: not found" in text


class TestReadability:
    def test_the_distinct_findings_come_before_the_repetitive_one(self):
        # The rubric sorts issues by resource, which scatters the one-off
        # findings through an alphabetised run of "this tool has no version".
        issues = [
            issue("major", "software version missing", "bedtools", "a"),
            issue("major", "software version missing", "zlib", "b"),
            issue(
                "major",
                "the repository does not contain the code required for a reported figure",
                "figure 2",
                "c",
            ),
        ]
        text = render(report(assessment={"issues": issues}))
        assert text.index("figure 2") < text.index("bedtools")

    def test_a_quote_cut_out_of_running_text_is_trimmed_at_both_ends(self):
        # A paper-side quote arrives as a 120-character window either side of
        # the match, so it starts and ends mid-word. Only evidence of that
        # length is trimmed: a short constructed string keeps its first word.
        evidence = (
            "reads to the entire genome. After that, bedtools was used to filter out regions "
            "containing basic genes. Then, the remaining reads were rem"
        )
        assert len(evidence) > 100
        text = render(
            report(
                assessment={
                    "issues": [issue("major", "software version missing", "bedtools", evidence)]
                }
            )
        )
        assert "After that, bedtools was used" in text
        assert "reads to the entire genome" not in text  # head cut at the sentence
        assert "the remaining reads were…" in text  # tail cut at the word

    def test_short_evidence_keeps_its_first_word(self):
        evidence = "we used STAR [32] as the aligner"
        text = render(
            report(
                assessment={
                    "issues": [issue("major", "software version missing", "STAR", evidence)]
                }
            )
        )
        assert evidence in text

    def test_constructed_evidence_keeps_its_file_label(self):
        # The trimmer drops a leading partial word, which would throw away the
        # provenance of evidence this codebase built itself.
        evidence = "lab/project:LocusMasterTE/data/annotation.gtf holds 20 records"
        text = render(
            report(
                assessment={
                    "issues": [
                        issue("hard_blocker", "required dataset unavailable", "a.gtf", evidence)
                    ]
                }
            )
        )
        assert evidence in text

    def test_one_issue_is_not_pluralised(self):
        text = render(report(assessment={"severity": {"hard_blocker": 1, "major": 0, "minor": 0}}))
        assert "1 hard blocker," in text

    def test_an_empty_audit_still_renders_every_section(self):
        text = render(report())
        for heading in (
            "## Before you start",
            "## What is required",
            "## What was found",
            "## What is missing",
            "## What could not be determined",
            "## How this was read",
        ):
            assert heading in text


class TestWhichMentionIsTheProvenance:
    def test_an_availability_statement_beats_a_body_section(self):
        # MATES names its repository in a methods subsection and in its code
        # availability statement. "Different modes for TE quantification" is
        # where it happens to appear first and says nothing about the paper
        # having published its code.
        finding = {
            "value": "github.com/lab/project",
            "kind": "github",
            "role": "analysis_code",
            "occurrences": [
                {
                    "page": 17,
                    "source": "text",
                    "section": "methods",
                    "section_heading": "Different modes for TE quantification",
                },
                {
                    "page": 20,
                    "source": "text",
                    "section": "code_availability",
                    "section_heading": "Code availability",
                },
            ],
        }
        text = render(report(findings=[finding]))
        assert "Code availability, segment 20" in text
        assert "Different modes" not in text

    def test_one_interpreter_version_is_one_row(self):
        interpreters = [
            {
                "ecosystem": "python",
                "version": "3.9",
                "pinning": "pinned",
                "source": "lab/project:README.md",
                "end_of_life": "2025-10-31",
            },
            {
                "ecosystem": "python",
                "version": "3.9",
                "pinning": "pinned",
                "source": "lab/project:example/README.md",
                "end_of_life": "2025-10-31",
            },
        ]
        text = render(
            report(
                repository={
                    "fetched": True,
                    "repositories": [],
                    "not_fetched": [],
                    "inventory": {"n_files": 1, "repositories": ["lab/project"]},
                    "execution": {"summary": {}, "inputs": []},
                    "dependencies": {
                        "summary": {},
                        "interpreters": interpreters,
                        "manifest_files": [],
                    },
                    "figure_traceability": {"assessable": False},
                    "undocumented_steps": [],
                }
            )
        )
        assert text.count("| interpreter |") == 1

    def test_a_docs_manifest_is_not_cited_for_a_runtime_count(self):
        text = render(
            report(
                repository={
                    "fetched": True,
                    "repositories": [],
                    "not_fetched": [],
                    "inventory": {"n_files": 1, "repositories": ["lab/project"]},
                    "execution": {"summary": {}, "inputs": []},
                    "dependencies": {
                        "summary": {"distinct_packages": 97, "distinct_pinned": 94},
                        "interpreters": [],
                        "manifest_files": [
                            "lab/project:docs/requirements.txt",
                            "lab/project:requirements.txt",
                        ],
                    },
                    "figure_traceability": {"assessable": False},
                    "undocumented_steps": [],
                }
            )
        )
        assert "`lab/project:requirements.txt`" in text
        assert "docs/requirements.txt" not in text


class TestTheRequirementsTableIsAGatheringList:
    def test_one_file_named_by_two_commands_is_one_row(self):
        inputs = [
            {
                "path": "Drosophila_TE.csv",
                "status": "user_supplied",
                "named_by": "lab/project:example/README.md",
                "detail": "",
            },
            {
                "path": "Drosophila_TE.csv",
                "status": "user_supplied",
                "named_by": "lab/project:tutorial/reference_downloading.md",
                "detail": "",
            },
        ]
        text = render(
            report(
                repository={
                    "fetched": True,
                    "repositories": [],
                    "not_fetched": [],
                    "inventory": {"n_files": 1, "repositories": ["lab/project"]},
                    "execution": {"summary": {}, "inputs": inputs},
                    "dependencies": {"summary": {}, "interpreters": [], "manifest_files": []},
                    "figure_traceability": {"assessable": False},
                    "undocumented_steps": [],
                }
            )
        )
        assert text.count("Drosophila_TE.csv") == 1
