"""Exhaustive bounded search through the shared interpreter — the
solver-synthesis lane's reference inhabitant (SYNTHESIS.md §7;
tools/procedure_dispatch.py).

A pure-Python decision procedure for the two hub shapes: enumerate
*every* complete per-cycle input assignment within the bound and run
each through the shared BTOR2 interpreter. ``reachable`` iff some run
fires a ``bad`` on a constraint-valid row; ``unreachable`` iff the
enumeration completed and none did — sound *and complete* within the
declared path budget, and ``resource-out`` beyond it, exactly as the
budget-honesty rule wants (a declared cap, never a silent one).

Why this engine exists: it is the artifact shape the synthesis lane
produces — a backend class beside the adapters, a registered brief
(solvers/brief.py), and admission through the solver gate at
``runs=2`` (deterministic pure Python gets the strict gate,
SYNTHESIS.md §6). It is deliberately naive: its value is not speed
but its TCB — the shared interpreter *is* the semantics, so deciding
and checking coincide (the found assignment replays by construction).
Its lineage says so: it shares no codebase with any external engine
(it corroborates with all of them) but is one lineage with the
deterministic core's interpreter — declared, so nothing it agrees
with can be over-counted.
"""

from __future__ import annotations

import itertools
from typing import Any

from ..core.solver import Verdict
from ..languages.btor2.eval import interpret
from ..languages.btor2.model import System, from_text


def _as_system(system: Any) -> System:
    if isinstance(system, System):
        return system
    text = (system.decode("utf-8")
            if isinstance(system, (bytes, bytearray)) else str(system))
    return from_text(text)


def _row_valid(row: dict) -> bool:
    # The witness checker's rule (languages/btor2/witness.py): a bad
    # counts only on a row where every declared constraint holds.
    return all(v == 1 for key, v in row.items()
               if key.startswith("constraint"))


def _fires(trace: Any) -> bool:
    return any(v == 1 for row in trace if _row_valid(row)
               for key, v in row.items() if key.startswith("bad"))


class EnumBtor2Solver:
    id = "enum-btor2"
    # One lineage with the shared interpreter (deciding *is*
    # interpreting) — disjoint from every external engine, so it
    # corroborates with all of them and never with the core it is.
    lineage = ("hurdy-gurdy-btor2-interpreter",)

    def __init__(self, max_paths: int = 4096) -> None:
        self.max_paths = max_paths  # the declared budget (brief.py)

    def decide_witness(self, system: Any,
                       k: int) -> tuple[Verdict, dict | None]:
        """Decide reachability within ``k`` steps; on ``reachable``
        also return the firing per-cycle input assignment — the
        witness, replayable through the same interpreter that found
        it."""
        sys_ = _as_system(system)
        steps = k + 1
        inputs = [n for n in sys_.nodes.values() if n.op == "input"]
        if not inputs:
            fired = _fires(interpret(sys_, {"steps": steps}))
            return ((Verdict.REACHABLE, {}) if fired
                    else (Verdict.UNREACHABLE, None))
        widths = [sys_.sorts[n.sort].width for n in inputs]
        per_cycle = 1
        for w in widths:
            per_cycle *= 1 << w
        if per_cycle ** steps > self.max_paths:
            return Verdict.RESOURCE_OUT, None
        combos = [dict(zip((n.id for n in inputs), vals))
                  for vals in itertools.product(
                      *[range(1 << w) for w in widths])]
        for path in itertools.product(combos, repeat=steps):
            binding = {c: dict(path[c]) for c in range(steps)}
            if _fires(interpret(sys_, {"steps": steps,
                                       "inputs": binding})):
                return Verdict.REACHABLE, {"inputs": binding}
        return Verdict.UNREACHABLE, None

    def decide(self, system: Any, k: int) -> Verdict:
        return self.decide_witness(system, k)[0]
