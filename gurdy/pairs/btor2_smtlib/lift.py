"""Target-to-source interpreter ``L`` for btor2-smtlib: decode an SMT model
(a solver witness) into a BTOR2 behavior.

The solver's model only *proposes* the witness (SOLVERS.md §4); the
deterministic BTOR2 interpreter then regrows the full run, which is what makes
the answer trustworthy. ``decode_witness`` extracts the initial bit-vector
state and the per-step inputs from the model's variable names (matching
``translate._name``); ``lift`` replays them through the shared BTOR2
interpreter.

Array-valued initial state is extracted from the model too (the z3 backend
decodes an array's ``store`` chain into ``{index: value}`` entries), so a
witness that depends on initial memory replays faithfully.
"""

from __future__ import annotations

from typing import Any

from ...languages.btor2.eval import interpret
from ...languages.btor2.model import Array, System, from_text


def _as_system(system: Any) -> System:
    if isinstance(system, System):
        return system
    text = system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
    return from_text(text)


def _label(sys: System, state) -> str:
    return state.symbol or f"n{state.id}"


def decode_witness(sys: System, k: int, model: dict[str, Any]) -> dict[str, Any]:
    state_init: dict[str, Any] = {}
    for s in sys.states():
        if isinstance(sys.sorts[s.sort], Array):
            raw = dict(model.get(f"s{s.id}_0", {}))
            arr: dict[Any, int] = {}
            for key, val in raw.items():
                arr[key if key == "default" else int(key)] = int(val)
            state_init[_label(sys, s)] = arr
        else:
            state_init[_label(sys, s)] = int(model.get(f"s{s.id}_0", 0))
    inputs: dict[int, dict[int, int]] = {}
    for t in range(k + 1):
        row = {n.id: int(model.get(f"i{n.id}_{t}", 0))
               for n in sys.nodes.values() if n.op == "input"}
        if row:
            inputs[t] = row
    return {"steps": k + 1, "state": state_init, "inputs": inputs}


def lift(witness: dict[str, Any]):
    """``witness`` bundles the BTOR2 ``system``, the bound ``k``, and the SMT
    ``model``; returns the replayed BTOR2 behavior."""
    sys = _as_system(witness["system"])
    binding = decode_witness(sys, int(witness["k"]), witness["model"])
    return interpret(sys, binding)
