"""Lifter for the ``btor2-smtlib`` bridge. The SMT solver is the shared, generic
z3 SMT-LIB backend (``z3-smt``) defined in ``crn_smtlib`` — both pairs target the
same reasoning language, so they share the engine that runs it."""

from __future__ import annotations

import json
from typing import Any

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.pairs.crn_smtlib.backend import Z3SmtSolver  # shared generic SMT-LIB z3 backend

_META_PREFIX = "; @btor2-bmc "


def _read_meta(flattened: bytes) -> dict[str, Any]:
    for ln in flattened.decode("utf-8", errors="replace").splitlines():
        if ln.startswith(_META_PREFIX):
            return json.loads(ln[len(_META_PREFIX):])
    return {}


class Btor2SmtLifter:
    """Lift a z3 verdict to a BTOR2-grounded witness: on ``reachable``, the
    per-step values of the BTOR2 state variables (by symbol) from the model."""

    def lift(self, artifact: Any, raw: RawSolverResult) -> dict[str, Any]:
        meta = _read_meta(artifact.flattened)
        report: dict[str, Any] = {
            "pair": artifact.pair,
            "verdict": raw.verdict,
            "engine": raw.engine,
        }
        if raw.verdict != "reachable" or not isinstance(raw.payload, dict):
            report["witness"] = None
            return report

        bound = int(meta.get("bound", 0))
        states = meta.get("states", [])
        model = raw.payload
        witness: list[dict[str, Any]] = []
        for t in range(bound + 1):
            state_vals: dict[str, Any] = {}
            for s in states:
                key = f"n{s['nid']}_{t}"
                if key in model:
                    state_vals[s.get("symbol") or f"nid{s['nid']}"] = model[key]
            witness.append({"step": t, "state": state_vals})
        report["witness"] = witness
        return report


__all__ = ["Z3SmtSolver", "Btor2SmtLifter"]
