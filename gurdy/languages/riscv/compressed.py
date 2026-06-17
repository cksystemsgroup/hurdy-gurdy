"""RV64C decompressor: expand a 16-bit compressed instruction to the 32-bit
base RV64I/M instruction it is defined to be equivalent to.

Both the interpreter and the riscv-btor2 translator consume the expansion and
reuse their existing 32-bit logic (parametrized by instruction length for the
fall-through / link address), so the C extension adds no new execution or
lowering rules — only this table. The integer C set is covered; the float
loads/stores (C.FLD/C.FSD/...) and reserved encodings hard-abort with
``Unsupported`` (BENCHMARKS.md §3).

Reference: the RISC-V "C" Standard Extension (the immediate scrambles are the
spec's CIW/CL/CS/CB/CJ/CI/CSS layouts).
"""

from __future__ import annotations

from ...core.errors import Unsupported


def _sext(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    if v >> (bits - 1):
        v -= 1 << bits
    return v


def _bit(c: int, i: int) -> int:
    return (c >> i) & 1


def _b(c: int, hi: int, lo: int) -> int:
    return (c >> lo) & ((1 << (hi - lo + 1)) - 1)


# 32-bit base-instruction encoders (inverse of interp's immediate decoders).
def _it(imm: int, rs1: int, f3: int, rd: int, op: int) -> int:
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op


def _rt(f7: int, rs2: int, rs1: int, f3: int, rd: int, op: int) -> int:
    return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op


def _st(imm: int, rs2: int, rs1: int, f3: int, op: int) -> int:
    imm &= 0xFFF
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | op


def _bt(imm: int, rs2: int, rs1: int, f3: int, op: int) -> int:
    imm &= 0x1FFF
    return (
        (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15)
        | (f3 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | op
    )


def _ut(imm20: int, rd: int, op: int) -> int:
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | op


def _jt(imm: int, rd: int, op: int) -> int:
    imm &= 0x1FFFFF
    return (
        (((imm >> 20) & 1) << 31) | (((imm >> 1) & 0x3FF) << 21) | (((imm >> 11) & 1) << 20)
        | (((imm >> 12) & 0xFF) << 12) | (rd << 7) | op
    )


def _cj_imm(c: int) -> int:
    imm = (
        (_bit(c, 12) << 11) | (_bit(c, 11) << 4) | (_b(c, 10, 9) << 8) | (_bit(c, 8) << 10)
        | (_bit(c, 7) << 6) | (_bit(c, 6) << 7) | (_b(c, 5, 3) << 1) | (_bit(c, 2) << 5)
    )
    return _sext(imm, 12)


def _cb_imm(c: int) -> int:
    imm = (
        (_bit(c, 12) << 8) | (_b(c, 11, 10) << 3) | (_b(c, 6, 5) << 6)
        | (_b(c, 4, 3) << 1) | (_bit(c, 2) << 5)
    )
    return _sext(imm, 9)


def _q0(c: int, f3: int) -> int:
    rd_ = 8 + _b(c, 4, 2)
    rs1_ = 8 + _b(c, 9, 7)
    if f3 == 0:                                          # C.ADDI4SPN
        imm = (_b(c, 12, 11) << 4) | (_b(c, 10, 7) << 6) | (_bit(c, 6) << 2) | (_bit(c, 5) << 3)
        if imm == 0:
            raise Unsupported("riscv", "c.addi4spn.reserved")
        return _it(imm, 2, 0, rd_, 0x13)
    if f3 == 2:                                          # C.LW
        off = (_b(c, 12, 10) << 3) | (_bit(c, 6) << 2) | (_bit(c, 5) << 6)
        return _it(off, rs1_, 2, rd_, 0x03)
    if f3 == 3:                                          # C.LD
        off = (_b(c, 12, 10) << 3) | (_b(c, 6, 5) << 6)
        return _it(off, rs1_, 3, rd_, 0x03)
    if f3 == 6:                                          # C.SW
        off = (_b(c, 12, 10) << 3) | (_bit(c, 6) << 2) | (_bit(c, 5) << 6)
        return _st(off, rd_, rs1_, 2, 0x23)
    if f3 == 7:                                          # C.SD
        off = (_b(c, 12, 10) << 3) | (_b(c, 6, 5) << 6)
        return _st(off, rd_, rs1_, 3, 0x23)
    raise Unsupported("riscv", f"c.q0.funct3={f3}")      # 1,4,5 = float/reserved


def _q1(c: int, f3: int) -> int:
    rd = _b(c, 11, 7)
    ci_imm = _sext((_bit(c, 12) << 5) | _b(c, 6, 2), 6)
    if f3 == 0:                                          # C.ADDI (C.NOP when rd=0)
        return _it(ci_imm, rd, 0, rd, 0x13)
    if f3 == 1:                                          # C.ADDIW (RV64)
        if rd == 0:
            raise Unsupported("riscv", "c.addiw.rd0")
        return _it(ci_imm, rd, 0, rd, 0x1B)
    if f3 == 2:                                          # C.LI
        return _it(ci_imm, 0, 0, rd, 0x13)
    if f3 == 3:                                          # C.ADDI16SP / C.LUI
        if rd == 2:
            imm = _sext(
                (_bit(c, 12) << 9) | (_b(c, 4, 3) << 7) | (_bit(c, 5) << 6)
                | (_bit(c, 2) << 5) | (_bit(c, 6) << 4), 10)
            if imm == 0:
                raise Unsupported("riscv", "c.addi16sp.reserved")
            return _it(imm, 2, 0, 2, 0x13)
        nzimm6 = (_bit(c, 12) << 5) | _b(c, 6, 2)
        if nzimm6 == 0:
            raise Unsupported("riscv", "c.lui.reserved")
        return _ut(_sext(nzimm6, 6) & 0xFFFFF, rd, 0x37)
    if f3 == 4:                                          # MISC-ALU
        f2 = _b(c, 11, 10)
        r_ = 8 + _b(c, 9, 7)
        sh = (_bit(c, 12) << 5) | _b(c, 6, 2)
        if f2 == 0:                                      # C.SRLI
            return _it(sh, r_, 5, r_, 0x13)
        if f2 == 1:                                      # C.SRAI
            return _it(0x400 | sh, r_, 5, r_, 0x13)
        if f2 == 2:                                      # C.ANDI
            return _it(ci_imm, r_, 7, r_, 0x13)
        rs2_ = 8 + _b(c, 4, 2)
        sel = (_bit(c, 12) << 2) | _b(c, 6, 5)
        table = {
            0b000: _rt(0x20, rs2_, r_, 0, r_, 0x33),     # C.SUB
            0b001: _rt(0x00, rs2_, r_, 4, r_, 0x33),     # C.XOR
            0b010: _rt(0x00, rs2_, r_, 6, r_, 0x33),     # C.OR
            0b011: _rt(0x00, rs2_, r_, 7, r_, 0x33),     # C.AND
            0b100: _rt(0x20, rs2_, r_, 0, r_, 0x3B),     # C.SUBW
            0b101: _rt(0x00, rs2_, r_, 0, r_, 0x3B),     # C.ADDW
        }
        if sel not in table:
            raise Unsupported("riscv", f"c.alu.sel={sel:03b}")
        return table[sel]
    if f3 == 5:                                          # C.J
        return _jt(_cj_imm(c), 0, 0x6F)
    if f3 == 6:                                          # C.BEQZ
        return _bt(_cb_imm(c), 0, 8 + _b(c, 9, 7), 0, 0x63)
    return _bt(_cb_imm(c), 0, 8 + _b(c, 9, 7), 1, 0x63)  # f3 == 7: C.BNEZ


def _q2(c: int, f3: int) -> int:
    rd = _b(c, 11, 7)
    if f3 == 0:                                          # C.SLLI
        return _it((_bit(c, 12) << 5) | _b(c, 6, 2), rd, 1, rd, 0x13)
    if f3 == 2:                                          # C.LWSP
        if rd == 0:
            raise Unsupported("riscv", "c.lwsp.rd0")
        off = (_bit(c, 12) << 5) | (_b(c, 6, 4) << 2) | (_b(c, 3, 2) << 6)
        return _it(off, 2, 2, rd, 0x03)
    if f3 == 3:                                          # C.LDSP
        if rd == 0:
            raise Unsupported("riscv", "c.ldsp.rd0")
        off = (_bit(c, 12) << 5) | (_b(c, 6, 5) << 3) | (_b(c, 4, 2) << 6)
        return _it(off, 2, 3, rd, 0x03)
    if f3 == 4:                                          # C.JR/C.MV/C.EBREAK/C.JALR/C.ADD
        rs2 = _b(c, 6, 2)
        if _bit(c, 12) == 0:
            if rs2 == 0:                                 # C.JR
                if rd == 0:
                    raise Unsupported("riscv", "c.jr.rs1=0")
                return _it(0, rd, 0, 0, 0x67)
            return _rt(0, rs2, 0, 0, rd, 0x33)           # C.MV
        if rd == 0 and rs2 == 0:                         # C.EBREAK
            return 0x00100073
        if rs2 == 0:                                     # C.JALR
            return _it(0, rd, 0, 1, 0x67)
        return _rt(0, rs2, rd, 0, rd, 0x33)              # C.ADD
    if f3 == 6:                                          # C.SWSP
        off = (_b(c, 12, 9) << 2) | (_b(c, 8, 7) << 6)
        return _st(off, _b(c, 6, 2), 2, 2, 0x23)
    if f3 == 7:                                          # C.SDSP
        off = (_b(c, 12, 10) << 3) | (_b(c, 9, 7) << 6)
        return _st(off, _b(c, 6, 2), 2, 3, 0x23)
    raise Unsupported("riscv", f"c.q2.funct3={f3}")      # 1,5 = float


def is_compressed(half: int) -> bool:
    """A halfword whose low two bits are not 0b11 begins a 16-bit instruction."""
    return (half & 0x3) != 0x3


def expand(c: int) -> int:
    """Expand a 16-bit RV64C instruction to its 32-bit base equivalent."""
    c &= 0xFFFF
    if c == 0:
        raise Unsupported("riscv", "c.illegal(0x0000)")
    op = c & 0x3
    f3 = (c >> 13) & 0x7
    if op == 0:
        return _q0(c, f3)
    if op == 1:
        return _q1(c, f3)
    if op == 2:
        return _q2(c, f3)
    raise Unsupported("riscv", "expand: not a compressed instruction")
