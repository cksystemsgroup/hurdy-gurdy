"""Independent RV64I/M ALU decoder + concrete semantics — the agent's own
front end. Written directly from the RISC-V Unprivileged ISA, NOT cribbed from
Sail or the verified machine model (differential-only independence). The same
decoded ``MicroOp`` list drives both the concrete interpreter (``run``, used to
differential-test against Sail) and the BTOR2 emission (``btor2.py``), so the
two lowerings of the agent's semantics cannot drift from each other.

Slice: RV64I/M ALU (reg-reg, reg-imm, word ops, LUI/AUIPC, M mul/div). Control
flow, loads/stores, CSRs, FP are out of scope (the agent's lowering stops at the
first instruction it does not recognise — the program's straight-line ALU
prefix).
"""

from __future__ import annotations

from dataclasses import dataclass

from gurdy.hops.riscv_btor2.elf import Loaded

M64 = (1 << 64) - 1
M32 = (1 << 32) - 1


# ---------------------------------------------------------------------------
# small arithmetic helpers (plain Python ints, masked to 64 bits)
# ---------------------------------------------------------------------------

def _s(v: int, bits: int) -> int:
    """interpret the low `bits` of v as signed two's complement."""
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def _sext(v: int, bits: int) -> int:
    """sign-extend the low `bits` of v to a 64-bit unsigned bit pattern."""
    return _s(v, bits) & M64


# ---------------------------------------------------------------------------
# the micro-op (one decoded instruction)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MicroOp:
    pc: int
    mnem: str
    rd: int
    rs1: int
    rs2: int
    imm: int                  # extended immediate / shamt, kind-dependent
    kind: str                 # rr | imm | sh6 | sh5 | lui | auipc


# ---------------------------------------------------------------------------
# decode: 32-bit word -> MicroOp (or None if not an ALU-slice instruction)
# ---------------------------------------------------------------------------

# (opcode, funct3, funct7-or-None, funct7hi-or-None) -> (mnem, kind)
_OP, _OPIMM, _OP32, _OPIMM32, _LUI, _AUIPC = 0x33, 0x13, 0x3B, 0x1B, 0x37, 0x17

_REGREG = {
    (0x0, 0x00): "add", (0x0, 0x20): "sub", (0x1, 0x00): "sll",
    (0x2, 0x00): "slt", (0x3, 0x00): "sltu", (0x4, 0x00): "xor",
    (0x5, 0x00): "srl", (0x5, 0x20): "sra", (0x6, 0x00): "or",
    (0x7, 0x00): "and",
    (0x0, 0x01): "mul", (0x1, 0x01): "mulh", (0x2, 0x01): "mulhsu",
    (0x3, 0x01): "mulhu", (0x4, 0x01): "div", (0x5, 0x01): "divu",
    (0x6, 0x01): "rem", (0x7, 0x01): "remu",
}
_REGREG_W = {
    (0x0, 0x00): "addw", (0x0, 0x20): "subw", (0x1, 0x00): "sllw",
    (0x5, 0x00): "srlw", (0x5, 0x20): "sraw",
    (0x0, 0x01): "mulw", (0x4, 0x01): "divw", (0x5, 0x01): "divuw",
    (0x6, 0x01): "remw", (0x7, 0x01): "remuw",
}
# reg-imm arith reuses the base operation's semantics with b = immediate; the
# MicroOp.mnem is the semantic op, MicroOp.kind ("imm") supplies the operand.
_OPIMM_ARITH = {0x0: "add", 0x2: "slt", 0x3: "sltu", 0x4: "xor",
                0x6: "or", 0x7: "and"}


def decode_word(pc: int, w: int) -> MicroOp | None:
    opcode = w & 0x7F
    rd = (w >> 7) & 0x1F
    funct3 = (w >> 12) & 0x7
    rs1 = (w >> 15) & 0x1F
    rs2 = (w >> 20) & 0x1F
    funct7 = (w >> 25) & 0x7F
    funct7hi = (w >> 26) & 0x3F

    def mk(mnem, kind, imm=0):
        return MicroOp(pc, mnem, rd, rs1, rs2, imm, kind)

    if opcode == _OP:
        m = _REGREG.get((funct3, funct7))
        return mk(m, "rr") if m else None
    if opcode == _OP32:
        m = _REGREG_W.get((funct3, funct7))
        return mk(m, "rr") if m else None
    if opcode == _OPIMM:
        if funct3 in _OPIMM_ARITH:
            return mk(_OPIMM_ARITH[funct3], "imm", _sext(w >> 20, 12))
        if funct3 == 0x1 and funct7hi == 0x00:                 # slli (RV64)
            return mk("sll", "sh6", (w >> 20) & 0x3F)
        if funct3 == 0x5 and funct7hi == 0x00:                 # srli
            return mk("srl", "sh6", (w >> 20) & 0x3F)
        if funct3 == 0x5 and funct7hi == 0x10:                 # srai
            return mk("sra", "sh6", (w >> 20) & 0x3F)
        return None
    if opcode == _OPIMM32:
        if funct3 == 0x0:                                      # addiw
            return mk("addw", "imm", _sext(w >> 20, 12))
        if funct3 == 0x1 and funct7 == 0x00:                   # slliw
            return mk("sllw", "sh5", (w >> 20) & 0x1F)
        if funct3 == 0x5 and funct7 == 0x00:                   # srliw
            return mk("srlw", "sh5", (w >> 20) & 0x1F)
        if funct3 == 0x5 and funct7 == 0x20:                   # sraiw
            return mk("sraw", "sh5", (w >> 20) & 0x1F)
        return None
    if opcode == _LUI:
        return mk("lui", "lui", _sext((w & 0xFFFFF000), 32))
    if opcode == _AUIPC:
        return mk("auipc", "auipc", _sext((w & 0xFFFFF000), 32))
    return None


def decode_program(prog: Loaded, *, max_insns: int = 4096) -> list[MicroOp]:
    """Statically decode the straight-line ALU prefix from the entry point. The
    agent stops at the first word it does not recognise (the program's control /
    halt tail), which bounds the specialized lowering to its slice."""
    ops: list[MicroOp] = []
    pc = prog.entry
    for _ in range(max_insns):
        w = prog.word(pc)
        if w is None:
            break
        op = decode_word(pc, w)
        if op is None:
            break
        ops.append(op)
        pc += 4
    return ops


# ---------------------------------------------------------------------------
# concrete semantics (independent transcription of the RV64 ISA)
# ---------------------------------------------------------------------------

def _alu(mnem: str, a: int, b: int, pc: int, imm: int) -> int:
    a &= M64
    b &= M64
    if mnem == "add":   return (a + b) & M64
    if mnem == "sub":   return (a - b) & M64
    if mnem == "and":   return a & b
    if mnem == "or":    return a | b
    if mnem == "xor":   return a ^ b
    if mnem == "sll":   return (a << (b & 63)) & M64
    if mnem == "srl":   return a >> (b & 63)
    if mnem == "sra":   return (_s(a, 64) >> (b & 63)) & M64
    if mnem == "slt":   return 1 if _s(a, 64) < _s(b, 64) else 0
    if mnem == "sltu":  return 1 if a < b else 0
    # word ops: compute in 32 bits, sign-extend to 64
    if mnem == "addw":  return _sext((a + b) & M32, 32)
    if mnem == "subw":  return _sext((a - b) & M32, 32)
    if mnem == "sllw":  return _sext(((a & M32) << (b & 31)) & M32, 32)
    if mnem == "srlw":  return _sext((a & M32) >> (b & 31), 32)
    if mnem == "sraw":  return _sext((_s(a, 32) >> (b & 31)) & M32, 32)
    # M extension
    if mnem == "mul":   return (a * b) & M64
    if mnem == "mulh":  return ((_s(a, 64) * _s(b, 64)) >> 64) & M64
    if mnem == "mulhu": return ((a * b) >> 64) & M64
    if mnem == "mulhsu":return ((_s(a, 64) * b) >> 64) & M64
    if mnem == "mulw":  return _sext((a * b) & M32, 32)
    if mnem in ("div", "divu", "rem", "remu"):
        return _divrem(mnem, a, b)
    if mnem in ("divw", "divuw", "remw", "remuw"):
        return _divrem_w(mnem, a, b)
    if mnem == "lui":   return imm & M64
    if mnem == "auipc": return (pc + imm) & M64
    raise KeyError(mnem)


def _divrem(mnem: str, a: int, b: int) -> int:
    if mnem == "div":
        if b == 0: return M64
        if a == (1 << 63) and _s(b, 64) == -1: return 1 << 63
        q = abs(_s(a, 64)) // abs(_s(b, 64))
        return (-q if (_s(a, 64) < 0) ^ (_s(b, 64) < 0) else q) & M64
    if mnem == "divu":
        return M64 if b == 0 else (a // b) & M64
    if mnem == "rem":
        if b == 0: return a
        if a == (1 << 63) and _s(b, 64) == -1: return 0
        r = abs(_s(a, 64)) % abs(_s(b, 64))
        return (-r if _s(a, 64) < 0 else r) & M64
    if mnem == "remu":
        return a if b == 0 else (a % b) & M64
    raise KeyError(mnem)


def _divrem_w(mnem: str, a: int, b: int) -> int:
    x, y = a & M32, b & M32
    base = mnem[:-1]                     # divw->div, etc.
    if base == "div":
        if y == 0: r32 = M32
        elif x == (1 << 31) and _s(y, 32) == -1: r32 = 1 << 31
        else:
            q = abs(_s(x, 32)) // abs(_s(y, 32))
            r32 = (-q if (_s(x, 32) < 0) ^ (_s(y, 32) < 0) else q) & M32
    elif base == "divu":
        r32 = M32 if y == 0 else (x // y) & M32
    elif base == "rem":
        if y == 0: r32 = x
        elif x == (1 << 31) and _s(y, 32) == -1: r32 = 0
        else:
            r = abs(_s(x, 32)) % abs(_s(y, 32))
            r32 = (-r if _s(x, 32) < 0 else r) & M32
    elif base == "remu":
        r32 = x if y == 0 else (x % y) & M32
    else:
        raise KeyError(mnem)
    return _sext(r32, 32)


def operands(op: MicroOp, regs: dict[int, int]) -> tuple[int, int]:
    """(a, b) operand values for a micro-op given the register file (x0 = 0)."""
    a = 0 if op.rs1 == 0 else regs.get(op.rs1, 0) & M64
    if op.kind == "rr":
        b = 0 if op.rs2 == 0 else regs.get(op.rs2, 0) & M64
    elif op.kind in ("imm", "sh6", "sh5"):
        b = op.imm & M64
    else:                                # lui / auipc: no register b
        b = 0
    return a, b


def eval_op(op: MicroOp, regs: dict[int, int]) -> int:
    a, b = operands(op, regs)
    return _alu(op.mnem, a, b, op.pc, op.imm)


def run(ops: list[MicroOp], init_regs: dict[int, int] | None = None) -> dict[int, int]:
    """Execute the decoded straight-line program; return the final register
    file x0..x31 (x0 pinned 0). This is the agent's own concrete interpreter,
    differential-tested against Sail."""
    regs = {i: 0 for i in range(32)}
    for i, v in (init_regs or {}).items():
        regs[i] = v & M64
    for op in ops:
        val = eval_op(op, regs)
        if op.rd != 0:
            regs[op.rd] = val & M64
        regs[0] = 0
    return regs
