"""How the repository says to run the thing, and what it needs to be handed.

Blueprint section 15 asks nine questions of a repository. This module answers
the ones about execution -- what the entry point is, what command runs the
experiment, what datasets and weights are required -- and section 16's
consistency checks that follow from them: files referenced but absent,
environment variables read but undocumented.

What counts as an entry point depends on the language, and getting that wrong
costs a whole criterion. A Python project declares one in ``console_scripts`` or
ships a shell script; an R package declares its public surface in ``NAMESPACE``
and shows how to call it in the README. Reading only the Python shapes scored
ASPEN -- a published, installable R package with a worked Quick start -- zero out
of ten for execution instructions, which was a statement about this reader
rather than about the package.

The distinction that makes this useful is between **a command existing** and
**its inputs being there**. LocusMasterTE ships ``run_sample.sh``, which runs
out of the box and is why its code availability scored well in the reproduction
attempt. The same script names ``annotation.gtf`` -- which is present, and holds
twenty records, where the published analysis quantified tens of thousands of
elements. The command is real; the input is a demo. Reporting only that the
command exists would describe the repository as more complete than it is, and
reporting only the file as missing would be false.

Nothing here runs anything. Shell scripts are read as text and Python through
``ast``.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass, field

from reprolens.extraction.checklist import SOFTWARE_NAMES, find_names
from reprolens.repository.inventory import Inventory, RepoFile
from reprolens.repository.manifests import setup_kwargs

Status = str  # "present" | "absent" | "demo_scale" | "user_supplied"

# Extensions that name an input a pipeline is handed, rather than source code.
_INPUT_SUFFIXES = (
    ".gtf",
    ".gff",
    ".gff3",
    ".bed",
    ".saf",
    ".bam",
    ".sam",
    ".cram",
    ".fa",
    ".fasta",
    ".fai",
    ".fq",
    ".fastq",
    ".fastq.gz",
    ".fq.gz",
    ".vcf",
    ".tsv",
    ".csv",
    ".txt",
    ".npz",
    ".h5ad",
    ".pt",
    ".pth",
    ".ckpt",
)

# First words in a shell line that are not the program being run.
_SHELL_WORDS = frozenset(
    """
    if then else elif fi for while do done case esac function return exit break continue
    echo printf cd mkdir rm mv cp ln touch chmod chown export set unset source eval read
    cat sed awk grep egrep cut sort uniq head tail tr wc tee xargs find ls pwd date sleep
    wait time test true false local declare shift trap
    """.split()
)

# Environment variables whose value the surrounding tooling supplies, so reading
# one is not an undocumented requirement placed on the user.
_AMBIENT_ENV = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "PWD",
        "TMPDIR",
        "SHELL",
        "LANG",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "LD_LIBRARY_PATH",
        # Supplied by the shell itself.
        "BASH_SOURCE",
        "BASH_VERSION",
        "IFS",
        "OSTYPE",
        "HOSTNAME",
        "RANDOM",
        "SECONDS",
    }
)

_REDIRECTS = frozenset({">", ">>", "2>", "&>", "2>>", "1>"})
_OUTPUT_FLAGS = frozenset({"-o", "-O", "--out", "--output", "--outfile", "-out"})

_FLAG_WITH_VALUE = re.compile(r"(--[A-Za-z][\w-]*)(?:[=\s]+([^\s'\"]+))?")
# "export(estim_bbparams)" in an R NAMESPACE: the package's public surface, and
# the closest thing R has to a console script.
_R_EXPORT = re.compile(r"^\s*(?:export|exportMethods|exportClasses)\s*\(\s*([\w.]+)", re.M)

# An R named argument: "min_cells = 5", "thetaFilter = 0.001". The lookarounds
# keep "==", "<=" and "!=" comparisons out.
_R_NAMED_ARG = re.compile(r"\b([A-Za-z.][\w.]*)\s*(?<![=!<>])=(?!=)\s*([^,()\s]+)")
_BARE_IDENTIFIER = re.compile(r"[A-Za-z.][\w.]*")

# How an R package is installed, and how one is loaded.
_R_SETUP = re.compile(
    r"^(?:library|require|suppressMessages)\s*\(|^(?:devtools|remotes|BiocManager|pak)::|"
    r"^install\.packages\s*\(",
    re.I,
)

_SHELL_VAR = re.compile(r"\$\{?([A-Z][A-Z0-9_]{2,})\}?")
_SHELL_ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_]\w*)=", re.M)
# Programs the paper-side vocabulary already knows. A documented command whose
# program is one of these is a pipeline step with its flags spelled out --
# LocusMasterTE's README gives the full STAR invocation that way, twenty flags
# and their values, which is the best parameter evidence either document holds.
_KNOWN_PROGRAMS = frozenset(name.casefold() for name in SOFTWARE_NAMES)
# Every triple-backtick span, paired in order. Matching the language tag in the
# opening fence looks tidier and is wrong: LocusMasterTE's README writes some
# commands as a one-line "```bash script.sh args```", so a pattern that insists
# on a newline after the tag skips that opening fence and pairs its closing one
# with the next block's opening fence -- which read four paragraphs of prose as
# a code block, and reported a sentence about Telescope as a command to run.
_FENCE = re.compile(r"```(.*?)```", re.S)
_INLINE_CODE = re.compile(r"`([^`\n]{4,400})`")
# Prose, not a command: a sentence boundary inside the line.
_SENTENCE = re.compile(r"[.!?]\s")
_HAS_FLAG = re.compile(r"(?:^|\s)-{1,2}[A-Za-z]")
# The argument has to look like a script. Without that, the prose "python 3.6 is
# required" parses as a command to run the file "3.6".
_RUNNER = re.compile(
    r"^(?:python3?|bash|sh|Rscript|snakemake|nextflow|make)\s+([\w./-]+\.(?:py|sh|R|r|ipynb|smk))\b",
    re.I,
)


@dataclass(slots=True)
class EntryPoint:
    kind: str  # "console_script" | "shell_script" | "notebook" | "module" | "documented"
    name: str
    command: str
    source: str


@dataclass(slots=True)
class Input:
    """A file an entry-point command names, and whether the repository has it."""

    path: str  # as written in the command
    status: Status
    named_by: str
    detail: str = ""


@dataclass(slots=True)
class Flag:
    flag: str
    value: str | None
    source: str


@dataclass(slots=True)
class ToolCall:
    """A recognized tool the repository invokes, with where it does so."""

    tool: str
    source: str
    evidence: str


@dataclass(slots=True)
class EnvironmentVariable:
    name: str
    source: str
    documented: bool


@dataclass(slots=True)
class Execution:
    entry_points: list[EntryPoint] = field(default_factory=list)
    inputs: list[Input] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    env_vars: list[EnvironmentVariable] = field(default_factory=list)
    tools_called: list[ToolCall] = field(default_factory=list)
    documented_in: list[str] = field(default_factory=list)

    @property
    def runnable(self) -> list[EntryPoint]:
        """Entry points that come with a command, not just a file to look at."""
        return [e for e in self.entry_points if e.command]

    @property
    def missing_inputs(self) -> list[Input]:
        """Inputs a repository command names and the repository does not hold.

        A placeholder in a documentation example is not one of these.
        """
        return [i for i in self.inputs if i.status in ("absent", "demo_scale")]

    def to_dict(self) -> dict:
        return {
            "summary": {
                "entry_points": len(self.entry_points),
                "with_a_command": len(self.runnable),
                "documented_in": len(self.documented_in),
                "inputs_named": len(self.inputs),
                "inputs_absent": len([i for i in self.inputs if i.status == "absent"]),
                "inputs_demo_scale": len([i for i in self.inputs if i.status == "demo_scale"]),
                "inputs_user_supplied": len(
                    [i for i in self.inputs if i.status == "user_supplied"]
                ),
                "flags_with_a_value": len([f for f in self.flags if f.value]),
                "undocumented_env_vars": len([v for v in self.env_vars if not v.documented]),
            },
            "entry_points": [asdict(e) for e in self.entry_points],
            "inputs": [asdict(i) for i in self.inputs],
            "flags": [asdict(f) for f in self.flags],
            "env_vars": [asdict(v) for v in self.env_vars],
            "tools_called": [asdict(t) for t in self.tools_called],
            "documented_in": self.documented_in,
        }


def read(inventory: Inventory) -> Execution:
    """Entry points, inputs, flags and called tools across every repository."""
    found = Execution()
    documentation = "\n".join(inventory.read(f) for f in inventory.by_kind("docs"))

    for file in inventory.named("setup.py"):
        found.entry_points += _console_scripts(inventory.read(file), file.label)

    exports: set[str] = set()
    for file in inventory.named("NAMESPACE"):
        names = _R_EXPORT.findall(inventory.read(file))
        exports.update(names)
        # Recorded with no command of its own: an exported function is a named
        # surface, not an invocation. What you actually run is the call the
        # documentation shows, which is picked up below.
        found.entry_points += [
            EntryPoint(kind="r_export", name=name, command="", source=file.label)
            for name in sorted(names)
        ]

    for file in inventory.by_kind("shell"):
        text = inventory.read(file)
        commands = _command_lines(text)
        found.entry_points.append(
            EntryPoint(
                kind="shell_script",
                name=file.name,
                command=commands[0] if commands else "",
                source=file.label,
            )
        )

    for file in inventory.named("__main__.py"):
        found.entry_points.append(
            EntryPoint(
                kind="module",
                name=file.path.rsplit("/", 2)[-2] if "/" in file.path else file.repo,
                command="",
                source=file.label,
            )
        )

    for file in inventory.by_kind("notebook"):
        found.entry_points.append(
            EntryPoint(kind="notebook", name=file.name, command="", source=file.label)
        )

    scripts = {e.name for e in found.entry_points if e.kind == "console_script"}
    for file in inventory.by_kind("docs"):
        found.entry_points += _documented_commands(
            inventory.read(file), file.label, scripts, exports
        )

    found.documented_in = sorted({e.source for e in found.entry_points if e.kind == "documented"})

    index = inventory.basenames()
    for entry in found.runnable:
        # An argument in a documentation example is a placeholder by nature:
        # LocusMasterTE's wrapper example passes "hg38.fasta", which no
        # repository should be expected to ship. Those are recorded as inputs
        # the user must bring rather than as files the repository is missing --
        # which is itself one of the questions blueprint section 15 asks.
        illustrative = entry.kind == "documented"
        for token in _input_tokens(entry.command):
            found.inputs.append(_resolve_input(token, entry.source, index, illustrative))
        found.flags += _flags(entry.command, entry.source)

    found.env_vars = _env_vars(inventory, documentation)
    found.tools_called = _tools_called(inventory)
    return found


def _console_scripts(text: str, source: str) -> list[EntryPoint]:
    """``entry_points={"console_scripts": ["name=module:function"]}``.

    The strongest kind of entry point available from a repository: it names a
    command that exists after installation, with no guessing about which file to
    run.
    """
    node = setup_kwargs(text).get("entry_points")
    if not isinstance(node, ast.Dict):
        return []
    out: list[EntryPoint] = []
    for key, value in zip(node.keys, node.values, strict=False):
        if not (isinstance(key, ast.Constant) and key.value == "console_scripts"):
            continue
        if not isinstance(value, (ast.List, ast.Tuple)):
            continue
        for element in value.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                name = element.value.partition("=")[0].strip()
                out.append(
                    EntryPoint(kind="console_script", name=name, command=name, source=source)
                )
    return out


def _code_blocks(text: str) -> list[str]:
    """Code spans in a documentation file: fenced blocks, then inline spans."""
    blocks: list[str] = []
    for raw in _FENCE.findall(text):
        first, newline, rest = raw.partition("\n")
        tag = first.strip()
        # "```bash\n..." opens with a bare language tag; "```samtools collate
        # -o ...```" opens with the command itself, and dropping its first word
        # would lose the program being run.
        blocks.append(rest if newline and tag.isalnum() else raw)
    blocks += _INLINE_CODE.findall(_FENCE.sub(" ", text))
    return blocks


def _documented_commands(
    text: str, source: str, scripts: set[str], exports: set[str] | None = None
) -> list[EntryPoint]:
    """Commands shown in the documentation, fenced or inline.

    ``scripts`` are the console-script names the packaging declares, so that
    "LocusMasterTE bulk assign -h" in a README is recognized as this project's
    own command rather than an unknown word. ``exports`` does the same job for
    an R package, where the call is rarely the first word of its line --
    "bb_init_params <- estim_bbparams(counts, min_cells = 5)" is an invocation
    whose head token is a variable.
    """
    exported = exports or set()
    out: list[EntryPoint] = []
    seen: set[str] = set()
    for block in _code_blocks(text):
        for line in _command_lines(block):
            head = line.split()[0]
            calls_an_export = any(f"{name}(" in line.replace(" (", "(") for name in exported)
            if calls_an_export or _R_SETUP.match(line):
                if line not in seen and not _SENTENCE.search(line):
                    seen.add(line)
                    out.append(
                        EntryPoint(kind="documented", name=head, command=line, source=source)
                    )
                continue
            names_a_script = bool(_RUNNER.match(line)) or head in scripts
            if not (names_a_script or head in ("snakemake", "nextflow")):
                # A recognized tool is admitted for its flags and values, so a
                # line that carries none of them adds nothing and is probably
                # prose: "htseq and intervaltree appear to yield identical..."
                # sits in a fenced block in LocusMasterTE's README.
                if head.casefold() not in _KNOWN_PROGRAMS or not _HAS_FLAG.search(line):
                    continue
            if line in seen or _SENTENCE.search(line):
                continue
            seen.add(line)
            out.append(EntryPoint(kind="documented", name=head, command=line, source=source))
    return out


def _command_lines(text: str) -> list[str]:
    """Lines that invoke a program, with comments, blanks and assignments gone."""
    out: list[str] = []
    # A long invocation is wrapped with trailing backslashes. Reading those
    # lines separately keeps only the first few flags and drops the rest, which
    # for the STAR command in LocusMasterTE's README is most of it.
    joined = re.sub(r"\\\s*\n\s*", " ", text)
    for raw in joined.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("}", "{", ")")):
            continue
        first = line.split()[0]
        if "=" in first or first in _SHELL_WORDS or first.startswith(("$", "-")):
            continue
        out.append(line)
    return out


def _input_tokens(command: str) -> list[str]:
    """Arguments that look like a file this command is handed.

    A token containing a shell variable is skipped: ``$GTF`` is a parameter of
    the wrapper script, and whether the file behind it exists is a question
    about the caller, not about the repository.
    """
    tokens: list[str] = []
    is_output = False
    for token in command.split():
        token = token.strip("'\"")
        if token in _REDIRECTS or token in _OUTPUT_FLAGS:
            # Everything a redirect or an -o flag introduces is produced by the
            # command, not required by it. "minimap2 ... > processed.sam" was
            # otherwise reported as a file the repository is missing.
            is_output = True
            continue
        if is_output:
            is_output = False
            continue
        if "$" in token or token.startswith("-") or "=" in token:
            continue
        if token.casefold().endswith(_INPUT_SUFFIXES):
            tokens.append(token)
    return tokens


def _resolve_input(
    token: str, named_by: str, index: dict[str, list[RepoFile]], illustrative: bool = False
) -> Input:
    name = token.rsplit("/", 1)[-1]
    candidates = index.get(name.casefold(), [])
    if not candidates:
        return Input(
            path=token,
            status="user_supplied" if illustrative else "absent",
            named_by=named_by,
        )
    file = candidates[0]
    if file.demo_scale:
        return Input(
            path=token,
            status="demo_scale",
            named_by=named_by,
            detail=(
                f"{file.label} holds {file.records} records "
                f"({file.size} bytes), too few to be a reference annotation"
            ),
        )
    return Input(path=token, status="present", named_by=named_by, detail=file.label)


def _flags(command: str, source: str) -> list[Flag]:
    """Configuration the command spells out, in either calling convention.

    A shell flag and an R named argument are the same evidence: a parameter of
    the published analysis, written down with a value. ASPEN's Quick start gives
    "min_cells = 5", "delta_set = 50" and "thetaFilter = 0.001" and the app read
    none of them, because it only knew how to look for "--flag value".
    """
    out: list[Flag] = []
    if "(" in command and not command.lstrip().startswith("-"):
        for match in _R_NAMED_ARG.finditer(command):
            value = match.group(2).strip("\"'")
            # A bare identifier is a reference to something defined elsewhere,
            # not a value: "min_cells = 5" documents a parameter and
            # "genes.excl = genes2remove" documents only that one is passed.
            # Same rule as a shell flag whose value is "$VAR" -- and the "$"
            # half of that rule has to be applied here too, because this branch
            # also sees shell. Its guard is only "has a paren, does not start
            # with a dash", which `IFS="$(printf '\t')"` satisfies: MATES's four
            # barcode-splitting scripts each reported a flag `IFS` valued `$`,
            # and those four were a third of the paper's valued flags.
            if value and (_BARE_IDENTIFIER.fullmatch(value) or "$" in value):
                value = None
            out.append(Flag(flag=match.group(1), value=value or None, source=source))
    for match in _FLAG_WITH_VALUE.finditer(command):
        value = match.group(2)
        # A flag whose value is the next flag has no value; one whose value is a
        # shell variable has a value only for whoever set the variable.
        if value and (value.startswith("-") or "$" in value):
            value = None
        out.append(Flag(flag=match.group(1), value=value, source=source))
    return out


def _env_vars(inventory: Inventory, documentation: str) -> list[EnvironmentVariable]:
    """Variables the code reads from the environment, and whether docs name them."""
    found: dict[str, str] = {}

    for file in inventory.by_kind("python"):
        if not file.path.endswith(".py"):
            continue
        try:
            tree = ast.parse(inventory.read(file))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            name = _env_name(node)
            if name and name not in _AMBIENT_ENV:
                found.setdefault(name, file.label)

    for file in inventory.by_kind("shell"):
        text = inventory.read(file)
        assigned = set(_SHELL_ASSIGN.findall(text))
        # A variable inside a commented-out block is not read by anything.
        # MATES's velocyto script keeps a disabled conda-activation preamble,
        # which otherwise reported three undocumented environment variables.
        live = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        for name in _SHELL_VAR.findall(live):
            if name not in _AMBIENT_ENV and name not in assigned:
                found.setdefault(name, file.label)

    return [
        EnvironmentVariable(
            name=name,
            source=source,
            # On a word boundary: "TPM" appears inside "long_read_TPM.txt" in
            # every README, which is not documentation of a variable named TPM.
            documented=bool(re.search(rf"\b{re.escape(name)}\b", documentation)),
        )
        for name, source in sorted(found.items())
        # A docs build's own configuration is not part of the published method.
        if not source.partition(":")[2].startswith(("doc/", "docs/"))
    ]


def _env_name(node: ast.AST) -> str | None:
    """``os.environ["X"]``, ``os.environ.get("X")`` or ``os.getenv("X")``."""
    if isinstance(node, ast.Subscript):
        target = node.value
        if isinstance(target, ast.Attribute) and target.attr == "environ":
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return key.value
        return None
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        is_get = isinstance(func, ast.Attribute) and (
            func.attr == "getenv"
            or (
                func.attr == "get"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "environ"
            )
            or (
                func.attr == "get"
                and isinstance(func.value, ast.Name)
                and func.value.id == "environ"
            )
        )
        if is_get and isinstance(node.args[0], ast.Constant):
            value = node.args[0].value
            return value if isinstance(value, str) else None
    return None


def _tools_called(inventory: Inventory) -> list[ToolCall]:
    """Recognized tools the repository's own scripts and notebooks invoke.

    Uses the paper-side checklist's vocabulary deliberately. The point of this
    list is to be compared against the tools the paper names, and a comparison
    between two different vocabularies would report the vocabularies' difference
    rather than the documents'.

    Read per file rather than over the concatenation, so each tool carries the
    file and the line that names it. A finding that a paper omits a step the
    code performs is only worth anything with the code to point at.
    """
    found: dict[str, ToolCall] = {}
    for file in inventory.by_kind("shell", "docs", "notebook"):
        raw = inventory.read(file)
        text = _notebook_source(raw) if file.kind == "notebook" else raw
        for tool in find_names(text):
            if tool not in found:
                found[tool] = ToolCall(
                    tool=tool, source=file.label, evidence=_line_with(text, tool)
                )
    return [found[name] for name in sorted(found, key=str.casefold)]


def _line_with(text: str, tool: str) -> str:
    """The first line naming this tool, trimmed, as the evidence quote."""
    pattern = re.compile(rf"\b{re.escape(tool)}\b", re.I)
    for line in text.splitlines():
        if pattern.search(line):
            return " ".join(line.split())[:200]
    return ""


def _notebook_source(raw: str) -> str:
    """Just the code and markdown of a notebook, never its stored outputs.

    An output cell can contain anything the run printed, including the contents
    of other files, and attributing that to the repository as a command it runs
    would be wrong.
    """
    try:
        document = json.loads(raw)
    except ValueError:
        return ""
    lines: list[str] = []
    for cell in document.get("cells", []):
        if isinstance(cell, dict) and cell.get("cell_type") in ("code", "markdown"):
            source = cell.get("source", "")
            lines.append("".join(source) if isinstance(source, list) else str(source))
    return "\n".join(lines)
