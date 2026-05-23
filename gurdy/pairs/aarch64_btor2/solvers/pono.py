"""Pono wrapper: external binary, shutil.which gated.

Pono ships several model-checking engines under one binary; this
wrapper exposes them through ``directive.extra_options["engine"]``.

- ``bmc`` (default) — bounded model checking. ``unsat`` → ``unreachable``.
- ``ind`` — k-induction. ``unsat`` → ``proved`` (an inductive
  invariant exists, so the property holds at every depth).
- ``bmc-sp``, ``ic3bits``, ``ic3ia``, ``ic3sa`` — additional pono
  engines passed through verbatim. The bmc family maps ``unsat`` to
  ``unreachable``; the IC3 family maps it to ``proved``.

Engines that prove unbounded correctness (``ind``, ``ic3*``) are how
pono cross-checks ``z3-spacer``'s ``proved`` claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import SubprocessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.dispatch.timeout import SubprocessOutcome


# Engines whose ``unsat`` answer is an unbounded proof, not a
# bounded "no trace within k" result.
_PROVING_ENGINES = frozenset({"ind", "ic3bits", "ic3ia", "ic3sa"})

# Engines this wrapper is willing to dispatch. Anything else returns
# a structured error (rather than handing pono an unknown flag).
_KNOWN_ENGINES = _PROVING_ENGINES | {"bmc", "bmc-sp"}


def _engine_mode(directive: Any) -> str:
    extras = getattr(directive, "extra_options", None) or {}
    return str(extras.get("engine", "bmc"))


@dataclass
class PonoSolver(SubprocessSolverBackend):
    name: str = "pono"
    binary: str = "pono"

    def build_argv(self, directive: Any) -> list[str]:
        bound = getattr(directive, "bound", None)
        engine = _engine_mode(directive)
        argv = [self.binary, "-e", engine, "--btor"]
        if bound is not None:
            argv.extend(["-k", str(int(bound))])
        argv.append("/dev/stdin")
        return argv

    def parse_output(
        self, outcome: SubprocessOutcome, directive: Any
    ) -> RawSolverResult:
        engine = _engine_mode(directive)
        if engine not in _KNOWN_ENGINES:
            return RawSolverResult(
                verdict="error",
                elapsed=outcome.elapsed,
                engine=self.name,
                reason=(
                    f"unknown pono engine {engine!r}; "
                    f"supported: {sorted(_KNOWN_ENGINES)}"
                ),
            )

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
            verdict = "proved" if engine in _PROVING_ENGINES else "unreachable"
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
