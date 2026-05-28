"""Full EVM bytecode → BTOR2 translator (SCHEMA.md §13).

``translate_bytecode`` orchestrates all translation layers:
  0. header  (sorts + machine states)
  1. machine (state declarations + init clauses)
  2. context (symbolic context inputs + spec assumptions)
  3. dispatch (PC-keyed ITE tree over per-opcode lowerings)
  4. binding  (``next`` clauses from dispatch outputs)
  5. bad      (negated reach property, SCHEMA.md §14)

P9 supported opcode set: STOP (0x00), ADD (0x01), ISZERO (0x15),
CALLDATALOAD (0x35), CALLDATASIZE (0x36), MLOAD (0x51), MSTORE (0x52),
MSTORE8 (0x53), SSTORE (0x55), JUMPI (0x57), JUMPDEST (0x5b), PUSH0 (0x5f),
PUSH1 (0x60), DUP1 (0x80), RETURN (0xf3).
All other opcodes use the out-of-scope lowering (trap=1, halted=1).
"""

from __future__ import annotations

from gurdy.pairs.evm_btor2.btor2.printer import to_text
from gurdy.pairs.evm_btor2.source_interp.disasm import Instruction, disassemble
from gurdy.pairs.evm_btor2.spec import ReachKind, ReachProperty
from gurdy.pairs.evm_btor2.translation.builder import Btor2Builder, MACHINE_STATE_VARS
from gurdy.pairs.evm_btor2.translation.layers import emit_context_inputs, emit_init_clauses
from gurdy.pairs.evm_btor2.translation.library import (
    EvmLoweringResult,
    lower_add,
    lower_calldataload,
    lower_calldatasize,
    lower_dup1,
    lower_iszero,
    lower_jumpi,
    lower_mload,
    lower_mstore,
    lower_mstore8,
    lower_push0,
    lower_push1,
    lower_return,
    lower_stop,
    lower_sstore,
)

_JUMPDEST_GAS = 1
_JUMPDEST_SIZE = 1


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def translate_bytecode(bytecode: bytes, spec) -> str:
    """Translate ``bytecode`` + ``spec`` into a BTOR2 model string.

    Returns the BTOR2 text suitable for writing to a file or parsing
    by the reasoning interpreter.
    """
    b = Btor2Builder()
    b.emit_header()
    b.emit_machine_states()
    ctx_nids = emit_context_inputs(b, spec)
    emit_init_clauses(b, spec, b.state_nids)

    instructions = disassemble(bytecode)

    # Compute per-PC lowering results (all combinational — no new states).
    pc_lowerings: list[tuple[int, EvmLoweringResult]] = []
    for insn in instructions:
        result = _lower_insn(b, b.state_nids, ctx_nids, insn)
        pc_lowerings.append((insn.pc, result))

    # Out-of-scope / default lowering: trap=1, halted=1.
    oos = _lower_oos(b, b.state_nids)

    # Build PC-keyed ITE dispatch tree for every machine state.
    dispatch = _build_dispatch(b, b.state_nids, pc_lowerings, oos)

    # Wire next clauses from dispatch outputs.
    b.comment("binding — next clauses (SCHEMA.md §13)")
    for sym, sort_name in MACHINE_STATE_VARS:
        b.next(sort_name, b.state_nids[sym], dispatch[sym])

    # Emit bad property.
    b.comment("bad property (SCHEMA.md §14)")
    bad_expr = _emit_bad_expr(b, b.state_nids, spec.property)
    b.bad(bad_expr)

    return to_text(b.model)


# ---------------------------------------------------------------------------
# Per-instruction lowering router
# ---------------------------------------------------------------------------


def _lower_insn(
    b: Btor2Builder,
    machine_nids: dict[str, int],
    ctx_nids: dict[str, int],
    insn: Instruction,
) -> EvmLoweringResult:
    op = insn.opcode
    if op == 0x00:
        return lower_stop(b, machine_nids)
    if op == 0x01:
        return lower_add(b, machine_nids)
    if op == 0x15:
        return lower_iszero(b, machine_nids)
    if op == 0x35:
        return lower_calldataload(b, machine_nids, ctx_nids)
    if op == 0x36:
        return lower_calldatasize(b, machine_nids, ctx_nids)
    if op == 0x51:
        return lower_mload(b, machine_nids)
    if op == 0x52:
        return lower_mstore(b, machine_nids)
    if op == 0x53:
        return lower_mstore8(b, machine_nids)
    if op == 0x55:
        return lower_sstore(b, machine_nids)
    if op == 0x57:
        return lower_jumpi(b, machine_nids)
    if op == 0x5B:
        return _lower_jumpdest(b, machine_nids)
    if op == 0x5F:
        return lower_push0(b, machine_nids)
    if op == 0x60:  # PUSH1 only; PUSH2-PUSH32 fall through to oos
        imm = int.from_bytes(insn.immediate, "big") if insn.immediate else 0
        return lower_push1(b, machine_nids, imm)
    if op == 0x80:
        return lower_dup1(b, machine_nids)
    if op == 0xF3:
        return lower_return(b, machine_nids)
    return _lower_oos(b, machine_nids)


def _lower_jumpdest(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """JUMPDEST is a no-op (pc+=1, gas-=1)."""
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
    c_gas = b.const("bv64", _JUMPDEST_GAS)
    oog = b.ult(gas, c_gas)
    trap_from_op = b.and_("bv1", b.not_("bv1", no_exec), oog)
    exec_ = b.not_("bv1", b.or_("bv1", no_exec, trap_from_op))

    pc_next = b.ite("bv16", exec_, b.add("bv16", pc, b.const("bv16", _JUMPDEST_SIZE)), pc)
    gas_next = b.ite("bv64", exec_, b.sub("bv64", gas, c_gas), gas)
    trap_next = b.or_("bv1", trap, trap_from_op)
    halted_next = b.or_("bv1", halted, trap_from_op)

    return EvmLoweringResult(
        sp=sp, stack=stack, mem=mem, mem_words=mem_words,
        sto=sto, sto_warm=sto_warm,
        pc=pc_next, gas=gas_next,
        trap=trap_next, halted=halted_next,
        returndata=returndata, returndatasize=returndatasize,
    )


def _lower_oos(
    b: Btor2Builder,
    machine_nids: dict[str, int],
) -> EvmLoweringResult:
    """Out-of-scope lowering: set trap=1, halted=1 (SCHEMA.md §16)."""
    trap = machine_nids["trap"]
    halted = machine_nids["halted"]
    no_exec = b.or_("bv1", halted, trap)
    exec_ = b.not_("bv1", no_exec)
    return EvmLoweringResult(
        sp=machine_nids["sp"],
        stack=machine_nids["stack"],
        mem=machine_nids["mem"],
        mem_words=machine_nids["mem_words"],
        sto=machine_nids["sto"],
        sto_warm=machine_nids["sto_warm"],
        pc=machine_nids["pc"],
        gas=machine_nids["gas"],
        trap=b.or_("bv1", trap, exec_),
        halted=b.or_("bv1", halted, exec_),
        returndata=machine_nids["returndata"],
        returndatasize=machine_nids["returndatasize"],
    )


# ---------------------------------------------------------------------------
# PC-keyed ITE dispatch
# ---------------------------------------------------------------------------


def _build_dispatch(
    b: Btor2Builder,
    machine_nids: dict[str, int],
    pc_lowerings: list[tuple[int, EvmLoweringResult]],
    oos: EvmLoweringResult,
) -> dict[str, int]:
    """Build the PC-keyed ITE tree (SCHEMA.md §13.1).

    Starting from the out-of-scope lowering as the default, wraps each
    (pc_offset, lowering) pair from the outermost to innermost so that
    the first PC check is the outermost ITE.
    """
    b.comment("dispatch — PC-keyed ITE (SCHEMA.md §13.1)")
    current: dict[str, int] = {sym: getattr(oos, sym) for sym, _ in MACHINE_STATE_VARS}
    pc_nid = machine_nids["pc"]

    for offset, result in reversed(pc_lowerings):
        cond = b.eq(pc_nid, b.const("bv16", offset))
        for sym, sort_name in MACHINE_STATE_VARS:
            current[sym] = b.ite(sort_name, cond, getattr(result, sym), current[sym])

    return current


# ---------------------------------------------------------------------------
# Bad-property encoder
# ---------------------------------------------------------------------------


def _emit_bad_expr(
    b: Btor2Builder,
    machine_nids: dict[str, int],
    prop: ReachProperty,
) -> int:
    """Encode the negated reach property as a bv1 BTOR2 expression.

    Returns the nid of the final bv1 expression suitable for ``bad``.
    """
    halted = machine_nids["halted"]
    trap = machine_nids["trap"]
    no_trap = b.not_("bv1", trap)

    if prop.kind == ReachKind.STOP:
        return b.and_("bv1", halted, no_trap)

    if prop.kind == ReachKind.REVERT:
        return b.and_("bv1", halted, trap)

    if prop.kind == ReachKind.STORAGE_EQ:
        slot_nid = b.const("bv256", prop.slot)
        val_nid = b.const("bv256", prop.value)
        read_nid = b.read("bv256", machine_nids["sto"], slot_nid)
        val_eq = b.eq(read_nid, val_nid)
        return b.and_("bv1", halted, b.and_("bv1", no_trap, val_eq))

    if prop.kind == ReachKind.RETURNDATA_EQ:
        cond = b.and_("bv1", halted, no_trap)
        for i, byte_val in enumerate(prop.data):
            idx_nid = b.const("bv256", prop.offset + i)
            byte_nid = b.read("bv8", machine_nids["returndata"], idx_nid)
            cond = b.and_("bv1", cond, b.eq(byte_nid, b.const("bv8", byte_val)))
        return cond

    raise ValueError(f"unsupported reach kind: {prop.kind}")


__all__ = ["translate_bytecode"]
