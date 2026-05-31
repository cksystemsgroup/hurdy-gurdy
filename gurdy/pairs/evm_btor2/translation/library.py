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


# ---------------------------------------------------------------------------
# SSTORE lowering (SCHEMA.md §12, opcode 0x55)
# ---------------------------------------------------------------------------

#: Cold-slot gas cost for SSTORE — simplified 2-case model (P4).
SSTORE_GAS_COLD: int = 2200

#: Warm-slot gas cost for SSTORE — simplified 2-case model (P4).
SSTORE_GAS_WARM: int = 100

#: Number of bytes consumed by SSTORE (single-byte opcode).
SSTORE_SIZE: int = 1


def lower_sstore(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one SSTORE instruction to BTOR2 next-state expressions.

    Pops ``slot`` (TOS = ``stack[sp-1]``) and ``value`` (NOS =
    ``stack[sp-2]``), writes ``sto[slot] := value``, marks the slot
    warm (``sto_warm[slot] := 1``), decrements ``sp`` by 2, advances
    ``pc`` by SSTORE_SIZE, and deducts gas.

    **Gas model (P4 simplification)**: 2-case warm/cold schedule
    (SCHEMA.md §10.4).  The full 6-case schedule (which also depends
    on the slot's *original* value) is deferred to P5.

    - Slot warm (``sto_warm[slot][0:0] == 1``): SSTORE_GAS_WARM (100)
    - Slot cold (``sto_warm[slot][0:0] == 0``): SSTORE_GAS_COLD (2200)

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < gas_cost
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 2 items.
    sp_wide = b.uext("bv256", sp, 256 - 10)
    c2 = b.const("bv256", 2)
    underflow = b.ult(sp_wide, c2)

    # Pop slot (TOS) and value (NOS) — computed unconditionally.
    c1_bv10 = b.const("bv10", 1)
    c2_bv10 = b.const("bv10", 2)
    sp_m1 = b.sub("bv10", sp, c1_bv10)
    sp_m2 = b.sub("bv10", sp, c2_bv10)
    slot_nid = b.read("bv256", stack, sp_m1)
    value_nid = b.read("bv256", stack, sp_m2)

    # Gas cost: warm/cold (SCHEMA.md §10.4, P4 2-case simplification).
    warm_word = b.read("bv256", sto_warm, slot_nid)
    warm = b.slice("bv1", warm_word, 0, 0)
    c_warm = b.const("bv64", SSTORE_GAS_WARM)
    c_cold = b.const("bv64", SSTORE_GAS_COLD)
    gas_cost = b.ite("bv64", warm, c_warm, c_cold)

    oog = b.ult(gas, gas_cost)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Normal-path writes.
    sto_written = b.write("sto_t", sto, slot_nid, value_nid)
    sto_warm_written = b.write("sto_t", sto_warm, slot_nid, b.const("bv256", 1))
    sp_new = b.sub("bv10", sp, c2_bv10)
    gas_new = b.sub("bv64", gas, gas_cost)
    pc_new = b.add("bv16", pc, b.const("bv16", SSTORE_SIZE))

    # ITE mux.
    sp_next = b.ite("bv10", exec_, sp_new, sp)
    sto_next = b.ite("sto_t", exec_, sto_written, sto)
    sto_warm_next = b.ite("sto_t", exec_, sto_warm_written, sto_warm)
    pc_next = b.ite("bv16", exec_, pc_new, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp_next,
        stack=stack,
        mem=mem,
        mem_words=mem_words,
        sto=sto_next,
        sto_warm=sto_warm_next,
        pc=pc_next,
        gas=gas_next,
        trap=trap_next,
        halted=halted_next,
        returndata=returndata,
        returndatasize=returndatasize,
    )


# ---------------------------------------------------------------------------
# CALLDATALOAD lowering (SCHEMA.md §12, opcode 0x35)
# ---------------------------------------------------------------------------

#: Gas cost for CALLDATALOAD (SCHEMA.md §10.1, London).
CALLDATALOAD_GAS: int = 3

#: Number of bytes consumed by CALLDATALOAD (single-byte opcode).
CALLDATALOAD_SIZE: int = 1


def lower_calldataload(
    b: Btor2Builder,
    machine_nids: dict[str, int],
    ctx_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one CALLDATALOAD instruction to BTOR2 next-state expressions.

    Pops ``offset`` (TOS = ``stack[sp-1]``), reads 32 bytes big-endian
    from ``calldata[offset..offset+31]`` (bytes past calldatasize are 0
    per the zero-constraint on calldata in ``emit_context_inputs``),
    and pushes the resulting bv256 word back at the same stack slot.
    Net stack depth change is zero (pop 1, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 1
    - Out-of-gas: gas < CALLDATALOAD_GAS
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
    calldata = ctx_nids["calldata"]

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 1 item.
    sp_wide = b.uext("bv256", sp, 256 - 10)
    c1_bv256 = b.const("bv256", 1)
    underflow = b.ult(sp_wide, c1_bv256)

    # OOG.
    c_gas = b.const("bv64", CALLDATALOAD_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Pop offset (TOS slot = sp-1).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    offset = b.read("bv256", stack, sp_m1)

    # Read 32 bytes big-endian from calldata.
    # byte k is at calldata[offset + k].  Accumulate MSB-first.
    byte_nids: list[int] = []
    for k in range(32):
        idx = b.add("bv256", offset, b.const("bv256", k))
        byte_nids.append(b.read("bv8", calldata, idx))

    # Build bv256 via 31 concat operations (big-endian: byte 0 is MSB).
    word_nid: int = byte_nids[0]  # bv8 so far
    for k in range(1, 32):
        width = 8 * (k + 1)
        word_nid = b.concat(f"bv{width}", word_nid, byte_nids[k])
    # word_nid is now bv256.

    # Write result back to TOS slot (net sp change = 0).
    stack_written = b.write("stack_t", stack, sp_m1, word_nid)
    pc_new = b.add("bv16", pc, b.const("bv16", CALLDATALOAD_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

    stack_next = b.ite("stack_t", exec_, stack_written, stack)
    pc_next = b.ite("bv16", exec_, pc_new, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp,
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
# JUMPI lowering (SCHEMA.md §12, opcode 0x57)
# ---------------------------------------------------------------------------

#: Gas cost for JUMPI (SCHEMA.md §10.1, London).
JUMPI_GAS: int = 10

#: Number of bytes consumed by JUMPI (single-byte opcode).
JUMPI_SIZE: int = 1


def lower_jumpi(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one JUMPI instruction to BTOR2 next-state expressions.

    Pops ``dest`` (TOS = ``stack[sp-1]``, bv256 → truncated to bv16) and
    ``cond`` (NOS = ``stack[sp-2]``, bv256).  If ``cond != 0``, jumps to
    ``dest``; otherwise falls through to ``pc + 1``.  Stack pointer is
    decremented by 2 regardless of the branch taken.

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < JUMPI_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 2 items.
    c2_bv10 = b.const("bv10", 2)
    underflow = b.ult(sp, c2_bv10)

    # Out-of-gas.
    c_gas = b.const("bv64", JUMPI_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Read dest (TOS = sp-1, bv256) and cond (NOS = sp-2, bv256).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    dest_full = b.read("bv256", stack, sp_m1)
    cond_nid = b.read("bv256", stack, sp_m2)

    # Truncate destination to bv16 (contracts fit within 64 KiB).
    dest16 = b.slice("bv16", dest_full, 15, 0)

    # Branch: if cond == 0 fall through, else jump.
    cond_zero = b.eq(cond_nid, b.const("bv256", 0))
    pc_fall = b.add("bv16", pc, b.const("bv16", JUMPI_SIZE))
    pc_new = b.ite("bv16", cond_zero, pc_fall, dest16)
    pc_next = b.ite("bv16", exec_, pc_new, pc)

    # Stack pointer decreases by 2 (both operands consumed).
    sp_dec2 = b.sub("bv10", sp, b.const("bv10", 2))
    sp_next = b.ite("bv10", exec_, sp_dec2, sp)

    gas_next = b.ite("bv64", exec_, b.sub("bv64", gas, c_gas), gas)
    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp_next,
        stack=stack,
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
# ISZERO lowering (SCHEMA.md §12, opcode 0x15)
# ---------------------------------------------------------------------------

#: Gas cost for ISZERO (SCHEMA.md §10.1, London).
ISZERO_GAS: int = 3

#: Number of bytes consumed by ISZERO (single-byte opcode).
ISZERO_SIZE: int = 1


def lower_iszero(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one ISZERO instruction to BTOR2 next-state expressions.

    Pops TOS (``stack[sp-1]``, bv256).  If TOS == 0 pushes the bv256
    value 1; otherwise pushes 0.  The result is written back to the
    same stack slot (TOS replaced in-place), so the net sp change is 0.

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 1
    - Out-of-gas: gas < ISZERO_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 1 item.
    underflow = b.ult(sp, b.const("bv10", 1))

    # Out-of-gas.
    c_gas = b.const("bv64", ISZERO_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Read TOS at slot sp-1.
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    tos = b.read("bv256", stack, sp_m1)

    # ISZERO: 1 if tos == 0, else 0 (both as bv256).
    tos_zero = b.eq(tos, b.const("bv256", 0))
    result_nid = b.ite("bv256", tos_zero, b.const("bv256", 1), b.const("bv256", 0))

    # Write result back to the same TOS slot (in-place replacement).
    stack_written = b.write("stack_t", stack, sp_m1, result_nid)
    pc_new = b.add("bv16", pc, b.const("bv16", ISZERO_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

    stack_next = b.ite("stack_t", exec_, stack_written, stack)
    pc_next = b.ite("bv16", exec_, pc_new, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp,
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
# DUP1 lowering (SCHEMA.md §12, opcode 0x80)
# ---------------------------------------------------------------------------

#: Gas cost for DUP1 (SCHEMA.md §10.1, London — same as all DUPn).
DUP1_GAS: int = 3

#: Number of bytes consumed by DUP1 (single-byte opcode).
DUP1_SIZE: int = 1


def lower_dup1(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one DUP1 instruction to BTOR2 next-state expressions.

    Reads TOS (``stack[sp-1]``, bv256) and writes a copy to ``stack[sp]``,
    then increments ``sp`` by 1.  TOS is the top-of-stack; DUP1 duplicates
    the item at depth 1.

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 1 (nothing to duplicate)
    - Stack overflow: sp == 1024 (no room for the copy)
    - Out-of-gas: gas < DUP1_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 1 item.
    underflow = b.ult(sp, b.const("bv10", 1))

    # Stack overflow: sp == 1024 (no room for the duplicate).
    sp_full = b.uext("bv256", sp, 256 - 10)
    overflow = b.eq(sp_full, b.const("bv256", 1024))

    # Out-of-gas.
    c_gas = b.const("bv64", DUP1_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", b.or_("bv1", underflow, overflow), oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Read TOS at slot sp-1.
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    tos = b.read("bv256", stack, sp_m1)

    # Write copy to stack[sp] (the new top slot).
    stack_written = b.write("stack_t", stack, sp, tos)
    sp_new = b.add("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", DUP1_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# MSTORE8 lowering (SCHEMA.md §12, opcode 0x53)
# ---------------------------------------------------------------------------

#: Base gas cost for MSTORE8 (SCHEMA.md §10.1, London).
MSTORE8_GAS: int = 3

#: Number of bytes consumed by MSTORE8 (single-byte opcode).
MSTORE8_SIZE: int = 1


def lower_mstore8(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one MSTORE8 instruction to BTOR2 next-state expressions.

    Pops offset (TOS = ``stack[sp-1]``) and byte_val (NOS = ``stack[sp-2]``);
    writes the low byte of byte_val to ``mem[offset]``; sp -= 2; pc += 1.

    Memory expansion (SCHEMA.md §7.1):
      new_mem_words = (offset + 32) udiv 32   [= ceil((offset+1)/32)]
      expansion gas = Cmem(new_mem_words) − Cmem(mem_words) when needed
      Cmem(n) = n*n/512 + 3*n  (bv256; truncated to bv64 for gas arithmetic)

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < 3 + expansion_gas
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need ≥ 2 items.
    underflow = b.ult(sp, b.const("bv10", 2))

    # TOS = offset (bv256), NOS = byte_val (bv256).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    offset = b.read("bv256", stack, sp_m1)
    byte_val_256 = b.read("bv256", stack, sp_m2)
    byte_val_8 = b.slice("bv8", byte_val_256, 7, 0)

    # Memory expansion: new_mem_words = (offset + 32) udiv 32.
    new_mw_calc = b.udiv(
        "bv256",
        b.add("bv256", offset, b.const("bv256", 32)),
        b.const("bv256", 32),
    )
    needs_exp = b.ugt(new_mw_calc, mem_words)
    actual_new_mw = b.ite("bv256", needs_exp, new_mw_calc, mem_words)

    # Cmem(actual_new_mw) and Cmem(mem_words) in bv256.
    nmw_sq = b.mul("bv256", actual_new_mw, actual_new_mw)
    cmem_new = b.add(
        "bv256",
        b.udiv("bv256", nmw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), actual_new_mw),
    )
    mw_sq = b.mul("bv256", mem_words, mem_words)
    cmem_old = b.add(
        "bv256",
        b.udiv("bv256", mw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), mem_words),
    )

    # delta_gas (bv256 → bv64 truncation is safe for practical gas values).
    delta_256 = b.sub("bv256", cmem_new, cmem_old)
    delta_64 = b.slice("bv64", delta_256, 63, 0)

    # Total gas cost: base + expansion (bv64).
    c_base = b.const("bv64", MSTORE8_GAS)
    total_gas_64 = b.add("bv64", c_base, delta_64)
    oog = b.ult(gas, total_gas_64)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Write low byte to mem[offset].
    mem_written = b.write("mem_t", mem, offset, byte_val_8)

    sp_new = b.sub("bv10", sp, b.const("bv10", 2))
    pc_new = b.add("bv16", pc, b.const("bv16", MSTORE8_SIZE))
    gas_new = b.sub("bv64", gas, total_gas_64)

    sp_next = b.ite("bv10", exec_, sp_new, sp)
    mem_next = b.ite("mem_t", exec_, mem_written, mem)
    mem_words_next = b.ite("bv256", exec_, actual_new_mw, mem_words)
    pc_next = b.ite("bv16", exec_, pc_new, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp_next,
        stack=stack,
        mem=mem_next,
        mem_words=mem_words_next,
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
# PUSH0 lowering (SCHEMA.md §12, opcode 0x5f)
# ---------------------------------------------------------------------------

#: Gas cost for PUSH0 (SCHEMA.md §10.1, EIP-3855).
PUSH0_GAS: int = 2

#: Number of bytes consumed by PUSH0 (single-byte opcode, no immediate).
PUSH0_SIZE: int = 1


def lower_push0(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one PUSH0 instruction to BTOR2 next-state expressions.

    Pushes the constant 0 (bv256) to ``stack[sp]``; sp += 1; pc += 1.
    Gas cost: 2 (EIP-3855, SCHEMA.md §10.1).

    Trap conditions (SCHEMA.md §11):
    - Stack overflow: sp == 1024
    - Out-of-gas: gas < 2
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack overflow: sp == 1024.
    sp_full = b.uext("bv256", sp, 256 - 10)
    overflow = b.eq(sp_full, b.const("bv256", 1024))

    # Out-of-gas.
    c_gas = b.const("bv64", PUSH0_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", overflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Push 0 to stack[sp].
    stack_written = b.write("stack_t", stack, sp, b.const("bv256", 0))
    sp_new = b.add("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", PUSH0_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# RETURN lowering (SCHEMA.md §12, opcode 0xf3)
# ---------------------------------------------------------------------------

#: Base gas cost for RETURN (SCHEMA.md §10.1 — zero; expansion is dynamic).
RETURN_GAS: int = 0

#: Number of bytes consumed by RETURN (single-byte opcode).
RETURN_SIZE: int = 1


def lower_return(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one RETURN instruction to BTOR2 next-state expressions.

    Pops offset (TOS = ``stack[sp-1]``) and length (NOS = ``stack[sp-2]``).
    Copies ``length`` bytes from ``mem[offset..]`` into ``returndata``,
    sets ``returndatasize = length``, and halts cleanly (``halted=1,
    trap=0``).

    P8 scope limitation: only one byte (``mem[offset]``) is written to
    ``returndata[0]``.  Correct for length=1; future iterations will
    unroll arbitrary lengths.

    Memory expansion (SCHEMA.md §7.1):
      new_mem_words = (offset + length + 31) udiv 32  [= ceil((off+len)/32)]
      expansion gas = Cmem(new_mem_words) − Cmem(mem_words) when needed
      Base gas cost is zero (SCHEMA.md §10.1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < expansion_gas
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need ≥ 2 items.
    underflow = b.ult(sp, b.const("bv10", 2))

    # TOS = offset (bv256), NOS = length (bv256).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    offset = b.read("bv256", stack, sp_m1)
    length = b.read("bv256", stack, sp_m2)

    # Memory expansion: ceil((offset + length) / 32) = (offset+length+31) udiv 32.
    sum_ol = b.add("bv256", offset, length)
    new_mw_calc = b.udiv(
        "bv256",
        b.add("bv256", sum_ol, b.const("bv256", 31)),
        b.const("bv256", 32),
    )
    needs_exp = b.ugt(new_mw_calc, mem_words)
    actual_new_mw = b.ite("bv256", needs_exp, new_mw_calc, mem_words)

    # Cmem(actual_new_mw) and Cmem(mem_words) in bv256.
    nmw_sq = b.mul("bv256", actual_new_mw, actual_new_mw)
    cmem_new = b.add(
        "bv256",
        b.udiv("bv256", nmw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), actual_new_mw),
    )
    mw_sq = b.mul("bv256", mem_words, mem_words)
    cmem_old = b.add(
        "bv256",
        b.udiv("bv256", mw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), mem_words),
    )
    delta_256 = b.sub("bv256", cmem_new, cmem_old)
    exp_gas_64 = b.slice("bv64", delta_256, 63, 0)

    # OOG: base cost is 0, so only expansion gas matters.
    oog = b.ult(gas, exp_gas_64)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Copy first byte: returndata[0] = mem[offset]  (P8 scope: length=1).
    mem_byte = b.read("bv8", mem, offset)
    rd_written = b.write("mem_t", returndata, b.const("bv256", 0), mem_byte)

    gas_new = b.sub("bv64", gas, exp_gas_64)

    rd_next = b.ite("mem_t", exec_, rd_written, returndata)
    rds_next = b.ite("bv256", exec_, length, returndatasize)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    # RETURN halts cleanly on exec_; trap path also halts but sets trap.
    halted_next = b.or_("bv1", halted, b.or_("bv1", exec_, trap_from_op))
    trap_next = b.or_("bv1", trap, trap_from_op)

    return EvmLoweringResult(
        sp=sp,
        stack=stack,
        mem=mem,
        mem_words=mem_words,
        sto=sto,
        sto_warm=sto_warm,
        pc=pc,
        gas=gas_next,
        trap=trap_next,
        halted=halted_next,
        returndata=rd_next,
        returndatasize=rds_next,
    )


# ---------------------------------------------------------------------------
# CALLDATASIZE lowering (SCHEMA.md §12, opcode 0x36)
# ---------------------------------------------------------------------------

#: Gas cost for CALLDATASIZE (SCHEMA.md §10.1, London).
CALLDATASIZE_GAS: int = 2

#: Number of bytes consumed by CALLDATASIZE (single-byte opcode).
CALLDATASIZE_SIZE: int = 1


def lower_calldatasize(
    b: Btor2Builder,
    machine_nids: dict[str, int],
    ctx_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one CALLDATASIZE instruction to BTOR2 next-state expressions.

    Pushes ``calldatasize`` (bv256, a symbolic context input) onto
    ``stack[sp]``; sp += 1; pc += 1; gas -= 2.

    Trap conditions (SCHEMA.md §11):
    - Stack overflow: sp == 1024
    - Out-of-gas: gas < CALLDATASIZE_GAS
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
    calldatasize_nid = ctx_nids["calldatasize"]

    no_exec = b.or_("bv1", halted, trap)

    # Stack overflow: sp == 1024.
    sp_full = b.uext("bv256", sp, 256 - 10)
    overflow = b.eq(sp_full, b.const("bv256", 1024))

    # Out-of-gas.
    c_gas = b.const("bv64", CALLDATASIZE_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", overflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Push calldatasize to stack[sp].
    stack_written = b.write("stack_t", stack, sp, calldatasize_nid)
    sp_new = b.add("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", CALLDATASIZE_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# MLOAD lowering (SCHEMA.md §12, opcode 0x51)
# ---------------------------------------------------------------------------

#: Base gas cost for MLOAD (SCHEMA.md §10.1, London).
MLOAD_GAS: int = 3

#: Number of bytes consumed by MLOAD (single-byte opcode).
MLOAD_SIZE: int = 1


def lower_mload(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one MLOAD instruction to BTOR2 next-state expressions.

    Pops offset (TOS = ``stack[sp-1]``); reads 32 bytes big-endian from
    ``mem[offset..offset+31]``; pushes the resulting bv256 word back at
    the same stack slot.  Net sp change is 0.

    Memory expansion (SCHEMA.md §7.1):
      new_mem_words = (offset + 32) udiv 32   [= ceil((offset+32)/32)]
      expansion gas = Cmem(new_mem_words) − Cmem(mem_words) when needed

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 1
    - Out-of-gas: gas < MLOAD_GAS + expansion_gas
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 1 item.
    underflow = b.ult(sp, b.const("bv10", 1))

    # TOS = offset (bv256).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    offset = b.read("bv256", stack, sp_m1)

    # Memory expansion: new_mem_words = (offset + 32) udiv 32.
    new_mw_calc = b.udiv(
        "bv256",
        b.add("bv256", offset, b.const("bv256", 32)),
        b.const("bv256", 32),
    )
    needs_exp = b.ugt(new_mw_calc, mem_words)
    actual_new_mw = b.ite("bv256", needs_exp, new_mw_calc, mem_words)

    # Cmem(actual_new_mw) and Cmem(mem_words) in bv256.
    nmw_sq = b.mul("bv256", actual_new_mw, actual_new_mw)
    cmem_new = b.add(
        "bv256",
        b.udiv("bv256", nmw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), actual_new_mw),
    )
    mw_sq = b.mul("bv256", mem_words, mem_words)
    cmem_old = b.add(
        "bv256",
        b.udiv("bv256", mw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), mem_words),
    )
    delta_256 = b.sub("bv256", cmem_new, cmem_old)
    delta_64 = b.slice("bv64", delta_256, 63, 0)

    # Total gas cost: base + expansion.
    c_base = b.const("bv64", MLOAD_GAS)
    total_gas_64 = b.add("bv64", c_base, delta_64)
    oog = b.ult(gas, total_gas_64)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Read 32 bytes big-endian from mem[offset..offset+31].
    byte_nids: list[int] = []
    for k in range(32):
        idx = b.add("bv256", offset, b.const("bv256", k))
        byte_nids.append(b.read("bv8", mem, idx))

    word_nid: int = byte_nids[0]  # bv8 so far
    for k in range(1, 32):
        width = 8 * (k + 1)
        word_nid = b.concat(f"bv{width}", word_nid, byte_nids[k])
    # word_nid is now bv256.

    # Write result back to TOS slot (in-place replacement; net sp = 0).
    stack_written = b.write("stack_t", stack, sp_m1, word_nid)
    pc_new = b.add("bv16", pc, b.const("bv16", MLOAD_SIZE))
    gas_new = b.sub("bv64", gas, total_gas_64)

    stack_next = b.ite("stack_t", exec_, stack_written, stack)
    mem_words_next = b.ite("bv256", exec_, actual_new_mw, mem_words)
    pc_next = b.ite("bv16", exec_, pc_new, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp,
        stack=stack_next,
        mem=mem,
        mem_words=mem_words_next,
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
# MSTORE lowering (SCHEMA.md §12, opcode 0x52)
# ---------------------------------------------------------------------------

#: Base gas cost for MSTORE (SCHEMA.md §10.1, London).
MSTORE_GAS: int = 3

#: Number of bytes consumed by MSTORE (single-byte opcode).
MSTORE_SIZE: int = 1


def lower_mstore(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one MSTORE instruction to BTOR2 next-state expressions.

    Pops offset (TOS = ``stack[sp-1]``) and value (NOS = ``stack[sp-2]``);
    writes the 32-byte big-endian encoding of value to ``mem[offset..offset+31]``;
    sp -= 2; pc += 1.

    Memory expansion (SCHEMA.md §7.1):
      new_mem_words = (offset + 32) udiv 32   [= ceil((offset+32)/32)]
      expansion gas = Cmem(new_mem_words) − Cmem(mem_words) when needed

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < MSTORE_GAS + expansion_gas
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 2 items.
    underflow = b.ult(sp, b.const("bv10", 2))

    # TOS = offset (bv256), NOS = value (bv256).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    offset = b.read("bv256", stack, sp_m1)
    value = b.read("bv256", stack, sp_m2)

    # Memory expansion: new_mem_words = (offset + 32) udiv 32.
    new_mw_calc = b.udiv(
        "bv256",
        b.add("bv256", offset, b.const("bv256", 32)),
        b.const("bv256", 32),
    )
    needs_exp = b.ugt(new_mw_calc, mem_words)
    actual_new_mw = b.ite("bv256", needs_exp, new_mw_calc, mem_words)

    # Cmem(actual_new_mw) and Cmem(mem_words) in bv256.
    nmw_sq = b.mul("bv256", actual_new_mw, actual_new_mw)
    cmem_new = b.add(
        "bv256",
        b.udiv("bv256", nmw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), actual_new_mw),
    )
    mw_sq = b.mul("bv256", mem_words, mem_words)
    cmem_old = b.add(
        "bv256",
        b.udiv("bv256", mw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), mem_words),
    )
    delta_256 = b.sub("bv256", cmem_new, cmem_old)
    delta_64 = b.slice("bv64", delta_256, 63, 0)

    # Total gas cost: base + expansion.
    c_base = b.const("bv64", MSTORE_GAS)
    total_gas_64 = b.add("bv64", c_base, delta_64)
    oog = b.ult(gas, total_gas_64)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Write 32 bytes big-endian of value to mem[offset..offset+31].
    # Byte k (big-endian): bits [255-8k : 255-8k-7] of value.
    mem_result = mem
    for k in range(32):
        idx = b.add("bv256", offset, b.const("bv256", k))
        hi_bit = 255 - 8 * k
        lo_bit = hi_bit - 7
        byte_k = b.slice("bv8", value, hi_bit, lo_bit)
        mem_result = b.write("mem_t", mem_result, idx, byte_k)

    sp_new = b.sub("bv10", sp, b.const("bv10", 2))
    pc_new = b.add("bv16", pc, b.const("bv16", MSTORE_SIZE))
    gas_new = b.sub("bv64", gas, total_gas_64)

    sp_next = b.ite("bv10", exec_, sp_new, sp)
    mem_next = b.ite("mem_t", exec_, mem_result, mem)
    mem_words_next = b.ite("bv256", exec_, actual_new_mw, mem_words)
    pc_next = b.ite("bv16", exec_, pc_new, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp_next,
        stack=stack,
        mem=mem_next,
        mem_words=mem_words_next,
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
# LT lowering (SCHEMA.md §12, opcode 0x10)
# ---------------------------------------------------------------------------

#: Gas cost for LT (SCHEMA.md §10.1, London).
LT_GAS: int = 3

#: Number of bytes consumed by LT (single-byte opcode).
LT_SIZE: int = 1


def lower_lt(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one LT instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes 1 if ``a < b`` (unsigned), else 0, to ``stack[sp-2]``.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < LT_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 2 items.
    underflow = b.ult(sp, b.const("bv10", 2))

    # Out-of-gas.
    c_gas = b.const("bv64", LT_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Read operands: a = TOS (sp-1), b = NOS (sp-2).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)

    # LT result: 1 if a < b (unsigned), else 0.
    lt_cond = b.ult(a_nid, b_nid)
    result_nid = b.ite("bv256", lt_cond, b.const("bv256", 1), b.const("bv256", 0))

    # Write result to stack[sp-2]; sp decrements by 1.
    stack_written = b.write("stack_t", stack, sp_m2, result_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", LT_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# GT lowering (SCHEMA.md §12, opcode 0x11)
# ---------------------------------------------------------------------------

#: Gas cost for GT (SCHEMA.md §10.1, London).
GT_GAS: int = 3

#: Number of bytes consumed by GT (single-byte opcode).
GT_SIZE: int = 1


def lower_gt(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one GT instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes 1 if ``a > b`` (unsigned), else 0, to ``stack[sp-2]``.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < GT_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 2 items.
    underflow = b.ult(sp, b.const("bv10", 2))

    # Out-of-gas.
    c_gas = b.const("bv64", GT_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Read operands: a = TOS (sp-1), b = NOS (sp-2).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)

    # GT result: 1 if a > b (unsigned), else 0.
    gt_cond = b.ugt(a_nid, b_nid)
    result_nid = b.ite("bv256", gt_cond, b.const("bv256", 1), b.const("bv256", 0))

    # Write result to stack[sp-2]; sp decrements by 1.
    stack_written = b.write("stack_t", stack, sp_m2, result_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", GT_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# EQ lowering (SCHEMA.md §12, opcode 0x14)
# ---------------------------------------------------------------------------

#: Gas cost for EQ (SCHEMA.md §10.1, London).
EQ_GAS: int = 3

#: Number of bytes consumed by EQ (single-byte opcode).
EQ_SIZE: int = 1


def lower_eq_op(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one EQ instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes 1 if ``a == b``, else 0, to ``stack[sp-2]``.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < EQ_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 2 items.
    underflow = b.ult(sp, b.const("bv10", 2))

    # Out-of-gas.
    c_gas = b.const("bv64", EQ_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Read operands: a = TOS (sp-1), b = NOS (sp-2).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)

    # EQ result: 1 if a == b, else 0.
    eq_cond = b.eq(a_nid, b_nid)
    result_nid = b.ite("bv256", eq_cond, b.const("bv256", 1), b.const("bv256", 0))

    # Write result to stack[sp-2]; sp decrements by 1.
    stack_written = b.write("stack_t", stack, sp_m2, result_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", EQ_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# CALLDATACOPY lowering (SCHEMA.md §12, opcode 0x37)
# ---------------------------------------------------------------------------

#: Base gas cost for CALLDATACOPY (SCHEMA.md §10.1, London).
CALLDATACOPY_GAS: int = 3

#: Per-word gas cost (G_copy) for CALLDATACOPY.
CALLDATACOPY_WORD_GAS: int = 3

#: Number of bytes consumed by CALLDATACOPY (single-byte opcode).
CALLDATACOPY_SIZE: int = 1

#: Maximum bytes unrolled symbolically (compile-time bound).
CALLDATACOPY_MAX_LEN: int = 32


def lower_calldatacopy(
    b: Btor2Builder,
    machine_nids: dict[str, int],
    ctx_nids: dict[str, int],
    max_len: int = CALLDATACOPY_MAX_LEN,
) -> EvmLoweringResult:
    """Lower one CALLDATACOPY instruction to BTOR2 next-state expressions.

    Pops dest (TOS = ``stack[sp-1]``), offset (NOS = ``stack[sp-2]``),
    and length (3rd = ``stack[sp-3]``).  Copies bytes from
    ``calldata[offset..offset+length-1]`` to ``mem[dest..dest+length-1]``
    up to ``max_len`` bytes (default: 32 — one 256-bit word).  Bytes beyond
    ``max_len`` are not modelled.  sp -= 3.

    Gas (SCHEMA.md §10.1 + §7.1):
      base = CALLDATACOPY_GAS (3)
      word_cost = CALLDATACOPY_WORD_GAS * ceil(length / 32) (symbolic)
      expansion_gas = Cmem(ceil((dest + length) / 32)) − Cmem(mem_words)
      total = base + word_cost + expansion_gas

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 3
    - Out-of-gas: gas < total
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
    calldata = ctx_nids["calldata"]

    no_exec = b.or_("bv1", halted, trap)

    # Stack underflow: need at least 3 items.
    underflow = b.ult(sp, b.const("bv10", 3))

    # Pop operands: dest=TOS, offset=NOS, length=3rd.
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    sp_m3 = b.sub("bv10", sp, b.const("bv10", 3))
    dest = b.read("bv256", stack, sp_m1)
    offset = b.read("bv256", stack, sp_m2)
    length = b.read("bv256", stack, sp_m3)

    # Word cost: 3 * ceil(length / 32) = 3 * ((length + 31) udiv 32).
    word_count_256 = b.udiv(
        "bv256",
        b.add("bv256", length, b.const("bv256", 31)),
        b.const("bv256", 32),
    )
    word_cost_256 = b.mul("bv256", b.const("bv256", CALLDATACOPY_WORD_GAS), word_count_256)
    word_cost_64 = b.slice("bv64", word_cost_256, 63, 0)

    # Memory expansion: new_mem_words = (dest + length + 31) udiv 32.
    new_mw_calc = b.udiv(
        "bv256",
        b.add("bv256", b.add("bv256", dest, length), b.const("bv256", 31)),
        b.const("bv256", 32),
    )
    needs_exp = b.ugt(new_mw_calc, mem_words)
    actual_new_mw = b.ite("bv256", needs_exp, new_mw_calc, mem_words)

    # Cmem(actual_new_mw) and Cmem(mem_words).
    nmw_sq = b.mul("bv256", actual_new_mw, actual_new_mw)
    cmem_new = b.add(
        "bv256",
        b.udiv("bv256", nmw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), actual_new_mw),
    )
    mw_sq = b.mul("bv256", mem_words, mem_words)
    cmem_old = b.add(
        "bv256",
        b.udiv("bv256", mw_sq, b.const("bv256", 512)),
        b.mul("bv256", b.const("bv256", 3), mem_words),
    )
    delta_256 = b.sub("bv256", cmem_new, cmem_old)
    exp_gas_64 = b.slice("bv64", delta_256, 63, 0)

    # Total gas = base + word_cost + expansion.
    c_base = b.const("bv64", CALLDATACOPY_GAS)
    total_gas_64 = b.add("bv64", b.add("bv64", c_base, word_cost_64), exp_gas_64)
    oog = b.ult(gas, total_gas_64)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Copy up to max_len bytes: for each k in [0, max_len), if k < length
    # write calldata[offset+k] to mem[dest+k], else keep original byte.
    mem_result = mem
    for k in range(max_len):
        k_nid = b.const("bv256", k)
        src_idx = b.add("bv256", offset, k_nid)
        dst_idx = b.add("bv256", dest, k_nid)
        byte_from_cd = b.read("bv8", calldata, src_idx)
        in_range = b.ult(k_nid, length)  # k < length (bv1)
        orig_byte = b.read("bv8", mem, dst_idx)  # read from original mem
        new_byte = b.ite("bv8", in_range, byte_from_cd, orig_byte)
        mem_result = b.write("mem_t", mem_result, dst_idx, new_byte)

    sp_new = b.sub("bv10", sp, b.const("bv10", 3))
    pc_new = b.add("bv16", pc, b.const("bv16", CALLDATACOPY_SIZE))
    gas_new = b.sub("bv64", gas, total_gas_64)

    sp_next = b.ite("bv10", exec_, sp_new, sp)
    mem_next = b.ite("mem_t", exec_, mem_result, mem)
    mem_words_next = b.ite("bv256", exec_, actual_new_mw, mem_words)
    pc_next = b.ite("bv16", exec_, pc_new, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp_next,
        stack=stack,
        mem=mem_next,
        mem_words=mem_words_next,
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
# SUB lowering (SCHEMA.md §12, opcode 0x03)
# ---------------------------------------------------------------------------

#: Gas cost for SUB (SCHEMA.md §10.1, London — VERYLOW tier).
SUB_GAS: int = 3

#: Number of bytes consumed by SUB (single-byte opcode).
SUB_SIZE: int = 1


def lower_sub(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one SUB instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes ``a - b`` (bv256 wrapping mod 2^256) to ``stack[sp-2]``.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < SUB_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", SUB_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)
    diff_nid = b.sub("bv256", a_nid, b_nid)

    stack_written = b.write("stack_t", stack, sp_m2, diff_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", SUB_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# MUL lowering (SCHEMA.md §12, opcode 0x02)
# ---------------------------------------------------------------------------

#: Gas cost for MUL (SCHEMA.md §10.1, London — LOW tier).
MUL_GAS: int = 5

#: Number of bytes consumed by MUL (single-byte opcode).
MUL_SIZE: int = 1


def lower_mul(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one MUL instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes ``a * b`` (bv256 wrapping mod 2^256) to ``stack[sp-2]``.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < MUL_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", MUL_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)
    prod_nid = b.mul("bv256", a_nid, b_nid)

    stack_written = b.write("stack_t", stack, sp_m2, prod_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", MUL_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# AND lowering (SCHEMA.md §12, opcode 0x16)
# ---------------------------------------------------------------------------

#: Gas cost for AND (SCHEMA.md §10.1, London — VERYLOW tier).
AND_GAS: int = 3

#: Number of bytes consumed by AND (single-byte opcode).
AND_SIZE: int = 1


def lower_and(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one AND instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes ``a & b`` (bitwise AND) to ``stack[sp-2]``.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < AND_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", AND_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)
    and_nid = b.and_("bv256", a_nid, b_nid)

    stack_written = b.write("stack_t", stack, sp_m2, and_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", AND_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# OR lowering (SCHEMA.md §12, opcode 0x17)
# ---------------------------------------------------------------------------

#: Gas cost for OR (SCHEMA.md §10.1, London — VERYLOW tier).
OR_GAS: int = 3

#: Number of bytes consumed by OR (single-byte opcode).
OR_SIZE: int = 1


def lower_or(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one OR instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes ``a | b`` (bitwise OR) to ``stack[sp-2]``.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < OR_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", OR_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)
    or_nid = b.or_("bv256", a_nid, b_nid)

    stack_written = b.write("stack_t", stack, sp_m2, or_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", OR_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# XOR lowering (SCHEMA.md §12, opcode 0x18)
# ---------------------------------------------------------------------------

#: Gas cost for XOR (SCHEMA.md §10.1, London — VERYLOW tier).
XOR_GAS: int = 3

#: Number of bytes consumed by XOR (single-byte opcode).
XOR_SIZE: int = 1


def lower_xor(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one XOR instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes ``a ^ b`` (bitwise XOR) to ``stack[sp-2]``.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < XOR_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", XOR_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)
    xor_nid = b.xor("bv256", a_nid, b_nid)

    stack_written = b.write("stack_t", stack, sp_m2, xor_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", XOR_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# NOT lowering (SCHEMA.md §12, opcode 0x19)
# ---------------------------------------------------------------------------

#: Gas cost for NOT (SCHEMA.md §10.1, London — VERYLOW tier).
NOT_GAS: int = 3

#: Number of bytes consumed by NOT (single-byte opcode).
NOT_SIZE: int = 1


def lower_not(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one NOT instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256); pushes ``~a`` (bitwise complement,
    all 256 bits inverted) back to the same slot.  Net sp change is 0
    (pop 1, push 1 in-place).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 1
    - Out-of-gas: gas < NOT_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 1))
    c_gas = b.const("bv64", NOT_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    a_nid = b.read("bv256", stack, sp_m1)
    not_nid = b.not_("bv256", a_nid)

    stack_written = b.write("stack_t", stack, sp_m1, not_nid)
    pc_new = b.add("bv16", pc, b.const("bv16", NOT_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

    stack_next = b.ite("stack_t", exec_, stack_written, stack)
    pc_next = b.ite("bv16", exec_, pc_new, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp,
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
# JUMP lowering (SCHEMA.md §12, opcode 0x56)
# ---------------------------------------------------------------------------

#: Gas cost for JUMP (SCHEMA.md §10.1, London — MID tier).
JUMP_GAS: int = 8

#: Number of bytes consumed by JUMP (single-byte opcode).
JUMP_SIZE: int = 1


def lower_jump(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one JUMP instruction to BTOR2 next-state expressions.

    Pops ``dest`` (TOS = ``stack[sp-1]``, bv256 truncated to bv16) and
    unconditionally sets ``pc = dest[15:0]``.  sp decrements by 1.

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 1
    - Out-of-gas: gas < JUMP_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 1))
    c_gas = b.const("bv64", JUMP_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    dest_full = b.read("bv256", stack, sp_m1)
    dest16 = b.slice("bv16", dest_full, 15, 0)

    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    gas_new = b.sub("bv64", gas, c_gas)

    sp_next = b.ite("bv10", exec_, sp_new, sp)
    pc_next = b.ite("bv16", exec_, dest16, pc)
    gas_next = b.ite("bv64", exec_, gas_new, gas)

    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp_next,
        stack=stack,
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
# DIV lowering (SCHEMA.md §12, opcode 0x04)
# ---------------------------------------------------------------------------

#: Gas cost for DIV (SCHEMA.md §10.1, London — LOW tier).
DIV_GAS: int = 5

#: Number of bytes consumed by DIV (single-byte opcode).
DIV_SIZE: int = 1


def lower_div(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one DIV instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256, numerator) and NOS
    (``b = stack[sp-2]``, bv256, denominator); pushes ``a / b``
    (unsigned integer division) to ``stack[sp-2]``.  If ``b == 0``
    the result is 0 (EVM convention).  Net sp change is -1.

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < DIV_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", DIV_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)  # TOS = numerator
    bv_nid = b.read("bv256", stack, sp_m2)  # NOS = denominator

    # EVM: a / 0 == 0; BTOR2 udiv(x, 0) gives all-ones — guard with ite.
    b_is_zero = b.eq(bv_nid, b.const("bv256", 0))
    raw_div = b.udiv("bv256", a_nid, bv_nid)
    result = b.ite("bv256", b_is_zero, b.const("bv256", 0), raw_div)

    stack_written = b.write("stack_t", stack, sp_m2, result)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", DIV_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# MOD lowering (SCHEMA.md §12, opcode 0x06)
# ---------------------------------------------------------------------------

#: Gas cost for MOD (SCHEMA.md §10.1, London — LOW tier).
MOD_GAS: int = 5

#: Number of bytes consumed by MOD (single-byte opcode).
MOD_SIZE: int = 1


def lower_mod(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one MOD instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes ``a % b`` (unsigned remainder) to ``stack[sp-2]``.
    If ``b == 0`` the result is 0 (EVM convention).  Net sp change is -1.

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < MOD_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", MOD_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)  # TOS
    bv_nid = b.read("bv256", stack, sp_m2)  # NOS = divisor

    # EVM: a % 0 == 0; BTOR2 urem(x, 0) gives all-ones — guard with ite.
    b_is_zero = b.eq(bv_nid, b.const("bv256", 0))
    raw_mod = b.urem("bv256", a_nid, bv_nid)
    result = b.ite("bv256", b_is_zero, b.const("bv256", 0), raw_mod)

    stack_written = b.write("stack_t", stack, sp_m2, result)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", MOD_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# ADDMOD lowering (SCHEMA.md §12, opcode 0x08)
# ---------------------------------------------------------------------------

#: Gas cost for ADDMOD (SCHEMA.md §10.1, London — MID tier).
ADDMOD_GAS: int = 8

#: Number of bytes consumed by ADDMOD (single-byte opcode).
ADDMOD_SIZE: int = 1


def lower_addmod(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one ADDMOD instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``), NOS (``b = stack[sp-2]``), and 3rd
    (``N = stack[sp-3]``); pushes ``(a + b) % N`` (all bv256 unsigned).
    The addition is performed with full 257-bit precision so intermediate
    overflow beyond 2^256 is preserved.  If ``N == 0`` the result is 0.
    Net sp change is -2 (pop 3, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 3
    - Out-of-gas: gas < ADDMOD_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 3))
    c_gas = b.const("bv64", ADDMOD_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    sp_m3 = b.sub("bv10", sp, b.const("bv10", 3))
    a_nid = b.read("bv256", stack, sp_m1)   # TOS
    bv_nid = b.read("bv256", stack, sp_m2)  # NOS
    n_nid = b.read("bv256", stack, sp_m3)   # 3rd = modulus

    # 257-bit arithmetic so (a + b) does not wrap mod 2^256.
    a_257 = b.uext("bv257", a_nid, 1)
    b_257 = b.uext("bv257", bv_nid, 1)
    n_257 = b.uext("bv257", n_nid, 1)
    sum_257 = b.add("bv257", a_257, b_257)
    raw_mod = b.urem("bv257", sum_257, n_257)
    result_256 = b.slice("bv256", raw_mod, 255, 0)

    # EVM: result is 0 when N == 0.
    n_is_zero = b.eq(n_nid, b.const("bv256", 0))
    result = b.ite("bv256", n_is_zero, b.const("bv256", 0), result_256)

    # Write result to stack[sp-3]; sp decrements by 2.
    stack_written = b.write("stack_t", stack, sp_m3, result)
    sp_new = b.sub("bv10", sp, b.const("bv10", 2))
    pc_new = b.add("bv16", pc, b.const("bv16", ADDMOD_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# MULMOD lowering (SCHEMA.md §12, opcode 0x09)
# ---------------------------------------------------------------------------

#: Gas cost for MULMOD (SCHEMA.md §10.1, London — MID tier).
MULMOD_GAS: int = 8

#: Number of bytes consumed by MULMOD (single-byte opcode).
MULMOD_SIZE: int = 1


def lower_mulmod(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one MULMOD instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``), NOS (``b = stack[sp-2]``), and 3rd
    (``N = stack[sp-3]``); pushes ``(a * b) % N`` (all bv256 unsigned).
    The multiplication is performed with full 512-bit precision so
    intermediate overflow beyond 2^256 is preserved.  If ``N == 0``
    the result is 0.  Net sp change is -2 (pop 3, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 3
    - Out-of-gas: gas < MULMOD_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 3))
    c_gas = b.const("bv64", MULMOD_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    sp_m3 = b.sub("bv10", sp, b.const("bv10", 3))
    a_nid = b.read("bv256", stack, sp_m1)   # TOS
    bv_nid = b.read("bv256", stack, sp_m2)  # NOS
    n_nid = b.read("bv256", stack, sp_m3)   # 3rd = modulus

    # 512-bit arithmetic so (a * b) does not wrap mod 2^256.
    a_512 = b.uext("bv512", a_nid, 256)
    b_512 = b.uext("bv512", bv_nid, 256)
    n_512 = b.uext("bv512", n_nid, 256)
    prod_512 = b.mul("bv512", a_512, b_512)
    raw_mod = b.urem("bv512", prod_512, n_512)
    result_256 = b.slice("bv256", raw_mod, 255, 0)

    # EVM: result is 0 when N == 0.
    n_is_zero = b.eq(n_nid, b.const("bv256", 0))
    result = b.ite("bv256", n_is_zero, b.const("bv256", 0), result_256)

    # Write result to stack[sp-3]; sp decrements by 2.
    stack_written = b.write("stack_t", stack, sp_m3, result)
    sp_new = b.sub("bv10", sp, b.const("bv10", 2))
    pc_new = b.add("bv16", pc, b.const("bv16", MULMOD_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# EXP lowering (SCHEMA.md §12, opcode 0x0a)
# ---------------------------------------------------------------------------

#: Base gas for EXP (SCHEMA.md §10.1, EIP-160).
EXP_GAS_BASE: int = 10

#: Per-byte-of-exponent gas for EXP (EIP-160, Gexpbyte = 50).
EXP_GAS_BYTE: int = 50

#: Gas for a 1-byte (8-bit) exponent: 10 + 50 = 60.
EXP_GAS_1BYTE: int = EXP_GAS_BASE + EXP_GAS_BYTE

#: Number of bits of the exponent modelled (symbolic tractability bound).
#: Only the low EXP_EXPONENT_BITS bits of exponent are used; higher bits
#: are ignored (their contribution would require up to 256 squarings each).
EXP_EXPONENT_BITS: int = 8

#: Number of bytes consumed by EXP (single-byte opcode).
EXP_SIZE: int = 1


def lower_exp(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one EXP instruction to BTOR2 next-state expressions.

    Pops TOS (``base = stack[sp-1]``, bv256) and NOS (``exp =
    stack[sp-2]``, bv256); pushes ``base ** exp mod 2**256``.
    Net sp change is -1 (pop 2, push 1).

    **Symbolic tractability bound**: only the low ``EXP_EXPONENT_BITS``
    (8) bits of ``exp`` are modelled via unrolled square-and-multiply.
    Bits above position 7 are ignored; the result is exact for any
    exponent in [0, 255].

    Gas (EIP-160, SCHEMA.md §10.1):
    - ``exp == 0``: 10
    - ``exp != 0``: 60 (10 + 50 × 1 byte — conservative for the 8-bit bound)

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < gas_cost
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))

    # Gas: ite(exp == 0, EXP_GAS_BASE, EXP_GAS_1BYTE).
    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    base_nid = b.read("bv256", stack, sp_m1)  # TOS = base
    exp_nid = b.read("bv256", stack, sp_m2)   # NOS = exponent

    exp_is_zero = b.eq(exp_nid, b.const("bv256", 0))
    c_gas_zero = b.const("bv64", EXP_GAS_BASE)
    c_gas_one = b.const("bv64", EXP_GAS_1BYTE)
    gas_cost = b.ite("bv64", exp_is_zero, c_gas_zero, c_gas_one)

    oog = b.ult(gas, gas_cost)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    # Square-and-multiply over EXP_EXPONENT_BITS bits of exp (low byte).
    # Bit i of exp_byte contributes base^(2^i) to the product.
    exp_byte = b.slice("bv8", exp_nid, 7, 0)
    result_nid = b.const("bv256", 1)   # accumulator starts at 1
    base_pow_nid = base_nid             # base^(2^0) = base
    for i in range(EXP_EXPONENT_BITS):
        bit_i = b.slice("bv1", exp_byte, i, i)
        result_nid = b.ite(
            "bv256", bit_i, b.mul("bv256", result_nid, base_pow_nid), result_nid
        )
        if i < EXP_EXPONENT_BITS - 1:
            base_pow_nid = b.mul("bv256", base_pow_nid, base_pow_nid)  # square

    stack_written = b.write("stack_t", stack, sp_m2, result_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", EXP_SIZE))
    gas_new = b.sub("bv64", gas, gas_cost)

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


# ---------------------------------------------------------------------------
# BYTE lowering (SCHEMA.md §12, opcode 0x1a)
# ---------------------------------------------------------------------------

#: Gas cost for BYTE (SCHEMA.md §10.1, London — VERYLOW tier).
BYTE_GAS: int = 3

#: Number of bytes consumed by BYTE (single-byte opcode).
BYTE_SIZE: int = 1


def lower_byte(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one BYTE instruction to BTOR2 next-state expressions.

    Pops TOS (``i = stack[sp-1]``, bv256, byte index from MSB) and
    NOS (``x = stack[sp-2]``, bv256); pushes byte ``i`` of ``x``
    zero-extended to 256 bits.  Byte 0 is the most significant byte.
    If ``i >= 32``, result is 0.  Net sp change is -1 (pop 2, push 1).

    Implementation: ``result = (x >> ((31 - i) * 8)) & 0xFF`` when
    ``i < 32``; the guard handles ``i >= 32`` explicitly.

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < BYTE_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", BYTE_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    i_nid = b.read("bv256", stack, sp_m1)   # TOS = byte index (0 = MSB)
    x_nid = b.read("bv256", stack, sp_m2)   # NOS = value

    c_31 = b.const("bv256", 31)
    c_8 = b.const("bv256", 8)
    c_ff = b.const("bv256", 0xFF)
    c_32 = b.const("bv256", 32)
    zero256 = b.const("bv256", 0)

    # shift_bits = (31 - i) * 8  (wraps for i >= 32, but guarded below)
    shift_bits = b.mul("bv256", b.sub("bv256", c_31, i_nid), c_8)
    shifted = b.srl("bv256", x_nid, shift_bits)
    byte_val = b.and_("bv256", shifted, c_ff)

    i_geq_32 = b.uge(i_nid, c_32)
    result_nid = b.ite("bv256", i_geq_32, zero256, byte_val)

    stack_written = b.write("stack_t", stack, sp_m2, result_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", BYTE_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# SHL lowering (SCHEMA.md §12, opcode 0x1b, EIP-145)
# ---------------------------------------------------------------------------

#: Gas cost for SHL (SCHEMA.md §10.1, London — VERYLOW tier, EIP-145).
SHL_GAS: int = 3

#: Number of bytes consumed by SHL (single-byte opcode).
SHL_SIZE: int = 1


def lower_shl(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one SHL instruction to BTOR2 next-state expressions.

    Pops TOS (``shift = stack[sp-1]``, bv256) and NOS
    (``value = stack[sp-2]``, bv256); pushes ``value << shift``
    (logical left shift).  If ``shift >= 256`` the result is 0 per
    EVM spec — BTOR2 ``sll`` with shift >= bit-width already returns 0.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < SHL_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", SHL_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    shift_nid = b.read("bv256", stack, sp_m1)   # TOS = shift amount
    value_nid = b.read("bv256", stack, sp_m2)   # NOS = value to shift

    shl_nid = b.sll("bv256", value_nid, shift_nid)

    stack_written = b.write("stack_t", stack, sp_m2, shl_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", SHL_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# SHR lowering (SCHEMA.md §12, opcode 0x1c, EIP-145)
# ---------------------------------------------------------------------------

#: Gas cost for SHR (SCHEMA.md §10.1, London — VERYLOW tier, EIP-145).
SHR_GAS: int = 3

#: Number of bytes consumed by SHR (single-byte opcode).
SHR_SIZE: int = 1


def lower_shr(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one SHR instruction to BTOR2 next-state expressions.

    Pops TOS (``shift = stack[sp-1]``, bv256) and NOS
    (``value = stack[sp-2]``, bv256); pushes ``value >> shift``
    (logical right shift, unsigned).  If ``shift >= 256`` the result
    is 0 per EVM spec — BTOR2 ``srl`` with shift >= bit-width returns 0.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < SHR_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", SHR_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    shift_nid = b.read("bv256", stack, sp_m1)   # TOS = shift amount
    value_nid = b.read("bv256", stack, sp_m2)   # NOS = value to shift

    shr_nid = b.srl("bv256", value_nid, shift_nid)

    stack_written = b.write("stack_t", stack, sp_m2, shr_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", SHR_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# SAR lowering (SCHEMA.md §12, opcode 0x1d, EIP-145)
# ---------------------------------------------------------------------------

#: Gas cost for SAR (SCHEMA.md §10.1, London — VERYLOW tier, EIP-145).
SAR_GAS: int = 3

#: Number of bytes consumed by SAR (single-byte opcode).
SAR_SIZE: int = 1


def lower_sar(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one SAR instruction to BTOR2 next-state expressions.

    Pops TOS (``shift = stack[sp-1]``, bv256) and NOS
    (``value = stack[sp-2]``, bv256); pushes ``value >> shift``
    (arithmetic right shift, signed two's-complement).  If
    ``shift >= 256``, result is 0 if ``value >= 0`` (MSB=0) or
    all-ones (0xFF..FF) if ``value < 0`` (MSB=1) — BTOR2 ``sra``
    with shift >= bit-width replicates the sign bit.
    Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < SAR_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", SAR_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    shift_nid = b.read("bv256", stack, sp_m1)   # TOS = shift amount
    value_nid = b.read("bv256", stack, sp_m2)   # NOS = signed value

    sar_nid = b.sra("bv256", value_nid, shift_nid)

    stack_written = b.write("stack_t", stack, sp_m2, sar_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", SAR_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# SIGNEXTEND lowering (SCHEMA.md §12, opcode 0x0b)
# ---------------------------------------------------------------------------

#: Gas cost for SIGNEXTEND (SCHEMA.md §10.1, London — VERYLOW tier).
SIGNEXTEND_GAS: int = 5

#: Number of bytes consumed by SIGNEXTEND (single-byte opcode).
SIGNEXTEND_SIZE: int = 1


def lower_signextend(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one SIGNEXTEND instruction to BTOR2 next-state expressions.

    Pops TOS (``bytenum = stack[sp-1]``, bv256) and NOS
    (``x = stack[sp-2]``, bv256); sign-extends ``x`` treating bit
    ``bytenum * 8 + 7`` as the sign bit and pushes the result to
    ``stack[sp-2]``.  If ``bytenum >= 31``, returns ``x`` unchanged.
    Net sp change is -1 (pop 2, push 1).

    Implementation: sra(sll(x, 248 - bytenum*8), 248 - bytenum*8)
    with a guard for bytenum >= 31 that returns x directly.

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < SIGNEXTEND_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", SIGNEXTEND_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    bytenum_nid = b.read("bv256", stack, sp_m1)  # TOS = byte index
    x_nid = b.read("bv256", stack, sp_m2)         # NOS = value to extend

    c_248 = b.const("bv256", 248)
    c_8 = b.const("bv256", 8)
    c_31 = b.const("bv256", 31)
    bytenum_times_8 = b.mul("bv256", bytenum_nid, c_8)
    shift_amt = b.sub("bv256", c_248, bytenum_times_8)
    shifted_left = b.sll("bv256", x_nid, shift_amt)
    raw_result = b.sra("bv256", shifted_left, shift_amt)
    bytenum_geq_31 = b.uge(bytenum_nid, c_31)
    result_nid = b.ite("bv256", bytenum_geq_31, x_nid, raw_result)

    stack_written = b.write("stack_t", stack, sp_m2, result_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", SIGNEXTEND_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# SLT lowering (SCHEMA.md §12, opcode 0x12)
# ---------------------------------------------------------------------------

#: Gas cost for SLT (SCHEMA.md §10.1, London — VERYLOW tier).
SLT_GAS: int = 3

#: Number of bytes consumed by SLT (single-byte opcode).
SLT_SIZE: int = 1


def lower_slt(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one SLT instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes 1 if ``a < b`` (signed two's-complement), else 0,
    to ``stack[sp-2]``.  Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < SLT_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", SLT_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)

    slt_cond = b.slt(a_nid, b_nid)
    result_nid = b.ite("bv256", slt_cond, b.const("bv256", 1), b.const("bv256", 0))

    stack_written = b.write("stack_t", stack, sp_m2, result_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", SLT_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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


# ---------------------------------------------------------------------------
# SGT lowering (SCHEMA.md §12, opcode 0x13)
# ---------------------------------------------------------------------------

#: Gas cost for SGT (SCHEMA.md §10.1, London — VERYLOW tier).
SGT_GAS: int = 3

#: Number of bytes consumed by SGT (single-byte opcode).
SGT_SIZE: int = 1


def lower_sgt(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Lower one SGT instruction to BTOR2 next-state expressions.

    Pops TOS (``a = stack[sp-1]``, bv256) and NOS (``b = stack[sp-2]``,
    bv256); pushes 1 if ``a > b`` (signed two's-complement), else 0,
    to ``stack[sp-2]``.  Net sp change is -1 (pop 2, push 1).

    Trap conditions (SCHEMA.md §11):
    - Stack underflow: sp < 2
    - Out-of-gas: gas < SGT_GAS
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

    no_exec = b.or_("bv1", halted, trap)

    underflow = b.ult(sp, b.const("bv10", 2))
    c_gas = b.const("bv64", SGT_GAS)
    oog = b.ult(gas, c_gas)

    exc = b.or_("bv1", underflow, oog)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), exc)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    sp_m1 = b.sub("bv10", sp, b.const("bv10", 1))
    sp_m2 = b.sub("bv10", sp, b.const("bv10", 2))
    a_nid = b.read("bv256", stack, sp_m1)
    b_nid = b.read("bv256", stack, sp_m2)

    sgt_cond = b.sgt(a_nid, b_nid)
    result_nid = b.ite("bv256", sgt_cond, b.const("bv256", 1), b.const("bv256", 0))

    stack_written = b.write("stack_t", stack, sp_m2, result_nid)
    sp_new = b.sub("bv10", sp, b.const("bv10", 1))
    pc_new = b.add("bv16", pc, b.const("bv16", SGT_SIZE))
    gas_new = b.sub("bv64", gas, c_gas)

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
    "lower_lt",
    "lower_gt",
    "lower_eq_op",
    "lower_sstore",
    "lower_calldataload",
    "lower_calldatacopy",
    "lower_jumpi",
    "lower_iszero",
    "lower_dup1",
    "lower_mstore8",
    "lower_push0",
    "lower_return",
    "lower_calldatasize",
    "lower_mload",
    "lower_mstore",
    "lower_sub",
    "lower_mul",
    "lower_and",
    "lower_or",
    "lower_xor",
    "lower_not",
    "lower_jump",
    "PUSH1_GAS",
    "PUSH1_SIZE",
    "STOP_GAS",
    "ADD_GAS",
    "ADD_SIZE",
    "LT_GAS",
    "LT_SIZE",
    "GT_GAS",
    "GT_SIZE",
    "EQ_GAS",
    "EQ_SIZE",
    "SSTORE_GAS_COLD",
    "SSTORE_GAS_WARM",
    "SSTORE_SIZE",
    "CALLDATALOAD_GAS",
    "CALLDATALOAD_SIZE",
    "CALLDATACOPY_GAS",
    "CALLDATACOPY_WORD_GAS",
    "CALLDATACOPY_SIZE",
    "CALLDATACOPY_MAX_LEN",
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
    "CALLDATASIZE_GAS",
    "CALLDATASIZE_SIZE",
    "MLOAD_GAS",
    "MLOAD_SIZE",
    "MSTORE_GAS",
    "MSTORE_SIZE",
    "SUB_GAS",
    "SUB_SIZE",
    "MUL_GAS",
    "MUL_SIZE",
    "AND_GAS",
    "AND_SIZE",
    "OR_GAS",
    "OR_SIZE",
    "XOR_GAS",
    "XOR_SIZE",
    "NOT_GAS",
    "NOT_SIZE",
    "JUMP_GAS",
    "JUMP_SIZE",
    "lower_div",
    "lower_mod",
    "lower_addmod",
    "lower_mulmod",
    "lower_exp",
    "lower_byte",
    "lower_shl",
    "lower_shr",
    "lower_sar",
    "DIV_GAS",
    "DIV_SIZE",
    "MOD_GAS",
    "MOD_SIZE",
    "ADDMOD_GAS",
    "ADDMOD_SIZE",
    "MULMOD_GAS",
    "MULMOD_SIZE",
    "EXP_GAS_BASE",
    "EXP_GAS_BYTE",
    "EXP_GAS_1BYTE",
    "EXP_EXPONENT_BITS",
    "EXP_SIZE",
    "BYTE_GAS",
    "BYTE_SIZE",
    "SHL_GAS",
    "SHL_SIZE",
    "SHR_GAS",
    "SHR_SIZE",
    "SAR_GAS",
    "SAR_SIZE",
    "lower_signextend",
    "lower_slt",
    "lower_sgt",
    "SIGNEXTEND_GAS",
    "SIGNEXTEND_SIZE",
    "SLT_GAS",
    "SLT_SIZE",
    "SGT_GAS",
    "SGT_SIZE",
]
