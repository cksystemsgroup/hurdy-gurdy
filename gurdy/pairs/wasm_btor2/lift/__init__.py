"""Witness lifter: solver witness → source-level facts.

Lifts a ``RawSolverResult`` with ``verdict="reachable"`` and a
``witness_text`` (z3 model string) into a ``WasmWitness`` containing
concrete parameter assignments and the BMC step at which the trap fired.

Public API::

    from gurdy.pairs.wasm_btor2.lift import WasmWitness, lift_witness

    witness = lift_witness(artifact.flattened, result.payload["witness_text"])
    print(witness.params)       # {0: 2147483648, 1: 1}
    print(witness.trap_step)    # 3
    print(witness.as_signed(0)) # -2147483648
"""

from gurdy.pairs.wasm_btor2.lift.lifter import lift_witness
from gurdy.pairs.wasm_btor2.lift.parse_z3_model import parse_z3_model
from gurdy.pairs.wasm_btor2.lift.witness import WasmWitness

__all__ = ["WasmWitness", "lift_witness", "parse_z3_model"]
