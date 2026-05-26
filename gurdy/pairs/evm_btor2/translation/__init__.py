"""EVM bytecode → BTOR2 translator — P4.

``Btor2Builder`` (builder.py) handles sort declarations (SCHEMA.md §2)
and machine-state declarations (§3.1 + §3.2).

``layers.py`` provides ``emit_context_inputs`` (SCHEMA.md §4 context
variables + spec assumption constraints) and ``emit_init_clauses``
(scalar zero-inits + GasLimitPin / StoragePin / StorageWarm).

``library.py`` provides per-opcode BTOR2 lowering functions and
``EvmLoweringResult`` (the next-state nid container).
"""

from gurdy.pairs.evm_btor2.translation.builder import (
    Btor2Builder,
    EVM_ARRAY_SORTS,
    EVM_BITVEC_SORTS,
    MACHINE_STATE_VARS,
)
from gurdy.pairs.evm_btor2.translation.layers import (
    CONTEXT_VARS,
    emit_context_inputs,
    emit_init_clauses,
)
from gurdy.pairs.evm_btor2.translation.library import (
    EvmLoweringResult,
    lower_push1,
    lower_stop,
    lower_add,
    PUSH1_GAS,
    PUSH1_SIZE,
    STOP_GAS,
    ADD_GAS,
    ADD_SIZE,
)

__all__ = [
    "Btor2Builder",
    "EVM_BITVEC_SORTS",
    "EVM_ARRAY_SORTS",
    "MACHINE_STATE_VARS",
    "CONTEXT_VARS",
    "emit_context_inputs",
    "emit_init_clauses",
    "EvmLoweringResult",
    "lower_push1",
    "lower_stop",
    "lower_add",
    "PUSH1_GAS",
    "PUSH1_SIZE",
    "STOP_GAS",
    "ADD_GAS",
    "ADD_SIZE",
]
