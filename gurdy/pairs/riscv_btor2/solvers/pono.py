"""Pono wrapper: external binary, shutil.which gated."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import SubprocessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.dispatch.timeout import SubprocessOutcome


@dataclass
class PonoSolver(SubprocessSolverBackend):
    name: str = "pono"
    binary: str = "pono"

    def build_argv(self, directive: Any) -> list[str]:
        bound = getattr(directive, "bound", None)
        argv = [self.binary, "-e", "bmc", "--btor"]
        if bound is not None:
            argv.extend(["-k", str(int(bound))])
        argv.append("/dev/stdin")
        return argv

    def parse_output(
        self, outcome: SubprocessOutcome, directive: Any
    ) -> RawSolverResult:
        out = outcome.stdout.decode("utf-8", "replace")
        if outcome.timed_out:
            return RawSolverResult(
                verdict="unknown",
                elapsed=outcome.elapsed,
                engine=self.name,
                reason="timeout",
            )
        if "sat" in out and "unsat" not in out:
            verdict = "reachable"
        elif "unsat" in out:
            verdict = "unreachable"
        else:
            verdict = "unknown"
        return RawSolverResult(
            verdict=verdict,
            elapsed=outcome.elapsed,
            engine=self.name,
            payload=outcome.stdout,
            reason=None if verdict != "unknown" else (out.strip() or "no output"),
        )


__all__ = ["PonoSolver"]
