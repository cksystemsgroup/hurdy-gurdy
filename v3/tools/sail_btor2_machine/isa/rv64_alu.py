"""RV64I + RV64M ALU instruction specs — the single source per instruction.

Each ``InstrSpec`` carries:
  * decode: opcode / funct3 / funct7 (or funct7 prefix for shift-immediates),
  * execute: an ``expr.Expr`` tree giving the result as a function of the
    operand bitvectors. This SAME tree is lowered to z3 (for the proof) and
    to BTOR2 (for the emitted model), so the two cannot drift.

Operand variables used by the execute trees:
  a   : 64-bit  source register rs1
  b   : 64-bit  source register rs2  (reg-reg)  OR  the already-extended
        64-bit immediate operand (reg-imm). For shift-immediates `b` carries
        the shamt in its low bits, matching reg-reg shift decode exactly.
  pc  : 64-bit  program counter (AUIPC only)
  uimm: 64-bit  sign-extended U-immediate (LUI/AUIPC)

Spec corners (RISC-V Unprivileged ISA, RV64) realized below:
  * RV64 SLL/SRL/SRA: shift count = low 6 bits of operand.
  * W-shifts SLLW/SRLW/SRAW (+ *IW): shift count = low 5 bits; compute in 32
    bits then SIGN-EXTEND the 32-bit result to 64.
  * ADDW/SUBW/MULW/DIV*W/REM*W: 32-bit op, sign-extend result to 64.
  * SLT*/SLTU*: signed/unsigned compare -> 64-bit 0/1.
  * DIV by 0 -> -1 ; REM by 0 -> dividend ; signed INT_MIN/-1 -> INT_MIN (DIV),
    0 (REM). W-variants apply the same in 32 bits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.sail_btor2_machine.isa import expr as E
from tools.sail_btor2_machine.isa.expr import (
    var, const, add, sub, mul, and_, or_, xor_, not_, sll, srl, sra,
    udiv, sdiv, urem, srem, ult, slt, eq, sext, zext, slice_, concat, ite,
)

XLEN = 64

# --- operand leaves --------------------------------------------------------
A = var("a", 64)
B = var("b", 64)
PC = var("pc", 64)
UIMM = var("uimm", 64)


# --- reusable building blocks ----------------------------------------------

def _shamt6(b):
    # low 6 bits of b, zero-extended back to 64 (RV64 shift count)
    return zext(slice_(b, 5, 0), 64)


def _shamt5(b):
    # low 5 bits of b, zero-extended to 32 (W-variant shift count)
    return zext(slice_(b, 4, 0), 32)


def _lo32(x):
    return slice_(x, 31, 0)


def _bool_word(cond1):
    # 1-bit condition -> 64-bit 0/1
    return ite(cond1, const(1, 64), const(0, 64))


# --- division corner helpers (parametric in width) -------------------------

def _div_signed(x, y, w):
    zero = const(0, w)
    minus1 = const((1 << w) - 1, w)
    intmin = const(1 << (w - 1), w)
    overflow = E.Expr("and", (eq(x, intmin), eq(y, minus1)), 1)
    return ite(eq(y, zero), minus1, ite(overflow, intmin, sdiv(x, y)))


def _div_unsigned(x, y, w):
    zero = const(0, w)
    allones = const((1 << w) - 1, w)
    return ite(eq(y, zero), allones, udiv(x, y))


def _rem_signed(x, y, w):
    zero = const(0, w)
    minus1 = const((1 << w) - 1, w)
    intmin = const(1 << (w - 1), w)
    overflow = E.Expr("and", (eq(x, intmin), eq(y, minus1)), 1)
    return ite(eq(y, zero), x, ite(overflow, zero, srem(x, y)))


def _rem_unsigned(x, y, w):
    zero = const(0, w)
    return ite(eq(y, zero), x, urem(x, y))


# ===========================================================================
# Execute trees (the per-instruction semantics, written once)
# ===========================================================================

EXEC = {
    # --- RV64I reg-reg ALU ---
    "ADD":  add(A, B),
    "SUB":  sub(A, B),
    "SLL":  sll(A, _shamt6(B)),
    "SLT":  _bool_word(slt(A, B)),
    "SLTU": _bool_word(ult(A, B)),
    "XOR":  xor_(A, B),
    "SRL":  srl(A, _shamt6(B)),
    "SRA":  sra(A, _shamt6(B)),
    "OR":   or_(A, B),
    "AND":  and_(A, B),

    # --- RV64I word ops (32-bit, sign-extend to 64) ---
    "ADDW": sext(add(_lo32(A), _lo32(B)), 64),
    "SUBW": sext(sub(_lo32(A), _lo32(B)), 64),
    "SLLW": sext(sll(_lo32(A), _shamt5(B)), 64),
    "SRLW": sext(srl(_lo32(A), _shamt5(B)), 64),
    "SRAW": sext(sra(_lo32(A), _shamt5(B)), 64),

    # --- LUI / AUIPC ---
    "LUI":   UIMM,
    "AUIPC": add(PC, UIMM),

    # --- RV64M multiply ---
    "MUL":    mul(A, B),
    "MULH":   slice_(mul(sext(A, 128), sext(B, 128)), 127, 64),
    "MULHU":  slice_(mul(zext(A, 128), zext(B, 128)), 127, 64),
    "MULHSU": slice_(mul(sext(A, 128), zext(B, 128)), 127, 64),

    # --- RV64M divide ---
    "DIV":  _div_signed(A, B, 64),
    "DIVU": _div_unsigned(A, B, 64),
    "REM":  _rem_signed(A, B, 64),
    "REMU": _rem_unsigned(A, B, 64),

    # --- RV64M W-variants ---
    "MULW":  sext(mul(_lo32(A), _lo32(B)), 64),
    "DIVW":  sext(_div_signed(_lo32(A), _lo32(B), 32), 64),
    "DIVUW": sext(_div_unsigned(_lo32(A), _lo32(B), 32), 64),
    "REMW":  sext(_rem_signed(_lo32(A), _lo32(B), 32), 64),
    "REMUW": sext(_rem_unsigned(_lo32(A), _lo32(B), 32), 64),
}


# ===========================================================================
# Decode tables (RISC-V Unprivileged ISA encodings)
# ===========================================================================
# opcode (7), funct3 (3), funct7 (7).  For shift-immediates SLLI/SRLI/SRAI the
# "funct7" field is really imm[11:5]; SRAI/SRA set bit30. SLLIW/SRLIW/SRAIW use
# the full 7-bit funct7 (shamt is 5 bits, so imm[11:5] is fixed).

OP      = 0b0110011    # reg-reg (RV64I + M)
OP_IMM  = 0b0010011    # reg-imm (RV64I)
OP_32   = 0b0111011    # reg-reg word (RV64I + M W-variants)
OP_IMM32= 0b0011011    # reg-imm word
LUI_OP  = 0b0110111
AUIPC_OP= 0b0010111


@dataclass(frozen=True)
class InstrSpec:
    name: str
    kind: str                         # "reg-reg" | "reg-imm" | "u-type"
    opcode: int
    funct3: int | None = None
    funct7: int | None = None         # full funct7 (reg-reg / word-imm)
    funct7_hi: int | None = None      # imm[11:6] prefix for RV64 SLLI/SRLI/SRAI
    exec_name: str = ""               # key into EXEC; defaults to name
    spec_ref: str = ""

    @property
    def execute(self):
        return EXEC[self.exec_name or self.name]


def _ref(section: str) -> str:
    return f"RISC-V Unprivileged ISA spec, {section}"


# reg-reg RV64I/M (opcode OP / OP_32)
REGREG_SPECS = [
    InstrSpec("ADD",  "reg-reg", OP, 0x0, 0x00, spec_ref=_ref("RV64I ADD")),
    InstrSpec("SUB",  "reg-reg", OP, 0x0, 0x20, spec_ref=_ref("RV64I SUB")),
    InstrSpec("SLL",  "reg-reg", OP, 0x1, 0x00, spec_ref=_ref("RV64I SLL")),
    InstrSpec("SLT",  "reg-reg", OP, 0x2, 0x00, spec_ref=_ref("RV64I SLT")),
    InstrSpec("SLTU", "reg-reg", OP, 0x3, 0x00, spec_ref=_ref("RV64I SLTU")),
    InstrSpec("XOR",  "reg-reg", OP, 0x4, 0x00, spec_ref=_ref("RV64I XOR")),
    InstrSpec("SRL",  "reg-reg", OP, 0x5, 0x00, spec_ref=_ref("RV64I SRL")),
    InstrSpec("SRA",  "reg-reg", OP, 0x5, 0x20, spec_ref=_ref("RV64I SRA")),
    InstrSpec("OR",   "reg-reg", OP, 0x6, 0x00, spec_ref=_ref("RV64I OR")),
    InstrSpec("AND",  "reg-reg", OP, 0x7, 0x00, spec_ref=_ref("RV64I AND")),
    InstrSpec("MUL",    "reg-reg", OP, 0x0, 0x01, spec_ref=_ref("M MUL")),
    InstrSpec("MULH",   "reg-reg", OP, 0x1, 0x01, spec_ref=_ref("M MULH")),
    InstrSpec("MULHSU", "reg-reg", OP, 0x2, 0x01, spec_ref=_ref("M MULHSU")),
    InstrSpec("MULHU",  "reg-reg", OP, 0x3, 0x01, spec_ref=_ref("M MULHU")),
    InstrSpec("DIV",    "reg-reg", OP, 0x4, 0x01, spec_ref=_ref("M DIV")),
    InstrSpec("DIVU",   "reg-reg", OP, 0x5, 0x01, spec_ref=_ref("M DIVU")),
    InstrSpec("REM",    "reg-reg", OP, 0x6, 0x01, spec_ref=_ref("M REM")),
    InstrSpec("REMU",   "reg-reg", OP, 0x7, 0x01, spec_ref=_ref("M REMU")),
    # word reg-reg (OP_32)
    InstrSpec("ADDW", "reg-reg", OP_32, 0x0, 0x00, spec_ref=_ref("RV64I ADDW")),
    InstrSpec("SUBW", "reg-reg", OP_32, 0x0, 0x20, spec_ref=_ref("RV64I SUBW")),
    InstrSpec("SLLW", "reg-reg", OP_32, 0x1, 0x00, spec_ref=_ref("RV64I SLLW")),
    InstrSpec("SRLW", "reg-reg", OP_32, 0x5, 0x00, spec_ref=_ref("RV64I SRLW")),
    InstrSpec("SRAW", "reg-reg", OP_32, 0x5, 0x20, spec_ref=_ref("RV64I SRAW")),
    InstrSpec("MULW",  "reg-reg", OP_32, 0x0, 0x01, spec_ref=_ref("M MULW")),
    InstrSpec("DIVW",  "reg-reg", OP_32, 0x4, 0x01, spec_ref=_ref("M DIVW")),
    InstrSpec("DIVUW", "reg-reg", OP_32, 0x5, 0x01, spec_ref=_ref("M DIVUW")),
    InstrSpec("REMW",  "reg-reg", OP_32, 0x6, 0x01, spec_ref=_ref("M REMW")),
    InstrSpec("REMUW", "reg-reg", OP_32, 0x7, 0x01, spec_ref=_ref("M REMUW")),
]

# reg-imm RV64I (opcode OP_IMM / OP_IMM32). exec_name reuses the reg-reg tree;
# the immediate is supplied as operand `b`. For shift-immediates the shamt is
# in the low bits of `b`, matching the reg-reg shift decode.
REGIMM_SPECS = [
    InstrSpec("ADDI",  "reg-imm", OP_IMM, 0x0, exec_name="ADD",  spec_ref=_ref("RV64I ADDI")),
    InstrSpec("SLTI",  "reg-imm", OP_IMM, 0x2, exec_name="SLT",  spec_ref=_ref("RV64I SLTI")),
    InstrSpec("SLTIU", "reg-imm", OP_IMM, 0x3, exec_name="SLTU", spec_ref=_ref("RV64I SLTIU")),
    InstrSpec("XORI",  "reg-imm", OP_IMM, 0x4, exec_name="XOR",  spec_ref=_ref("RV64I XORI")),
    InstrSpec("ORI",   "reg-imm", OP_IMM, 0x6, exec_name="OR",   spec_ref=_ref("RV64I ORI")),
    InstrSpec("ANDI",  "reg-imm", OP_IMM, 0x7, exec_name="AND",  spec_ref=_ref("RV64I ANDI")),
    # RV64 shift-immediates: imm[11:6] prefix selects logical/arith; shamt 6 bits
    InstrSpec("SLLI",  "reg-imm", OP_IMM, 0x1, funct7_hi=0x00, exec_name="SLL", spec_ref=_ref("RV64I SLLI")),
    InstrSpec("SRLI",  "reg-imm", OP_IMM, 0x5, funct7_hi=0x00, exec_name="SRL", spec_ref=_ref("RV64I SRLI")),
    InstrSpec("SRAI",  "reg-imm", OP_IMM, 0x5, funct7_hi=0x10, exec_name="SRA", spec_ref=_ref("RV64I SRAI")),
    # word shift-immediates: shamt 5 bits, full funct7
    InstrSpec("ADDIW", "reg-imm", OP_IMM32, 0x0, exec_name="ADDW", spec_ref=_ref("RV64I ADDIW")),
    InstrSpec("SLLIW", "reg-imm", OP_IMM32, 0x1, funct7=0x00, exec_name="SLLW", spec_ref=_ref("RV64I SLLIW")),
    InstrSpec("SRLIW", "reg-imm", OP_IMM32, 0x5, funct7=0x00, exec_name="SRLW", spec_ref=_ref("RV64I SRLIW")),
    InstrSpec("SRAIW", "reg-imm", OP_IMM32, 0x5, funct7=0x20, exec_name="SRAW", spec_ref=_ref("RV64I SRAIW")),
]

UTYPE_SPECS = [
    InstrSpec("LUI",   "u-type", LUI_OP,   exec_name="LUI",   spec_ref=_ref("RV64I LUI")),
    InstrSpec("AUIPC", "u-type", AUIPC_OP, exec_name="AUIPC", spec_ref=_ref("RV64I AUIPC")),
]

ALL_SPECS = REGREG_SPECS + REGIMM_SPECS + UTYPE_SPECS
SPEC_BY_NAME = {s.name: s for s in ALL_SPECS}


def operand_vars(spec: InstrSpec) -> list[str]:
    """Which symbolic input leaves this instruction's execute references."""
    seen: list[str] = []

    def walk(e):
        if e.op == "var" and e.attr[0] not in seen:
            seen.append(e.attr[0])
        for c in e.args:
            walk(c)

    walk(spec.execute)
    return seen
