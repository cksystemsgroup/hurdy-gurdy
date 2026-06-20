"""RV64C (compressed) → base-instruction expansion for the Sail realization.

A compressed 16-bit instruction is, by the RISC-V spec, a short encoding of a
32-bit base instruction; expanding it lets the Sail-derived ``rv64.decode`` +
``Expr`` semantics handle the C extension with **no new semantics** — a C.ADD is
an ADD, a C.LW is an LW. This decompressor is written **independently** of
``languages/riscv/compressed.py`` (its own encoders and dispatch), so the
Sail-mediated route stays a self-contained second realization; that the two
expansions agree on the fixed RV64C encoding is itself a cross-check.

``expand`` raises ``Unsupported("sail", ...)`` on reserved/illegal/float
encodings (the honest-failure rule, BENCHMARKS.md §3).
"""

from __future__ import annotations

from ...core.errors import Unsupported

# 32-bit base opcodes the expansions target.
_OP, _OP_IMM, _OP_32, _OP_IMM32 = 0x33, 0x13, 0x3B, 0x1B
_LUI, _LOAD, _STORE, _BRANCH, _JALR, _JAL = 0x37, 0x03, 0x23, 0x63, 0x67, 0x6F


def _f(c: int, hi: int, lo: int) -> int:
    """Bits [hi:lo] of the 16-bit instruction ``c``."""
    return (c >> lo) & ((1 << (hi - lo + 1)) - 1)


def _signed(v: int, bits: int) -> int:
    return v - (1 << bits) if v >> (bits - 1) else v


# --- 32-bit base-instruction encoders (standard RISC-V formats) -------------

def _i(imm: int, rs1: int, f3: int, rd: int, op: int) -> int:
    return (((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op) & 0xFFFFFFFF


def _r(f7: int, rs2: int, rs1: int, f3: int, rd: int, op: int) -> int:
    return ((f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op) & 0xFFFFFFFF


def _s(imm: int, rs2: int, rs1: int, f3: int, op: int) -> int:
    imm &= 0xFFF
    return (((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12)
            | ((imm & 0x1F) << 7) | op) & 0xFFFFFFFF


def _u(imm20: int, rd: int, op: int) -> int:
    return (((imm20 & 0xFFFFF) << 12) | (rd << 7) | op) & 0xFFFFFFFF


def _b(imm: int, rs2: int, rs1: int, f3: int) -> int:
    imm &= 0x1FFF
    return ((((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | (rs2 << 20)
            | (rs1 << 15) | (f3 << 12) | (((imm >> 1) & 0xF) << 8)
            | (((imm >> 11) & 1) << 7) | _BRANCH) & 0xFFFFFFFF


def _j(imm: int, rd: int) -> int:
    imm &= 0x1FFFFF
    return ((((imm >> 20) & 1) << 31) | (((imm >> 1) & 0x3FF) << 21)
            | (((imm >> 11) & 1) << 20) | (((imm >> 12) & 0xFF) << 12)
            | (rd << 7) | _JAL) & 0xFFFFFFFF


# CJ (C.J) and CB (C.BEQZ/C.BNEZ) immediate gathers.
def _cj_off(c: int) -> int:
    off = ((_f(c, 12, 12) << 11) | (_f(c, 11, 11) << 4) | (_f(c, 10, 9) << 8)
           | (_f(c, 8, 8) << 10) | (_f(c, 7, 7) << 6) | (_f(c, 6, 6) << 7)
           | (_f(c, 5, 3) << 1) | (_f(c, 2, 2) << 5))
    return _signed(off, 12)


def _cb_off(c: int) -> int:
    off = ((_f(c, 12, 12) << 8) | (_f(c, 11, 10) << 3) | (_f(c, 6, 5) << 6)
           | (_f(c, 4, 3) << 1) | (_f(c, 2, 2) << 5))
    return _signed(off, 9)


def _quadrant0(c: int, f3: int) -> int:
    rd_, rs1_ = 8 + _f(c, 4, 2), 8 + _f(c, 9, 7)
    if f3 == 0:  # C.ADDI4SPN -> addi rd', x2, nzuimm
        nz = (_f(c, 12, 11) << 4) | (_f(c, 10, 7) << 6) | (_f(c, 6, 6) << 2) | (_f(c, 5, 5) << 3)
        if nz == 0:
            raise Unsupported("sail", "c.addi4spn.reserved")
        return _i(nz, 2, 0, rd_, _OP_IMM)
    if f3 == 2:  # C.LW
        off = (_f(c, 12, 10) << 3) | (_f(c, 6, 6) << 2) | (_f(c, 5, 5) << 6)
        return _i(off, rs1_, 2, rd_, _LOAD)
    if f3 == 3:  # C.LD
        off = (_f(c, 12, 10) << 3) | (_f(c, 6, 5) << 6)
        return _i(off, rs1_, 3, rd_, _LOAD)
    if f3 == 6:  # C.SW
        off = (_f(c, 12, 10) << 3) | (_f(c, 6, 6) << 2) | (_f(c, 5, 5) << 6)
        return _s(off, rd_, rs1_, 2, _STORE)
    if f3 == 7:  # C.SD
        off = (_f(c, 12, 10) << 3) | (_f(c, 6, 5) << 6)
        return _s(off, rd_, rs1_, 3, _STORE)
    raise Unsupported("sail", f"c.q0.funct3={f3}")


def _quadrant1(c: int, f3: int) -> int:
    rd = _f(c, 11, 7)
    imm6 = _signed((_f(c, 12, 12) << 5) | _f(c, 6, 2), 6)
    if f3 == 0:  # C.ADDI / C.NOP
        return _i(imm6, rd, 0, rd, _OP_IMM)
    if f3 == 1:  # C.ADDIW (RV64)
        if rd == 0:
            raise Unsupported("sail", "c.addiw.rd0")
        return _i(imm6, rd, 0, rd, _OP_IMM32)
    if f3 == 2:  # C.LI
        return _i(imm6, 0, 0, rd, _OP_IMM)
    if f3 == 3:  # C.ADDI16SP (rd==2) / C.LUI
        if rd == 2:
            imm = _signed((_f(c, 12, 12) << 9) | (_f(c, 4, 3) << 7) | (_f(c, 5, 5) << 6)
                          | (_f(c, 2, 2) << 5) | (_f(c, 6, 6) << 4), 10)
            if imm == 0:
                raise Unsupported("sail", "c.addi16sp.reserved")
            return _i(imm, 2, 0, 2, _OP_IMM)
        nz = (_f(c, 12, 12) << 5) | _f(c, 6, 2)
        if nz == 0:
            raise Unsupported("sail", "c.lui.reserved")
        return _u(_signed(nz, 6) & 0xFFFFF, rd, _LUI)
    if f3 == 4:  # MISC-ALU
        f2, r_ = _f(c, 11, 10), 8 + _f(c, 9, 7)
        sh = (_f(c, 12, 12) << 5) | _f(c, 6, 2)
        if f2 == 0:  # C.SRLI
            return _i(sh, r_, 5, r_, _OP_IMM)
        if f2 == 1:  # C.SRAI
            return _i(0x400 | sh, r_, 5, r_, _OP_IMM)
        if f2 == 2:  # C.ANDI
            return _i(imm6, r_, 7, r_, _OP_IMM)
        rs2_, sel = 8 + _f(c, 4, 2), (_f(c, 12, 12) << 2) | _f(c, 6, 5)
        alu = {
            0b000: _r(0x20, rs2_, r_, 0, r_, _OP),     # C.SUB
            0b001: _r(0x00, rs2_, r_, 4, r_, _OP),     # C.XOR
            0b010: _r(0x00, rs2_, r_, 6, r_, _OP),     # C.OR
            0b011: _r(0x00, rs2_, r_, 7, r_, _OP),     # C.AND
            0b100: _r(0x20, rs2_, r_, 0, r_, _OP_32),  # C.SUBW
            0b101: _r(0x00, rs2_, r_, 0, r_, _OP_32),  # C.ADDW
        }
        if sel not in alu:
            raise Unsupported("sail", f"c.alu.sel={sel:03b}")
        return alu[sel]
    if f3 == 5:  # C.J -> jal x0, off
        return _j(_cj_off(c), 0)
    if f3 == 6:  # C.BEQZ -> beq rs1', x0, off
        return _b(_cb_off(c), 0, 8 + _f(c, 9, 7), 0)
    return _b(_cb_off(c), 0, 8 + _f(c, 9, 7), 1)  # f3 == 7: C.BNEZ


def _quadrant2(c: int, f3: int) -> int:
    rd, rs2 = _f(c, 11, 7), _f(c, 6, 2)
    if f3 == 0:  # C.SLLI
        return _i((_f(c, 12, 12) << 5) | _f(c, 6, 2), rd, 1, rd, _OP_IMM)
    if f3 == 2:  # C.LWSP
        if rd == 0:
            raise Unsupported("sail", "c.lwsp.rd0")
        off = (_f(c, 12, 12) << 5) | (_f(c, 6, 4) << 2) | (_f(c, 3, 2) << 6)
        return _i(off, 2, 2, rd, _LOAD)
    if f3 == 3:  # C.LDSP
        if rd == 0:
            raise Unsupported("sail", "c.ldsp.rd0")
        off = (_f(c, 12, 12) << 5) | (_f(c, 6, 5) << 3) | (_f(c, 4, 2) << 6)
        return _i(off, 2, 3, rd, _LOAD)
    if f3 == 4:  # C.JR / C.MV / C.EBREAK / C.JALR / C.ADD
        if _f(c, 12, 12) == 0:
            if rs2 == 0:  # C.JR
                if rd == 0:
                    raise Unsupported("sail", "c.jr.rs1=0")
                return _i(0, rd, 0, 0, _JALR)
            return _r(0, rs2, 0, 0, rd, _OP)  # C.MV
        if rd == 0 and rs2 == 0:  # C.EBREAK
            return 0x00100073
        if rs2 == 0:  # C.JALR
            return _i(0, rd, 0, 1, _JALR)
        return _r(0, rs2, rd, 0, rd, _OP)  # C.ADD
    if f3 == 6:  # C.SWSP
        off = (_f(c, 12, 9) << 2) | (_f(c, 8, 7) << 6)
        return _s(off, rs2, 2, 2, _STORE)
    if f3 == 7:  # C.SDSP
        off = (_f(c, 12, 10) << 3) | (_f(c, 9, 7) << 6)
        return _s(off, rs2, 2, 3, _STORE)
    raise Unsupported("sail", f"c.q2.funct3={f3}")


def is_compressed(half: int) -> bool:
    """A 16-bit unit begins a compressed instruction iff its low 2 bits ≠ 0b11."""
    return (half & 0x3) != 0x3


def expand(c: int) -> int:
    """Expand an RV64C 16-bit instruction to its 32-bit base equivalent."""
    c &= 0xFFFF
    if c == 0:
        raise Unsupported("sail", "c.illegal(0x0000)")
    op, f3 = c & 0x3, _f(c, 15, 13)
    if op == 0:
        return _quadrant0(c, f3)
    if op == 1:
        return _quadrant1(c, f3)
    return _quadrant2(c, f3)
