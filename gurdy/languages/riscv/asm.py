"""RV64I instruction encoders (shared helper).

Used by the construct-coverage inventory and by tests so programs are readable
and toolchain-free. Names are lowercase mnemonics; operands are explicit.
"""

from __future__ import annotations

_M = 0xFFFFFFFF


def _r(op, rd, f3, rs1, rs2, f7):
    return ((f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op) & _M


def _i(op, rd, f3, rs1, imm):
    return (((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op) & _M


def _s(op, f3, rs1, rs2, imm):
    imm &= 0xFFF
    return (((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | op) & _M


def _b(f3, rs1, rs2, imm):
    imm &= 0x1FFF
    return (
        (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15)
        | (f3 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | 0x63
    ) & _M


def _u(op, rd, val):
    return ((val & 0xFFFFF000) | (rd << 7) | op) & _M


def _j(rd, off):
    off &= 0x1FFFFF
    imm = (((off >> 20) & 1) << 31) | (((off >> 1) & 0x3FF) << 21) | (((off >> 11) & 1) << 20) | (((off >> 12) & 0xFF) << 12)
    return (imm | (rd << 7) | 0x6F) & _M


# U / J / jumps
def lui(rd, imm): return _u(0x37, rd, imm)
def auipc(rd, imm): return _u(0x17, rd, imm)
def jal(rd, off): return _j(rd, off)
def jalr(rd, rs1, imm): return _i(0x67, rd, 0, rs1, imm)

# branches
def beq(a, c, off): return _b(0, a, c, off)
def bne(a, c, off): return _b(1, a, c, off)
def blt(a, c, off): return _b(4, a, c, off)
def bge(a, c, off): return _b(5, a, c, off)
def bltu(a, c, off): return _b(6, a, c, off)
def bgeu(a, c, off): return _b(7, a, c, off)

# loads / stores
def lb(rd, rs1, off): return _i(0x03, rd, 0, rs1, off)
def lh(rd, rs1, off): return _i(0x03, rd, 1, rs1, off)
def lw(rd, rs1, off): return _i(0x03, rd, 2, rs1, off)
def ld(rd, rs1, off): return _i(0x03, rd, 3, rs1, off)
def lbu(rd, rs1, off): return _i(0x03, rd, 4, rs1, off)
def lhu(rd, rs1, off): return _i(0x03, rd, 5, rs1, off)
def lwu(rd, rs1, off): return _i(0x03, rd, 6, rs1, off)
def sb(rs2, rs1, off): return _s(0x23, 0, rs1, rs2, off)
def sh(rs2, rs1, off): return _s(0x23, 1, rs1, rs2, off)
def sw(rs2, rs1, off): return _s(0x23, 2, rs1, rs2, off)
def sd(rs2, rs1, off): return _s(0x23, 3, rs1, rs2, off)

# OP-IMM
def addi(rd, rs1, im): return _i(0x13, rd, 0, rs1, im)
def slti(rd, rs1, im): return _i(0x13, rd, 2, rs1, im)
def sltiu(rd, rs1, im): return _i(0x13, rd, 3, rs1, im)
def xori(rd, rs1, im): return _i(0x13, rd, 4, rs1, im)
def ori(rd, rs1, im): return _i(0x13, rd, 6, rs1, im)
def andi(rd, rs1, im): return _i(0x13, rd, 7, rs1, im)
def slli(rd, rs1, sh): return _i(0x13, rd, 1, rs1, sh)
def srli(rd, rs1, sh): return _i(0x13, rd, 5, rs1, sh)
def srai(rd, rs1, sh): return _i(0x13, rd, 5, rs1, 0x400 | sh)

# OP
def add(rd, a, c): return _r(0x33, rd, 0, a, c, 0x00)
def sub(rd, a, c): return _r(0x33, rd, 0, a, c, 0x20)
def sll(rd, a, c): return _r(0x33, rd, 1, a, c, 0x00)
def slt(rd, a, c): return _r(0x33, rd, 2, a, c, 0x00)
def sltu(rd, a, c): return _r(0x33, rd, 3, a, c, 0x00)
def xor(rd, a, c): return _r(0x33, rd, 4, a, c, 0x00)
def srl(rd, a, c): return _r(0x33, rd, 5, a, c, 0x00)
def sra(rd, a, c): return _r(0x33, rd, 5, a, c, 0x20)
def or_(rd, a, c): return _r(0x33, rd, 6, a, c, 0x00)
def and_(rd, a, c): return _r(0x33, rd, 7, a, c, 0x00)

# OP-IMM-32
def addiw(rd, rs1, im): return _i(0x1B, rd, 0, rs1, im)
def slliw(rd, rs1, sh): return _i(0x1B, rd, 1, rs1, sh)
def srliw(rd, rs1, sh): return _i(0x1B, rd, 5, rs1, sh)
def sraiw(rd, rs1, sh): return _i(0x1B, rd, 5, rs1, 0x400 | sh)

# OP-32
def addw(rd, a, c): return _r(0x3B, rd, 0, a, c, 0x00)
def subw(rd, a, c): return _r(0x3B, rd, 0, a, c, 0x20)
def sllw(rd, a, c): return _r(0x3B, rd, 1, a, c, 0x00)
def srlw(rd, a, c): return _r(0x3B, rd, 5, a, c, 0x00)
def sraw(rd, a, c): return _r(0x3B, rd, 5, a, c, 0x20)

# misc
def fence(): return 0x0000000F
def ecall(): return 0x00000073
def ebreak(): return 0x00100073

# M-extension (RV64M)
def mul(rd, a, c): return _r(0x33, rd, 0, a, c, 0x01)
def mulh(rd, a, c): return _r(0x33, rd, 1, a, c, 0x01)
def mulhsu(rd, a, c): return _r(0x33, rd, 2, a, c, 0x01)
def mulhu(rd, a, c): return _r(0x33, rd, 3, a, c, 0x01)
def div(rd, a, c): return _r(0x33, rd, 4, a, c, 0x01)
def divu(rd, a, c): return _r(0x33, rd, 5, a, c, 0x01)
def rem(rd, a, c): return _r(0x33, rd, 6, a, c, 0x01)
def remu(rd, a, c): return _r(0x33, rd, 7, a, c, 0x01)
def mulw(rd, a, c): return _r(0x3B, rd, 0, a, c, 0x01)
def divw(rd, a, c): return _r(0x3B, rd, 4, a, c, 0x01)
def divuw(rd, a, c): return _r(0x3B, rd, 5, a, c, 0x01)
def remw(rd, a, c): return _r(0x3B, rd, 6, a, c, 0x01)
def remuw(rd, a, c): return _r(0x3B, rd, 7, a, c, 0x01)
