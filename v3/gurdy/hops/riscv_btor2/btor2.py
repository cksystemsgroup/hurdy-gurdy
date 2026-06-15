"""The agent's own BTOR2 emitter — independent of the verified machine model.

A **specializing** lowering: it statically decodes a concrete program (via
``decode.py``) and emits a program-specific BTOR2 transition system with a
per-PC dispatch, rather than a general fetch/decode machine. State is one
``bvXLEN`` per GPR (x0 hardwired 0), a ``pc`` and a ``halted`` flag; at each
step the instruction whose address equals ``pc`` fires. The instruction
SEMANTICS are emitted here directly from the RISC-V ISA (no crib of the
Sail-derived machine IR), keyed by the same ``MicroOp.mnem`` the concrete
interpreter uses, so the two lowerings of the agent's semantics stay in step.

The emitted model is validated end-to-end against Sail with pono
(``differential.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gurdy.hops.riscv_btor2.decode import MicroOp

XLEN = 64
M64 = (1 << 64) - 1


@dataclass
class _B:
    """A tiny, independent BTOR2 line builder."""

    lines: list = field(default_factory=list)
    _nid: int = 0
    _sorts: dict = field(default_factory=dict)
    _consts: dict = field(default_factory=dict)

    def n(self) -> int:
        self._nid += 1
        return self._nid

    def sort(self, w: int) -> int:
        if w not in self._sorts:
            i = self.n()
            self.lines.append(f"{i} sort bitvec {w}")
            self._sorts[w] = i
        return self._sorts[w]

    def emit(self, fmt: str, *a) -> int:
        i = self.n()
        self.lines.append(f"{i} " + fmt.format(*a))
        return i

    def const(self, w: int, v: int) -> int:
        key = (w, v & ((1 << w) - 1))
        if key not in self._consts:
            self._consts[key] = self.emit("constd {} {}", self.sort(w), key[1])
        return self._consts[key]

    # convenience wrappers (sorts inferred from the result width)
    def binop(self, op, w, x, y):
        return self.emit("{} {} {} {}", op, self.sort(w), x, y)

    def ite(self, w, c, x, y):
        return self.emit("ite {} {} {} {}", self.sort(w), c, x, y)

    def slice(self, w, x, hi, lo):
        return self.emit("slice {} {} {} {}", self.sort(w), x, hi, lo)

    def sext(self, to_w, x, by):
        return self.emit("sext {} {} {}", self.sort(to_w), x, by)

    def uext(self, to_w, x, by):
        return self.emit("uext {} {} {}", self.sort(to_w), x, by)


def _emit_value(b: _B, op: MicroOp, reg) -> int:
    """Emit the BTOR2 nodes computing this instruction's result (bv64)."""
    s1, s64 = b.sort(1), b.sort(64)
    a = reg(op.rs1)
    if op.kind == "rr":
        y = reg(op.rs2)
    elif op.kind in ("imm", "sh6", "sh5"):
        y = b.const(64, op.imm)
    else:
        y = b.const(64, 0)
    m = op.mnem
    one64, zero64 = b.const(64, 1), b.const(64, 0)

    if m == "add":  return b.binop("add", 64, a, y)
    if m == "sub":  return b.binop("sub", 64, a, y)
    if m == "and":  return b.binop("and", 64, a, y)
    if m == "or":   return b.binop("or", 64, a, y)
    if m == "xor":  return b.binop("xor", 64, a, y)
    if m == "mul":  return b.binop("mul", 64, a, y)
    if m == "sll":  return b.binop("sll", 64, a, b.binop("and", 64, y, b.const(64, 63)))
    if m == "srl":  return b.binop("srl", 64, a, b.binop("and", 64, y, b.const(64, 63)))
    if m == "sra":  return b.binop("sra", 64, a, b.binop("and", 64, y, b.const(64, 63)))
    if m == "slt":  return b.ite(64, b.binop("slt", 1, a, y), one64, zero64)
    if m == "sltu": return b.ite(64, b.binop("ult", 1, a, y), one64, zero64)

    if m in ("addw", "subw", "sllw", "srlw", "sraw", "mulw"):
        return _emit_word_alu(b, m, a, y)
    if m in ("mulh", "mulhu", "mulhsu"):
        return _emit_mulh(b, m, a, y)
    if m in ("div", "divu", "rem", "remu"):
        return _emit_divrem(b, m, a, y)
    if m in ("divw", "divuw", "remw", "remuw"):
        return _emit_word_divrem(b, m, a, y)
    if m == "lui":   return b.const(64, op.imm)
    if m == "auipc": return b.binop("add", 64, b.const(64, op.pc), b.const(64, op.imm))
    raise KeyError(m)


def _lo32(b, x):
    return b.slice(32, x, 31, 0)


def _emit_word_alu(b: _B, m, a, y) -> int:
    x32, y32 = _lo32(b, a), _lo32(b, y)
    if m == "addw": r = b.binop("add", 32, x32, y32)
    elif m == "subw": r = b.binop("sub", 32, x32, y32)
    elif m == "mulw": r = b.binop("mul", 32, x32, y32)
    elif m == "sllw": r = b.binop("sll", 32, x32, b.binop("and", 32, y32, b.const(32, 31)))
    elif m == "srlw": r = b.binop("srl", 32, x32, b.binop("and", 32, y32, b.const(32, 31)))
    elif m == "sraw": r = b.binop("sra", 32, x32, b.binop("and", 32, y32, b.const(32, 31)))
    else: raise KeyError(m)
    return b.sext(64, r, 32)


def _emit_mulh(b: _B, m, a, y) -> int:
    if m == "mulh":
        aa, yy = b.sext(128, a, 64), b.sext(128, y, 64)
    elif m == "mulhu":
        aa, yy = b.uext(128, a, 64), b.uext(128, y, 64)
    else:  # mulhsu
        aa, yy = b.sext(128, a, 64), b.uext(128, y, 64)
    return b.slice(64, b.binop("mul", 128, aa, yy), 127, 64)


def _emit_divrem(b: _B, m, a, y) -> int:
    zero, allone = b.const(64, 0), b.const(64, M64)
    intmin, minus1 = b.const(64, 1 << 63), b.const(64, M64)
    beq0 = b.binop("eq", 1, y, zero)
    if m == "div":
        ovf = b.binop("and", 1, b.binop("eq", 1, a, intmin), b.binop("eq", 1, y, minus1))
        return b.ite(64, beq0, allone, b.ite(64, ovf, intmin, b.binop("sdiv", 64, a, y)))
    if m == "divu":
        return b.ite(64, beq0, allone, b.binop("udiv", 64, a, y))
    if m == "rem":
        ovf = b.binop("and", 1, b.binop("eq", 1, a, intmin), b.binop("eq", 1, y, minus1))
        return b.ite(64, beq0, a, b.ite(64, ovf, zero, b.binop("srem", 64, a, y)))
    if m == "remu":
        return b.ite(64, beq0, a, b.binop("urem", 64, a, y))
    raise KeyError(m)


def _emit_word_divrem(b: _B, m, a, y) -> int:
    x, yy = _lo32(b, a), _lo32(b, y)
    zero, allone = b.const(32, 0), b.const(32, (1 << 32) - 1)
    intmin, minus1 = b.const(32, 1 << 31), b.const(32, (1 << 32) - 1)
    beq0 = b.binop("eq", 1, yy, zero)
    if m == "divw":
        ovf = b.binop("and", 1, b.binop("eq", 1, x, intmin), b.binop("eq", 1, yy, minus1))
        r = b.ite(32, beq0, allone, b.ite(32, ovf, intmin, b.binop("sdiv", 32, x, yy)))
    elif m == "divuw":
        r = b.ite(32, beq0, allone, b.binop("udiv", 32, x, yy))
    elif m == "remw":
        ovf = b.binop("and", 1, b.binop("eq", 1, x, intmin), b.binop("eq", 1, yy, minus1))
        r = b.ite(32, beq0, x, b.ite(32, ovf, zero, b.binop("srem", 32, x, yy)))
    elif m == "remuw":
        r = b.ite(32, beq0, x, b.binop("urem", 32, x, yy))
    else:
        raise KeyError(m)
    return b.sext(64, r, 32)


@dataclass
class LoweredModel:
    text: str
    reg_state: dict[int, int]     # GPR index -> BTOR2 state nid (1..31)
    pc_state: int
    halted_state: int
    end_pc: int
    entry: int
    sorts: dict                   # width -> sort nid (for harness extensions)


def lower(ops: list[MicroOp], entry: int, *, init_regs: dict[int, int] | None = None,
          with_init: bool = True, checks: list[tuple[int, int]] | None = None) -> LoweredModel:
    """Emit a specialized BTOR2 transition system for the decoded program.

    With ``with_init`` the GPRs/pc/halted are initialized (GPRs to ``init_regs``
    or 0, pc to ``entry``, halted to 0) — needed for a concrete model check.
    pono requires an init value's nid < its state's nid, so init constants are
    emitted before the state lines."""
    b = _B()
    s1, s64 = b.sort(1), b.sort(64)
    end = entry + 4 * len(ops)
    init_regs = init_regs or {}

    # init constants (must precede the states for pono)
    if with_init:
        c_entry = b.const(64, entry)
        c_zero1 = b.const(1, 0)
        reg_init = {k: b.const(64, init_regs.get(k, 0)) for k in range(1, 32)}

    # states
    reg_state = {k: b.emit("state {} x{}", s64, k) for k in range(1, 32)}
    pc = b.emit("state {} pc", s64)
    halted = b.emit("state {} halted", s1)

    if with_init:
        for k in range(1, 32):
            b.emit("init {} {} {}", s64, reg_state[k], reg_init[k])
        b.emit("init {} {} {}", s64, pc, c_entry)
        b.emit("init {} {} {}", s1, halted, c_zero1)

    def reg(k):
        return b.const(64, 0) if k == 0 else reg_state[k]

    # per-instruction result + active predicate (pc == PC_i)
    c_end = b.const(64, end)
    at_end = b.emit("ugte {} {} {}", s1, pc, c_end)

    # next(reg_k): fold over instructions writing k, in program order
    writes: dict[int, list[tuple[int, int]]] = {}     # k -> [(active_pred, value_nid)]
    for op in ops:
        val = _emit_value(b, op, reg)
        active = b.emit("eq {} {} {}", s1, pc, b.const(64, op.pc))
        if op.rd != 0:
            writes.setdefault(op.rd, []).append((active, val))
    for k in range(1, 32):
        nv = reg_state[k]
        for active, val in reversed(writes.get(k, [])):
            nv = b.ite(64, active, val, nv)
        b.emit("next {} {} {}", s64, reg_state[k], nv)

    # next(pc): advance by 4 until end, then freeze; halted latches at end
    pc4 = b.binop("add", 64, pc, b.const(64, 4))
    b.emit("next {} {} {}", s64, pc, b.ite(64, at_end, pc, pc4))
    b.emit("next {} {} {}", s1, halted, b.emit("or {} {} {}", s1, halted, at_end))

    # optional safety property for differential model checking: once halted, a
    # checked register must equal its expected value, else `bad` is reachable.
    if checks:
        diff = None
        for k, expected in checks:
            ne = b.emit("neq {} {} {}", s1, reg(k), b.const(64, expected))
            diff = ne if diff is None else b.emit("or {} {} {}", s1, diff, ne)
        b.emit("bad {}", b.emit("and {} {} {}", s1, halted, diff))

    text = ("; specialized BTOR2 (own lowering) for a straight-line RV64 ALU program\n"
            + "\n".join(b.lines) + "\n")
    return LoweredModel(text=text, reg_state=reg_state, pc_state=pc, halted_state=halted,
                        end_pc=end, entry=entry, sorts=dict(b._sorts))
