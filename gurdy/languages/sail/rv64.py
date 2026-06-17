"""RV64I + RV64M ALU instruction specs — the Sail-derived semantics, one
``Expr`` execute tree per instruction (salvaged from v3, proven equivalent to
the reference). Plus a self-contained decoder, so this realization shares no
encoding/semantics code with the hand-written ``riscv`` interpreter or the
``riscv-btor2`` translator — that independence is the whole point of the Sail
branch.

Scope: the ALU core — OP / OP-IMM / OP-32 / OP-IMM-32, LUI, AUIPC (and the M
extension). Control flow (branches, jumps, loads/stores) is out of this slice
and decodes to ``None`` (the pair aborts with ``Unsupported``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .expr import (
    Expr, add, and1, and_, concat, const, eq, ite, mul, or_, sext, slice_,
    sll, slt, sra, srl, sub, udiv, sdiv, urem, srem, ult, var, xor_, zext,
)

MASK64 = (1 << 64) - 1
A, B, PC, UIMM = var("a", 64), var("b", 64), var("pc", 64), var("uimm", 64)


def _shamt6(b):  # RV64 shift count: low 6 bits
    return zext(slice_(b, 5, 0), 64)


def _shamt5(b):  # W-variant shift count: low 5 bits, in 32 bits
    return zext(slice_(b, 4, 0), 32)


def _lo32(x):
    return slice_(x, 31, 0)


def _bool_word(cond1):
    return ite(cond1, const(1, 64), const(0, 64))


def _div_signed(x, y, w):
    minus1, intmin = const((1 << w) - 1, w), const(1 << (w - 1), w)
    overflow = and1(eq(x, intmin), eq(y, minus1))
    return ite(eq(y, const(0, w)), minus1, ite(overflow, intmin, sdiv(x, y)))


def _div_unsigned(x, y, w):
    return ite(eq(y, const(0, w)), const((1 << w) - 1, w), udiv(x, y))


def _rem_signed(x, y, w):
    intmin = const(1 << (w - 1), w)
    overflow = and1(eq(x, intmin), eq(y, const((1 << w) - 1, w)))
    return ite(eq(y, const(0, w)), x, ite(overflow, const(0, w), srem(x, y)))


def _rem_unsigned(x, y, w):
    return ite(eq(y, const(0, w)), x, urem(x, y))


# The per-instruction execute trees (written once; proven == reference in v3).
EXEC = {
    "ADD": add(A, B), "SUB": sub(A, B), "SLL": sll(A, _shamt6(B)),
    "SLT": _bool_word(slt(A, B)), "SLTU": _bool_word(ult(A, B)),
    "XOR": xor_(A, B), "SRL": srl(A, _shamt6(B)), "SRA": sra(A, _shamt6(B)),
    "OR": or_(A, B), "AND": and_(A, B),
    "ADDW": sext(add(_lo32(A), _lo32(B)), 64), "SUBW": sext(sub(_lo32(A), _lo32(B)), 64),
    "SLLW": sext(sll(_lo32(A), _shamt5(B)), 64), "SRLW": sext(srl(_lo32(A), _shamt5(B)), 64),
    "SRAW": sext(sra(_lo32(A), _shamt5(B)), 64),
    "LUI": UIMM, "AUIPC": add(PC, UIMM),
    "MUL": mul(A, B),
    "MULH": slice_(mul(sext(A, 128), sext(B, 128)), 127, 64),
    "MULHU": slice_(mul(zext(A, 128), zext(B, 128)), 127, 64),
    "MULHSU": slice_(mul(sext(A, 128), zext(B, 128)), 127, 64),
    "DIV": _div_signed(A, B, 64), "DIVU": _div_unsigned(A, B, 64),
    "REM": _rem_signed(A, B, 64), "REMU": _rem_unsigned(A, B, 64),
    "MULW": sext(mul(_lo32(A), _lo32(B)), 64),
    "DIVW": sext(_div_signed(_lo32(A), _lo32(B), 32), 64),
    "DIVUW": sext(_div_unsigned(_lo32(A), _lo32(B), 32), 64),
    "REMW": sext(_rem_signed(_lo32(A), _lo32(B), 32), 64),
    "REMUW": sext(_rem_unsigned(_lo32(A), _lo32(B), 32), 64),
}

OP, OP_IMM, OP_32, OP_IMM32, LUI_OP, AUIPC_OP = \
    0x33, 0x13, 0x3B, 0x1B, 0x37, 0x17


@dataclass(frozen=True)
class InstrSpec:
    name: str
    kind: str            # "reg-reg" | "reg-imm" | "u-type"
    exec_name: str

    @property
    def execute(self) -> Expr:
        return EXEC[self.exec_name]


# (opcode, funct3, funct7) -> spec, for reg-reg OP / OP_32
_REGREG = {
    (OP, 0x0, 0x00): "ADD", (OP, 0x0, 0x20): "SUB", (OP, 0x1, 0x00): "SLL",
    (OP, 0x2, 0x00): "SLT", (OP, 0x3, 0x00): "SLTU", (OP, 0x4, 0x00): "XOR",
    (OP, 0x5, 0x00): "SRL", (OP, 0x5, 0x20): "SRA", (OP, 0x6, 0x00): "OR",
    (OP, 0x7, 0x00): "AND",
    (OP, 0x0, 0x01): "MUL", (OP, 0x1, 0x01): "MULH", (OP, 0x2, 0x01): "MULHSU",
    (OP, 0x3, 0x01): "MULHU", (OP, 0x4, 0x01): "DIV", (OP, 0x5, 0x01): "DIVU",
    (OP, 0x6, 0x01): "REM", (OP, 0x7, 0x01): "REMU",
    (OP_32, 0x0, 0x00): "ADDW", (OP_32, 0x0, 0x20): "SUBW", (OP_32, 0x1, 0x00): "SLLW",
    (OP_32, 0x5, 0x00): "SRLW", (OP_32, 0x5, 0x20): "SRAW",
    (OP_32, 0x0, 0x01): "MULW", (OP_32, 0x4, 0x01): "DIVW", (OP_32, 0x5, 0x01): "DIVUW",
    (OP_32, 0x6, 0x01): "REMW", (OP_32, 0x7, 0x01): "REMUW",
}
# (opcode, funct3) -> exec_name, for non-shift reg-imm
_REGIMM = {
    (OP_IMM, 0x0): "ADD", (OP_IMM, 0x2): "SLT", (OP_IMM, 0x3): "SLTU",
    (OP_IMM, 0x4): "XOR", (OP_IMM, 0x6): "OR", (OP_IMM, 0x7): "AND",
    (OP_IMM32, 0x0): "ADDW",
}
_REGIMM_NAME = {
    (OP_IMM, 0x0): "ADDI", (OP_IMM, 0x2): "SLTI", (OP_IMM, 0x3): "SLTIU",
    (OP_IMM, 0x4): "XORI", (OP_IMM, 0x6): "ORI", (OP_IMM, 0x7): "ANDI",
    (OP_IMM32, 0x0): "ADDIW",
}


def _sext(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def _iimm(instr): return _sext(instr >> 20, 12)
def _uimm(instr): return _sext(instr & 0xFFFFF000, 32)


@dataclass(frozen=True)
class Decoded:
    spec: InstrSpec
    rd: int
    a_reg: int | None = None
    b_reg: int | None = None
    b_imm: int | None = None
    uimm: int | None = None


def decode(instr: int) -> Decoded | None:
    """Decode a 32-bit word to a Sail-ALU :class:`Decoded`, or ``None`` if it is
    not in this slice (control flow, system, etc.)."""
    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x7
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F

    if opcode == LUI_OP:
        return Decoded(InstrSpec("LUI", "u-type", "LUI"), rd, uimm=_uimm(instr))
    if opcode == AUIPC_OP:
        return Decoded(InstrSpec("AUIPC", "u-type", "AUIPC"), rd, uimm=_uimm(instr))
    if opcode in (OP, OP_32):
        name = _REGREG.get((opcode, funct3, funct7))
        if name is None:
            return None
        return Decoded(InstrSpec(name, "reg-reg", name), rd, a_reg=rs1, b_reg=rs2)
    if opcode in (OP_IMM, OP_IMM32):
        if funct3 in (1, 5):                              # shift-immediate
            return _decode_shift(instr, opcode, funct3, rd, rs1)
        exec_name = _REGIMM.get((opcode, funct3))
        if exec_name is None:
            return None
        name = _REGIMM_NAME[(opcode, funct3)]
        return Decoded(InstrSpec(name, "reg-imm", exec_name), rd, a_reg=rs1,
                       b_imm=_iimm(instr) & MASK64)
    return None


def _decode_shift(instr, opcode, funct3, rd, rs1) -> Decoded | None:
    if opcode == OP_IMM:                                  # RV64 shift-imm (6-bit)
        shamt = (instr >> 20) & 0x3F
        if funct3 == 1:
            name, exec_name = "SLLI", "SLL"
        elif ((instr >> 26) & 0x3F) == 0x10:
            name, exec_name = "SRAI", "SRA"
        else:
            name, exec_name = "SRLI", "SRL"
    else:                                                 # OP_IMM32 shift-imm (5-bit)
        shamt = (instr >> 20) & 0x1F
        if funct3 == 1:
            name, exec_name = "SLLIW", "SLLW"
        elif ((instr >> 25) & 0x7F) == 0x20:
            name, exec_name = "SRAIW", "SRAW"
        else:
            name, exec_name = "SRLIW", "SRLW"
    return Decoded(InstrSpec(name, "reg-imm", exec_name), rd, a_reg=rs1, b_imm=shamt)
