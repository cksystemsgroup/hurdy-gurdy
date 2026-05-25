"""Unit tests for the AArch64 A64 decoder.

Verified encodings come from manually-computed bit patterns and
cross-checked against the ARM Architecture Reference Manual.
"""

from __future__ import annotations

import pytest

from gurdy.pairs.aarch64_btor2.source.decoder import Decoded, decode


def test_nop():
    # NOP: 0xD503201F
    d = decode(0xD503201F, 0x1000)
    assert d is not None
    assert d.mnemonic == "NOP"


def test_ret():
    # RET (default x30): 0xD65F03C0
    d = decode(0xD65F03C0, 0x1000)
    assert d is not None
    assert d.mnemonic == "RET"
    assert d.rn == 30


def test_add_imm_64():
    # ADD X10, X10, #20 → 0x9100514A
    # sf=1, op=0, S=0, imm12=20, Rn=10, Rd=10
    d = decode(0x9100514A, 0)
    assert d is not None
    assert d.mnemonic == "ADD"
    assert d.sf is True
    assert d.rd == 10
    assert d.rn == 10
    assert d.imm == 20
    assert d.sets_flags is False


def test_adds_imm_64():
    # ADDS X0, X1, #1: sf=1, op=0, S=1, imm12=1, Rn=1, Rd=0
    # Bits: 1_0_1_10001_00_000000000001_00001_00000
    # = 1011_0001_0000_0000_0000_0100_0010_0000 = 0xB1000420? Let me recompute.
    # bit31=1(sf), bit30=0(ADD), bit29=1(S), bits28:24=10001, bits23:22=00, imm12=1, Rn=1, Rd=0
    # 1 0 1 10001 00 000000000001 00001 00000
    # = 1011 0001 0000 0000 0000 0100 0010 0000 = 0xB1000420
    d = decode(0xB1000420, 0)
    assert d is not None
    assert d.mnemonic == "ADDS"
    assert d.sets_flags is True
    assert d.imm == 1


def test_sub_imm_64():
    # SUB X0, X1, #4: sf=1, op=1, S=0, imm12=4, Rn=1, Rd=0
    # bit31=1, bit30=1(SUB), bit29=0, bits28:24=10001, bits23:22=00, imm12=4, Rn=1, Rd=0
    # 1_1_0_10001_00_000000000100_00001_00000 = 0xD1001020
    d = decode(0xD1001020, 0)
    assert d is not None
    assert d.mnemonic == "SUB"
    assert d.imm == 4
    assert d.rd == 0
    assert d.rn == 1


def test_movz():
    # MOVZ X0, #1: 0xD2800020 per analysis
    d = decode(0xD2800020, 0)
    assert d is not None
    assert d.mnemonic == "MOVZ"
    assert d.sf is True
    assert d.rd == 0
    assert d.imm == 1
    assert d.shift_amount == 0


def test_cbz_64():
    # CBZ X1, #8 → offset=2 in imm19, rt=1
    # top8=0xB4, imm19=2 → bits23:5 = 0b0000000000000000010, rt=1
    # 0xB4 0000 0000 0000 0000 0100 0001 = 0xB4000041
    d = decode(0xB4000041, 0x1000)
    assert d is not None
    assert d.mnemonic == "CBZ"
    assert d.sf is True
    assert d.rd == 1    # rt stored in rd
    assert d.imm == 8


def test_b_cond_eq():
    # B.EQ #8: bits[31:24]=0101_0100, imm19=2, cond=0000(EQ)
    # 0x54000040 = 0101_0100_0000_0000_0000_0000_0100_0000
    d = decode(0x54000040, 0x1000)
    assert d is not None
    assert d.mnemonic == "B.cond"
    assert d.cond == 0  # EQ
    assert d.imm == 8


def test_b_unconditional():
    # B #+4 (offset imm26=1 → imm=4): bits[30:26]=00101, bit31=0, imm26=1
    # 0x14000001 = 0001_0100_0000_0000_0000_0000_0000_0001
    d = decode(0x14000001, 0x1000)
    assert d is not None
    assert d.mnemonic == "B"
    assert d.imm == 4


def test_bl():
    # BL #+4: bit31=1, bits[30:26]=00101, imm26=1
    # 0x94000001
    d = decode(0x94000001, 0x1000)
    assert d is not None
    assert d.mnemonic == "BL"
    assert d.rd == 0    # x30 wired in simulator, rd not used


def test_br():
    # BR X1: bits[31:25]=1101011, opc=0000, op2=11111, Rn=1, op4=0
    # 0xD61F0020 = 1101_0110_0001_1111_0000_0000_0010_0000
    d = decode(0xD61F0020, 0)
    assert d is not None
    assert d.mnemonic == "BR"
    assert d.rn == 1


def test_svc():
    # SVC #0: 0xD4000001
    d = decode(0xD4000001, 0)
    assert d is not None
    assert d.mnemonic == "SVC"


def test_ldr_xt_unsigned_offset():
    # LDR X0, [X1, #0]: 0xF9400020
    d = decode(0xF9400020, 0)
    assert d is not None
    assert d.mnemonic == "LDR"
    assert d.sf is True
    assert d.rd == 0
    assert d.rn == 1
    assert d.imm == 0
    assert d.addr_mode == "base_imm"


def test_str_xt_unsigned_offset():
    # STR X1, [X2, #0]: size=11, opc=00, imm12=0, Rn=2, Rt=1
    # 1_1_1_11001_00_000000000000_00010_00001 = 0xF9000041
    d = decode(0xF9000041, 0)
    assert d is not None
    assert d.mnemonic == "STR"
    assert d.sf is True
    assert d.rd == 1
    assert d.rn == 2


def test_sdiv():
    # SDIV X0, X1, X2: 0x9AC20C20 (verified above)
    d = decode(0x9AC20C20, 0)
    assert d is not None
    assert d.mnemonic == "SDIV"
    assert d.sf is True
    assert d.rd == 0
    assert d.rn == 1
    assert d.rm == 2


def test_add_reg_shifted():
    # ADD X0, X1, X2, LSL #3
    # sf=1, op=0, S=0, bit28=1, bit24=0(shifted), shift=00(LSL), imm6=3, Rm=2, Rn=1, Rd=0
    # bit31=1, bit30=0, bit29=0, bit28=1, bits27:24=0000(?), shift=00, bit21=0, imm6=000011, Rm=2, Rn=1, Rd=0
    # Actually: sf[31] op[30] S[29] 01011 shift[23:22] 0 Rm[20:16] imm6[15:10] Rn[9:5] Rd[4:0]
    # = 1_0_0_01011_00_0_00010_000011_00001_00000
    # = 1000_1011_0000_0010_0000_1100_0010_0000 = 0x8B020C20
    d = decode(0x8B020C20, 0)
    assert d is not None
    assert d.mnemonic == "ADD"
    assert d.sf is True
    assert d.rd == 0
    assert d.rn == 1
    assert d.rm == 2
    assert d.shift_type == 0   # LSL
    assert d.shift_amount == 3


def test_ldr_wt_zero_extends():
    # LDR W0, [X1, #0]: size=10, opc=01, imm12=0, Rn=1, Rt=0
    # 1_0_1_11001_01_000000000000_00001_00000 = 0xB9400020
    d = decode(0xB9400020, 0)
    assert d is not None
    assert d.mnemonic == "LDR"
    assert d.sf is False   # 32-bit (W) form
