"""Vision backends for reading figures, and the seam they sit behind.

The same arrangement as the text backends in ``reprolens.documents``: callers
depend on the protocol, so adding or swapping a model is a class, not a rewrite.

Having two of them is not only convenience. The image channel cannot verify
itself -- there is no string to match a reading against -- so the only checks
available are corroboration against the text channel and *agreement between
independent models*. One backend forecloses the second check entirely.

Every reading records which model produced it, because on this channel the
answer is not reproducible without knowing that.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from reprolens.discovery.patterns import PATTERNS
from reprolens.documents.base import Figure
from reprolens.extraction.schema import FigureContents
from reprolens.llm.cache import ResponseCache

PROMPT_PATH = Path("prompts/figure_v1.md")
PROMPT_VERSION = "figure_v1"

# Fields holding identifiers, which must be corroborated before they are trusted.
CHECKED_FIELDS = ("accessions_visible", "versions_visible", "tools_named")

# Pattern kinds that are genuinely database accessions, as opposed to the other
# things patterns.py recognises (repository URLs, DOIs, bare links).
_ACCESSION_KINDS = frozenset(
    {
        "geo_series",
        "geo_sample",
        "geo_platform",
        "sra_run",
        "sra_experiment",
        "sra_study",
        "bioproject",
        "biosample",
        "ena_run",
        "ena_study",
        "dbgap",
    }
)


@runtime_checkable
class VlmBackend(Protocol):
    name: str
    model: str

    def read(self, image: bytes, prompt: str) -> FigureContents: ...

    def unavailable(self) -> str | None:
        """Why this backend cannot read a figure right now, or None if it can.

        Asked *before* a run, so a caller can say "the figure channel did not
        run, and here is why" instead of discovering it one figure in. The
        distinction this whole project rests on applies to its own channels:
        a figure nobody could read is not a figure containing nothing.
        """
        ...


def build_prompt(figure: Figure) -> str:
    return PROMPT_PATH.read_text().replace("{caption}", figure.caption)


def read_figure(
    figure: Figure, backend: VlmBackend, cache: ResponseCache | None = None
) -> FigureContents:
    prompt = build_prompt(figure)
    image = figure.image_path.read_bytes()

    key = ResponseCache.key(backend.model, prompt, image) if cache else None
    if cache and key and (hit := cache.get(key)) is not None:
        return FigureContents.model_validate(hit)

    contents = backend.read(image, prompt)
    if cache and key:
        cache.put(key, backend.model, contents.model_dump())
    return contents


class OllamaVlm:
    """A vision model served locally by Ollama.

    Ollama constrains generation to a JSON schema via ``format``, so the same
    Pydantic model that defines the Anthropic call defines this one -- the
    backends are interchangeable rather than merely similar.

    ``num_ctx`` is raised from Ollama's default because a page-width figure
    becomes a lot of image tokens, and the default silently truncates them,
    which looks exactly like a model that cannot read the figure.

    ``repeat_penalty`` is deliberately **off**. Raising it is the obvious
    response to a model repeating itself and it backfires here: JSON is
    inherently repetitive -- quotes, commas, brackets, field names all recur --
    so penalising repeated tokens pushes the model to close every array as soon
    as it opens one. At 1.3 this model returned a fully-formed, entirely empty
    object in three seconds. The array bounds in the schema are the right
    control, because they constrain the grammar rather than the sampler.
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "qwen2.5vl:7b",
        host: str | None = None,
        num_ctx: int = 8192,
        num_predict: int = 1024,
        repeat_penalty: float = 1.0,
    ):
        self.model = model
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.repeat_penalty = repeat_penalty
        self._host = host

    def unavailable(self) -> str | None:
        try:
            import ollama
        except ImportError:
            return "the ollama Python package is not installed"
        try:
            client = ollama.Client(host=self._host) if self._host else ollama.Client()
            served = {m.get("model") or m.get("name") for m in client.list().get("models", [])}
        except Exception as error:  # server down, wrong host, refused connection
            return (
                f"no Ollama server answered ({type(error).__name__}). "
                f"Start one with `ollama serve`."
            )
        # Ollama resolves a bare name to its ``:latest`` tag, so both spellings
        # of the same model have to count as present.
        wanted = {self.model, self.model.split(":")[0], f"{self.model.split(':')[0]}:latest"}
        if not (served & wanted):
            return (
                f"Ollama is running but does not have {self.model}. "
                f"Pull it with `ollama pull {self.model}`."
            )
        return None

    def read(self, image: bytes, prompt: str) -> FigureContents:
        import ollama

        client = ollama.Client(host=self._host) if self._host else ollama.Client()
        response = client.chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.standard_b64encode(image).decode()],
                }
            ],
            format=FigureContents.model_json_schema(),
            options={
                "temperature": 0,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
                "repeat_penalty": self.repeat_penalty,
            },
        )
        content = response["message"]["content"]
        if response.get("done_reason") == "length":
            # Grammar-constrained output cut off mid-token is not recoverable
            # JSON, and a half-read figure must not pass as a complete one.
            raise ValueError(
                f"{self.model} hit the {self.num_predict}-token limit before closing its "
                f"JSON; the reading is truncated and was discarded"
            )
        return FigureContents.model_validate(json.loads(content)).deduplicated()


class AnthropicVlm:
    """Claude, via structured outputs."""

    name = "anthropic"

    def __init__(self, model: str = "claude-opus-5-5"):
        self.model = model

    def unavailable(self) -> str | None:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return "the anthropic Python package is not installed"
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return "ANTHROPIC_API_KEY is not set in the environment"
        return None

    def read(self, image: bytes, prompt: str) -> FigureContents:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.parse(
            model=self.model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.standard_b64encode(image).decode(),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            output_format=FigureContents,
        )
        return response.parsed_output


BACKENDS: dict[str, type] = {"ollama": OllamaVlm, "anthropic": AnthropicVlm}


def get_backend(name: str, model: str | None = None) -> VlmBackend:
    if name not in BACKENDS:
        raise ValueError(f"unknown vlm backend {name!r}; known: {', '.join(sorted(BACKENDS))}")
    cls = BACKENDS[name]
    return cls(model=model) if model else cls()


def blocked(name: str, model: str | None = None) -> str | None:
    """Why the figure channel cannot run, or None when it can.

    The one function both the CLI and the page ask, so they cannot disagree
    about whether figures are being read.
    """
    try:
        return get_backend(name, model).unavailable()
    except ValueError as error:  # an unknown backend name
        return str(error)


def shape_errors(contents: FigureContents) -> list[str]:
    """Values filed as accessions that are not accession-shaped.

    The observed failure of a small local model on these figures is not
    invention but misfiling: Qwen2.5-VL 7B read ``chr13|89384655|89385083`` off
    MATES figure 4 correctly -- that is exactly how these papers write a TE locus
    -- and then reported it as an accession. The reading is right, the field is
    wrong, and left alone it enters the audit as a dataset that does not exist.

    The accession patterns from the text channel already know what an accession
    looks like, so they type-check the image channel's output for free. Reported
    rather than silently dropped: a misfiled value is still a real reading, and
    which field it belongs in is a judgement this layer should not make alone.
    """
    errors: list[str] = []
    for value in contents.accessions_visible:
        if not is_accession_shaped(value):
            errors.append(f"accessions_visible:{value}")
    return errors


def is_accession_shaped(value: str) -> bool:
    """Whether a value could be a database accession at all.

    Split out from ``shape_errors`` so the channel merge can ask the same
    question of one value. A misfiled reading is still corroborated by the text
    -- ``Meg3`` really is in ASPEN's prose, as a gene -- so text agreement alone
    would promote it to a confirmed accession, which is how a gene name becomes
    a dataset the paper never deposited.
    """
    candidate = value.strip()
    return any(p.regex.fullmatch(candidate) for p in PATTERNS if p.kind in _ACCESSION_KINDS)


def corroborate(contents: FigureContents, document_text: str) -> tuple[list[str], list[str]]:
    """Split a figure's identifiers by whether the document's text confirms them.

    Comparison is case- and whitespace-insensitive, since a model renders what it
    sees rather than reproducing the document's typography.

    Anything uncorroborated is reported, never dropped: an identifier visible
    only in a figure may be perfectly real, and the audit's job is to say what
    evidence stands behind each finding, not to discard the weaker kind. This
    matters more with a small local model, whose uncorroborated output is where
    its errors will concentrate.
    """
    haystack = "".join(document_text.split()).lower()

    corroborated: list[str] = []
    unverified: list[str] = []
    for field in CHECKED_FIELDS:
        for value in getattr(contents, field):
            needle = "".join(value.split()).lower()
            target = corroborated if needle and needle in haystack else unverified
            target.append(f"{field}:{value}")
    return corroborated, unverified
