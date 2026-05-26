"""Per-opcode BTOR2 lowering library for evm-btor2 (SCHEMA.md §12).

Each function takes a ``Btor2Builder``, the current machine-state nid
dict (``machine_nids``, as returned by ``Btor2Builder.emit_machine_states``),
and any opcode-specific operands.  It returns an ``EvmLoweringResult``
holding the *next-state nid* for every machine-state variable.

The caller (dispatch layer) is responsible for wiring ``next`` clauses
from the result.  Unchanged states are represented by their original
nid from ``machine_nids`` so the dispatch layer can iterate uniformly.

Trap / halted semantics (SCHEMA.md §11 / §16)
----------------------------------------------
- ``no_exec = or(halted, trap)`` — when already stopped, all states
  are held constant (the result nids are identical to the input nids).
- ``trap_from_op`` — exception raised by *this* instruction (overflow,
  out-of-gas, etc.).  Only computed when ``not no_exec``.
- ``exec = not(no_exec OR trap_from_op)`` — true iff the instruction
  runs without error.
- All mutated states are mux-selected: ``ite(exec, new_val, old_val)``.
- ``trap_next = or(trap, trap_from_op)``
- ``halted_next = or(halted, trap_from_op)``
"""

from __future__ import annotations

from dataclasses import dataclass

from gurdy.pairs.evm_btor2.translation.builder import Btor2Builder


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class EvmLoweringResult:
    """Next-state nids for all 12 SCHEMA.md §3 machine-state variables.

    Fields mirror ``MACHINE_STATE_VARS`` key names.  Unchanged states
    hold the same nid as in ``machine_nids`` (the input).
    """

    sp: int
    stack: int
    mem: int
    mem_words: int
    sto: int
    sto_warm: int
    pc: int
    gas: int
    trap: int
    halted: int
    returndata: int
    returndatasize: int


# ---------------------------------------------------------------------------
# PUSH1 lowering (SCHEMA.md §12 / §10.1)
# ---------------------------------------------------------------------------

#: Static gas cost for PUSH1 (SCHEMA.md §10.1, London).
PUSH1_GAS: int = 3

#: Number of bytes consumed by PUSH1 (opcode + 1 immediate byte).
PUSH1_SIZE: int = 2


def lower_push1(
    b: Btor2Builder,
    machine_nids: dict[str, int],
    immediate: int,
) -> EvmLoweringResult:
    """Lower one PUSH1 instruction to BTOR2 next-state expressions.

    ``immediate`` is the 1-byte literal value (0x00–0xFF) that the
    instruction pushes onto the stack as a zero-padded bv256 word.

    Returns an ``EvmLoweringResult`` with next-state nids for all
    machine states.  The caller must emit ``next`` clauses.

    Trap conditions (SCHEMA.md §11):
    - Stack overflow: sp_full (= zext(sp, 246) → bv256) == 1024
    - Out-of-gas: gas < PUSH1_GAS (3)
    """
    sp = machine_nids["sp"]
    stack = machine_nids["stack"]
    mem = machine_nids["mem"]
    mem_words = machine_nids["mem_words"]
    sto = machine_nids["sto"]
    sto_warm = machine_nids["sto_warm"]
    pc = machine_nids["pc"]
    gas = machine_nids["gas"]
    trap = machine_nids["trap"]
    halted = machine_nids["halted"]
    returndata = machine_nids["returndata"]
    returndatasize = machine_nids["returndatasize"]

    # Already stopped — skip execution entirely.
    no_exec = b.or_("bv1", halted, trap)

    # Stack overflow: sp == 1024 (SCHEMA.md §7.2 + §11).
    # sp is bv10; extend to bv256 for comparison with the literal 1024.
    sp_full = b.uext("bv256", sp, 256 - 10)
    c1024 = b.const("bv256", 1024)
    overflow = b.eq(sp_full, c1024)

    # Out-of-gas: gas < PUSH1_GAS.
    c_gas_cost = b.const("bv64", PUSH1_GAS)
    oog = b.ult(gas, c_gas_cost)

    # Exception raised by this instruction (guarded: only when active).
    exc = b.or_("bv1", overflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)

    # Instruction executes cleanly: not stopped AND no exception.
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # --- Normal-path values -------------------------------------------------
    imm_nid = b.const("bv256", immediate & 0xFF)
    stack_written = b.write("stack_t", stack, sp, imm_nid)
    sp_inc = b.add("bv10", sp, b.const("bv10", 1))
    pc_inc = b.add("bv16", pc, b.const("bv16", PUSH1_SIZE))
    gas_dec = b.sub("bv64", gas, c_gas_cost)

    # --- ITE mux: apply updates only when exec_ = 1 -----------------------
    sp_next = b.ite("bv10", exec_, sp_inc, sp)
    stack_next = b.ite("stack_t", exec_, stack_written, stack)
    pc_next = b.ite("bv16", exec_, pc_inc, pc)
    gas_next = b.ite("bv64", exec_, gas_dec, gas)

    # trap / halted are sticky (SCHEMA.md §16).
    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp_next,
        stack=stack_next,
        mem=mem,
        mem_words=mem_words,
        sto=sto,
        sto_warm=sto_warm,
        pc=pc_next,
        gas=gas_next,
        trap=trap_next,
        halted=halted_next,
        returndata=returndata,
        returndatasize=returndatasize,
    )


# ---------------------------------------------------------------------------
# STOP lowering (SCHEMA.md §12, opcode 0x00)
# ---------------------------------------------------------------------------

#: Gas cost for STOP (SCHEMA.md §10.1 — zero).
STOP_GAS: int = 0


def lower_stop(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower a STOP instruction to BTOR2 next-state expressions.

    STOP is a clean termination: sets ``halted=1`` without setting
    ``trap`` (SCHEMA.md §16, trap-semantics table).  All other states
    are frozen.  Gas cost is zero (SCHEMA.md §10.1).

    If the machine is already halted or trapped the instruction is a
    no-op (``no_exec`` guard).
    """
    sp = machine_nids["sp"]
    stack = machine_nids["stack"]
    mem = machine_nids["mem"]
    mem_words = machine_nids["mem_words"]
    sto = machine_nids["sto"]
    sto_warm = machine_nids["sto_warm"]
    pc = machine_nids["pc"]
    gas = machine_nids["gas"]
    trap = machine_nids["trap"]
    halted = machine_nids["halted"]
    returndata = machine_nids["returndata"]
    returndatasize = machine_nids["returndatasize"]

    # Already stopped — no-op.
    no_exec = b.or_("bv1", halted, trap)
    exec_ = b.not_("bv1", no_exec)

    # STOP: set halted=1 cleanly; trap stays unchanged.
    halted_next = b.or_("bv1", halted, exec_)

    return EvmLoweringResult(
        sp=sp,
        stack=stack,
        mem=mem,
        mem_words=mem_words,
        sto=sto,
        sto_warm=sto_warm,
        pc=pc,
        gas=gas,
        trap=trap,
        halted=halted_next,
        returndata=returndata,
        returndatasize=returndatasize,
    )


# ---------------------------------------------------------------------------
# ADD lowering (SCHEMA.md §12, opcode 0x01)
# ---------------------------------------------------------------------------

#: Static gas cost for ADD (SCHEMA.md §10.1, London).
ADD_GAS: int = 3

#: Number of bytes consumed by ADD (single-byte opcode, no immediate).
ADD_SIZE: int = 1


def lower_add(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one ADD instruction to BTOR2 next-state expressions.

    Pops TOS (``stack[sp-1]``) and NOS (``stack[sp-2]``), pushes their
    bv256 sum (wrapping mod 2^256) at ``stack[sp-2]``, decrements ``sp``
    by 1, decrements ``gas`` by ADD_GAS, and advances ``pc`` by ADD_SIZE.

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < ADD_GAS
    """
    sp = machine_nids["sp"]
    stack = machine_nids["stack"]
    mem = machine_nids["mem"]
    mem_words = machine_nids["mem_words"]
    sto = machine_nids["sto"]
    sto_warm = machine_nids["sto_warm"]
    pc = machine_nids["pc"]
    gas = machine_nids["gas"]
    trap = machine_nids["trap"]
    halted = machine_nids["halted"]
    returndata = machine_nids["returndata"]
    returndatasize = machine_nids["returndatasize"]

    # Already stopped — skip execution.
    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: sp < 2 (need TOS and NOS).
    sp_wide = b.uext("bv256", sp, 256 - 10)
    c2 = b.const("bv256", 2)
    underflow = b.ult(sp_wide, c2)

    # Out-of-gas.
    c_gas = b.const("bv64", ADD_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Stack reads (computed unconditionally; muxed out when not exec_).
    c1_bv10 = b.const("bv10", 1)
    c2_bv10 = b.const("bv10", 2)
    sp_m1 = b.sub("bv10", sp, c1_bv10)   # TOS index
    sp_m2 = b.sub("bv10", sp, c2_bv10)   # NOS index / result slot
    a_nid = b.read("bv256", stack, sp_m1)
    bv_nid = b.read("bv256", stack, sp_m2)
    sum_nid = b.add("bv256", a_nid, bv_nid)

    # Normal-path writes.
    stack_written = b.write("stack_t", stack, sp_m2, sum_nid)
    sp_new = b.sub("bv10", sp, c1_bv10)
    pc_new = b.add("bv16", pc, b.const("bv16", ADD_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

    # ITE mux.
    sp_next = b.ite("bv10", exec_, sp_new, sp)
    stack_next = b.ite("stack_t", exec_, stack_written, stack)
    pc_next = b.ite("bv16", exec_, pc_new, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp_next,
        stack=stack_next,
        mem=mem,
        mem_words=mem_words,
        sto=sto,
        sto_warm=sto_warm,
        pc=pc_next,
        gas=gas_next,
        trap=trap_next,
        halted=halted_next,
        returndata=returndata,
        returndatasize=returndatasize,
    )


__all__ = [
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
