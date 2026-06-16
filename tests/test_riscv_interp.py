"""RV64I interpreter tests (self-contained; the sail differential is the
dev-image acceptance, languages/riscv brief).

Tiny RV64I encoders live here so the programs are readable and the tests do
not depend on a toolchain.
"""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.languages.riscv.interp import run, image_from_words


# --- minimal RV64I encoders (test-local) ----------------------------------
def r(opcode, rd, funct3, rs1, rs2, funct7):
    return (
        (funct7 << 25) | (rs2 << 20) | (rs1 << 15)
        | (funct3 << 12) | (rd << 7) | opcode
    ) & 0xFFFFFFFF


def i(opcode, rd, funct3, rs1, imm):
    return (((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode) & 0xFFFFFFFF


def s(opcode, funct3, rs1, rs2, imm):
    imm &= 0xFFF
    return (
        ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15)
        | (funct3 << 12) | ((imm & 0x1F) << 7) | opcode
    ) & 0xFFFFFFFF


def b(funct3, rs1, rs2, imm):
    imm &= 0x1FFF
    return (
        (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15)
        | (funct3 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | 0x63
    ) & 0xFFFFFFFF


ADDI = lambda rd, rs1, imm: i(0x13, rd, 0, rs1, imm)       # noqa: E731
ADD = lambda rd, rs1, rs2: r(0x33, rd, 0, rs1, rs2, 0x00)  # noqa: E731
SUB = lambda rd, rs1, rs2: r(0x33, rd, 0, rs1, rs2, 0x20)  # noqa: E731
SLLI = lambda rd, rs1, sh: i(0x13, rd, 1, rs1, sh)         # noqa: E731
SD = lambda rs2, rs1, off: s(0x23, 3, rs1, rs2, off)       # noqa: E731
LD = lambda rd, rs1, off: i(0x03, rd, 3, rs1, off)         # noqa: E731
BNE = lambda rs1, rs2, off: b(1, rs1, rs2, off)            # noqa: E731
ECALL = lambda: i(0x73, 0, 0, 0, 0)                        # noqa: E731


def final(trace):
    return trace[-1]


class TestRV64I(unittest.TestCase):
    def test_addi_add_halt(self):
        prog = [ADDI(1, 0, 5), ADDI(2, 0, 37), ADD(3, 1, 2), ECALL()]
        t = run(image_from_words(prog))
        self.assertEqual(final(t)["x3"], 42)
        self.assertTrue(final(t)["halted"])

    def test_x0_is_hardwired_zero(self):
        t = run(image_from_words([ADDI(0, 0, 99), ECALL()]))
        self.assertEqual(final(t)["x1"], 0)
        # x0 stays 0 (it's not even in the observable set beyond x1..x31)

    def test_sub_negative_wraps_64bit(self):
        # x1 = 5; x2 = 7; x3 = x1 - x2 = -2 == 2^64 - 2
        prog = [ADDI(1, 0, 5), ADDI(2, 0, 7), SUB(3, 1, 2), ECALL()]
        t = run(image_from_words(prog))
        self.assertEqual(final(t)["x3"], (1 << 64) - 2)

    def test_slli_shift(self):
        prog = [ADDI(1, 0, 1), SLLI(2, 1, 10), ECALL()]
        t = run(image_from_words(prog))
        self.assertEqual(final(t)["x2"], 1 << 10)

    def test_load_store_roundtrip(self):
        # store x1 to [x5+0], load it back into x6. x5 points past the code.
        base_data = 0x400
        prog = [
            ADDI(1, 0, 1234 & 0x7FF),  # x1 = small value
            ADDI(5, 0, 0),
            # set x5 = base_data via two steps (no LUI needed for 0x400)
            ADDI(5, 5, base_data),
            SD(1, 5, 0),
            LD(6, 5, 0),
            ECALL(),
        ]
        t = run(image_from_words(prog))
        self.assertEqual(final(t)["x6"], final(t)["x1"])

    def test_loop_countdown(self):
        # x1 = 3; loop: x1 -= 1; if x1 != 0 branch back; ecall
        prog = [
            ADDI(1, 0, 3),         # 0x00
            ADDI(1, 1, -1),        # 0x04  loop body
            BNE(1, 0, -4),         # 0x08  branch back to 0x04 if x1 != 0
            ECALL(),               # 0x0c
        ]
        t = run(image_from_words(prog))
        self.assertEqual(final(t)["x1"], 0)
        self.assertTrue(final(t)["halted"])

    def test_deterministic(self):
        prog = [ADDI(1, 0, 5), ADD(3, 1, 1), ECALL()]
        img = image_from_words(prog)
        self.assertEqual(run(img), run(image_from_words(prog)))

    def test_unsupported_opcode_aborts(self):
        # 0x2b is a valid encoding space we don't implement (AMO etc.)
        with self.assertRaises(Unsupported):
            run(image_from_words([0x0000002B, ECALL()]))


if __name__ == "__main__":
    unittest.main()
