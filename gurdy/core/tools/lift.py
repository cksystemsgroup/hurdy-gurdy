"""``lift(artifact, raw)`` tool."""

from __future__ import annotations

from typing import Any

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.pair import CompiledArtifact, get_pair


def lift(artifact: CompiledArtifact, raw: RawSolverResult) -> Any:
    pair = get_pair(artifact.pair)
    return pair.lifter.lift(artifact, raw)


__all__ = ["lift"]
