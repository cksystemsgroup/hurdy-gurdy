"""``check(spec, binding, max_steps)`` tool.

Runs the source interpreter and evaluates the spec's observables,
assumptions, and property predicates against the resulting concrete
trace. Returns a structured ``SpecEvaluation`` that exposes vacuous
assumptions, never-firing observables, and trivially violated
properties without invoking a solver.

The actual predicate semantics are pair-specific: each pair registers
a ``predicate_evaluator`` callable that maps `(spec, source_trace) ->
SpecEvaluation`. Pairs that haven't wired one up get a structured
"not yet supported" diagnostic — the tool surface is stable, but the
content is gated on PR4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gurdy.core.interp.diagnostics import (
    CODE_PROPERTY_UNSUPPORTED,
    warning,
)
from gurdy.core.interp.types import (
    InputBinding,
    SpecEvaluation,
    SpecPredicateResult,
    PredicateKind,
)
from gurdy.core.pair import get_pair
from gurdy.core.spec.base import BaseSpec
from gurdy.core.tools.simulate import simulate


def check(
    spec: BaseSpec,
    binding: InputBinding,
    max_steps: int,
    *,
    source_payload: bytes | str | Path | Any | None = None,
) -> SpecEvaluation:
    pair = get_pair(spec.pair)
    trace = simulate(spec, binding, max_steps, source_payload=source_payload)

    if pair.predicate_evaluator is None:
        diag = warning(
            CODE_PROPERTY_UNSUPPORTED,
            f"pair {spec.pair!r} has no predicate_evaluator; "
            "spec predicates not evaluated. "
            "Source trace is still produced.",
        )
        return SpecEvaluation(
            pair=spec.pair,
            inputs_hash=binding.inputs_hash(),
            steps_executed=len(trace.steps),
            halted=trace.halted,
            observables=(),
            assumptions=(),
            property_result=SpecPredicateResult(
                name="property",
                kind=PredicateKind.PROPERTY,
                fired=False,
                holds=None,
                note="not evaluated: pair has no predicate_evaluator",
            ),
            diagnostics=({"severity": diag.severity.value, "code": diag.code, "message": diag.message},),
        )
    return pair.predicate_evaluator(spec, trace)


__all__ = ["check"]
