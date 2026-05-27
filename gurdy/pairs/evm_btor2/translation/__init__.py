"""EVM bytecode → BTOR2 translator — P4.

``translate_bytecode`` (translator.py) is the main entry point: it
orchestrates header + machine + context + dispatch + binding + bad
layers into a single BTOR2 model string ready for the solver.


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
from gurdy.pairs.evm_btor2.translation.translator import translate_bytecode
from gurdy.pairs.evm_btor2.translation.library import (
    EvmLoweringResult,
    lower_push1,
    lower_stop,
    lower_add,
    lower_sstore,
    lower_calldataload,
    lower_jumpi,
    lower_iszero,
    lower_dup1,
    lower_mstore8,
    lower_push0,
    lower_return,
    PUSH1_GAS,
    PUSH1_SIZE,
    STOP_GAS,
    ADD_GAS,
    ADD_SIZE,
    SSTORE_GAS_COLD,
    SSTORE_GAS_WARM,
    SSTORE_SIZE,
    CALLDATALOAD_GAS,
    CALLDATALOAD_SIZE,
    JUMPI_GAS,
    JUMPI_SIZE,
    ISZERO_GAS,
    ISZERO_SIZE,
    DUP1_GAS,
    DUP1_SIZE,
    MSTORE8_GAS,
    MSTORE8_SIZE,
    PUSH0_GAS,
    PUSH0_SIZE,
    RETURN_GAS,
    RETURN_SIZE,
)

__all__ = [
    "translate_bytecode",
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
    "lower_sstore",
    "lower_calldataload",
    "lower_jumpi",
    "lower_iszero",
    "lower_dup1",
    "lower_mstore8",
    "lower_push0",
    "lower_return",
    "PUSH1_GAS",
    "PUSH1_SIZE",
    "STOP_GAS",
    "ADD_GAS",
    "ADD_SIZE",
    "SSTORE_GAS_COLD",
    "SSTORE_GAS_WARM",
    "SSTORE_SIZE",
    "CALLDATALOAD_GAS",
    "CALLDATALOAD_SIZE",
    "JUMPI_GAS",
    "JUMPI_SIZE",
    "ISZERO_GAS",
    "ISZERO_SIZE",
    "DUP1_GAS",
    "DUP1_SIZE",
    "MSTORE8_GAS",
    "MSTORE8_SIZE",
    "PUSH0_GAS",
    "PUSH0_SIZE",
    "RETURN_GAS",
    "RETURN_SIZE",
]
