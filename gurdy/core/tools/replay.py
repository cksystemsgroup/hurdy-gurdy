"""``replay(artifact, raw)`` tool.

Takes a SAT-verdict witness from ``dispatch`` / ``lift`` and
mechanically re-runs both interpreters on it, returning a
``JoinedTrace``. The actual extraction of bindings from a solver's
witness format is pair-specific, so the framework delegates to the
pair's ``witness_replayer``.

This is the low-level mechanical join under the hood of ``lift``;
exposing it as its own tool lets the LLM call it on any cached
artifact + raw payload without re-dispatching the solver.
"""

from __future__ import annotations

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.interp.types import JoinedTrace
from gurdy.core.pair import CompiledArtifact, get_pair


def replay(artifact: CompiledArtifact, raw: RawSolverResult) -> JoinedTrace:
    pair = get_pair(artifact.pair)
    if pair.witness_replayer is None:
        raise ValueError(
            f"pair {artifact.pair!r} has no witness_replayer registered; "
            "cannot replay solver witnesses"
        )
    return pair.witness_replayer(artifact, raw)


__all__ = ["replay"]
