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


__all__ = [
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
    "lower_calldatasize",
    "lower_mload",
    "lower_mstore",
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
    "CALLDATASIZE_GAS",
    "CALLDATASIZE_SIZE",
    "MLOAD_GAS",
    "MLOAD_SIZE",
    "MSTORE_GAS",
    "MSTORE_SIZE",
]
