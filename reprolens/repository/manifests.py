"""What the repositories say they need, and whether the declarations agree.

The paper-side checklist asks whether a named tool carries a version. This asks
the harder question the repository can actually answer: is there a declaration
at all, does it pin anything, and do the declarations contradict each other.

Three findings this module is built to produce, each seen in the benchmark
repositories and each invisible from the paper:

* **A lower bound is not a pin.** LocusMasterTE's ``setup.py`` asks for
  ``numpy>=1.16.3``, which resolves to whatever numpy exists on the day you
  install it -- six years of releases later, a different library. The README
  pins the same environment properly (``conda create ... numpy=1.16.3``), so the
  repository both does and does not specify its environment depending on which
  file you read.
* **Two manifests disagreeing.** MATES pins ``torch==2.0.1`` in
  ``requirements.txt`` and ``torch==2.0.0`` in ``setup.py``. Blueprint section
  16 names this class directly, and no reading of either file alone finds it.
* **A dependency the code imports and no manifest declares.** This is the gap
  that produces an install which succeeds and then fails at runtime.

Imports are read with ``ast``, which parses without executing. Nothing in this
package runs repository code.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from dataclasses import asdict, dataclass, field

from reprolens.repository.inventory import Inventory, RepoFile

Ecosystem = str  # "python" | "conda" | "r" | "system"
Pinning = str  # "pinned" | "bounded" | "unconstrained"

# Python versions already out of support, with the date support ended. Used to
# report a pinned interpreter that no longer receives fixes, which is the
# documented cause of LocusMasterTE's multi-week environment setup.
#
# Deliberately stops at 3.9: the table has to be right rather than complete, and
# a version near its end-of-life date is the case where being wrong is easiest.
PYTHON_END_OF_LIFE: dict[str, str] = {
    "2.7": "2020-01-01",
    "3.5": "2020-09-13",
    "3.6": "2021-12-23",
    "3.7": "2023-06-27",
    "3.8": "2024-10-07",
    "3.9": "2025-10-31",
}

# Import name -> the distribution that provides it, for the cases where they
# differ. Without this, every project using scikit-learn reports an undeclared
# dependency on "sklearn".
_IMPORT_TO_DISTRIBUTION = {
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "cv2": "opencv-python",
    "pil": "pillow",
    "yaml": "pyyaml",
    "bio": "biopython",
    "pkg_resources": "setuptools",
    "dateutil": "python-dateutil",
    "mpl_toolkits": "matplotlib",
    # The "future" distribution installs both "future" and "past".
    "past": "future",
    "torch_geometric": "torch-geometric",
    "umap": "umap-learn",
}

_REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9][\w.\-]*)\s*(?:\[[^\]]*\])?\s*(?P<constraint>[=<>!~^].*)?$"
)
_CONDA_SPEC = re.compile(r"^(?P<name>[A-Za-z0-9][\w.\-]*)(?:(?P<constraint>[=<>].*))?$")
_LIBRARY_CALL = re.compile(r"""^\s*(?:library|require)\s*\(\s*['"]?([\w.]+)['"]?""", re.M)
_INSTALL_PACKAGES = re.compile(r"""install\.packages\s*\(\s*['"]([\w.]+)['"]""")
_PIP_INSTALL = re.compile(r"\bpip3?\s+install\s+(?P<args>[^\n|&;]+)")
_CONDA_LINE = re.compile(r"\bconda\s+(?:create|install)\s+(?P<args>[^\n|&;]+)")
_DOCKER_FROM = re.compile(r"^\s*FROM\s+(?P<image>\S+)", re.M | re.I)
_PYTHON_SPEC = re.compile(r"^python(?P<constraint>[=<>~!].*)?$", re.I)


@dataclass(slots=True)
class Dependency:
    name: str
    ecosystem: Ecosystem
    constraint: str  # "==2.0.1", ">=1.16.3", "" when unconstrained
    pinning: Pinning
    source: str  # repo:path the declaration was read from

    @property
    def purpose(self) -> str:
        """Whether this declaration is for running the project or building docs.

        MATES keeps a second copy of its requirements under ``docs/`` for Read
        the Docs. Counting those as project dependencies would report 213
        declared packages where the pipeline has 100, and would attribute the
        torch disagreement to a documentation file.
        """
        path = self.source.partition(":")[2]
        return "docs" if path.startswith(("doc/", "docs/")) else "runtime"

    @property
    def prose_only(self) -> bool:
        """Declared in documentation, where no installer will read it."""
        return self.source.endswith((".md", ".rst", ".rsd"))


@dataclass(slots=True)
class Import:
    """A module the code actually uses, as opposed to one a manifest declares."""

    name: str
    ecosystem: Ecosystem  # "python" | "r"
    source: str


@dataclass(slots=True)
class Interpreter:
    ecosystem: Ecosystem  # "python" | "r"
    version: str
    pinning: Pinning
    source: str
    end_of_life: str | None = None  # the date support ended, when it has

    @property
    def prose_only(self) -> bool:
        return self.source.endswith((".md", ".rst", ".rsd"))


@dataclass(slots=True)
class Conflict:
    name: str
    left_constraint: str
    left_source: str
    right_constraint: str
    right_source: str


@dataclass(slots=True)
class Manifests:
    dependencies: list[Dependency] = field(default_factory=list)
    interpreters: list[Interpreter] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    manifest_files: list[str] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    undeclared_imports: list[Import] = field(default_factory=list)
    # Languages with source files in the tree. An R script with no R manifest
    # anywhere is a whole missing environment, not a missing version.
    languages: list[str] = field(default_factory=list)
    unmanaged_languages: list[str] = field(default_factory=list)

    @property
    def pinned(self) -> list[Dependency]:
        return [d for d in self.runtime if d.pinning == "pinned"]

    @property
    def runtime(self) -> list[Dependency]:
        return [d for d in self.dependencies if d.purpose == "runtime"]

    @property
    def installable(self) -> list[Dependency]:
        """Declarations in a file an installer reads, as opposed to in prose.

        A README that documents the right versions is better than nothing and
        worse than a manifest: ``pip install .`` never sees it.
        """
        return [d for d in self.runtime if not d.prose_only]

    def distinct_pinning(self) -> dict[str, Pinning]:
        """The tightest constraint each distinct package carries anywhere.

        Per package, not per declaration. LocusMasterTE asks for
        ``numpy>=1.16.3`` in setup.py and ``numpy=1.16.3`` in its README; that
        is one dependency with a resolvable version, not one good declaration
        and one bad one. Counting declarations instead measures how many times
        the authors wrote a name down, which is not a property of the
        environment -- and it penalised the repository for documenting the same
        package twice, once loosely and once exactly.
        """
        rank = {"unconstrained": 0, "bounded": 1, "pinned": 2}
        tightest: dict[str, Pinning] = {}
        for dependency in self.runtime:
            key = _normalize(dependency.name)
            current = tightest.get(key)
            if current is None or rank[dependency.pinning] > rank[current]:
                tightest[key] = dependency.pinning
        return tightest

    def to_dict(self) -> dict:
        distinct = self.distinct_pinning()
        return {
            "summary": {
                "declared": len(self.runtime),
                "distinct_packages": len(distinct),
                "distinct_pinned": len([v for v in distinct.values() if v == "pinned"]),
                "pinned": len(self.pinned),
                "bounded": len([d for d in self.runtime if d.pinning == "bounded"]),
                "unconstrained": len([d for d in self.runtime if d.pinning == "unconstrained"]),
                "in_an_installable_manifest": len(self.installable),
                "conflicts": len(self.conflicts),
                "imports": len(self.imports),
                "undeclared_imports": len(self.undeclared_imports),
            },
            "manifest_files": self.manifest_files,
            "interpreters": [asdict(i) for i in self.interpreters],
            "dependencies": [asdict(d) | {"purpose": d.purpose} for d in self.dependencies],
            "conflicts": [asdict(c) for c in self.conflicts],
            "imports": [asdict(i) for i in self.imports],
            "undeclared_imports": [asdict(i) for i in self.undeclared_imports],
            "languages": self.languages,
            "unmanaged_languages": self.unmanaged_languages,
        }


def read(inventory: Inventory) -> Manifests:
    """Dependency and environment declarations across every fetched repository."""
    found = Manifests()

    for file in inventory.by_kind("manifest"):
        found.manifest_files.append(file.label)
        _read_manifest(inventory, file, found)

    # Documentation counts as a declaration, recorded with its source so the
    # difference from an installable manifest stays visible downstream.
    for file in inventory.by_kind("docs"):
        _read_prose(inventory, file, found)

    # An R ``library()`` call is a use, not a declaration -- the exact
    # counterpart of a Python ``import``. Recording it as a dependency was the
    # first thing tried here and it hid the finding that matters: it made R look
    # like a managed environment because something, somewhere, had named every
    # package. Nothing had declared one.
    found.imports = _python_imports(inventory) + _r_imports(inventory)
    found.undeclared_imports = _undeclared(found)
    found.languages, found.unmanaged_languages = _languages(inventory, found)
    found.conflicts = _conflicts(found.dependencies)
    return found


def setup_kwargs(text: str) -> dict[str, ast.expr]:
    """The keyword arguments of a ``setup(...)`` call in a setup.py.

    Parsed, never executed: ``setup.py`` is arbitrary code and LocusMasterTE's
    reads environment variables and cythonizes an extension at import time.
    Shared with the execution reader, which wants ``entry_points`` from the same
    call.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            name = getattr(node.func, "id", "")
        if name == "setup":
            return {kw.arg: kw.value for kw in node.keywords if kw.arg}
    return {}


def _r_imports(inventory: Inventory) -> list[Import]:
    """``library()`` and ``require()`` calls across the R sources."""
    out: list[Import] = []
    for file in inventory.by_kind("r"):
        text = inventory.read(file)
        assigned = set(re.findall(r"^\s*([\w.]+)\s*(?:<-|=[^=])", text, re.M))
        names = {*_LIBRARY_CALL.findall(text), *_INSTALL_PACKAGES.findall(text)}
        # "ref_genome <- \"BSgenome.Hsapiens.UCSC.hg38\"" then
        # "library(ref_genome, character.only = TRUE)" names a variable, not a
        # package, and reporting it as an undeclared dependency would be wrong.
        out += [Import(name, "r", file.label) for name in sorted(names - assigned)]
    return out


def _read_manifest(inventory: Inventory, file: RepoFile, found: Manifests) -> None:
    name = file.name.casefold()
    text = inventory.read(file)
    if not text:
        return

    if name.startswith("requirements") and name.endswith(".txt"):
        found.dependencies += _requirements(text, file.label)
    elif name == "setup.py":
        found.dependencies += _setup_py(text, file.label)
        _setup_python_requires(text, file.label, found)
    elif name == "pyproject.toml":
        found.dependencies += _pyproject(text, file.label, found)
    elif name in ("environment.yml", "environment.yaml", "conda.yml", "conda.yaml"):
        found.dependencies += _conda_yaml(text, file.label, found)
    elif name == "dockerfile":
        _dockerfile(text, file.label, found)
    elif name == "description":
        found.dependencies += _r_description(text, file.label)
    elif name == "renv.lock":
        found.dependencies += _renv_lock(text, file.label)


def _requirements(text: str, source: str) -> list[Dependency]:
    out: list[Dependency] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _REQUIREMENT.match(line)
        if not match:
            continue
        constraint = (match.group("constraint") or "").strip()
        out.append(
            Dependency(
                name=match.group("name"),
                ecosystem="python",
                constraint=constraint,
                pinning=_pinning(constraint),
                source=source,
            )
        )
    return out


def _setup_py(text: str, source: str) -> list[Dependency]:
    node = setup_kwargs(text).get("install_requires")
    return [
        dependency
        for spec in _string_list(node)
        if (dependency := _one_requirement(spec, source)) is not None
    ]


def _setup_python_requires(text: str, source: str, found: Manifests) -> None:
    node = setup_kwargs(text).get("python_requires")
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        _record_python(node.value, source, found)


def _pyproject(text: str, source: str, found: Manifests) -> list[Dependency]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    project = data.get("project", {})
    if isinstance(project.get("requires-python"), str):
        _record_python(project["requires-python"], source, found)
    out: list[Dependency] = []
    for spec in project.get("dependencies", []) or []:
        if isinstance(spec, str) and (dependency := _one_requirement(spec, source)):
            out.append(dependency)
    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for name, constraint in (poetry or {}).items():
        if name.casefold() == "python":
            if isinstance(constraint, str):
                _record_python(constraint, source, found)
            continue
        text_constraint = constraint if isinstance(constraint, str) else ""
        out.append(
            Dependency(
                name=name,
                ecosystem="python",
                constraint=text_constraint,
                pinning=_pinning(text_constraint),
                source=source,
            )
        )
    return out


def _conda_yaml(text: str, source: str, found: Manifests) -> list[Dependency]:
    """The ``dependencies:`` block of an environment file.

    Read line by line rather than with a YAML parser: this is the only YAML
    shape the project needs, and the alternative is a dependency of its own in a
    module whose subject is unnecessary dependencies.
    """
    out: list[Dependency] = []
    in_block = False
    in_pip = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^dependencies\s*:", stripped):
            in_block = True
            continue
        if in_block and not raw.startswith((" ", "\t", "-")):
            in_block = False
        if not in_block:
            continue
        if re.match(r"^-\s*pip\s*:", stripped):
            in_pip = True
            continue
        if not stripped.startswith("-"):
            continue
        spec = stripped.lstrip("- ").strip().strip("'\"")
        if not spec or spec.endswith(":"):
            continue
        ecosystem = "python" if in_pip else "conda"
        if (dependency := _one_conda_spec(spec, source, ecosystem, found)) is not None:
            out.append(dependency)
    return out


def _dockerfile(text: str, source: str, found: Manifests) -> None:
    for match in _DOCKER_FROM.finditer(text):
        image = match.group("image")
        base, _, tag = image.partition(":")
        if base.casefold().endswith("python") and tag:
            _record_python(f"=={tag}", source, found)
        else:
            found.interpreters.append(
                Interpreter(
                    ecosystem="container",
                    version=image,
                    pinning="pinned" if tag and tag != "latest" else "unconstrained",
                    source=source,
                )
            )
    for match in _PIP_INSTALL.finditer(text):
        found.dependencies += _pip_arguments(match.group("args"), source)


def _r_description(text: str, source: str) -> list[Dependency]:
    out: list[Dependency] = []
    for field_name in ("Imports", "Depends", "Suggests"):
        match = re.search(rf"^{field_name}:\s*(.+?)(?=^\S|\Z)", text, re.M | re.S)
        if not match:
            continue
        for entry in match.group(1).split(","):
            entry = " ".join(entry.split())
            if not entry:
                continue
            name, _, constraint = entry.partition(" ")
            constraint = constraint.strip("()")
            out.append(
                Dependency(
                    name=name,
                    ecosystem="r",
                    constraint=constraint,
                    pinning=_pinning(constraint),
                    source=source,
                )
            )
    return out


def _renv_lock(text: str, source: str) -> list[Dependency]:
    try:
        import json

        data = json.loads(text)
    except ValueError:
        return []
    packages = data.get("Packages", {})
    return [
        Dependency(
            name=name,
            ecosystem="r",
            constraint=f"=={entry.get('Version', '')}" if entry.get("Version") else "",
            pinning="pinned" if entry.get("Version") else "unconstrained",
            source=source,
        )
        for name, entry in (packages or {}).items()
        if isinstance(entry, dict)
    ]


def _read_prose(inventory: Inventory, file: RepoFile, found: Manifests) -> None:
    """Install instructions written in documentation rather than a manifest."""
    text = inventory.read(file)
    if not text:
        return
    for match in _CONDA_LINE.finditer(text):
        for spec in _tokens(match.group("args")):
            dependency = _one_conda_spec(spec, file.label, "conda", found)
            if dependency is not None:
                found.dependencies.append(dependency)
    for match in _PIP_INSTALL.finditer(text):
        found.dependencies += _pip_arguments(match.group("args"), file.label)


def _pip_arguments(arguments: str, source: str) -> list[Dependency]:
    out: list[Dependency] = []
    for spec in _tokens(arguments):
        if (dependency := _one_requirement(spec, source)) is not None:
            out.append(dependency)
    return out


def _tokens(arguments: str) -> list[str]:
    """Package specs from a shell command's arguments, flags dropped."""
    tokens: list[str] = []
    skip_next = False
    for token in arguments.split():
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            # "-c bioconda" and "-n LocusMasterTE" both take a value that is not
            # a package, so the flag's argument is skipped with it.
            skip_next = token in ("-c", "-n", "-p", "--channel", "--name", "--prefix", "-r", "-f")
            continue
        tokens.append(token.strip("'\"`"))
    return tokens


def _one_requirement(spec: str, source: str) -> Dependency | None:
    spec = spec.split("#", 1)[0].strip().strip("'\"")
    spec = spec.split(";", 1)[0].strip()  # drop an environment marker
    if not spec or spec.startswith(("-", ".", "/")):
        return None
    match = _REQUIREMENT.match(spec)
    if not match:
        return None
    constraint = (match.group("constraint") or "").strip()
    return Dependency(
        name=match.group("name"),
        ecosystem="python",
        constraint=constraint,
        pinning=_pinning(constraint),
        source=source,
    )


def _one_conda_spec(
    spec: str, source: str, ecosystem: Ecosystem, found: Manifests
) -> Dependency | None:
    if python := _PYTHON_SPEC.match(spec):
        _record_python(python.group("constraint") or "", source, found)
        return None
    match = _CONDA_SPEC.match(spec)
    if not match:
        return None
    constraint = (match.group("constraint") or "").strip()
    return Dependency(
        name=match.group("name"),
        ecosystem=ecosystem,
        constraint=constraint,
        # In conda syntax a single "=" is an exact request, unlike pip.
        pinning=_pinning(constraint, single_equals_pins=True),
        source=source,
    )


def _record_python(constraint: str, source: str, found: Manifests) -> None:
    constraint = constraint.strip()
    version = re.sub(r"^[=<>~!^]+", "", constraint).strip()
    pinning = _pinning(constraint, single_equals_pins=True)
    minor = ".".join(version.split(".")[:2]) if version else ""
    found.interpreters.append(
        Interpreter(
            ecosystem="python",
            version=version or "unspecified",
            pinning=pinning,
            source=source,
            # Only reported for a pinned interpreter. ">=3.8" says the project
            # runs on supported versions too, which is a different claim from
            # "this project requires 3.8".
            end_of_life=PYTHON_END_OF_LIFE.get(minor) if pinning == "pinned" else None,
        )
    )


def _pinning(constraint: str, *, single_equals_pins: bool = False) -> Pinning:
    constraint = constraint.strip()
    if not constraint:
        return "unconstrained"
    if constraint.startswith("=="):
        return "pinned"
    if single_equals_pins and re.match(r"^=[^=]", constraint):
        return "pinned"
    return "bounded"


def _string_list(node: ast.expr | None) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return []
    return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]


def _python_imports(inventory: Inventory) -> list[Import]:
    """Third-party top-level modules imported anywhere in the Python sources."""
    local = _local_modules(inventory)
    first_seen: dict[str, str] = {}
    for file in inventory.by_kind("python"):
        if not file.path.endswith(".py"):
            continue  # .pyx is Cython, which ast cannot parse
        try:
            tree = ast.parse(inventory.read(file))
        except (SyntaxError, ValueError):
            continue
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
        for name in sorted(names):
            if name in sys.stdlib_module_names or name in local or name.startswith("_"):
                continue
            first_seen.setdefault(name, file.label)
    return [Import(name, "python", source) for name, source in sorted(first_seen.items())]


def _local_modules(inventory: Inventory) -> set[str]:
    """Module names the repositories define themselves.

    Without this every package reports an undeclared dependency on itself:
    MATES imports ``MATES.scripts.helper_function``, and LocusMasterTE's
    ``setup.py`` would never list ``telescope_scripts``.
    """
    local: set[str] = set()
    for file in inventory.files:
        parts = file.path.split("/")
        if file.path.endswith(".py"):
            local.add(parts[-1].removesuffix(".py"))
        if len(parts) > 1:
            local.add(parts[0])
        if parts[-1] == "__init__.py" and len(parts) > 1:
            local.add(parts[-2])
    return local


def _undeclared(found: Manifests) -> list[Import]:
    """Imports no declaration covers, per ecosystem.

    Scoped per ecosystem on purpose: an R package is not declared by a Python
    manifest that happens to share its name.
    """
    declared: dict[Ecosystem, set[str]] = {}
    for dependency in found.dependencies:
        # conda installs Python packages; the two pools are interchangeable here.
        ecosystem = "python" if dependency.ecosystem == "conda" else dependency.ecosystem
        declared.setdefault(ecosystem, set()).add(_normalize(dependency.name))
    return [
        used
        for used in found.imports
        if _normalize(_IMPORT_TO_DISTRIBUTION.get(used.name.casefold(), used.name))
        not in declared.get(used.ecosystem, set())
    ]


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _languages(inventory: Inventory, found: Manifests) -> tuple[list[str], list[str]]:
    """Languages present in the tree, and which of them nothing declares for.

    LocusMasterTE's TPM step is an R script calling ``library(tidyverse)``, and
    the repository contains no DESCRIPTION, no renv.lock and no R version
    anywhere. That is not an unpinned dependency, it is an undeclared second
    environment -- and it is where the reproduction attempt lost a week to R
    3.6 silently converting a column to a factor.
    """
    present: list[str] = []
    for language, kind in (("python", "python"), ("r", "r"), ("shell", "shell")):
        if inventory.by_kind(kind):
            present.append(language)

    # Only a declaration counts, and only one an installer reads. A README that
    # says "install tidyverse" documents the dependency; it does not manage it.
    managed = {
        dependency.ecosystem if dependency.ecosystem != "conda" else "python"
        for dependency in found.installable
    }
    managed |= {
        interpreter.ecosystem for interpreter in found.interpreters if not interpreter.prose_only
    }
    # Shell is excluded: there is no such thing as a declared shell environment,
    # and the tools a script calls are checked against the paper elsewhere.
    unmanaged = [
        language for language in present if language != "shell" and language not in managed
    ]
    return present, unmanaged


def _conflicts(dependencies: list[Dependency]) -> list[Conflict]:
    """The same package pinned to two different versions in two places."""
    by_name: dict[str, list[Dependency]] = {}
    for dependency in dependencies:
        if dependency.pinning == "pinned" and dependency.purpose == "runtime":
            by_name.setdefault(_normalize(dependency.name), []).append(dependency)

    out: list[Conflict] = []
    for entries in by_name.values():
        versions = {e.constraint.lstrip("=") for e in entries}
        if len(versions) < 2:
            continue
        # Report the shallowest declaration first. MATES pins torch in both
        # requirements.txt and docs/requirements.txt, and naming the second as
        # the source of the project's torch version would be true but useless.
        entries.sort(key=lambda e: (e.source.count("/"), e.source))
        first = entries[0]
        second = next(
            e for e in entries if e.constraint.lstrip("=") != first.constraint.lstrip("=")
        )
        out.append(
            Conflict(
                name=first.name,
                left_constraint=first.constraint,
                left_source=first.source,
                right_constraint=second.constraint,
                right_source=second.source,
            )
        )
    return sorted(out, key=lambda c: c.name.casefold())
