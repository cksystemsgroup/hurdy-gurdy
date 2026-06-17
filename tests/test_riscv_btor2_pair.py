"""riscv-btor2 tests: the commuting square holds across the RV64I integer set
(validated against the shared RISC-V interpreter via the framework oracle),
the translator is deterministic and emits canonical BTOR2, and out-of-scope
instructions (M-extension) hard-abort.

RV64I encoders are test-local.
"""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import list_pairs
from gurdy.languages.btor2 import from_text, to_text
from gurdy.languages.riscv.interp import image_from_words
from gurdy.pairs.riscv_btor2 import square, translate


# --- RV64I encoders --------------------------------------------------------
def r(op, rd, f3, rs1, rs2, f7):
    return ((f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op) & 0xFFFFFFFF


def i(op, rd, f3, rs1, imm):
    return (((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op) & 0xFFFFFFFF


def s(op, f3, rs1, rs2, imm):
    imm &= 0xFFF
    return (((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | op) & 0xFFFFFFFF


def bt(f3, rs1, rs2, imm):
    imm &= 0x1FFF
    return (
        (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15)
        | (f3 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | 0x63
    ) & 0xFFFFFFFF


def u(op, rd, val):
    return ((val & 0xFFFFF000) | (rd << 7) | op) & 0xFFFFFFFF


def jal(rd, off):
    off &= 0x1FFFFF
    imm = (((off >> 20) & 1) << 31) | (((off >> 1) & 0x3FF) << 21) | (((off >> 11) & 1) << 20) | (((off >> 12) & 0xFF) << 12)
    return (imm | (rd << 7) | 0x6F) & 0xFFFFFFFF


ADDI = lambda d, a, im: i(0x13, d, 0, a, im)       # noqa: E731
SLTI = lambda d, a, im: i(0x13, d, 2, a, im)       # noqa: E731
XORI = lambda d, a, im: i(0x13, d, 4, a, im)       # noqa: E731
SLLI = lambda d, a, sh: i(0x13, d, 1, a, sh)       # noqa: E731
SRLI = lambda d, a, sh: i(0x13, d, 5, a, sh)       # noqa: E731
SRAI = lambda d, a, sh: i(0x13, d, 5, a, 0x400 | sh)  # noqa: E731
ADDIW = lambda d, a, im: i(0x1B, d, 0, a, im)      # noqa: E731
SLLIW = lambda d, a, sh: i(0x1B, d, 1, a, sh)      # noqa: E731
ADD = lambda d, a, c: r(0x33, d, 0, a, c, 0x00)    # noqa: E731
SUB = lambda d, a, c: r(0x33, d, 0, a, c, 0x20)    # noqa: E731
SLT = lambda d, a, c: r(0x33, d, 2, a, c, 0x00)    # noqa: E731
SLTU = lambda d, a, c: r(0x33, d, 3, a, c, 0x00)   # noqa: E731
AND = lambda d, a, c: r(0x33, d, 7, a, c, 0x00)    # noqa: E731
SRL = lambda d, a, c: r(0x33, d, 5, a, c, 0x00)    # noqa: E731
SRA = lambda d, a, c: r(0x33, d, 5, a, c, 0x20)    # noqa: E731
ADDW = lambda d, a, c: r(0x3B, d, 0, a, c, 0x00)   # noqa: E731
MUL = lambda d, a, c: r(0x33, d, 0, a, c, 0x01)    # M-extension (unsupported)  # noqa: E731
LUI = lambda d, val: u(0x37, d, val)               # noqa: E731
SW = lambda rs2, rs1, off: s(0x23, 2, rs1, rs2, off)  # noqa: E731
SB = lambda rs2, rs1, off: s(0x23, 0, rs1, rs2, off)  # noqa: E731
LW = lambda d, rs1, off: i(0x03, d, 2, rs1, off)   # noqa: E731
LB = lambda d, rs1, off: i(0x03, d, 0, rs1, off)   # noqa: E731
LBU = lambda d, rs1, off: i(0x03, d, 4, rs1, off)  # noqa: E731
BNE = lambda a, c, off: bt(1, a, c, off)           # noqa: E731
ECALL = lambda: i(0x73, 0, 0, 0, 0)                # noqa: E731


def prog(words, init_regs=None):
    return {"image": image_from_words(words), "init_regs": init_regs or {}}


def ok(self, words, init_regs=None):
    report = square(prog(words, init_regs))
    self.assertTrue(report.ok, msg=str(report.divergence))


class TestRiscvBtor2Wide(unittest.TestCase):
    def test_registered(self):
        self.assertIn("riscv-btor2", list_pairs())

    def test_arithmetic(self):
        ok(self, [ADDI(1, 0, 5), ADDI(2, 0, 37), ADD(3, 1, 2), SUB(4, 2, 1), ECALL()])

    def test_logic_and_shifts(self):
        ok(self, [ADDI(1, 0, 0xF), SLLI(2, 1, 4), SRLI(3, 2, 2),
                  XORI(4, 1, -1), AND(5, 1, 2), SRA(6, 4, 1), SRL(7, 4, 1), ECALL()])

    def test_comparisons(self):
        ok(self, [ADDI(1, 0, 5), ADDI(2, 0, -3), SLT(3, 2, 1), SLTU(4, 2, 1),
                  SLTI(5, 2, 0), ECALL()])

    def test_word_ops_sign_extend(self):
        ok(self, [ADDI(1, 0, 1), SLLIW(2, 1, 31), ADDW(3, 2, 2), ADDIW(4, 2, 1), ECALL()])

    def test_lui(self):
        ok(self, [LUI(1, 0x80000000), LUI(2, 0x12345000), ADD(3, 1, 2), ECALL()])

    def test_branch_countdown_loop(self):
        # x1 = 3; loop: x1 -= 1; bne x1, x0, loop; ecall  -> x1 == 0
        ok(self, [ADDI(1, 0, 3), ADDI(1, 1, -1), BNE(1, 0, -4), ECALL()])

    def test_jal_skips(self):
        # jal x1, +8 (skip the ADDI x2); then ADDI x3; ecall
        ok(self, [jal(1, 8), ADDI(2, 0, 99), ADDI(3, 0, 7), ECALL()])

    def test_load_store_word(self):
        ok(self, [ADDI(5, 0, 0x100), ADDI(1, 0, 123), SW(1, 5, 0), LW(6, 5, 0), ECALL()])

    def test_byte_store_sign_vs_unsigned_load(self):
        ok(self, [ADDI(5, 0, 0x100), ADDI(1, 0, -1), SB(1, 5, 0),
                  LB(6, 5, 0), LBU(7, 5, 0), ECALL()])

    def test_initial_registers(self):
        ok(self, [ADD(3, 1, 2), ECALL()], init_regs={1: 100, 2: 23})

    def test_translate_deterministic(self):
        p = prog([ADDI(1, 0, 5), ADD(2, 1, 1), SW(1, 0, 0), ECALL()])
        self.assertEqual(translate(p), translate(p))

    def test_artifact_roundtrips_as_btor2(self):
        art = translate(prog([ADDI(1, 0, 5), SW(1, 0, 0x10), LW(2, 0, 0x10), ECALL()])).decode()
        self.assertEqual(to_text(from_text(art)), art)

    def test_m_extension_aborts(self):
        with self.assertRaises(Unsupported):
            translate(prog([MUL(3, 1, 2), ECALL()]))


if __name__ == "__main__":
    unittest.main()
