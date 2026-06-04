"""Full EVM bytecode → BTOR2 translator (SCHEMA.md §13).

``translate_bytecode`` orchestrates all translation layers:
  0. header  (sorts + machine states)
  1. machine (state declarations + init clauses)
  2. context (symbolic context inputs + spec assumptions)
  3. dispatch (PC-keyed ITE tree over per-opcode lowerings)
  4. binding  (``next`` clauses from dispatch outputs)
  5. bad      (negated reach property, SCHEMA.md §14)

P30 supported opcode set: STOP (0x00), ADD (0x01), MUL (0x02), SUB (0x03),
DIV (0x04), SDIV (0x05), MOD (0x06), SMOD (0x07), ADDMOD (0x08),
MULMOD (0x09), EXP (0x0a), SIGNEXTEND (0x0b), LT (0x10), GT (0x11),
SLT (0x12), SGT (0x13),
EQ (0x14), ISZERO (0x15), AND (0x16), OR (0x17),
XOR (0x18), NOT (0x19), BYTE (0x1a), SHL (0x1b), SHR (0x1c), SAR (0x1d),
BALANCE (0x31), ORIGIN (0x32), CALLER (0x33), CALLVALUE (0x34),
CALLDATALOAD (0x35), CALLDATASIZE (0x36), CALLDATACOPY (0x37),
CODESIZE (0x38), CODECOPY (0x39), EXTCODESIZE (0x3b), EXTCODECOPY (0x3c),
RETURNDATASIZE (0x3d), RETURNDATACOPY (0x3e),
BLOCKHASH (0x40), COINBASE (0x41), TIMESTAMP (0x42), NUMBER (0x43),
PREVRANDAO (0x44), GASLIMIT (0x45), CHAINID (0x46), SELFBALANCE (0x47),
BASEFEE (0x48),
ADDRESS (0x30),
POP (0x50), MLOAD (0x51), MSTORE (0x52), MSTORE8 (0x53), SLOAD (0x54), PC (0x58), MSIZE (0x59),
TLOAD (0x5c), TSTORE (0x5d),
SSTORE (0x55), JUMP (0x56), JUMPI (0x57), JUMPDEST (0x5b), GAS (0x5a), PUSH0 (0x5f),
PUSH1..PUSH32 (0x60..0x7f), DUP1..DUP16 (0x80..0x8f),
SWAP1..SWAP16 (0x90..0x9f), LOG0..LOG4 (0xa0..0xa4),
RETURN (0xf3), REVERT (0xfd), INVALID (0xfe).
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
    lower_addmod,
    lower_and,
    lower_balance,
    lower_byte,
    lower_calldatacopy,
    lower_calldataload,
    lower_calldatasize,
    lower_caller,
    lower_callvalue,
    lower_chainid,
    lower_codecopy,
    lower_codesize,
    lower_div,
    lower_dup1,
    lower_dupn,
    lower_pop,
    lower_swapn,
    lower_eq_op,
    lower_exp,
    lower_extcodecopy,
    lower_extcodesize,
    lower_gt,
    lower_iszero,
    lower_jump,
    lower_jumpi,
    lower_lt,
    lower_mload,
    lower_mod,
    lower_mstore,
    lower_mstore8,
    lower_mul,
    lower_mulmod,
    lower_not,
    lower_or,
    lower_origin,
    lower_push0,
    lower_push1,
    lower_pushn,
    lower_return,
    lower_sar,
    lower_sdiv,
    lower_selfbalance,
    lower_sgt,
    lower_shl,
    lower_shr,
    lower_signextend,
    lower_slt,
    lower_smod,
    lower_gas,
    lower_gaslimit,
    lower_blockhash,
    lower_coinbase,
    lower_timestamp,
    lower_number,
    lower_prevrandao,
    lower_basefee,
    lower_invalid,
    lower_revert,
    lower_returndatasize,
    lower_returndatacopy,
    lower_stop,
    lower_msize,
    lower_address,
    lower_pc,
    lower_tload,
    lower_tstore,
    lower_sload,
    SLOAD_GAS_COLD,
    SLOAD_GAS_WARM,
    SLOAD_SIZE,
    lower_sstore,
    lower_logn,
    lower_sub,
    lower_xor,
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

    # Collect valid JUMPDEST PCs for destination validation in JUMP/JUMPI.
    jumpdests = frozenset(insn.pc for insn in instructions if insn.opcode == 0x5B)

    # Compute per-PC lowering results (all combinational — no new states).
    pc_lowerings: list[tuple[int, EvmLoweringResult]] = []
    for insn in instructions:
        result = _lower_insn(b, b.state_nids, ctx_nids, insn, jumpdests, bytecode)
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
    jumpdests: frozenset[int] = frozenset(),
    bytecode: bytes = b"",
) -> EvmLoweringResult:
    op = insn.opcode
    if op == 0x00:
        return lower_stop(b, machine_nids)
    if op == 0x01:
        return lower_add(b, machine_nids)
    if op == 0x02:
        return lower_mul(b, machine_nids)
    if op == 0x03:
        return lower_sub(b, machine_nids)
    if op == 0x04:
        return lower_div(b, machine_nids)
    if op == 0x05:
        return lower_sdiv(b, machine_nids)
    if op == 0x06:
        return lower_mod(b, machine_nids)
    if op == 0x07:
        return lower_smod(b, machine_nids)
    if op == 0x08:
        return lower_addmod(b, machine_nids)
    if op == 0x09:
        return lower_mulmod(b, machine_nids)
    if op == 0x0A:
        return lower_exp(b, machine_nids)
    if op == 0x0B:
        return lower_signextend(b, machine_nids)
    if op == 0x10:
        return lower_lt(b, machine_nids)
    if op == 0x11:
        return lower_gt(b, machine_nids)
    if op == 0x12:
        return lower_slt(b, machine_nids)
    if op == 0x13:
        return lower_sgt(b, machine_nids)
    if op == 0x14:
        return lower_eq_op(b, machine_nids)
    if op == 0x15:
        return lower_iszero(b, machine_nids)
    if op == 0x16:
        return lower_and(b, machine_nids)
    if op == 0x17:
        return lower_or(b, machine_nids)
    if op == 0x18:
        return lower_xor(b, machine_nids)
    if op == 0x19:
        return lower_not(b, machine_nids)
    if op == 0x1A:
        return lower_byte(b, machine_nids)
    if op == 0x1B:
        return lower_shl(b, machine_nids)
    if op == 0x1C:
        return lower_shr(b, machine_nids)
    if op == 0x1D:
        return lower_sar(b, machine_nids)
    if op == 0x30:
        return lower_address(b, machine_nids, ctx_nids)
    if op == 0x31:
        return lower_balance(b, machine_nids, ctx_nids)
    if op == 0x32:
        return lower_origin(b, machine_nids, ctx_nids)
    if op == 0x33:
        return lower_caller(b, machine_nids, ctx_nids)
    if op == 0x34:
        return lower_callvalue(b, machine_nids, ctx_nids)
    if op == 0x35:
        return lower_calldataload(b, machine_nids, ctx_nids)
    if op == 0x36:
        return lower_calldatasize(b, machine_nids, ctx_nids)
    if op == 0x37:
        return lower_calldatacopy(b, machine_nids, ctx_nids)
    if op == 0x38:
        return lower_codesize(b, machine_nids, len(bytecode))
    if op == 0x39:
        return lower_codecopy(b, machine_nids, bytecode)
    if op == 0x3B:
        return lower_extcodesize(b, machine_nids, ctx_nids)
    if op == 0x3C:
        return lower_extcodecopy(b, machine_nids, ctx_nids)
    if op == 0x3D:
        return lower_returndatasize(b, machine_nids)
    if op == 0x3E:
        return lower_returndatacopy(b, machine_nids)
    if op == 0x40:
        return lower_blockhash(b, machine_nids, ctx_nids)
    if op == 0x41:
        return lower_coinbase(b, machine_nids, ctx_nids)
    if op == 0x42:
        return lower_timestamp(b, machine_nids, ctx_nids)
    if op == 0x43:
        return lower_number(b, machine_nids, ctx_nids)
    if op == 0x44:
        return lower_prevrandao(b, machine_nids, ctx_nids)
    if op == 0x45:
        return lower_gaslimit(b, machine_nids, ctx_nids)
    if op == 0x46:
        return lower_chainid(b, machine_nids, ctx_nids)
    if op == 0x47:
        return lower_selfbalance(b, machine_nids, ctx_nids)
    if op == 0x48:
        return lower_basefee(b, machine_nids, ctx_nids)
    if op == 0x50:
        return lower_pop(b, machine_nids)
    if op == 0x51:
        return lower_mload(b, machine_nids)
    if op == 0x52:
        return lower_mstore(b, machine_nids)
    if op == 0x53:
        return lower_mstore8(b, machine_nids)
    if op == 0x54:
        return lower_sload(b, machine_nids)
    if op == 0x55:
        return lower_sstore(b, machine_nids)
    if op == 0x56:
        return lower_jump(b, machine_nids, jumpdests)
    if op == 0x57:
        return lower_jumpi(b, machine_nids, jumpdests)
    if op == 0x58:
        return lower_pc(b, machine_nids)
    if op == 0x59:
        return lower_msize(b, machine_nids)
    if op == 0x5A:
        return lower_gas(b, machine_nids)
    if op == 0x5B:
        return _lower_jumpdest(b, machine_nids)
    if op == 0x5C:
        return lower_tload(b, machine_nids)
    if op == 0x5D:
        return lower_tstore(b, machine_nids)
    if op == 0x5F:
        return lower_push0(b, machine_nids)
    if 0x60 <= op <= 0x7F:  # PUSH1..PUSH32
        n = op - 0x5F
        imm = int.from_bytes(insn.immediate, "big") if insn.immediate else 0
        return lower_pushn(b, machine_nids, imm, n)
    if 0x80 <= op <= 0x8F:  # DUP1..DUP16
        n = op - 0x7F
        return lower_dupn(b, machine_nids, n)
    if 0x90 <= op <= 0x9F:  # SWAP1..SWAP16
        n = op - 0x8F
        return lower_swapn(b, machine_nids, n)
    if 0xA0 <= op <= 0xA4:  # LOG0..LOG4
        n = op - 0xA0
        return lower_logn(b, machine_nids, n)
    if op == 0xF3:
        return lower_return(b, machine_nids)
    if op == 0xFD:
        return lower_revert(b, machine_nids)
    if op == 0xFE:
        return lower_invalid(b, machine_nids)
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
    transient_sto = machine_nids["transient_sto"]
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
        sto=sto, sto_warm=sto_warm, transient_sto=transient_sto,
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
        transient_sto=machine_nids["transient_sto"],
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
