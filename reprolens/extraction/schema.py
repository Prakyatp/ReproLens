"""What a figure can contribute to a reproducibility audit.

Kept in its own module because every VLM backend needs it and none of them
should need each other. It is also the contract the backends are compared on:
two models answering the same schema about the same image are directly
diffable, which is the point of having more than one.

**The bounds on these lists are load-bearing, not cosmetic.** Ollama constrains
local generation to this schema as a grammar, so an unbounded array is a grammar
that permits an infinite one. Given a dense multi-panel figure, Qwen2.5-VL 7B at
temperature 0 took that permission and emitted "TE Region" until it hit the token
ceiling. ``maxItems`` makes the failure unrepresentable rather than merely
discouraged. The caps are set well above what any real figure needs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Generous relative to real figures; tight enough that a loop cannot run away.
_MAX_STEPS = 15
_MAX_TOOLS = 15
_MAX_SAMPLES = 20
_MAX_IDENTIFIERS = 10
_MAX_PARAMETERS = 15
_MAX_AXES = 15
_MAX_NOTES = 500


class FigureContents(BaseModel):
    figure_type: Literal["workflow", "plot", "heatmap", "micrograph", "schematic", "other"]
    workflow_steps: list[str] = Field(default_factory=list, max_length=_MAX_STEPS)
    tools_named: list[str] = Field(default_factory=list, max_length=_MAX_TOOLS)
    sample_labels: list[str] = Field(default_factory=list, max_length=_MAX_SAMPLES)
    accessions_visible: list[str] = Field(default_factory=list, max_length=_MAX_IDENTIFIERS)
    versions_visible: list[str] = Field(default_factory=list, max_length=_MAX_IDENTIFIERS)
    parameters_visible: list[str] = Field(default_factory=list, max_length=_MAX_PARAMETERS)
    axis_labels: list[str] = Field(default_factory=list, max_length=_MAX_AXES)
    notes: str = Field(default="", max_length=_MAX_NOTES)

    def deduplicated(self) -> FigureContents:
        """Collapse repeats while preserving order.

        A bounded grammar stops a runaway loop but not a short one: a model may
        still emit the same label several times because the figure really does
        repeat it. Downstream these are set-compared anyway, so duplicates only
        distort the per-figure counts used to compare backends.
        """
        updates: dict[str, list[str]] = {}
        for name, field in self.model_fields.items():
            if getattr(field.annotation, "__origin__", None) is not list:
                continue
            seen: dict[str, None] = {}
            for value in getattr(self, name):
                seen.setdefault(" ".join(value.split()), None)
            updates[name] = list(seen)
        return self.model_copy(update=updates)
