"""What the paper says it needs, and whether it says it precisely enough to act on.

This is a *specificity* audit, not an inventory. Finding "RepeatMasker" in a
methods section is easy and nearly useless on its own. The reportable fact is
that RepeatMasker is named and never versioned, because that is the gap the lab
actually hit: the TE annotation behind LocusMasterTE's headline figure was built
"using RepeatMasker [27] for GRCh38" and could not be reconstructed from that.

**A version-anchored detector gets this exactly backwards**, which is worth
stating because it is the obvious way to build this. Across both benchmark
papers there are three version strings in total -- ``v2.8.2``, ``version 0.17``
and ``version 42`` -- against 25 or so distinct tools named between them. A
detector that keys on version tokens therefore finds the handful of tools that
are already documented and misses every one that is not, reporting a paper as
well specified in precisely the case where it is worst.

So tool names are matched independently of any version, and the version is
checked for afterwards. The cost is a vocabulary with a recall ceiling, and that
ceiling has now been measured rather than assumed. On ASPEN -- the first paper
this module was not built against -- it knew **3 of the 8 tools the paper
names**: clusterProfiler, Rsubread, scater, scDALI and scuttle were all absent,
and all five are Bioconductor packages the paper pins to an exact version. The
five have since been added, which closes the gap on ASPEN and says nothing about
paper four.

Note which direction that error runs. On the benchmark papers a missing name
costs a *gap* -- a tool named without a version goes unreported. On ASPEN it cost
*credit*: the paper documents its versions well, and the module reported 3 pinned
of 11 where the truth is nearer 8 of 16. A fixed list under-reports good practice
and bad practice alike.

Extending recall past a fixed list is the next piece of work, and it needs a
model proposing names with the text available to check them against.

Two gap classes exist and only one is visible from the text. A tool named
without a version is detectable here. A resource the pipeline requires and the
paper never mentions is not: MATES needs a gene annotation to quantify genes
alongside TEs, and the string "GENCODE" appears nowhere in it. That second class
needs a model of what the method requires, which this module does not have, so
it reports what it checked rather than implying coverage.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from reprolens.discovery.patterns import normalize_with_offsets
from reprolens.documents.base import PageText
from reprolens.documents.sections import SectionLabel, resolve

Kind = str  # "tool" | "library" | "reference" | "database" | "language" | "environment"

Specificity = str  # "pinned" | "deferred_to_citation" | "named_only"

# Sections where a name is a citation rather than a declared dependency.
_NOT_A_DECLARATION = frozenset({"references", "page_furniture"})

# How far after a name to accept a version as belonging to it. LocusMasterTE
# writes "Gencode annotation of the hg38 version 42 Basic GTF file", so the
# version sits 26 characters past the name and adjacency is too strict.
_VERSION_WINDOW = 60

_VERSION = re.compile(r"\bv(?:er(?:sion)?)?\.?\s?(\d[\w.]*)", re.I)

# A genome assembly pins the coordinate system, not the annotation. Recorded
# separately and deliberately NOT accepted as a version: "RepeatMasker for
# GRCh38" is the exact wording that could not be reproduced from.
_ASSEMBLY = re.compile(r"\b(hg\d{2}|GRCh\d{2}|GRCm\d{2}|mm\d{1,2}|dm\d|TAIR\d{1,2})\b")

# "[ 27 ]" in JATS, "[27]" in print. On the PDF path superscript citation
# markers are dropped during text assembly -- they had to be, or repository URLs
# pick up the marker that follows them -- so this signal is XML-only for now.
_CITATION = re.compile(r"^\s*\[\s*(\d{1,3})\s*\]")

_FLAG = re.compile(r"-{2}[A-Za-z][\w-]{2,}")

# A quoted run that carries a flag is a command; one that does not is prose, and
# a curly apostrophe in "MATES's" otherwise opens a match that never closes.
_QUOTED = re.compile(r"['‘’\"“”]([^'‘’\"“”]{6,160})")
_PROGRAM = re.compile(r"^[a-z][\w.-]*\s")


# --- named settings ------------------------------------------------------------
# A parameter the paper states in prose or in a hyperparameter table, as opposed
# to a command-line flag. Deliberately a CLOSED vocabulary, because the open
# form does not work: a rule of "a name, a separator, a number" returns 188-401
# matches per paper across the five, and the most frequent captures are DOIs
# ("doi 10", 51 on ASPEN), author names, table cross-references ("Additional
# file 13") and elapsed days. The signal is there but the ratio is unusable, so
# this names what it is looking for -- the same decision, for the same reason,
# as the software vocabulary above.
_SETTING_NAMES: tuple[str, ...] = (
    # training configuration, as ALIGNN's "Parameter Value" table spells it out
    r"learning[-\s]rate",
    r"batch size",
    r"weight decay",
    r"hidden features",
    r"embedding features",
    r"edge input features",
    r"triplet input features",
    r"atom input features",
    r"ALIGNN layers",
    r"GCN layers",
    r"number of layers",
    r"epochs",
    r"dropout",
    r"momentum",
    r"patience",
    r"n_estimators",
    # "train-validation-test split" is deliberately NOT here. It matched twice
    # on ALIGNN and one of the two came out as "110000-1000010829": the paper
    # prints "110000-10000- 10829" across a line break, and the hyphen-join that
    # repairs wrapped words removes the separator. Reporting a mangled number
    # under a provenance quote is worse than reporting nothing, and a dataset
    # split is not a configured parameter of the method anyway.
    # statistical thresholds, which are the configuration of an analysis paper
    r"FDR",
    r"q-?value",
    r"threshold",
    # clustering and filtering
    r"resolution",
    r"min(?:imum)? cells",
    r"min(?:imum)? genes",
    r"window size",
    r"bin size",
    r"cutoff",
)

# The exponent form comes FIRST or it never matches: "10^-5" starts with a digit
# run, so a leading "\d[\d.]*" alternative captures "10" and reports ALIGNN's
# weight decay as four thousand times its real value. A hyphenated run is kept
# whole for the same reason -- "110000-10000-10829" is one split specification,
# and its first third is not a number the paper stated.
_SETTING_VALUE = re.compile(
    r"(\d[\d.]*\s*[×x]\s*10\^[-+]?\d+|10\^[-+]?\d+|"
    r"\d[\d.]*(?:-\d[\d.]*)+|\d[\d.]*)"
)

# Every way the five papers join a name to its value, including a bare space:
# the text layer flattens ALIGNN's two-column table to "Batch size 64 Learning
# rate 0.001", so requiring punctuation would lose the one paper that documents
# its configuration in full.
_SETTING_SEP = r"\s*(?:=|:|\bof\b|\b(?:was\s+)?set\s+to\b|\bto\b|\bis\b|[<>≤≥]|\s)\s*"

_SETTINGS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(rf"\b{name}\b{_SETTING_SEP}{_SETTING_VALUE.pattern}", re.I))
    for name in _SETTING_NAMES
)

# A percentage is a measured quantity, not a configured one. ASPEN writes "the
# resolution of 20-38% of total sequencing reads", which is the single false
# positive the closed vocabulary produced on all five papers; its real
# "resolution = 0.9" (Seurat's FindClusters) is three pages later and unaffected.
_A_PROPORTION = re.compile(r"\s*%")

# The joining words, stripped back off the name the paper used. The separator is
# matched as part of the name's span so the value's position is known, which
# otherwise leaves the label reading "weight decay of".
_SETTING_TAIL = re.compile(r"\s*(?:=|:|[<>≤≥]|\b(?:of|to|is|was set to|set to)\b)\s*$", re.I)


def _flex(name: str) -> str:
    """Allow typesetting to split a name: "RepeatMasker" -> "Repeat Masker".

    MATES's data availability statement reads "sourced from the Repeat Masker
    website", so an exact-name match misses the one mention that matters most.
    Same failure mode as "GSE 212945", handled the same way.
    """
    parts = re.split(r"(?<=[a-z])(?=[A-Z])|\s+", name)
    return r"\s*".join(re.escape(part) for part in parts if part)


# Ordered longest-first so "STARsolo" claims its span before "STAR" can.
# (canonical name, kind, explicit regex or None). A name needs an explicit
# pattern only where the generated one would misfire: "R" as a single letter
# matches everywhere, so it counts only where the paper is plainly talking
# about the language.
_SOFTWARE: tuple[tuple[str, Kind, str | None], ...] = (
    # --- aligners and read handling -----------------------------------------
    ("STARsolo", "tool", None),
    ("Rsubread", "tool", None),
    ("STAR", "tool", None),
    ("Cell Ranger", "tool", None),
    ("CellRanger", "tool", None),
    ("minimap2", "tool", None),
    ("bowtie2", "tool", None),
    ("bowtie", "tool", None),
    ("HISAT2", "tool", None),
    ("BWA", "tool", None),
    ("samtools", "tool", None),
    ("bedtools", "tool", None),
    ("Picard", "tool", None),
    ("SeqKit", "tool", None),
    ("Trimmomatic", "tool", None),
    ("cutadapt", "tool", None),
    ("fastp", "tool", None),
    ("FastQC", "tool", None),
    ("Guppy", "tool", None),
    ("Dorado", "tool", None),
    ("Pychopper", "tool", None),
    # --- quantification ------------------------------------------------------
    ("featureCounts", "tool", None),
    ("HTSeq", "tool", None),
    ("Salmon", "tool", None),
    ("kallisto", "tool", None),
    ("RSEM", "tool", None),
    ("StringTie", "tool", None),
    ("Velocyto", "tool", None),
    ("scNanoGPS", "tool", None),
    ("Monocle", "tool", None),
    ("TALON", "tool", r"\bTalon\b"),
    ("Spanki", "tool", None),
    # --- transposable-element tools -----------------------------------------
    ("TEtranscripts", "tool", None),
    ("Telescope", "tool", None),
    ("SoloTE", "tool", None),
    ("SQuIRE", "tool", None),
    ("scTE", "tool", None),
    # --- single-cell analysis ------------------------------------------------
    ("Seurat", "library", None),
    ("Scanpy", "library", None),
    ("Signac", "library", None),
    ("ArchR", "library", None),
    ("Harmony", "library", None),
    ("AnnData", "library", None),
    ("pysam", "library", None),
    ("intervaltree", "library", None),
    ("htslib", "library", None),
    ("DESeq2", "library", None),
    ("edgeR", "library", None),
    ("limma", "library", None),
    ("MACS2", "tool", None),
    ("Polyester", "library", None),
    # Bioconductor single-cell and enrichment packages. Added after ASPEN named
    # five of them, each with an exact version, and this module found none.
    ("SingleCellExperiment", "library", None),
    ("clusterProfiler", "library", None),
    ("scDALI", "tool", None),
    ("scater", "library", None),
    ("scuttle", "library", None),
    ("tximport", "library", None),
    ("PyTorch", "library", None),
    ("TensorFlow", "library", None),
    ("scikit-learn", "library", None),
    ("IGV", "tool", None),
    # --- annotation and reference sources -----------------------------------
    ("RepeatMasker", "reference", None),
    ("GENCODE", "reference", None),
    ("Ensembl", "reference", None),
    ("RefSeq", "reference", None),
    ("RepBase", "reference", None),
    ("Dfam", "reference", None),
    ("UCSC", "reference", None),
    # --- materials science ---------------------------------------------------
    # The vocabulary above is computational biology only, and the consequence
    # was measurable: ALIGNN named 1 tool (PyTorch) and Atomate2 named 1
    # (Python), against ASPEN's 16. Both papers were scored for environment
    # specification and parameters as though they had declared almost nothing,
    # which is a defect in this module rather than a property of the papers.
    #
    # Every name below was mined from the two papers' own text rather than
    # recalled, and the ones that collide with English or with a metric were
    # dropped or disambiguated after measuring them against all five papers.
    # Dropped: GAP (a Gaussian Approximation Potential, and also "band gap",
    # 5 hits in ALIGNN and 14 in Atomate2), SCAN (also an
    # exchange-correlation functional and an English verb), MP (also an
    # author's initials in LocusMasterTE's reference list), NOMAD (in
    # Atomate2 it is only an author affiliation, "The NOMAD Laboratory").
    # --- simulation engines --------------------------------------------------
    ("VASP", "tool", None),
    ("ABINIT", "tool", None),
    ("CP2K", "tool", None),
    ("FHI-aims", "tool", None),
    ("JDFTx", "tool", None),
    ("Quantum ESPRESSO", "tool", None),
    ("OpenMM", "tool", None),
    # --- post-processing -----------------------------------------------------
    ("LobsterPy", "library", None),
    ("LOBSTER", "tool", None),
    ("BoltzTraP", "tool", None),
    ("AMSET", "tool", None),
    ("hiPhive", "tool", None),
    ("phonopy", "tool", None),
    ("Wannier90", "tool", r"\bWannier\s*90\b"),
    # --- workflow and data infrastructure ------------------------------------
    ("pymatgen", "library", None),
    ("jobflow", "library", None),
    ("custodian", "library", None),
    ("emmet", "library", None),
    ("spglib", "library", None),
    ("MPMorph", "library", None),
    ("FireWorks", "library", None),
    ("AiiDA", "library", None),
    ("AFLOW", "library", None),
    ("MongoDB", "tool", None),
    # "ASE" alone is not usable: it is Allele-Specific Expression in ASPEN,
    # 12 occurrences, in the domain this module started in. So the Atomic
    # Simulation Environment is matched only where the paper spells it out or
    # introduces the abbreviation in parentheses.
    (
        "Atomic Simulation Environment",
        "library",
        r"\bAtomic\s+Simulation\s+Environment\b|\(ASE[\s\),;]",
    ),
    # --- machine-learned potentials and graph networks -----------------------
    ("CHGNet", "library", None),
    ("M3GNet", "library", None),
    ("NequIP", "library", None),
    ("MACE", "library", None),
    ("iCGCNN", "library", None),
    ("CGCNN", "library", None),
    ("SchNet", "library", None),
    ("MEGNet", "library", None),
    # The "++" cannot take a trailing \b: "DimeNet++ " ends on a non-word
    # character followed by a space, so the boundary never matches.
    ("DimeNet++", "library", r"\bDimeNet\s*\+\+"),
    ("DimeNet", "library", None),
    ("OrbNet", "library", None),
    ("DGL", "library", None),
    ("PyTorch Ignite", "library", r"\bpytorch[-\s]ignite\b"),
    # --- reference databases -------------------------------------------------
    # A queryable record collection, not a sequence to align against, so the
    # issue it raises when unversioned is phrased for what it is.
    ("JARVIS-DFT", "database", None),
    ("JARVIS-Tools", "library", None),
    ("JARVIS", "database", None),
    ("Materials Project", "database", None),
    ("MatPES", "database", None),
    ("OQMD", "database", None),
    ("QM9", "database", None),
    # --- language and environment -------------------------------------------
    # The rubric scores environment specification separately, and here absence
    # is the finding: a paper that never names a language version, an
    # environment file or a container has not specified an environment at all.
    ("Python", "language", r"\bPython\b"),
    # A dotted version only. Both papers report correlations as R-squared,
    # which reaches the text as "R 2" once the superscript is handled, so a
    # bare "R <digit>" matched the statistic nine times in LocusMasterTE.
    (
        "R",
        "language",
        r"\bR\s+(?:v(?:er(?:sion)?)?\.?\s?)?\d+\.\d|\bR\s+(?:package|script|librar|environment)",
    ),
    ("conda", "environment", r"\b(?:conda|Anaconda|Miniconda|Bioconda)\b"),
    ("Docker", "environment", r"\bDocker\b"),
    ("Singularity", "environment", r"\bSingularity\b"),
    ("Snakemake", "environment", r"\bSnakemake\b"),
    ("Nextflow", "environment", r"\bNextflow\b"),
    ("environment file", "environment", r"requirements\.txt|environment\.ya?ml"),
)

_COMPILED = tuple(
    (name, kind, re.compile(explicit or rf"\b{_flex(name)}\b", re.I))
    for name, kind, explicit in _SOFTWARE
)


@dataclass(slots=True)
class Software:
    name: str
    kind: Kind
    specificity: Specificity
    version: str | None = None
    assembly: str | None = None
    mentions: int = 0
    sections: list[SectionLabel] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    evidence: str = ""

    @property
    def declared(self) -> bool:
        """Named somewhere that counts as the paper claiming to use it."""
        return any(section not in _NOT_A_DECLARATION for section in self.sections)


@dataclass(slots=True)
class Parameter:
    flag: str
    value: str | None
    evidence: str


@dataclass(slots=True)
class Setting:
    """A parameter the paper itself states a value for.

    Separate from ``Parameter`` on purpose. A ``Parameter`` is a command-line
    flag, and the interesting thing about one is usually that its value is
    *missing* -- MATES names ``--outFilterMultimapNmax`` and never says what it
    was set to. A ``Setting`` always carries a value, and because the paper is
    the one stating it, it raises the floor rather than the ceiling.
    """

    name: str
    value: str
    evidence: str


@dataclass(slots=True)
class Command:
    command: str
    evidence: str


@dataclass(slots=True)
class Checklist:
    software: list[Software]
    parameters: list[Parameter]
    commands: list[Command]
    settings: list[Setting] = field(default_factory=list)

    def gaps(self) -> list[Software]:
        """Declared software the paper does not pin down."""
        return [item for item in self.software if item.declared and item.specificity != "pinned"]

    def to_dict(self) -> dict:
        pinned = [s for s in self.software if s.declared and s.specificity == "pinned"]
        declared = [s for s in self.software if s.declared]
        return {
            "summary": {
                "declared": len(declared),
                "pinned": len(pinned),
                "named_only": len([s for s in declared if s.specificity == "named_only"]),
                "deferred_to_citation": len(
                    [s for s in declared if s.specificity == "deferred_to_citation"]
                ),
                "flags_named": len(self.parameters),
                "flags_with_a_value": len([p for p in self.parameters if p.value]),
                "settings_stated": len(self.settings),
                "commands_given": len(self.commands),
            },
            "software": [asdict(s) | {"declared": s.declared} for s in self.software],
            "parameters": [asdict(p) for p in self.parameters],
            "settings": [asdict(s) for s in self.settings],
            "commands": [asdict(c) for c in self.commands],
        }


SOFTWARE_NAMES: tuple[str, ...] = tuple(name for name, _kind, _pattern in _SOFTWARE)

# What kind of thing each name is, for callers that need to tell a pipeline step
# from a library or a reference source. The repository channel uses it to decide
# what counts as an undocumented preprocessing step: a paper that does not name
# the Python package its code imports is normal, and one that does not name the
# read-trimming program it ran is not.
SOFTWARE_KINDS: dict[str, Kind] = {name: kind for name, kind, _pattern in _SOFTWARE}


def find_names(text: str) -> list[str]:
    """Canonical software names mentioned in arbitrary prose.

    Used by the grader to read which resources a ground-truth record says could
    not be recovered, so the checklist can be scored on whether it flagged those
    same ones. Deliberately the same vocabulary the detector uses: a name the
    detector cannot represent is a known blind spot, and scoring it against a
    second list would hide that rather than report it.
    """
    return [name for name, _kind, pattern in _COMPILED if pattern.search(text)]


def build(pages: list[PageText]) -> Checklist:
    """The required-resource checklist for one paper."""
    resolver = resolve(pages)
    found: dict[str, Software] = {}
    parameters: dict[str, Parameter] = {}
    settings: dict[tuple[str, str], Setting] = {}
    commands: dict[str, Command] = {}

    for page in pages:
        text, offsets = normalize_with_offsets(page.text)
        claimed: list[tuple[int, int]] = []

        for name, kind, pattern in _COMPILED:
            for match in pattern.finditer(text):
                start, end = match.span()
                if any(start < c_end and end > c_start for c_start, c_end in claimed):
                    continue
                claimed.append((start, end))
                section = resolver.at(page.page, offsets[start], page.document).label
                _record(found, name, kind, section, text, start, end)

        for match in _FLAG.finditer(text):
            flag = match.group(0)
            if flag not in parameters:
                parameters[flag] = Parameter(
                    flag=flag, value=_value_after(text, match.end()), evidence=_quote(text, match)
                )

        for name, pattern in _SETTINGS:
            for match in pattern.finditer(text):
                if _A_PROPORTION.match(text, match.end()):
                    continue
                value = match.group(1).strip().rstrip(".")
                # Keyed on the pair, not the name: ASPEN states four different
                # FDR thresholds and every one of them is a real configured
                # value. Keyed on the name alone, the paper would appear to have
                # documented one.
                key = (name, value)
                if key not in settings:
                    label = " ".join(match.group(0)[: match.start(1) - match.start()].split())
                    settings[key] = Setting(
                        name=_SETTING_TAIL.sub("", label).strip() or name,
                        value=value,
                        evidence=_quote(text, match),
                    )

        for match in _QUOTED.finditer(text):
            body = " ".join(match.group(1).split())
            # A command names a program and then its arguments. Requiring the
            # program token keeps the quoted flag MATES mentions on its own
            # ("--outFilterMultimapNmax") out of the command list, where it
            # would look like executable instructions the paper gave.
            if not _PROGRAM.match(body):
                continue
            if _FLAG.search(body) or re.search(r"\s-[A-Za-z]\b", body):
                commands.setdefault(body, Command(command=body, evidence=_quote(text, match)))

    return Checklist(
        software=sorted(found.values(), key=lambda s: (s.kind, s.name.casefold())),
        parameters=sorted(parameters.values(), key=lambda p: p.flag),
        settings=sorted(settings.values(), key=lambda s: (s.name.casefold(), s.value)),
        commands=sorted(commands.values(), key=lambda c: c.command),
    )


def _record(
    found: dict[str, Software],
    name: str,
    kind: Kind,
    section: SectionLabel,
    text: str,
    start: int,
    end: int,
) -> None:
    window = text[end : end + _VERSION_WINDOW].split(". ")[0]
    version = _VERSION.search(window)
    assembly = _ASSEMBLY.search(window)
    citation = _CITATION.match(text[end : end + 12])

    item = found.get(name)
    if item is None:
        item = Software(name=name, kind=kind, specificity="named_only")
        found[name] = item

    item.mentions += 1
    if section not in item.sections:
        item.sections.append(section)
    if assembly and not item.assembly:
        item.assembly = assembly.group(1)
    if citation and citation.group(1) not in item.citations:
        item.citations.append(citation.group(1))

    # A tool counts as pinned if *any* mention versions it. Velocyto is named
    # three times bare in MATES before the one mention that gives 0.17, so
    # judging on first mention alone reports a documented tool as a gap.
    if version and item.specificity != "pinned":
        item.specificity = "pinned"
        item.version = version.group(1)
        item.evidence = _span(text, start, end + _VERSION_WINDOW)
    elif item.specificity != "pinned":
        # Evidence has to come from the mention that carries the citation, not
        # from whichever mention came first. Otherwise the quote shows one
        # reference number and the record points at another, which sends
        # somebody to the wrong paper to look for the missing detail.
        if citation and item.specificity != "deferred_to_citation":
            item.specificity = "deferred_to_citation"
            item.evidence = _span(text, start, end + 90)
        elif not item.evidence:
            item.evidence = _span(text, start, end + 90)


def _value_after(text: str, position: int) -> str | None:
    """The value given for a flag, where one is given at all.

    MATES names ``--outFilterMultimapNmax`` and never says what it was set to,
    which is the paper's documented blocker: the multi-mapper retention
    threshold is the parameter the whole quantification turns on.
    """
    tail = text[position : position + 40]
    match = re.match(r"[\s=]+([\w./]+)", tail)
    if not match:
        return None
    candidate = match.group(1)
    return candidate if not candidate.isalpha() or len(candidate) < 4 else None


def _span(text: str, start: int, end: int) -> str:
    return " ".join(text[max(0, start - 40) : min(len(text), end)].split())


def _quote(text: str, match: re.Match) -> str:
    return _span(text, match.start(), match.end() + 40)
