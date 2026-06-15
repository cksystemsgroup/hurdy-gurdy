"""Independent bit-precise RV64I/M reference semantics, as z3 functions.

WHY THIS FILE EXISTS (the "stands in for Sail" caveat)
======================================================
In the hurdy-gurdy v3 architecture the *reference* / oracle for the
``sail-riscv`` group is the Sail-RISCV emulator (``realizations/emulator``).
The machine-build agent is supposed to verify the BTOR2 machine model against
**Sail**.

This module provides a small, documented, bit-precise reference RV64 semantics
derived *directly from the RISC-V Unprivileged ISA spec* (volume I, RV64I +
the "M" standard extension), as z3 functions. The BTOR2 fragments in
``tools/sail_btor2_machine/isa`` are proven equivalent to THIS reference with
z3 over all inputs (the F3 lowering lemmas).

    *** This reference is CROSS-VALIDATED against the real Sail emulator. ***
    The Sail-RISCV emulator is wired into ``realizations/emulator/oracle.py``
    (pinned release v0.12). ``tools/sail_btor2_machine/sail_cross.cross_check``
    runs each function below against Sail on random + corner inputs; the
    machine gate records the outcome as ``reference_vs_sail_ok``. So this is no
    longer an unaudited stand-in: the symbolic reference is pinned to Sail
    concretely, and the BTOR2 model is proven equal to it symbolically. A
    symbolic Sail extraction (``sail -smt`` / Isla) remains a possible future
    swap, but the two-step chain here already discharges the caveat honestly.

Each function takes z3 BitVec terms and returns a z3 BitVec term, so the
reference and the BTOR2 encoding can be compared symbolically over ALL inputs
(QF_BV), not merely sampled.

Spec corners deliberately encoded (RISC-V Unprivileged ISA, RV64):
  * RV64I shifts SLL/SRL/SRA use the low **6 bits** of the shift operand
    (shamt in [0,63]); the W-variants SLLW/SRLW/SRAW use the low **5 bits**.
  * W-ops (ADDW/SUBW/SLLW/SRLW/SRAW and the *IW immediates) compute in 32
    bits and **sign-extend the 32-bit result to 64 bits**.
  * SLT/SLTU/SLTI/SLTIU produce a 64-bit 0/1 (signed / unsigned compare).
  * LUI: imm[31:12] << 12, then sign-extended to 64 (upper 20 placed in
    bits [31:12], bits [11:0] zero, bit 31 sign-extended).
  * AUIPC: pc + (sign-extended LUI-immediate).
  * "M": MULH/MULHU/MULHSU take the high XLEN bits of the 2*XLEN product.
    Division semantics (RISC-V spec, "Division Operations"):
        - DIV/DIVU/REM/REMU by zero: DIVU/DIV return all-ones (-1);
          REM/REMU return the dividend.
        - signed overflow (INT_MIN / -1): DIV returns INT_MIN, REM returns 0.
    The W-division variants apply the same rules in 32 bits then sign-extend.
"""

from __future__ import annotations

import z3

XLEN = 64


# --- small helpers ---------------------------------------------------------

def _sext(term: z3.BitVecRef, to_bits: int) -> z3.BitVecRef:
    cur = term.size()
    if cur == to_bits:
        return term
    return z3.SignExt(to_bits - cur, term)


def _zext(term: z3.BitVecRef, to_bits: int) -> z3.BitVecRef:
    cur = term.size()
    if cur == to_bits:
        return term
    return z3.ZeroExt(to_bits - cur, term)


def _low(term: z3.BitVecRef, n: int) -> z3.BitVecRef:
    return z3.Extract(n - 1, 0, term)


def _bool_to_bv64(b: z3.BoolRef) -> z3.BitVecRef:
    return z3.If(b, z3.BitVecVal(1, XLEN), z3.BitVecVal(0, XLEN))


def _shamt6(b: z3.BitVecRef) -> z3.BitVecRef:
    # RV64: shift amount = low 6 bits of operand, as a 64-bit shift count.
    return _zext(_low(b, 6), XLEN)


def _shamt5(b: z3.BitVecRef) -> z3.BitVecRef:
    # W-variants: shift amount = low 5 bits of operand, as a 32-bit count.
    return _zext(_low(b, 5), 32)


# --- RV64I register-register / register-immediate ALU ----------------------
# Each takes (a, b) as 64-bit BitVec terms.  For immediate instructions `b`
# is the already sign/zero-extended 64-bit immediate operand.

def ADD(a, b):   return a + b
def SUB(a, b):   return a - b
def SLL(a, b):   return a << _shamt6(b)
def SLT(a, b):   return _bool_to_bv64(a < b)            # signed (z3 BV < is signed)
def SLTU(a, b):  return _bool_to_bv64(z3.ULT(a, b))     # unsigned
def XOR(a, b):   return a ^ b
def SRL(a, b):   return z3.LShR(a, _shamt6(b))          # logical right shift
def SRA(a, b):   return a >> _shamt6(b)                 # arithmetic right shift (z3 >> is arithmetic)
def OR(a, b):    return a | b
def AND(a, b):   return a & b


# --- RV64I 32-bit word ops (lowering-sensitive) ----------------------------
# Compute in 32 bits, sign-extend the 32-bit result to 64.

def ADDW(a, b):
    r32 = _low(a, 32) + _low(b, 32)
    return _sext(r32, XLEN)


def SUBW(a, b):
    r32 = _low(a, 32) - _low(b, 32)
    return _sext(r32, XLEN)


def SLLW(a, b):
    r32 = _low(a, 32) << _shamt5(b)
    return _sext(r32, XLEN)


def SRLW(a, b):
    r32 = z3.LShR(_low(a, 32), _shamt5(b))
    return _sext(r32, XLEN)


def SRAW(a, b):
    r32 = _low(a, 32) >> _shamt5(b)
    return _sext(r32, XLEN)


# --- LUI / AUIPC -----------------------------------------------------------
# `uimm` here is the full 64-bit sign-extended U-immediate (imm[31:12]<<12).

def LUI(uimm):
    return uimm


def AUIPC(pc, uimm):
    return pc + uimm


# --- RV64M multiply --------------------------------------------------------

def MUL(a, b):
    return a * b                                        # low 64 bits


def _mulh_signed(a, b):
    aa = _sext(a, 2 * XLEN)
    bb = _sext(b, 2 * XLEN)
    return z3.Extract(2 * XLEN - 1, XLEN, aa * bb)


def _mulh_unsigned(a, b):
    aa = _zext(a, 2 * XLEN)
    bb = _zext(b, 2 * XLEN)
    return z3.Extract(2 * XLEN - 1, XLEN, aa * bb)


def _mulh_su(a, b):
    aa = _sext(a, 2 * XLEN)        # a signed
    bb = _zext(b, 2 * XLEN)        # b unsigned
    return z3.Extract(2 * XLEN - 1, XLEN, aa * bb)


def MULH(a, b):    return _mulh_signed(a, b)
def MULHU(a, b):   return _mulh_unsigned(a, b)
def MULHSU(a, b):  return _mulh_su(a, b)


# --- RV64M divide (full corner-case semantics) -----------------------------

def DIV(a, b):
    # signed; div-by-zero -> -1 ; INT_MIN/-1 -> INT_MIN
    zero = z3.BitVecVal(0, XLEN)
    minus1 = z3.BitVecVal(-1, XLEN)
    intmin = z3.BitVecVal(1 << (XLEN - 1), XLEN)
    overflow = z3.And(a == intmin, b == minus1)
    return z3.If(b == zero, minus1,
           z3.If(overflow, intmin, a / b))              # z3 BV / is signed sdiv


def DIVU(a, b):
    zero = z3.BitVecVal(0, XLEN)
    allones = z3.BitVecVal(-1, XLEN)
    return z3.If(b == zero, allones, z3.UDiv(a, b))


def REM(a, b):
    zero = z3.BitVecVal(0, XLEN)
    minus1 = z3.BitVecVal(-1, XLEN)
    intmin = z3.BitVecVal(1 << (XLEN - 1), XLEN)
    overflow = z3.And(a == intmin, b == minus1)
    return z3.If(b == zero, a,
           z3.If(overflow, zero, z3.SRem(a, b)))        # signed remainder (sign of dividend)


def REMU(a, b):
    zero = z3.BitVecVal(0, XLEN)
    return z3.If(b == zero, a, z3.URem(a, b))


# --- RV64M W-variants: 32-bit divide, then sign-extend to 64 ----------------

def _div32_signed(x, y):
    zero = z3.BitVecVal(0, 32)
    minus1 = z3.BitVecVal(-1, 32)
    intmin = z3.BitVecVal(1 << 31, 32)
    overflow = z3.And(x == intmin, y == minus1)
    return z3.If(y == zero, minus1,
           z3.If(overflow, intmin, x / y))


def _divu32(x, y):
    zero = z3.BitVecVal(0, 32)
    allones = z3.BitVecVal(-1, 32)
    return z3.If(y == zero, allones, z3.UDiv(x, y))


def _rem32_signed(x, y):
    zero = z3.BitVecVal(0, 32)
    minus1 = z3.BitVecVal(-1, 32)
    intmin = z3.BitVecVal(1 << 31, 32)
    overflow = z3.And(x == intmin, y == minus1)
    return z3.If(y == zero, x,
           z3.If(overflow, zero, z3.SRem(x, y)))


def _remu32(x, y):
    zero = z3.BitVecVal(0, 32)
    return z3.If(y == zero, x, z3.URem(x, y))


def MULW(a, b):
    r32 = _low(a, 32) * _low(b, 32)
    return _sext(r32, XLEN)


def DIVW(a, b):
    return _sext(_div32_signed(_low(a, 32), _low(b, 32)), XLEN)


def DIVUW(a, b):
    return _sext(_divu32(_low(a, 32), _low(b, 32)), XLEN)


def REMW(a, b):
    return _sext(_rem32_signed(_low(a, 32), _low(b, 32)), XLEN)


def REMUW(a, b):
    return _sext(_remu32(_low(a, 32), _low(b, 32)), XLEN)


# Convenience registry: name -> (arity-kind, fn).  "ab" = binary over (a,b);
# the immediate ALU ops reuse the same binary fn with b = extended immediate.
REGREG = {
    "ADD": ADD, "SUB": SUB, "SLL": SLL, "SLT": SLT, "SLTU": SLTU,
    "XOR": XOR, "SRL": SRL, "SRA": SRA, "OR": OR, "AND": AND,
    "ADDW": ADDW, "SUBW": SUBW, "SLLW": SLLW, "SRLW": SRLW, "SRAW": SRAW,
    "MUL": MUL, "MULH": MULH, "MULHU": MULHU, "MULHSU": MULHSU,
    "DIV": DIV, "DIVU": DIVU, "REM": REM, "REMU": REMU,
    "MULW": MULW, "DIVW": DIVW, "DIVUW": DIVUW, "REMW": REMW, "REMUW": REMUW,
}

# Immediate ALU: maps the I-type mnemonic to the reg-reg fn it shares.
IMM_ALIAS = {
    "ADDI": ADD, "SLTI": SLT, "SLTIU": SLTU, "XORI": XOR, "ORI": OR,
    "ANDI": AND, "SLLI": SLL, "SRLI": SRL, "SRAI": SRA,
    "ADDIW": ADDW, "SLLIW": SLLW, "SRLIW": SRLW, "SRAIW": SRAW,
}


# ===========================================================================
# Independent reference STEP — fetch/decode/dispatch/writeback/pc, as z3.
# ===========================================================================
# This is the *reference* whole-instruction step the harness lemma proves the
# machine model equal to. It is written INDEPENDENTLY of the machine's decode
# tables (``tools/sail_btor2_machine/isa/rv64_alu.py``): the encodings below
# are transcribed here directly from the RISC-V Unprivileged ISA, organized by
# instruction format, so that the lemma "machine step == ref step" genuinely
# constrains the machine decoder (a wrong opcode/funct/immediate in EITHER
# transcription is caught — see the negative control in ``verify.py``). The
# execute SEMANTICS reuse the validated functions above (those are already
# cross-validated against Sail); the new content under test is the DECODE.
#
# State model (the pinned rv64 ALU-slice projection): a regfile z3 Array
# (bv5 -> bv64) and a pc (bv64). x0 reads as 0 and writes to x0 are discarded.
# Every instruction in this slice writes rd and advances pc by 4 (no control
# flow / loads / stores in slice).

# RISC-V opcodes (independent transcription).
_OP, _OP_IMM, _OP_32, _OP_IMM32, _LUI, _AUIPC = 0x33, 0x13, 0x3B, 0x1B, 0x37, 0x17


def _bits(iw, hi, lo):
    return z3.Extract(hi, lo, iw)


# operand-selection kinds for the decode table
_RR, _IMM_I, _SH6, _SH5, _U_LUI, _U_AUIPC = "rr", "imm_i", "sh6", "sh5", "lui", "auipc"


def _ref_decode_table():
    """(mnemonic, opcode, funct3, funct7, funct7_hi, exec_fn, operand_kind),
    transcribed independently from the RISC-V Unprivileged ISA by format.
    funct7 / funct7_hi are None when the format does not constrain them."""
    T = []
    # ---- R-type RV64I (OP) ----
    for name, f3, f7 in [("ADD",0x0,0x00),("SUB",0x0,0x20),("SLL",0x1,0x00),
                         ("SLT",0x2,0x00),("SLTU",0x3,0x00),("XOR",0x4,0x00),
                         ("SRL",0x5,0x00),("SRA",0x5,0x20),("OR",0x6,0x00),
                         ("AND",0x7,0x00)]:
        T.append((name, _OP, f3, f7, None, REGREG[name], _RR))
    # ---- R-type "M" (OP) ----
    for name, f3 in [("MUL",0x0),("MULH",0x1),("MULHSU",0x2),("MULHU",0x3),
                     ("DIV",0x4),("DIVU",0x5),("REM",0x6),("REMU",0x7)]:
        T.append((name, _OP, f3, 0x01, None, REGREG[name], _RR))
    # ---- R-type word RV64I (OP_32) ----
    for name, f3, f7 in [("ADDW",0x0,0x00),("SUBW",0x0,0x20),("SLLW",0x1,0x00),
                         ("SRLW",0x5,0x00),("SRAW",0x5,0x20)]:
        T.append((name, _OP_32, f3, f7, None, REGREG[name], _RR))
    # ---- R-type word "M" (OP_32) ----
    for name, f3 in [("MULW",0x0),("DIVW",0x4),("DIVUW",0x5),("REMW",0x6),("REMUW",0x7)]:
        T.append((name, _OP_32, f3, 0x01, None, REGREG[name], _RR))
    # ---- I-type arithmetic (OP_IMM): b = sign-extended imm[11:0] ----
    for name, f3 in [("ADDI",0x0),("SLTI",0x2),("SLTIU",0x3),("XORI",0x4),
                     ("ORI",0x6),("ANDI",0x7)]:
        T.append((name, _OP_IMM, f3, None, None, IMM_ALIAS[name], _IMM_I))
    # ---- RV64 shift-immediates (OP_IMM): 6-bit shamt, imm[11:6] distinguishes ----
    T.append(("SLLI", _OP_IMM, 0x1, None, 0x00, IMM_ALIAS["SLLI"], _SH6))
    T.append(("SRLI", _OP_IMM, 0x5, None, 0x00, IMM_ALIAS["SRLI"], _SH6))
    T.append(("SRAI", _OP_IMM, 0x5, None, 0x10, IMM_ALIAS["SRAI"], _SH6))
    # ---- I-type word arithmetic (OP_IMM32) ----
    T.append(("ADDIW", _OP_IMM32, 0x0, None, None, IMM_ALIAS["ADDIW"], _IMM_I))
    # ---- word shift-immediates (OP_IMM32): 5-bit shamt, full funct7 ----
    T.append(("SLLIW", _OP_IMM32, 0x1, 0x00, None, IMM_ALIAS["SLLIW"], _SH5))
    T.append(("SRLIW", _OP_IMM32, 0x5, 0x00, None, IMM_ALIAS["SRLIW"], _SH5))
    T.append(("SRAIW", _OP_IMM32, 0x5, 0x20, None, IMM_ALIAS["SRAIW"], _SH5))
    # ---- U-type ----
    T.append(("LUI",   _LUI,   None, None, None, None, _U_LUI))
    T.append(("AUIPC", _AUIPC, None, None, None, None, _U_AUIPC))
    return T


_REF_TABLE = _ref_decode_table()


def _ref_match(iw, opcode, funct3, funct7, funct7_hi):
    conds = [_bits(iw, 6, 0) == opcode]
    if funct3 is not None:
        conds.append(_bits(iw, 14, 12) == funct3)
    if funct7 is not None:
        conds.append(_bits(iw, 31, 25) == funct7)
    if funct7_hi is not None:
        conds.append(_bits(iw, 31, 26) == funct7_hi)
    return z3.And(*conds)


def _ref_result(iw, a, rs2v, pc, kind, fn):
    imm_i = z3.SignExt(52, _bits(iw, 31, 20))
    sh6 = z3.ZeroExt(58, _bits(iw, 25, 20))
    sh5 = z3.ZeroExt(59, _bits(iw, 24, 20))
    imm_u = z3.SignExt(32, z3.Concat(_bits(iw, 31, 12), z3.BitVecVal(0, 12)))
    if kind == _RR:
        return fn(a, rs2v)
    if kind == _IMM_I:
        return fn(a, imm_i)
    if kind == _SH6:
        return fn(a, sh6)
    if kind == _SH5:
        return fn(a, sh5)
    if kind == _U_LUI:
        return LUI(imm_u)
    if kind == _U_AUIPC:
        return AUIPC(pc, imm_u)
    raise ValueError(kind)


def ref_read(regfile, idx):
    """Read a GPR, honoring the x0-hardwired-zero rule."""
    return z3.If(idx == z3.BitVecVal(0, 5), z3.BitVecVal(0, XLEN), z3.Select(regfile, idx))


def ref_decodes_in_slice(iw):
    """1-bit predicate: iw encodes one of the slice's 43 ALU instructions."""
    return z3.Or(*[_ref_match(iw, op, f3, f7, f7h)
                   for (_n, op, f3, f7, f7h, _fn, _k) in _REF_TABLE])


def ref_step(iw, regfile, pc):
    """Independent reference whole-instruction step. Returns (regfile', pc').

    ``iw`` is the fetched 32-bit instruction word; ``regfile`` is a z3 Array
    bv5->bv64; ``pc`` is bv64. Decodes independently, reads rs1/rs2 (x0=0),
    computes via the validated execute functions, writes rd (x0 discarded),
    advances pc by 4."""
    rd = _bits(iw, 11, 7)
    rs1 = _bits(iw, 19, 15)
    rs2 = _bits(iw, 24, 20)
    a = ref_read(regfile, rs1)
    rs2v = ref_read(regfile, rs2)

    result = z3.BitVecVal(0, XLEN)
    for (_n, op, f3, f7, f7h, fn, kind) in reversed(_REF_TABLE):
        result = z3.If(_ref_match(iw, op, f3, f7, f7h),
                       _ref_result(iw, a, rs2v, pc, kind, fn), result)

    # writeback (x0 discarded) and pc advance
    new_rf = z3.If(rd == z3.BitVecVal(0, 5), regfile, z3.Store(regfile, rd, result))
    new_pc = pc + z3.BitVecVal(4, XLEN)
    return new_rf, new_pc
