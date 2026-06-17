"""Minimal RV64C (compressed) encoders for tests and coverage probes — the
inverse of ``compressed.expand``. Each returns a 16-bit instruction word.

Validated against ``expand`` (and the base encoders) by a round-trip test, so
the coverage inventory exercises real compressed encodings rather than hand
hex. ``rp(r)`` are the popular registers x8..x15 the 3-bit fields address.
"""

from __future__ import annotations


def _p(r: int) -> int:
    assert 8 <= r <= 15, f"compressed register must be x8..x15, got x{r}"
    return r - 8


# --- Quadrant 0 ------------------------------------------------------------
def c_addi4spn(rd: int, uimm: int) -> int:
    return ((((uimm >> 4) & 3) << 11) | (((uimm >> 6) & 0xF) << 7)
            | (((uimm >> 2) & 1) << 6) | (((uimm >> 3) & 1) << 5) | (_p(rd) << 2))


def c_lw(rd: int, rs1: int, off: int) -> int:
    return ((2 << 13) | (((off >> 3) & 7) << 10) | (_p(rs1) << 7)
            | (((off >> 2) & 1) << 6) | (((off >> 6) & 1) << 5) | (_p(rd) << 2))


def c_ld(rd: int, rs1: int, off: int) -> int:
    return ((3 << 13) | (((off >> 3) & 7) << 10) | (_p(rs1) << 7)
            | (((off >> 6) & 3) << 5) | (_p(rd) << 2))


def c_sw(rs2: int, rs1: int, off: int) -> int:
    return ((6 << 13) | (((off >> 3) & 7) << 10) | (_p(rs1) << 7)
            | (((off >> 2) & 1) << 6) | (((off >> 6) & 1) << 5) | (_p(rs2) << 2))


def c_sd(rs2: int, rs1: int, off: int) -> int:
    return ((7 << 13) | (((off >> 3) & 7) << 10) | (_p(rs1) << 7)
            | (((off >> 6) & 3) << 5) | (_p(rs2) << 2))


# --- Quadrant 1 ------------------------------------------------------------
def _ci(f3: int, rd: int, imm: int) -> int:
    return (f3 << 13) | (((imm >> 5) & 1) << 12) | (rd << 7) | ((imm & 0x1F) << 2) | 1


def c_addi(rd: int, imm: int) -> int:
    return _ci(0, rd, imm)


def c_addiw(rd: int, imm: int) -> int:
    return _ci(1, rd, imm)


def c_li(rd: int, imm: int) -> int:
    return _ci(2, rd, imm)


def c_lui(rd: int, imm6: int) -> int:
    return _ci(3, rd, imm6)


def c_addi16sp(imm: int) -> int:
    return ((3 << 13) | (((imm >> 9) & 1) << 12) | (2 << 7) | (((imm >> 4) & 1) << 6)
            | (((imm >> 6) & 1) << 5) | (((imm >> 7) & 3) << 3) | (((imm >> 5) & 1) << 2) | 1)


def _ca(f2: int, rd: int, imm: int) -> int:
    return ((4 << 13) | (((imm >> 5) & 1) << 12) | (f2 << 10) | (_p(rd) << 7)
            | ((imm & 0x1F) << 2) | 1)


def c_srli(rd: int, sh: int) -> int:
    return _ca(0, rd, sh)


def c_srai(rd: int, sh: int) -> int:
    return _ca(1, rd, sh)


def c_andi(rd: int, imm: int) -> int:
    return _ca(2, rd, imm)


def _cr3(sel: int, rd: int, rs2: int) -> int:
    return ((4 << 13) | ((sel >> 2) << 12) | (3 << 10) | (_p(rd) << 7)
            | ((sel & 3) << 5) | (_p(rs2) << 2) | 1)


def c_sub(rd, rs2): return _cr3(0b000, rd, rs2)
def c_xor(rd, rs2): return _cr3(0b001, rd, rs2)
def c_or(rd, rs2): return _cr3(0b010, rd, rs2)
def c_and(rd, rs2): return _cr3(0b011, rd, rs2)
def c_subw(rd, rs2): return _cr3(0b100, rd, rs2)
def c_addw(rd, rs2): return _cr3(0b101, rd, rs2)


def c_j(off: int) -> int:
    return ((5 << 13) | (((off >> 11) & 1) << 12) | (((off >> 4) & 1) << 11)
            | (((off >> 8) & 3) << 9) | (((off >> 10) & 1) << 8) | (((off >> 6) & 1) << 7)
            | (((off >> 7) & 1) << 6) | (((off >> 1) & 7) << 3) | (((off >> 5) & 1) << 2) | 1)


def _cb(f3: int, rs1: int, off: int) -> int:
    return ((f3 << 13) | (((off >> 8) & 1) << 12) | (((off >> 3) & 3) << 10) | (_p(rs1) << 7)
            | (((off >> 6) & 3) << 5) | (((off >> 1) & 3) << 3) | (((off >> 5) & 1) << 2) | 1)


def c_beqz(rs1, off): return _cb(6, rs1, off)
def c_bnez(rs1, off): return _cb(7, rs1, off)


# --- Quadrant 2 ------------------------------------------------------------
def c_slli(rd: int, sh: int) -> int:
    return (0 << 13) | (((sh >> 5) & 1) << 12) | (rd << 7) | ((sh & 0x1F) << 2) | 2


def c_lwsp(rd: int, off: int) -> int:
    return ((2 << 13) | (((off >> 5) & 1) << 12) | (rd << 7)
            | (((off >> 2) & 7) << 4) | (((off >> 6) & 3) << 2) | 2)


def c_ldsp(rd: int, off: int) -> int:
    return ((3 << 13) | (((off >> 5) & 1) << 12) | (rd << 7)
            | (((off >> 3) & 3) << 5) | (((off >> 6) & 7) << 2) | 2)


def c_jr(rs1: int) -> int:
    return (4 << 13) | (rs1 << 7) | 2


def c_mv(rd: int, rs2: int) -> int:
    return (4 << 13) | (rd << 7) | (rs2 << 2) | 2


def c_jalr(rs1: int) -> int:
    return (4 << 13) | (1 << 12) | (rs1 << 7) | 2


def c_add(rd: int, rs2: int) -> int:
    return (4 << 13) | (1 << 12) | (rd << 7) | (rs2 << 2) | 2


def c_ebreak() -> int:
    return (4 << 13) | (1 << 12) | 2


def c_swsp(rs2: int, off: int) -> int:
    return ((6 << 13) | (((off >> 2) & 0xF) << 9) | (((off >> 6) & 3) << 7) | (rs2 << 2) | 2)


def c_sdsp(rs2: int, off: int) -> int:
    return ((7 << 13) | (((off >> 3) & 7) << 10) | (((off >> 6) & 7) << 7) | (rs2 << 2) | 2)
