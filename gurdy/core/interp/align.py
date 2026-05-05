"""Cross-trace alignment.

The framework walks ``SourceTrace`` and ``ReasoningTrace`` step-by-
step; the *projection*, supplied by the pair, decides which fields to
compare at each step and how to render their views. Returns the first
divergence or an agreement report.

Alignment is the only framework-level pair-independent code that
"knows" how to walk both traces. Pairs do not implement alignment;
they only project a step-pair into a list of ``ProjectedField``s.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable

from gurdy.core.interp.types import (
    CrossCheckOutcome,
    CrossCheckReport,
    ReasoningStep,
    ReasoningTrace,
    SourceStep,
    SourceTrace,
)


@dataclass(frozen=True)
class ProjectedField:
    """One labelled correspondence between a source-side and reasoning-side
    view at a given step. ``agree`` says whether they match concretely."""

    label: str
    source_view: Any
    reasoning_view: Any
    agree: bool


@runtime_checkable
class Projection(Protocol):
    """Pair-supplied projector that turns a (source, reasoning) step pair
    into a sequence of fields the framework can compare.

    The projection is responsible for applying the schema-defined
    correspondence between source-side state and reasoning-side state
    nids. Returning an empty sequence is fine — alignment then advances
    without checking any field at that step.
    """

    def __call__(
        self,
        source_step: SourceStep,
        reasoning_step: ReasoningStep,
    ) -> Sequence[ProjectedField]: ...


def align_traces(
    source: SourceTrace,
    reasoning: ReasoningTrace,
    projection: Projection,
    *,
    max_steps: int | None = None,
) -> CrossCheckReport:
    """Walk both traces step-by-step until a divergence is found.

    Returns ``AGREEMENT`` if every projected field at every observed
    step matches; otherwise ``DIVERGENCE`` with the first failing
    field localized.

    The number of steps actually checked is ``min(len(source.steps),
    len(reasoning.steps), max_steps)``.
    """

    if source.pair != reasoning.pair:
        return CrossCheckReport(
            pair=source.pair,
            outcome=CrossCheckOutcome.DIVERGENCE,
            steps_checked=0,
            note=(
                f"trace pair mismatch: source={source.pair!r}, "
                f"reasoning={reasoning.pair!r}"
            ),
        )

    steps = min(len(source.steps), len(reasoning.steps))
    if max_steps is not None:
        steps = min(steps, max_steps)

    fields_checked = 0
    for i in range(steps):
        s = source.steps[i]
        r = reasoning.steps[i]
        for pf in projection(s, r):
            fields_checked += 1
            if not pf.agree:
                return CrossCheckReport(
                    pair=source.pair,
                    outcome=CrossCheckOutcome.DIVERGENCE,
                    steps_checked=i,
                    fields_checked=fields_checked,
                    divergence_step=i,
                    divergence_label=pf.label,
                    source_view=pf.source_view,
                    reasoning_view=pf.reasoning_view,
                )
    return CrossCheckReport(
        pair=source.pair,
        outcome=CrossCheckOutcome.AGREEMENT,
        steps_checked=steps,
        fields_checked=fields_checked,
    )


__all__ = ["ProjectedField", "Projection", "align_traces"]
