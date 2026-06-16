"""riscv-btor2 thin-slice tests: the commuting square holds, the translator
is deterministic, and out-of-scope instructions hard-abort.

The translator is validated against the shared RISC-V interpreter via the
framework's commuting-square oracle (no solver needed). RV64I encoders are
test-local (reused from the interpreter test's style).
"""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import list_pairs
from gurdy.languages.btor2 import from_text, to_text
from gurdy.languages.riscv.interp import image_from_words
from gurdy.pairs.riscv_btor2 import square, translate


def r(opcode, rd, funct3, rs1, rs2, funct7):
    return ((funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode) & 0xFFFFFFFF


def i(opcode, rd, funct3, rs1, imm):
    return (((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode) & 0xFFFFFFFF


ADDI = lambda rd, rs1, imm: i(0x13, rd, 0, rs1, imm)        # noqa: E731
XORI = lambda rd, rs1, imm: i(0x13, rd, 4, rs1, imm)        # noqa: E731
ADD = lambda rd, rs1, rs2: r(0x33, rd, 0, rs1, rs2, 0x00)   # noqa: E731
SUB = lambda rd, rs1, rs2: r(0x33, rd, 0, rs1, rs2, 0x20)   # noqa: E731
AND = lambda rd, rs1, rs2: r(0x33, rd, 7, rs1, rs2, 0x00)   # noqa: E731
OR = lambda rd, rs1, rs2: r(0x33, rd, 6, rs1, rs2, 0x00)    # noqa: E731
ECALL = lambda: i(0x73, 0, 0, 0, 0)                         # noqa: E731
BNE = lambda rs1, rs2, off: 0x00001063                      # placeholder branch (unsupported)  # noqa: E731


def prog(words):
    return {"image": image_from_words(words), "init_regs": {}}


class TestRiscvBtor2Pair(unittest.TestCase):
    def test_registered(self):
        self.assertIn("riscv-btor2", list_pairs())

    def test_square_arith(self):
        # x1=5; x2=37; x3=x1+x2; ecall  -> x3 == 42
        report = square(prog([ADDI(1, 0, 5), ADDI(2, 0, 37), ADD(3, 1, 2), ECALL()]))
        self.assertTrue(report.ok, msg=str(report.divergence))

    def test_square_sub_and_logic(self):
        report = square(prog([
            ADDI(1, 0, 0x2A),
            ADDI(2, 0, 0x0F),
            SUB(3, 1, 2),
            AND(4, 1, 2),
            OR(5, 1, 2),
            XORI(6, 1, -1),   # bitwise not of x1 (xori with -1)
            ECALL(),
        ]))
        self.assertTrue(report.ok, msg=str(report.divergence))

    def test_square_with_initial_regs(self):
        program = {"image": image_from_words([ADD(3, 1, 2), ECALL()]), "init_regs": {1: 100, 2: 23}}
        report = square(program)
        self.assertTrue(report.ok, msg=str(report.divergence))

    def test_translate_deterministic(self):
        p = prog([ADDI(1, 0, 5), ADD(2, 1, 1), ECALL()])
        self.assertEqual(translate(p), translate(p))

    def test_artifact_roundtrips_as_btor2(self):
        # the emitted artifact is canonical BTOR2 (parser/printer round-trip).
        art = translate(prog([ADDI(1, 0, 5), ECALL()])).decode()
        self.assertEqual(to_text(from_text(art)), art)

    def test_unsupported_instruction_aborts(self):
        with self.assertRaises(Unsupported):
            translate(prog([BNE(1, 0, 0), ECALL()]))


if __name__ == "__main__":
    unittest.main()
