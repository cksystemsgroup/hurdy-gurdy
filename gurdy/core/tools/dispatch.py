"""``dispatch(artifact, directive)`` tool."""

from __future__ import annotations

from typing import Any

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.pair import CompiledArtifact, get_pair


def dispatch(
    artifact: CompiledArtifact, directive: Any
) -> RawSolverResult:
    """Run a single solver against the flattened artifact.

    The directive's ``engine`` field selects one of the pair's
    registered solvers. If it isn't registered, a structured error
    result is returned rather than raising — so the LLM gets a
    well-typed answer in all cases.
    """
    pair = get_pair(artifact.pair)
    engine = getattr(directive, "engine", None)
    if engine is None:
        return RawSolverResult(
            verdict="error",
            elapsed=0.0,
            engine="<none>",
            reason="directive has no .engine field",
        )
    backend_cls = pair.solvers.get(engine)
    if backend_cls is None:
        return RawSolverResult(
            verdict="error",
            elapsed=0.0,
            engine=engine,
            reason=(
                f"pair {artifact.pair!r} has no solver registered as "
                f"{engine!r}; available: {sorted(pair.solvers)}"
            ),
        )
    backend = backend_cls()
    return backend.dispatch(artifact.flattened, directive)


__all__ = ["dispatch"]
