"""``evaluate(artifact, binding, max_steps)`` tool.

Runs the pair's reasoning-language interpreter on a compiled artifact
plus a concrete reasoning binding. No solver; concrete-only execution.
"""

from __future__ import annotations

from gurdy.core.interp.types import ReasoningBinding, ReasoningTrace
from gurdy.core.pair import CompiledArtifact, get_pair


def evaluate(
    artifact: CompiledArtifact,
    binding: ReasoningBinding,
    max_steps: int,
) -> ReasoningTrace:
    pair = get_pair(artifact.pair)
    if pair.reasoning_interpreter is None:
        raise ValueError(
            f"pair {artifact.pair!r} has no reasoning_interpreter; cannot evaluate"
        )
    return pair.reasoning_interpreter.run(artifact, binding, max_steps)


__all__ = ["evaluate"]
