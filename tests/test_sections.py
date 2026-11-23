"""Regressions for section detection.

Every case here is taken from MATES or LocusMasterTE, and every one of them was
wrong at some point while this was being built. The failures share a shape: the
section label is still produced, still plausible, and now attributes a finding
to the wrong part of the paper.
"""

from __future__ import annotations

from reprolens.discovery.patterns import normalize, normalize_with_offsets
from reprolens.documents.base import PageText
from reprolens.documents.pdf_text import (
    Line,
    _assemble,
    _drop_front_matter_headings,
    _furniture_blocks,
    _inherit_labels,
    _is_heading,
    _is_table_row,
    _split_run_in,
)
from reprolens.documents.sections import SectionMark, classify_heading, resolve

BODY = 8.2  # MATES's modal body size, weighted by characters


def plain(text: str, size: float) -> Line:
    """A line with the bold flag clear, as Nature sets every one of its headings."""
    return Line(text=text, size=size, bold=False)


def bold(text: str, size: float) -> Line:
    """A line bold end to end, as PLOS sets every one of its headings."""
    return Line(text=text, size=size, bold=True)


def mark(offset: int, heading: str, level: int = 1) -> SectionMark:
    return SectionMark(offset=offset, heading=heading, label=classify_heading(heading), level=level)


class TestHeadingDetection:
    def test_accepts_a_real_heading_without_the_bold_flag(self):
        # Nature sets headings in a separate font face and leaves the bold flag
        # clear, so a bold-flag rule finds none of MATES's 11 headings. Size is
        # the signal.
        assert _is_heading(plain("Data availability", 10.71), BODY)
        assert _is_heading(plain("Results", 10.71), BODY)

    def test_rejects_body_line_that_opens_with_a_heading_word(self):
        # The 10 false positives a keyword rule produces on MATES.
        assert not _is_heading(plain("methods.", 8.22), BODY)
        assert not _is_heading(plain("results across various experimental configu", 8.22), BODY)
        assert not _is_heading(plain("Supplementary Fig. S5 illustrates the cell", 8.22), BODY)

    def test_rejects_long_line_set_larger_than_the_body(self):
        # MATES's abstract is 9.96pt against an 8.22pt body, so size alone
        # accepts its lines. Length is the second guard.
        line = "methods, enhancing the accuracy of TE quantification and aiding in the"
        assert not _is_heading(plain(line, 9.96), BODY)

    def test_rejects_figure_panel_labels(self):
        # MATES p12: "a." and "b." are short, large, and contain a letter.
        assert not _is_heading(plain("a.", 10.71), BODY)
        assert not _is_heading(plain("b.", 10.71), BODY)


class TestWeightAsTheSecondSignal:
    """PLOS's case, where size is not available.

    Every PLOS heading is ArialMTStd-Bold with the flag set, and the back-matter
    headings sit at the body size. Keying on size alone missed "Availability of
    data and materials" on ASPEN page 19, and missing that one heading cost the
    whole code-availability criterion: with no availability section the
    repository URLs read as citations, nothing was cloned, and a paper that
    publishes an R package scored zero out of twenty for its code.
    """

    PLOS = 10.0  # ASPEN's body size, and also its back-matter heading size

    def test_a_body_size_bold_heading_is_accepted(self):
        assert _is_heading(bold("Availability of data and materials", self.PLOS), self.PLOS)

    def test_the_same_line_unweighted_is_body_text(self):
        # The rule has to stay off for Nature, where no heading is bold and body
        # text at body size is everywhere.
        assert not _is_heading(plain("Availability of data and materials", self.PLOS), self.PLOS)

    def test_a_bold_run_in_lead_in_is_not_a_heading(self):
        # "Results." opening a paragraph is bold, short and at body size. The
        # trailing full stop is what separates it from a heading, and it applies
        # only on the weight path -- a heading found by size may end however its
        # publisher likes.
        assert not _is_heading(bold("Results.", self.PLOS), self.PLOS)
        assert not _is_heading(bold("Sample preparation.", self.PLOS), self.PLOS)

    def test_bold_smaller_than_the_body_is_not_a_heading(self):
        # A bold caption label or table header sits below the body size.
        assert not _is_heading(bold("Sample", 8.0), self.PLOS)

    def test_weight_does_not_relax_the_other_guards(self):
        long_line = "Availability of data and materials for every sample in the cohort study"
        assert len(long_line) > 60
        assert not _is_heading(bold(long_line, self.PLOS), self.PLOS)
        assert not _is_heading(bold("a", self.PLOS), self.PLOS)
        assert not _is_heading(bold("Results and", self.PLOS), self.PLOS)

    def test_a_heading_found_by_size_may_end_in_a_full_stop(self):
        assert _is_heading(plain("Fig. 1.", 10.71), BODY)


class TestHeadingClassification:
    def test_recognizes_both_journals_phrasings(self):
        assert classify_heading("Data availability") == "data_availability"
        assert classify_heading("Availability of data and materials") == "data_availability"
        assert classify_heading("Code availability") == "code_availability"

    def test_does_not_claim_a_subsection_by_its_first_word(self):
        # MATES p11, inside Results, four pages before Methods begins. Prefix
        # matching sent every finding in it to the Methods section.
        assert classify_heading("Method benchmarking in single-cell TE quantification") == "other"
        assert classify_heading("Methods") == "methods"
        assert classify_heading("Materials and Methods") == "methods"

    def test_tolerates_numbering(self):
        assert classify_heading("1. Introduction") == "background"


class TestNesting:
    def test_unrecognized_subsection_inherits_its_parent(self):
        # MATES sets "Methods" at 10.71pt and "Raw reads preprocessing" at
        # 8.72pt directly beneath it. Without inheritance the subsection resets
        # the section to "other" and the whole Methods section -- the only place
        # parameters and tool versions live -- is mislabelled.
        page = PageText(
            page=15,
            text="",
            sections=[mark(0, "Methods", level=1), mark(8, "Raw reads preprocessing", level=2)],
        )
        _inherit_labels([page])
        assert [m.label for m in page.sections] == ["methods", "methods"]

    def test_a_sibling_section_is_not_inherited_from(self):
        pages = [
            PageText(page=20, text="", sections=[mark(0, "Data availability", level=1)]),
            PageText(page=22, text="", sections=[mark(0, "Additional information", level=1)]),
        ]
        _inherit_labels(pages)
        assert pages[1].sections[0].label == "other"


class TestFrontMatter:
    def test_display_type_before_the_first_real_heading_is_discarded(self):
        # A title page is display type throughout, so typography cannot tell the
        # author list from a section heading: MATES yields marks for "Article"
        # and "Ruohan Wang".
        pages = [
            PageText(page=1, text="", sections=[mark(0, "Article"), mark(158, "Ruohan Wang")]),
            PageText(page=2, text="", sections=[mark(5688, "Results")]),
        ]
        _drop_front_matter_headings(pages)
        assert pages[0].sections == []
        assert [m.label for m in pages[1].sections] == ["results"]


class TestFurniture:
    def test_repeated_header_is_furniture_and_a_unique_block_is_not(self):
        # MATES repeats its DOI in the header of 21 of 22 pages, which inflated
        # one finding into 19 occurrences. Three body paragraphs also start near
        # a page edge; those must survive.
        line = plain("Article https://doi.org/10.1038/s41467-024-53114-7", 7.0)
        header = {"lines": [line], "y0": 24.0}
        layout = [
            [header, {"lines": [plain(f"unique body text {n}", 8.2)], "y0": 713.0}]
            for n in range(4)
        ]
        furniture = _furniture_blocks(layout, [790.9] * 4)
        assert all(furniture[page] == {0} for page in range(1, 5))

    def test_page_numbers_do_not_defeat_the_match(self):
        # The footer differs on every page: "... 15:8798  20".
        layout = [
            [{"lines": [plain(f"Nature Communications| (2024) 15:8798 {n}", 7.0)], "y0": 764.0}]
            for n in range(1, 5)
        ]
        furniture = _furniture_blocks(layout, [790.9] * 4)
        assert all(furniture[page] == {0} for page in range(1, 5))


class TestResolver:
    def test_carries_the_section_across_pages(self):
        # MATES's Methods heading is on page 15 and the next heading is on page
        # 20, so a finding on page 17 is in Methods.
        pages = [
            PageText(page=15, text="", sections=[mark(4253, "Methods")]),
            PageText(page=17, text="", sections=[]),
            PageText(page=20, text="", sections=[mark(1140, "Data availability")]),
        ]
        resolver = resolve(pages)
        assert resolver.at(17, 500).label == "methods"
        assert resolver.at(20, 900).label == "methods"
        assert resolver.at(20, 2000).label == "data_availability"

    def test_defaults_to_front_matter_before_any_heading(self):
        resolver = resolve([PageText(page=2, text="", sections=[mark(100, "Results")])])
        assert resolver.at(1, 0).label == "front_matter"
        assert resolver.at(2, 50).label == "front_matter"


class TestNormalizeOffsets:
    def test_offsets_index_the_original_text(self):
        text = "see GSE225377 at\nhttps://exam-\nple.org/x"
        normalized, offsets = normalize_with_offsets(text)
        position = normalized.index("GSE225377")
        assert text[offsets[position] : offsets[position] + 9] == "GSE225377"

    def test_still_matches_the_plain_normalizer(self):
        for text in ["a­b", "x y", "en–dash", "two-\n  column", ""]:
            assert normalize_with_offsets(text)[0] == normalize(text)

    def test_offsets_survive_a_dehyphenation_before_the_match(self):
        # Normalization is not length-preserving, and MATES drifts by 52
        # characters on a single page. An offset taken from the normalized
        # string lands earlier and earlier in the original, until it crosses a
        # section boundary and files a reference-list DOI under Data
        # availability.
        text = "quanti-\nfication of repeat-\nelements then GSE212945"
        normalized, offsets = normalize_with_offsets(text)
        position = normalized.index("GSE212945")
        assert position != offsets[position]
        assert text[offsets[position] :].startswith("GSE212945")


class TestBackMatterSections:
    """The back matter's own sections, which are where availability lives.

    Found on a materials-science paper from a publisher none of the benchmark
    papers use. RSC's Digital Discovery puts its availability statement in a
    ``<sec sec-type="data-availability">`` inside ``<back>``, after the
    acknowledgements, where Nature and PLOS put theirs in the body. Emitting
    ``<back>`` as one "Back matter" segment classified the lot as "other", so
    Atomate2's statement -- which names its repository, pins it to version
    0.0.21 and gives a Zenodo DOI -- was never seen. The repository then read as
    a dependency rather than the paper's own code, nothing was cloned, three
    criteria went unassessed, and a paper with an exemplary availability
    statement scored 0 of 20 for code availability.
    """

    ARTICLE = """<article>
      <body><sec><title>Introduction</title><p>We present a framework.</p></sec></body>
      <back>
        <ack><p>We thank the funders.</p></ack>
        <sec sec-type="data-availability"><title>Data availability</title>
          <p>The code can be found at https://github.com/materialsproject/atomate2
             and the version employed is 0.0.21.</p></sec>
        <ref-list><ref><p>Someone et al., a cited paper, 2020.</p></ref></ref-list>
      </back>
    </article>"""

    def segments(self, tmp_path):
        from reprolens.documents.jats_xml import JatsXmlBackend

        path = tmp_path / "paper.xml"
        path.write_text(self.ARTICLE)
        return JatsXmlBackend().read(path)

    def test_a_back_matter_section_gets_its_own_segment(self, tmp_path):
        labels = [m.label for page in self.segments(tmp_path) for m in page.sections]
        assert "data_availability" in labels

    def test_the_statement_is_not_buried_in_an_other_labelled_segment(self, tmp_path):
        for page in self.segments(tmp_path):
            if "atomate2" in page.text:
                assert [m.label for m in page.sections] == ["data_availability"]
                break
        else:
            raise AssertionError("the availability statement reached no segment at all")

    def test_the_rest_of_the_back_matter_still_arrives(self, tmp_path):
        # Acknowledgements and the reference list have to keep coming through,
        # because a reference-list DOI must still be labelled as one.
        text = "\n".join(p.text for p in self.segments(tmp_path))
        assert "We thank the funders" in text
        assert "a cited paper" in text

    def test_no_text_belongs_to_two_segments_at_once(self, tmp_path):
        # The remainder is rebuilt from the non-section children rather than
        # re-emitting the whole of <back>. Emitting both would count every
        # finding in the availability statement twice.
        pages = self.segments(tmp_path)
        assert sum("atomate2" in p.text for p in pages) == 1


class TestNamedBackMatterElements:
    """Back matter JATS names structurally rather than as a <sec>.

    The fix above split the <sec> children of <back> out, which left <ack> and
    <ref-list> -- siblings of <sec>, not children of one -- pooled in the
    "Back matter" remainder and labelled "other". Measured on the three XML
    papers: 64 of ASPEN's 89 finding occurrences and 149 of Atomate2's 209,
    i.e. essentially all of the cited literature in both. The failure hid
    behind LocusMasterTE, where PMC wraps the reference list in a
    ``<sec sec-type="ref-list">`` so it split out and classified by title.

    Which is why the label here comes from the element name and not the title:
    <ref-list> frequently carries no <title> at all, and the name is the one
    structural fact the format guarantees.
    """

    def segments(self, tmp_path, article):
        from reprolens.documents.jats_xml import JatsXmlBackend

        path = tmp_path / "paper.xml"
        path.write_text(article)
        return JatsXmlBackend().read(path)

    def labels_of(self, tmp_path, article):
        return {
            m.label: page.text for page in self.segments(tmp_path, article) for m in page.sections
        }

    def test_a_titleless_ref_list_is_still_labelled_references(self, tmp_path):
        article = """<article><body><sec><title>Results</title><p>Shown.</p></sec></body>
          <back><ref-list><ref><p>Someone, 10.1038/s41467-024-53114-7, 2020.</p></ref>
          </ref-list></back></article>"""
        labels = self.labels_of(tmp_path, article)
        assert "references" in labels
        assert "10.1038" in labels["references"]

    def test_acknowledgments_separate_from_the_reference_list(self, tmp_path):
        # Both in one segment is the bug: a funder URL in the acknowledgements
        # and a DOI in the reference list carry different meaning.
        article = """<article><body><sec><title>Results</title><p>Shown.</p></sec></body>
          <back><ack><p>Funded by grant 10.13039/100000001.</p></ack>
          <ref-list><ref><p>Someone, 2020.</p></ref></ref-list></back></article>"""
        labels = self.labels_of(tmp_path, article)
        assert "acknowledgments" in labels
        assert "references" in labels
        assert "Someone" not in labels["acknowledgments"]

    def test_an_elements_own_title_wins_over_the_canonical_name(self, tmp_path):
        # The canonical heading stands in for a missing one; it does not
        # overwrite what the typesetter actually printed.
        article = """<article><body><sec><title>Results</title><p>Shown.</p></sec></body>
          <back><ack><title>Acknowledgements</title><p>Thanks.</p></ack></back></article>"""
        headings = [m.heading for page in self.segments(tmp_path, article) for m in page.sections]
        assert "Acknowledgements" in headings

    def test_an_unrecognized_element_still_arrives(self, tmp_path):
        # Fail-closed: an element this map has never heard of must not vanish.
        article = """<article><body><sec><title>Results</title><p>Shown.</p></sec></body>
          <back><some-future-tag><p>Content worth keeping.</p></some-future-tag></back>
          </article>"""
        text = "\n".join(p.text for p in self.segments(tmp_path, article))
        assert "Content worth keeping" in text

    def test_no_text_belongs_to_two_segments(self, tmp_path):
        article = """<article><body><sec><title>Results</title><p>Shown.</p></sec></body>
          <back><ack><p>Thanks.</p></ack>
          <ref-list><ref><p>Someone, 2020.</p></ref></ref-list></back></article>"""
        pages = self.segments(tmp_path, article)
        assert sum("Thanks" in p.text for p in pages) == 1
        assert sum("Someone" in p.text for p in pages) == 1


class TestNestedStatementSections:
    """A statement the publisher nested inside a body section.

    The same mistake as emitting <back> whole, one level deeper. ASPEN nests
    its "Availability of data and materials" -- a <sec
    sec-type="data-availability"> -- as the twenty-first subsection of Methods,
    so the statement naming both of its repositories arrived inside a
    25,935-character segment labelled "methods". Both repositories read as
    dependencies rather than the paper's own code, neither was cloned, and the
    paper scored 0 of 20 for code availability from the XML channel while
    scoring 18 of 20 from its own PDF -- 16-26 against 74-82 overall, on one
    document read two ways.
    """

    ARTICLE = """<article>
      <body>
        <sec><title>Methods</title><p>We aligned reads.</p>
          <sec><title>Bayesian shrinkage implementation</title>
            <p>Shrinkage was applied per gene.</p></sec>
          <sec sec-type="data-availability"><title>Availability of data and materials</title>
            <p>Code is at https://github.com/ewonglab/ASPEN and the manuscript
               analyses at https://github.com/ewonglab/ASPEN_manuscript.</p></sec>
        </sec>
      </body>
    </article>"""

    def segments(self, tmp_path, article=None):
        from reprolens.documents.jats_xml import JatsXmlBackend

        path = tmp_path / "paper.xml"
        path.write_text(article or self.ARTICLE)
        return JatsXmlBackend().read(path)

    def test_the_nested_statement_gets_its_own_segment(self, tmp_path):
        labels = [m.label for page in self.segments(tmp_path) for m in page.sections]
        assert labels.count("data_availability") == 1

    def test_the_repositories_land_in_it_and_not_in_methods(self, tmp_path):
        for page in self.segments(tmp_path):
            label = page.sections[0].label
            if "ewonglab/ASPEN" in page.text:
                assert label == "data_availability"
            if label == "methods":
                assert "ewonglab" not in page.text

    def test_an_ordinary_subsection_stays_inside_its_parent(self, tmp_path):
        # The heading rules are anchored so that a Methods subsection
        # classifies as "other"; fragmenting Methods into twenty segments
        # would buy nothing and would scatter its findings.
        for page in self.segments(tmp_path):
            if page.sections[0].label == "methods":
                assert "Shrinkage was applied" in page.text
                break
        else:
            raise AssertionError("Methods reached no segment")

    def test_the_lifted_text_is_removed_from_its_parent(self, tmp_path):
        pages = self.segments(tmp_path)
        assert sum("ewonglab/ASPEN" in p.text for p in pages) == 1

    def test_a_statement_inside_a_statement_is_left_alone(self, tmp_path):
        # PMC repeats Data availability verbatim inside <sec
        # sec-type="associated-data">. ``associated_data`` is a separate label
        # precisely so the copy can be told from the original; lifting the
        # nested copy out relabels it ``data_availability`` and makes the
        # document state its accessions twice with equal authority.
        article = """<article><body>
          <sec><title>Results</title><p>Shown.</p></sec>
          <sec sec-type="associated-data"><title>Associated Data</title>
            <sec sec-type="data-availability-statement">
              <title>Data Availability Statement</title>
              <p>Reads are deposited under GSE225377.</p></sec>
          </sec>
        </body></article>"""
        labels = [m.label for page in self.segments(tmp_path, article) for m in page.sections]
        assert labels.count("associated_data") == 1
        assert "data_availability" not in labels


class TestConclusionsWithATrailingPhrase:
    """``^conclusions?$`` is anchored on purpose, and was anchored too tight.

    The anchoring exists because single body words also open subsection titles
    that sit in a different section ("Method benchmarking..." inside Results).
    But Atomate2 titles its last body section "Conclusions and future work",
    and the anchored rule sent its 8 finding occurrences to "other". The
    trailing phrases are enumerated rather than left open, so the rule keeps
    rejecting a subsection that merely begins with the word.
    """

    def test_the_common_trailing_phrases_classify(self):
        for heading in (
            "Conclusions and future work",
            "Conclusion and future directions",
            "Conclusions and outlook",
            "Conclusion and perspectives",
        ):
            assert classify_heading(heading) == "conclusions", heading

    def test_a_subsection_opening_with_the_word_is_still_rejected(self):
        assert classify_heading("Conclusions drawn from the ablation study") == "other"

    def test_the_bare_forms_are_unaffected(self):
        assert classify_heading("Conclusion") == "conclusions"
        assert classify_heading("Conclusions") == "conclusions"


class TestColonTerminatedHeadings:
    """A publisher class that ends every back-matter heading with a colon.

    ALIGNN, an accepted manuscript typeset from Word, writes "Code
    availability:" and "Data availability:". The colon was in the bad-tail
    guard, so both were rejected, both sections were lost, the paper's two
    repositories read as dependencies rather than its own code, nothing was
    cloned, and a paper that publishes its code and its Figshare collection
    scored zero out of twenty for each.
    """

    BODY = 12.0

    def test_a_bold_heading_ending_in_a_colon_is_accepted(self):
        assert _is_heading(bold("Code availability:", self.BODY), self.BODY)
        assert _is_heading(bold("Data availability:", self.BODY), self.BODY)

    def test_the_classifier_still_recognizes_it(self):
        assert classify_heading("Code availability:") == "code_availability"
        assert classify_heading("Data availability:") == "data_availability"

    def test_a_phrase_that_breaks_mid_clause_is_still_rejected(self):
        # The other bad tails stay: these are wrapped prose, not headings.
        assert not _is_heading(bold("the method and", self.BODY), self.BODY)
        assert not _is_heading(bold("a summary of", self.BODY), self.BODY)
        assert not _is_heading(bold("Results, methods,", self.BODY), self.BODY)

    def test_a_long_prose_line_ending_in_a_colon_is_not_a_heading(self):
        line = "We evaluated the model on the following five benchmark datasets:"
        assert len(line) > 60
        assert not _is_heading(bold(line, self.BODY), self.BODY)


class TestRunInHeadings:
    """A heading that shares its line with the prose it introduces.

    ALIGNN sets "Code availability: The code and full model and training
    configurations..." as a single line: a bold prefix, then regular body text.
    Judged whole it is eighty characters and not bold end to end, so neither
    signal fires. The bold prefix is the heading.
    """

    BODY = 12.0

    def line(self, text: str, prefix: str) -> Line:
        return Line(text=text, size=self.BODY, bold=False, prefix=prefix)

    def test_the_bold_prefix_becomes_its_own_heading_line(self):
        run_in = self.line(
            "Code availability: The code and full model and training configurations used",
            "Code availability: ",
        )
        out = _split_run_in([run_in], self.BODY)
        assert len(out) == 2
        assert out[0].text == "Code availability:"
        assert out[0].bold is True
        assert out[1].text.startswith("The code and full model")

    def test_the_prose_is_kept_rather_than_discarded(self):
        run_in = self.line("Data availability: All data is at Figshare.", "Data availability: ")
        out = _split_run_in([run_in], self.BODY)
        assert "All data is at Figshare." in out[1].text

    def test_a_line_with_no_bold_prefix_is_left_alone(self):
        plain_line = self.line("just some prose on a line", "")
        assert _split_run_in([plain_line], self.BODY) == [plain_line]

    def test_a_line_that_is_already_a_heading_is_left_alone(self):
        heading = bold("Methods", self.BODY)
        assert _split_run_in([heading], self.BODY) == [heading]

    def test_a_bold_lead_in_that_is_not_heading_shaped_is_left_alone(self):
        # "Results." opening a paragraph is a bold run-in lead-in, and the full
        # stop is what separates it from a heading. Splitting it would file the
        # paragraph under a section called "Results." on every such paragraph.
        lead_in = self.line("Results. We found that the model converged.", "Results. ")
        assert _split_run_in([lead_in], self.BODY) == [lead_in]

    def test_later_lines_of_the_block_survive_the_split(self):
        run_in = self.line("Data availability: All data", "Data availability: ")
        tail = Line("is on Figshare.", self.BODY, False)
        out = _split_run_in([run_in, tail], self.BODY)
        assert out[-1] == tail


class TestTablesAndLetteredSubsections:
    """ALIGNN, an accepted manuscript set in one size and weight throughout.

    Its table header rows read as headings ("Property Units MAD CFID CGCNN
    ALIGNN MAD:"), and its lettered subsections ("A. Atomistic graph
    representation") read as siblings of Results, so everything under them
    was labelled ``other``.
    """

    SIZE = 12.0

    def cells(self, *texts: str, weight: bool = True) -> list[Line]:
        return [Line(text=t, size=self.SIZE, bold=weight, y=124.0) for t in texts]

    def test_a_bold_row_of_cells_is_a_table_not_a_heading(self):
        assert _is_table_row(self.cells("Property ", "Units ", "MAD ", "CFID "))

    def test_a_justified_sentence_after_a_run_in_heading_is_not_a_table(self):
        row = self.cells("Data ", "availability: ") + self.cells("All ", "data ", weight=False)
        assert not _is_table_row(row)

    def test_a_row_that_names_a_section_is_kept(self):
        assert not _is_table_row(self.cells("Data ", "availability"))

    def test_lines_without_geometry_are_never_a_table(self):
        assert not _is_table_row([bold("Methods", 12), bold("overview", 12)])

    def test_table_cells_leave_no_mark(self):
        block = {"lines": self.cells("Target ", "Units ", "SchNet "), "y0": 0}
        _, marks, _ = _assemble([block], body_size=10.0, furniture=set(), levels={12.0: 1})
        assert marks == []

    def test_a_lone_acronym_cell_leaves_no_mark(self):
        block = {"lines": [bold("MAE", 12)], "y0": 0}
        _, marks, _ = _assemble([block], body_size=10.0, furniture=set(), levels={12.0: 1})
        assert marks == []

    def test_a_lettered_subsection_inherits_its_section(self):
        blocks = [
            {"lines": [bold("Results and discussion", 12)], "y0": 0},
            {"lines": [bold("A. Atomistic graph representation", 12)], "y0": 0},
            {"lines": [bold("Methods", 12)], "y0": 0},
            {"lines": [bold("A: JARVIS-DFT dataset", 12)], "y0": 0},
        ]
        _, marks, _ = _assemble(blocks, body_size=10.0, furniture=set(), levels={12.0: 1})
        page = PageText(page=1, text="", sections=marks)
        _inherit_labels([page])
        assert [m.label for m in marks] == ["results", "results", "methods", "methods"]
