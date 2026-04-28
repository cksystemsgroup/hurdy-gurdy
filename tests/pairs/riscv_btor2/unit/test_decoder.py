"""Per-mnemonic decode samples covering RV64I + M + selected RVC.

Each entry is (encoded_word, expected_mnemonic, expected_fields_dict).
We don't try to cover *every* operand combination — just enough to
exercise field extraction for each mnemonic.
"""

import pytest

from gurdy.pairs.riscv_btor2.source.decoder import (
    decode,
    decode_compressed,
    expand_rvc,
)
from gurdy.pairs.riscv_btor2.source.disasm import disasm


# Encoders to build sample words.
def _i(imm, rs1, funct3, rd, op):
    return ((imm & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | ((funct3 & 0x7) << 12) | ((rd & 0x1F) << 7) | (op & 0x7F)


def _r(funct7, rs2, rs1, funct3, rd, op):
    return ((funct7 & 0x7F) << 25) | ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | ((funct3 & 0x7) << 12) | ((rd & 0x1F) << 7) | (op & 0x7F)


def _s(imm, rs2, rs1, funct3, op):
    imm12 = imm & 0xFFF
    return (((imm12 >> 5) & 0x7F) << 25) | ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | ((funct3 & 0x7) << 12) | ((imm12 & 0x1F) << 7) | (op & 0x7F)


def _b(imm, rs2, rs1, funct3, op):
    imm = imm & 0x1FFF
    return (
        (((imm >> 12) & 0x1) << 31)
        | (((imm >> 5) & 0x3F) << 25)
        | ((rs2 & 0x1F) << 20)
        | ((rs1 & 0x1F) << 15)
        | ((funct3 & 0x7) << 12)
        | (((imm >> 1) & 0xF) << 8)
        | (((imm >> 11) & 0x1) << 7)
        | (op & 0x7F)
    )


def _u(imm, rd, op):
    return ((imm & 0xFFFFF) << 12) | ((rd & 0x1F) << 7) | (op & 0x7F)


def _j(imm, rd, op):
    imm = imm & 0x1FFFFF
    return (
        (((imm >> 20) & 0x1) << 31)
        | (((imm >> 1) & 0x3FF) << 21)
        | (((imm >> 11) & 0x1) << 20)
        | (((imm >> 12) & 0xFF) << 12)
        | ((rd & 0x1F) << 7)
        | (op & 0x7F)
    )


def test_addi_basic():
    w = _i(5, 10, 0, 11, 0b0010011)
    d = decode(w)
    assert d.mnemonic == "ADDI"
    assert d.rd == 11
    assert d.rs1 == 10
    assert d.imm == 5


def test_addi_negative_immediate_sign_extends():
    w = _i((-1) & 0xFFF, 0, 0, 0, 0b0010011)
    d = decode(w)
    assert d.imm == -1


def test_addi_x0_x0_0_is_nop():
    w = _i(0, 0, 0, 0, 0b0010011)
    d = decode(w)
    assert d.mnemonic == "ADDI"
    assert disasm(d) == "nop"


def test_add_sub_share_funct3():
    add = decode(_r(0, 2, 1, 0, 3, 0b0110011))
    sub = decode(_r(0b0100000, 2, 1, 0, 3, 0b0110011))
    assert add.mnemonic == "ADD"
    assert sub.mnemonic == "SUB"


def test_branch_decoders():
    for funct3, mnem in [(0, "BEQ"), (1, "BNE"), (4, "BLT"), (5, "BGE"), (6, "BLTU"), (7, "BGEU")]:
        d = decode(_b(8, 1, 2, funct3, 0b1100011))
        assert d.mnemonic == mnem
        assert d.rs1 == 2 and d.rs2 == 1 and d.imm == 8


def test_load_store_decoders():
    for funct3, mnem in [(0, "LB"), (1, "LH"), (2, "LW"), (3, "LD"), (4, "LBU"), (5, "LHU"), (6, "LWU")]:
        d = decode(_i(12, 5, funct3, 7, 0b0000011))
        assert d.mnemonic == mnem
        assert d.rd == 7 and d.rs1 == 5 and d.imm == 12

    for funct3, mnem in [(0, "SB"), (1, "SH"), (2, "SW"), (3, "SD")]:
        d = decode(_s(20, 6, 8, funct3, 0b0100011))
        assert d.mnemonic == mnem
        assert d.rs1 == 8 and d.rs2 == 6 and d.imm == 20


def test_jal_decodes_signed_offset():
    d = decode(_j(0x1234 & ~1, 1, 0b1101111))
    assert d.mnemonic == "JAL"
    assert d.rd == 1
    assert (d.imm & 0xFFFFFFFE) == (0x1234 & ~1)


def test_jalr_x0_ra_0_is_ret():
    w = _i(0, 1, 0, 0, 0b1100111)
    d = decode(w)
    assert d.mnemonic == "JALR"
    assert disasm(d) == "ret"


def test_lui_auipc_immediate():
    lui = decode(_u(0x12345, 4, 0b0110111))
    auipc = decode(_u(0x100, 5, 0b0010111))
    assert lui.mnemonic == "LUI"
    assert lui.imm == 0x12345 << 12
    assert auipc.mnemonic == "AUIPC"
    assert auipc.imm == 0x100 << 12


def test_shift_immediate_64bit_uses_6bit_shamt():
    # SLLI rd=2, rs1=3, shamt=33: funct6=000000, funct3=001, op=0010011
    w = (0 << 26) | (33 << 20) | (3 << 15) | (1 << 12) | (2 << 7) | 0b0010011
    d = decode(w)
    assert d.mnemonic == "SLLI"
    assert d.imm == 33


def test_srai_funct6():
    w = (0b010000 << 26) | (5 << 20) | (3 << 15) | (5 << 12) | (2 << 7) | 0b0010011
    d = decode(w)
    assert d.mnemonic == "SRAI"
    assert d.imm == 5


def test_word_arith_addiw_addw_subw():
    addiw = decode(_i(7, 1, 0, 2, 0b0011011))
    addw = decode(_r(0, 2, 1, 0, 3, 0b0111011))
    subw = decode(_r(0b0100000, 2, 1, 0, 3, 0b0111011))
    assert addiw.mnemonic == "ADDIW"
    assert addw.mnemonic == "ADDW"
    assert subw.mnemonic == "SUBW"


def test_m_extension_mul_div_etc():
    for funct3, mnem in [
        (0, "MUL"),
        (1, "MULH"),
        (2, "MULHSU"),
        (3, "MULHU"),
        (4, "DIV"),
        (5, "DIVU"),
        (6, "REM"),
        (7, "REMU"),
    ]:
        d = decode(_r(0b0000001, 2, 1, funct3, 3, 0b0110011))
        assert d.mnemonic == mnem


def test_m_extension_word_variants():
    for funct3, mnem in [(0, "MULW"), (4, "DIVW"), (5, "DIVUW"), (6, "REMW"), (7, "REMUW")]:
        d = decode(_r(0b0000001, 2, 1, funct3, 3, 0b0111011))
        assert d.mnemonic == mnem


def test_ecall_ebreak_fence():
    assert decode(0x00000073).mnemonic == "ECALL"
    assert decode(0x00100073).mnemonic == "EBREAK"
    assert decode(0x0000000F).mnemonic == "FENCE"
    assert decode(0x0000100F).mnemonic == "FENCE.I"


def test_csr_instructions():
    # csrrw rd=2, rs1=3, csr=0x300
    w = (0x300 << 20) | (3 << 15) | (1 << 12) | (2 << 7) | 0b1110011
    d = decode(w)
    assert d.mnemonic == "CSRRW"
    assert d.imm == 0x300
    assert d.rd == 2
    assert d.rs1 == 3


def test_reserved_returns_none():
    # An invalid funct7 for ADD/SUB.
    w = _r(0b0011110, 0, 0, 0, 0, 0b0110011)
    assert decode(w) is None


# ---------- RVC ----------


def test_rvc_c_nop_expands_to_addi_x0_x0_0():
    assert expand_rvc(0x0001) == 0x00000013


def test_rvc_c_add_expands():
    # C.ADD rd=2, rs2=3 -> add x2, x2, x3
    half = (0b1001 << 12) | (2 << 7) | (3 << 2) | 0b10
    word = expand_rvc(half)
    d = decode(word)
    assert d.mnemonic == "ADD"
    assert d.rd == 2 and d.rs1 == 2 and d.rs2 == 3


def test_rvc_c_li_expands():
    # C.LI rd=5, imm=3 -> addi x5, x0, 3
    half = (0b010 << 13) | (0 << 12) | (5 << 7) | (3 << 2) | 0b01
    word = expand_rvc(half)
    d = decode(word)
    assert d.mnemonic == "ADDI"
    assert d.rs1 == 0 and d.rd == 5 and d.imm == 3


def test_decode_compressed_marks_length_2():
    half = 0x0001  # c.nop
    d = decode_compressed(half)
    assert d.length == 2
    assert d.mnemonic == "ADDI"


def test_rvc_reserved_returns_none():
    # 0x0000 is not a valid RVC encoding.
    assert decode_compressed(0x0000) is None
