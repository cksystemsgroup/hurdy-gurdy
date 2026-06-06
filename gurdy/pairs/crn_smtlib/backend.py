"""SMT solver backend (z3) and lifter for the ``crn-smtlib`` pair.

The backend runs the artifact's SMT-LIB through z3: ``sat`` => the target is
reachable, ``unsat`` => unreachable within the bound. The lifter turns a sat
model into a CRN-grounded trajectory (counts per step + the reaction that fires)
using the ``; @crn-meta`` header the translator embeds.
"""

from __future__ import annotations

import json
import time
from typing import Any

from gurdy.core.dispatch.result import RawSolverResult

_META_PREFIX = "; @crn-meta "


class Z3SmtSolver:
    """Solve the SMT-LIB artifact with z3 (in-process). Engine id ``z3-smt``."""

    name = "z3-smt"

    def dispatch(self, artifact_bytes: bytes, directive: Any) -> RawSolverResult:
        try:
            import z3
        except ImportError:
            return RawSolverResult(
                verdict="error", elapsed=0.0, engine=self.name, reason="z3 not installed"
            )

        text = artifact_bytes.decode("utf-8", errors="replace")
        # Drive check()/model() ourselves, so strip the solve commands.
        body = "\n".join(
            ln
            for ln in text.splitlines()
            if not ln.strip().startswith(("(check-sat", "(get-model"))
        )

        solver = z3.Solver()
        timeout = getattr(directive, "timeout", None)
        if timeout:
            solver.set("timeout", int(float(timeout) * 1000))

        start = time.monotonic()
        try:
            solver.from_string(body)
            result = solver.check()
        except z3.Z3Exception as exc:  # pragma: no cover - malformed artifact
            return RawSolverResult(
                verdict="error",
                elapsed=time.monotonic() - start,
                engine=self.name,
                reason=str(exc),
            )
        elapsed = time.monotonic() - start

        if result == z3.sat:
            model = solver.model()
            payload: dict[str, Any] = {}
            for decl in model.decls():
                value = model[decl]
                try:
                    payload[decl.name()] = value.as_long()
                except Exception:  # pragma: no cover - non-integer model entry
                    payload[decl.name()] = str(value)
            return RawSolverResult(
                verdict="reachable", elapsed=elapsed, engine=self.name, payload=payload
            )
        if result == z3.unsat:
            return RawSolverResult(verdict="unreachable", elapsed=elapsed, engine=self.name)
        return RawSolverResult(
            verdict="unknown", elapsed=elapsed, engine=self.name, reason="z3 returned unknown"
        )


def _read_meta(flattened: bytes) -> dict[str, Any]:
    for ln in flattened.decode("utf-8", errors="replace").splitlines():
        if ln.startswith(_META_PREFIX):
            return json.loads(ln[len(_META_PREFIX):])
    return {}


class CrnLifter:
    """Lift a z3 verdict to CRN-grounded facts: the reachability verdict and, on
    a reachable witness, the per-step trajectory (counts + the firing reaction)."""

    def lift(self, artifact: Any, raw: RawSolverResult) -> dict[str, Any]:
        meta = _read_meta(artifact.flattened)
        report: dict[str, Any] = {
            "pair": artifact.pair,
            "verdict": raw.verdict,
            "engine": raw.engine,
        }
        if raw.verdict != "reachable" or not isinstance(raw.payload, dict):
            report["trajectory"] = None
            return report

        species = meta.get("species", [])
        reactions = meta.get("reactions", [])
        bound = int(meta.get("bound", 0))
        model = raw.payload

        trajectory: list[dict[str, Any]] = []
        for t in range(bound + 1):
            step: dict[str, Any] = {
                "step": t,
                "counts": {s: int(model.get(f"x_{s}_{t}", 0)) for s in species},
            }
            if t < bound:
                sel = model.get(f"sel_{t}")
                if sel is not None and 0 <= int(sel) < len(reactions):
                    step["fires"] = reactions[int(sel)]
            trajectory.append(step)

        report["trajectory"] = trajectory
        report["fired"] = [s["fires"] for s in trajectory if "fires" in s]
        return report


__all__ = ["Z3SmtSolver", "CrnLifter"]
