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

The BTOR2 input is canonicalized via ``btor2_for_pono`` before being
piped to ``pono``: Pono v2.0.0's parser is stricter than the BTOR2
standard about ``init <S> <V>`` requiring ``nid(S) > nid(V)``, and
hurdy-gurdy's emitter doesn't satisfy that on its own. Without the
canonicalize step Pono rejects every model with a parse error.

When the engine is in ``ic3sa`` / ``ic3ia`` and the verdict is
``proved``, ``--show-invar`` is passed and the resulting INVAR line
is parsed off stderr into the same certificate payload shape
``z3spacer`` emits: ``{invariant_smtlib, state_nid_order,
canonical_artifact}``. Other verdicts / engines keep the legacy
behavior of returning raw stdout as the payload.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gurdy.core.dispatch.backend import SubprocessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.dispatch.timeout import SubprocessOutcome, run_with_timeout
from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.lift.btor2_for_pono import (
    INVAR_RE,
    INVARIANT_ENGINES,
    build_invariant_smtlib,
    canonicalize_for_pono,
)
from gurdy.pairs.riscv_btor2.solvers._bmc import compile_btor2


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

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def build_argv(self, directive: Any, btor_path: str = "/dev/stdin") -> list[str]:
        """Build the pono argv.

        ``btor_path`` is the file pono should parse. v2.0.0 picks the
        format from the file extension, so the caller passes a real
        path ending in ``.btor2``; the default is kept only for
        backwards-compatibility with unit tests that exercise the argv
        shape without running pono.
        """
        bound = getattr(directive, "bound", None)
        engine = _engine_mode(directive)
        argv = [self.binary, "-e", engine]
        if bound is not None:
            argv.extend(["-k", str(int(bound))])
        if engine in INVARIANT_ENGINES:
            argv.append("--show-invar")
        argv.append(btor_path)
        return argv

    def dispatch(
        self, artifact_bytes: bytes, directive: Any
    ) -> RawSolverResult:
        if not self.is_available():
            return RawSolverResult(
                verdict="error", elapsed=0.0, engine=self.name,
                reason=f"{self.binary}: not on PATH",
            )

        engine = _engine_mode(directive)
        if engine not in _KNOWN_ENGINES:
            return RawSolverResult(
                verdict="error", elapsed=0.0, engine=self.name,
                reason=(
                    f"unknown pono engine {engine!r}; "
                    f"supported: {sorted(_KNOWN_ENGINES)}"
                ),
            )

        try:
            canon_bytes = canonicalize_for_pono(
                artifact_bytes.decode("utf-8", "replace")
            )
        except Exception as e:
            return RawSolverResult(
                verdict="error", elapsed=0.0, engine=self.name,
                reason=f"canonicalize failed: {type(e).__name__}: {e}",
            )

        # Pono v2.0.0 picks the input format from the file extension, so
        # we can't pipe via /dev/stdin — write to a real ``.btor2`` file.
        timeout = getattr(directive, "timeout", None)
        with tempfile.TemporaryDirectory(prefix="pono-") as td:
            btor_path = Path(td) / "model.btor2"
            btor_path.write_bytes(canon_bytes)
            argv = self.build_argv(directive, btor_path=str(btor_path))
            outcome = run_with_timeout(argv, stdin=None, timeout=timeout)
        return self.parse_output(outcome, directive, canon_bytes)

    def parse_output(  # type: ignore[override]
        self,
        outcome: SubprocessOutcome,
        directive: Any,
        canon_bytes: bytes = b"",
    ) -> RawSolverResult:
        engine = _engine_mode(directive)
        if engine not in _KNOWN_ENGINES:
            return RawSolverResult(
                verdict="error", elapsed=outcome.elapsed, engine=self.name,
                reason=(
                    f"unknown pono engine {engine!r}; "
                    f"supported: {sorted(_KNOWN_ENGINES)}"
                ),
            )
        out = outcome.stdout.decode("utf-8", "replace")
        err = outcome.stderr.decode("utf-8", "replace")
        if outcome.timed_out:
            return RawSolverResult(
                verdict="unknown", elapsed=outcome.elapsed, engine=self.name,
                reason="timeout",
            )

        # Pono prints parse errors with the model not parsing at all; surface
        # them as ``error`` rather than misleading ``unknown``.
        if "error" in out and "INVAR" not in err:
            head = (err or out).strip().splitlines()
            return RawSolverResult(
                verdict="error", elapsed=outcome.elapsed, engine=self.name,
                reason=head[0] if head else "pono error",
            )

        if "sat" in out and "unsat" not in out:
            verdict = "reachable"
        elif "unsat" in out:
            verdict = "proved" if engine in _PROVING_ENGINES else "unreachable"
        else:
            verdict = "unknown"

        payload: Any = outcome.stdout
        if verdict == "proved" and engine in INVARIANT_ENGINES and canon_bytes:
            m = INVAR_RE.search(err) or INVAR_RE.search(out)
            if m is not None:
                try:
                    parsed = from_text(canon_bytes.decode("utf-8", "replace"))
                    comp = compile_btor2(parsed.model)
                    payload = {
                        "invariant_smtlib": build_invariant_smtlib(
                            m.group(1).strip(), comp
                        ),
                        "state_nid_order": list(comp.state_nids),
                        "canonical_artifact": canon_bytes,
                    }
                except Exception:
                    pass  # fall back to raw stdout payload

        return RawSolverResult(
            verdict=verdict, elapsed=outcome.elapsed, engine=self.name,
            payload=payload,
            reason=None if verdict != "unknown" else (out.strip() or "no output"),
        )


__all__ = ["PonoSolver"]
