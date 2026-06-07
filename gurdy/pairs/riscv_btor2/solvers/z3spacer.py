"""z3-Spacer wrapper: encode the BTOR2 transition system as Horn
clauses and let Spacer prove or refute the property.

The Horn encoding lives in ``btor2_to_z3_spacer``; this wrapper just
parses the artifact, dispatches, and shapes the result.

When Spacer returns ``proved``, the property holds at all depths
(an inductive invariant exists). This is strictly stronger than a
BMC ``unreachable`` verdict, which only says "no trace within the
bound." When Spacer returns ``reachable``, a counterexample exists
in some trace; the wrapper reports it as ``reachable`` and the LLM
can re-dispatch through ``z3-bmc`` to recover a witness trace.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import InProcessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.btor2.parser import from_text
from gurdy.core.btor2.btor2_to_z3_spacer import (
    compile_btor2,
    extract_invariant,
    invariant_to_smtlib,
    query,
)


@dataclass
class Z3SpacerSolver(InProcessSolverBackend):
    name: str = "z3-spacer"

    def dispatch(self, artifact_bytes: bytes, directive: Any) -> RawSolverResult:
        start = time.monotonic()
        try:
            import z3  # noqa: F401
        except ImportError:
            return RawSolverResult(
                verdict="error",
                elapsed=0.0,
                engine=self.name,
                reason="z3-solver is not installed",
            )

        timeout = getattr(directive, "timeout", None)
        timeout_ms = int(timeout * 1000) if timeout is not None else None

        try:
            parsed = from_text(artifact_bytes.decode("utf-8", "replace"))
            comp = compile_btor2(parsed.model)
            verdict, fp, inv_decl = query(comp, timeout_ms=timeout_ms)
        except Exception as e:
            return RawSolverResult(
                verdict="error",
                elapsed=time.monotonic() - start,
                engine=self.name,
                reason=f"{type(e).__name__}: {e}",
            )

        payload: Any = None
        if verdict == "proved":
            extracted = extract_invariant(fp, inv_decl, comp)
            if extracted is not None:
                inv_expr, state_nids = extracted
                payload = {
                    "invariant_smtlib": invariant_to_smtlib(inv_expr, state_nids, comp),
                    "state_nid_order": state_nids,
                }

        return RawSolverResult(
            verdict=verdict,
            elapsed=time.monotonic() - start,
            engine=self.name,
            payload=payload,
            reason=None if verdict != "unknown" else "spacer returned unknown",
        )


__all__ = ["Z3SpacerSolver"]
