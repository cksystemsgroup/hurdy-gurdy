"""Independent bit-precise RV64I/M reference semantics, as z3 functions.

WHY THIS FILE EXISTS (the "stands in for Sail" caveat)
======================================================
In the hurdy-gurdy v3 architecture the *reference* / oracle for the
``sail-riscv`` group is the Sail-RISCV emulator (``realizations/emulator``).
The machine-build agent is supposed to verify the BTOR2 machine model against
**Sail**.

In THIS environment Sail and Spike are absent, so we cannot execute Sail. To
keep the verification structure honest rather than fake, this module provides
a small, documented, bit-precise reference RV64 semantics derived *directly
from the RISC-V Unprivileged ISA spec* (volume I, RV64I + the "M" standard
extension). The BTOR2 fragments in ``tools/sail_btor2_machine/isa`` are then
proven equivalent to THIS reference with z3.

    *** TODO(machine-agent): swap this reference for the Sail emulator. ***
    When the Sail-RISCV emulator is wired into ``realizations/emulator``,
    replace the bodies below with calls into Sail's per-instruction relation
    (or keep this as a cross-check). Only the *reference source* changes; the
    BTOR2 fragments and the z3 lemma harness stay put. This is the single
    point of substitution the architecture promises.

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
