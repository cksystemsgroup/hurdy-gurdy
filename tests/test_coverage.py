"""Coverage-harness tests (BENCHMARKS.md §2): construct coverage against the
spec-derived RV64IM inventory, the typed-unsupported histogram, and the
anti-triviality check (a trivial translator scores low, visibly)."""

import unittest

from gurdy.core.coverage import measure
from gurdy.core.errors import Unsupported
from gurdy.languages.riscv import asm
from gurdy.languages.riscv.interp import image_from_words
from gurdy.pairs.riscv_btor2 import translate
from gurdy.pairs.riscv_btor2.inventory import ALL_PROBES, RV64I_PROBES, coverage


class TestCoverage(unittest.TestCase):
    def test_covers_rv64im(self):
        report = coverage()
        self.assertEqual(report.missing, {})
        self.assertEqual(report.fraction, 1.0)
        self.assertTrue(report.meets(1.0))
        self.assertGreaterEqual(report.total, 60)  # ~51 RV64I + 13 RV64M

    def test_out_of_scope_constructs_are_itemized(self):
        amo = 0x0000202F                                    # A-extension (opcode 0x2f)
        csrrw = (0xC00 << 20) | (1 << 12) | (1 << 7) | 0x73  # SYSTEM funct3=1
        probes = {
            "AMOADD.W": {"image": image_from_words([amo, asm.ecall()]), "init_regs": {}},
            "CSRRW": {"image": image_from_words([csrrw, asm.ecall()]), "init_regs": {}},
        }
        report = measure(translate, probes)
        self.assertEqual(report.fraction, 0.0)
        self.assertEqual(set(report.missing), {"AMOADD.W", "CSRRW"})
        self.assertIn("opcode=0x2f", report.histogram)

    def test_trivial_translator_is_caught(self):
        # a translator that only handles ADDI (and the trailing ECALL) scores
        # low coverage over RV64I -- triviality is visible, not hidden.
        def trivial(program):
            image = program["image"]
            instr = image.load(image.entry, 4)
            if (instr & 0x707F) != 0x13 and instr != asm.ecall():
                raise Unsupported("trivial", "only-addi")
            return b""

        report = measure(trivial, RV64I_PROBES)
        self.assertLess(report.fraction, 0.2)
        self.assertGreater(len(report.missing), 30)

    def test_pair_exposes_probes(self):
        from gurdy.core.registry import get_pair
        self.assertIs(get_pair("riscv-btor2").probes, ALL_PROBES)


if __name__ == "__main__":
    unittest.main()
