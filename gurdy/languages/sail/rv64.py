"""RV64I + RV64M instruction specs — the Sail-derived semantics. Each
instruction's computational content (ALU result, branch condition, jump
target) is an ``Expr`` tree (salvaged/extended from v3, proven equivalent to
the reference); the pc-selection / link structure is carried as decode
metadata, consumed identically by the Sail interpreter and the ``sail-btor2``
translator. Self-contained decoder, so this realization shares no
encoding/semantics code with the hand-written ``riscv`` line.

Scope: the ALU core (OP / OP-IMM / OP-32 / OP-IMM-32, LUI, AUIPC, M), control
flow (the branches, JAL, JALR, FENCE), and loads/stores; the C-compressed
encodings are expanded by ``compressed``. Out-of-scope / reserved encodings
decode to ``None`` (the pair aborts with ``Unsupported``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .expr import (
    Expr, add, and1, and_, const, eq, ite, mul, not_, or_, sext, slice_,
    sll, slt, sra, srl, sub, udiv, sdiv, urem, srem, ult, var, xor_, zext,
)

MASK64 = (1 << 64) - 1
A, B, PC, UIMM = var("a", 64), var("b", 64), var("pc", 64), var("uimm", 64)


def _shamt6(b):
    return zext(slice_(b, 5, 0), 64)


def _shamt5(b):
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

# branch conditions (1-bit Expr over a, b)
_BRANCH = {
    0x0: ("BEQ", eq(A, B)), 0x1: ("BNE", not_(eq(A, B))),
    0x4: ("BLT", slt(A, B)), 0x5: ("BGE", not_(slt(A, B))),
    0x6: ("BLTU", ult(A, B)), 0x7: ("BGEU", not_(ult(A, B))),
}

OP, OP_IMM, OP_32, OP_IMM32, LUI_OP, AUIPC_OP = 0x33, 0x13, 0x3B, 0x1B, 0x37, 0x17
BRANCH, JALR_OP, JAL_OP, FENCE_OP = 0x63, 0x67, 0x6F, 0x0F
LOAD_OP, STORE_OP = 0x03, 0x23

# load funct3 -> (nbytes, signed); store funct3 -> nbytes
_LOAD = {0: (1, True), 1: (2, True), 2: (4, True), 3: (8, False),
         4: (1, False), 5: (2, False), 6: (4, False)}
_STORE = {0: 1, 1: 2, 2: 4, 3: 8}

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
_REGIMM = {
    (OP_IMM, 0x0): ("ADDI", "ADD"), (OP_IMM, 0x2): ("SLTI", "SLT"),
    (OP_IMM, 0x3): ("SLTIU", "SLTU"), (OP_IMM, 0x4): ("XORI", "XOR"),
    (OP_IMM, 0x6): ("ORI", "OR"), (OP_IMM, 0x7): ("ANDI", "AND"),
    (OP_IMM32, 0x0): ("ADDIW", "ADDW"),
}


def _sext(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def _iimm(instr): return _sext(instr >> 20, 12)
def _uimm(instr): return _sext(instr & 0xFFFFF000, 32)


def _simm(instr):
    return _sext(((instr >> 25) << 5) | ((instr >> 7) & 0x1F), 12)


def _bimm(instr):
    imm = ((((instr >> 31) & 1) << 12) | (((instr >> 7) & 1) << 11)
           | (((instr >> 25) & 0x3F) << 5) | (((instr >> 8) & 0xF) << 1))
    return _sext(imm, 13)


def _jimm(instr):
    imm = ((((instr >> 31) & 1) << 20) | (((instr >> 12) & 0xFF) << 12)
           | (((instr >> 20) & 1) << 11) | (((instr >> 21) & 0x3FF) << 1))
    return _sext(imm, 21)


def instruction_stream(prog: dict) -> list[tuple[int, int, int]]:
    """The ``(addr, instr32, length)`` sequence a Sail program executes. Each
    ``words[j]`` is the (already-expanded) 32-bit instruction; ``lengths[j]`` is
    its byte length (2 for an expanded RV64C instr, 4 otherwise). Addresses are
    ``entry`` plus the cumulative byte length, so compressed and base
    instructions interleave at their true 2-byte-granular PCs. ``lengths`` is
    optional — absent means an all-32-bit program (the legacy 4-byte stride)."""
    words = prog["words"]
    lengths = prog.get("lengths") or [4] * len(words)
    addr = int(prog.get("entry", 0))
    out: list[tuple[int, int, int]] = []
    for instr, length in zip(words, lengths):
        out.append((addr, instr, length))
        addr += length
    return out


@dataclass(frozen=True)
class Decoded:
    name: str
    kind: str            # "alu" | "branch" | "jal" | "jalr" | "fence"
    rd: int = 0
    a_reg: int | None = None
    b_reg: int | None = None
    b_imm: int | None = None
    uimm: int | None = None
    execute: Expr | None = None   # alu result
    cond: Expr | None = None      # branch condition (1-bit)
    target: Expr | None = None    # jalr computed target
    offset: int = 0               # branch / jal pc-relative offset
    addr: Expr | None = None      # load/store effective address (rs1 + imm)
    nbytes: int = 0               # load/store width
    signed: bool = False          # load sign-extends


def operands(d: Decoded, addr: int) -> dict[str, tuple]:
    """Operand recipe for the Expr lowerings: var -> ("reg", i) | ("imm", v) |
    ("pc", addr). The lowering only reads the vars its tree references."""
    ops: dict[str, tuple] = {"pc": ("pc", addr)}
    if d.a_reg is not None:
        ops["a"] = ("reg", d.a_reg)
    if d.b_reg is not None:
        ops["b"] = ("reg", d.b_reg)
    elif d.b_imm is not None:
        ops["b"] = ("imm", d.b_imm)
    if d.uimm is not None:
        ops["uimm"] = ("imm", d.uimm)
    return ops


def decode(instr: int) -> Decoded | None:
    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x7
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F

    if opcode == LUI_OP:
        return Decoded("LUI", "alu", rd, uimm=_uimm(instr), execute=EXEC["LUI"])
    if opcode == AUIPC_OP:
        return Decoded("AUIPC", "alu", rd, uimm=_uimm(instr), execute=EXEC["AUIPC"])
    if opcode in (OP, OP_32):
        name = _REGREG.get((opcode, funct3, funct7))
        if name is None:
            return None
        return Decoded(name, "alu", rd, a_reg=rs1, b_reg=rs2, execute=EXEC[name])
    if opcode in (OP_IMM, OP_IMM32):
        if funct3 in (1, 5):
            return _decode_shift(instr, opcode, funct3, rd, rs1)
        entry = _REGIMM.get((opcode, funct3))
        if entry is None:
            return None
        name, exec_name = entry
        return Decoded(name, "alu", rd, a_reg=rs1, b_imm=_iimm(instr) & MASK64,
                       execute=EXEC[exec_name])
    if opcode == BRANCH:
        br = _BRANCH.get(funct3)
        if br is None:
            return None
        return Decoded(br[0], "branch", a_reg=rs1, b_reg=rs2, cond=br[1], offset=_bimm(instr))
    if opcode == JAL_OP:
        return Decoded("JAL", "jal", rd, offset=_jimm(instr))
    if opcode == JALR_OP and funct3 == 0:
        target = and_(add(A, const(_iimm(instr) & MASK64, 64)), const((~1) & MASK64, 64))
        return Decoded("JALR", "jalr", rd, a_reg=rs1, target=target)
    if opcode == FENCE_OP:
        return Decoded("FENCE", "fence")
    if opcode == LOAD_OP:
        info = _LOAD.get(funct3)
        if info is None:
            return None
        nbytes, signed = info
        addr = add(A, const(_iimm(instr) & MASK64, 64))
        return Decoded("LOAD", "load", rd, a_reg=rs1, addr=addr, nbytes=nbytes, signed=signed)
    if opcode == STORE_OP:
        nbytes = _STORE.get(funct3)
        if nbytes is None:
            return None
        addr = add(A, const(_simm(instr) & MASK64, 64))
        return Decoded("STORE", "store", a_reg=rs1, b_reg=rs2, addr=addr, nbytes=nbytes)
    return None


def _decode_shift(instr, opcode, funct3, rd, rs1) -> Decoded:
    if opcode == OP_IMM:
        shamt = (instr >> 20) & 0x3F
        if funct3 == 1:
            name, exec_name = "SLLI", "SLL"
        elif ((instr >> 26) & 0x3F) == 0x10:
            name, exec_name = "SRAI", "SRA"
        else:
            name, exec_name = "SRLI", "SRL"
    else:
        shamt = (instr >> 20) & 0x1F
        if funct3 == 1:
            name, exec_name = "SLLIW", "SLLW"
        elif ((instr >> 25) & 0x7F) == 0x20:
            name, exec_name = "SRAIW", "SRAW"
        else:
            name, exec_name = "SRLIW", "SRLW"
    return Decoded(name, "alu", rd, a_reg=rs1, b_imm=shamt, execute=EXEC[exec_name])
