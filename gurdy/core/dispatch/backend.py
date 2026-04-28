"""``SolverBackend`` Protocol plus subprocess and in-process scaffolds.

Concrete pair-specific backends inherit from one of:

- ``SubprocessSolverBackend``: external binaries; supplies ``argv``
  builder and ``parse_output``.
- ``InProcessSolverBackend``: in-Python solvers (z3, bitwuzla via
  bindings); subclasses just override ``run``.

Both produce the framework's ``RawSolverResult``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.dispatch.timeout import SubprocessOutcome, run_with_timeout


@runtime_checkable
class SolverBackend(Protocol):
    """Runs one solver invocation against pre-flattened artifact bytes."""

    name: str

    def dispatch(
        self, artifact_bytes: bytes, directive: Any
    ) -> RawSolverResult: ...


@dataclass
class SubprocessSolverBackend:
    """Helper base class for subprocess-based solvers."""

    name: str
    binary: str

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def build_argv(self, directive: Any) -> list[str]:
        """Override per pair to translate directive options into CLI flags."""
        return [self.binary]

    def parse_output(
        self, outcome: SubprocessOutcome, directive: Any
    ) -> RawSolverResult:
        """Override to interpret the solver's stdout into a verdict and
        pair-specific payload."""

        verdict = "unknown"
        reason = None
        if outcome.timed_out:
            reason = "timeout"
        elif outcome.returncode != 0:
            reason = f"exit {outcome.returncode}"
        return RawSolverResult(
            verdict=verdict,
            elapsed=outcome.elapsed,
            engine=self.name,
            payload=outcome.stdout,
            reason=reason,
        )

    def dispatch(
        self, artifact_bytes: bytes, directive: Any
    ) -> RawSolverResult:
        if not self.is_available():
            return RawSolverResult(
                verdict="error",
                elapsed=0.0,
                engine=self.name,
                reason=f"{self.binary}: not on PATH",
            )
        argv = self.build_argv(directive)
        timeout = getattr(directive, "timeout", None)
        outcome = run_with_timeout(argv, stdin=artifact_bytes, timeout=timeout)
        return self.parse_output(outcome, directive)


class InProcessSolverBackend:
    """Helper base class for in-process solver bindings."""

    name: str = "in-process"

    def dispatch(
        self, artifact_bytes: bytes, directive: Any
    ) -> RawSolverResult:  # pragma: no cover - abstract
        raise NotImplementedError


__all__ = [
    "SolverBackend",
    "SubprocessSolverBackend",
    "InProcessSolverBackend",
]
