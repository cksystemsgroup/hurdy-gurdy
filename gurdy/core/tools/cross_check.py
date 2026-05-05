"""``cross_check(spec, source_binding, reasoning_binding, max_steps)`` tool.

Runs the source interpreter and the reasoning interpreter on the same
concrete inputs and aligns their traces step-by-step through the
pair's projection. Returns a ``CrossCheckReport`` reporting either
agreement or the first divergence.

This is the translator-soundness oracle: a divergence means the
schema's promise has been broken on this concrete input. Pairs cannot
opt out of this — every pair declaring an ``interpreter_version``
must register a ``projection`` factory too, since alignment is what
the contract is *for*.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gurdy.core.interp.align import align_traces
from gurdy.core.interp.types import (
    CrossCheckOutcome,
    CrossCheckReport,
    InputBinding,
    ReasoningBinding,
)
from gurdy.core.pair import CompiledArtifact, get_pair
from gurdy.core.spec.base import BaseSpec
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.evaluate import evaluate
from gurdy.core.tools.simulate import simulate


def cross_check(
    spec: BaseSpec,
    source_binding: InputBinding,
    reasoning_binding: ReasoningBinding,
    max_steps: int,
    *,
    source_payload: bytes | str | Path | Any | None = None,
    artifact: CompiledArtifact | None = None,
) -> CrossCheckReport:
    """Drive both interpreters and align them.

    ``artifact`` is optional; if omitted, the spec is compiled here.
    ``source_payload`` is the same shape ``compile`` / ``simulate``
    accept.
    """
    pair = get_pair(spec.pair)
    if pair.projection is None:
        return CrossCheckReport(
            pair=spec.pair,
            outcome=CrossCheckOutcome.DIVERGENCE,
            steps_checked=0,
            note=f"pair {spec.pair!r} has no projection registered",
        )

    src_trace = simulate(
        spec, source_binding, max_steps, source_payload=source_payload
    )
    if artifact is None:
        artifact = compile_spec(spec, source_payload)
    reas_trace = evaluate(artifact, reasoning_binding, max_steps)
    projection = pair.projection(artifact)
    return align_traces(src_trace, reas_trace, projection, max_steps=max_steps)


__all__ = ["cross_check"]
