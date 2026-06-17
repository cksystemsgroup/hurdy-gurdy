"""Coverage-harness tests (BENCHMARKS.md §2): construct coverage against the
spec-derived RV64I inventory, the typed-unsupported histogram, and the
anti-triviality check (a trivial translator scores low, visibly)."""

import unittest

from gurdy.core.coverage import measure
from gurdy.core.errors import Unsupported
from gurdy.languages.riscv import asm
from gurdy.languages.riscv.interp import image_from_words
from gurdy.pairs.riscv_btor2 import translate
from gurdy.pairs.riscv_btor2.inventory import RV64I_PROBES, coverage


class TestCoverage(unittest.TestCase):
    def test_riscv_btor2_covers_full_rv64i(self):
        report = coverage()
        self.assertEqual(report.missing, {})
        self.assertEqual(report.fraction, 1.0)
        self.assertTrue(report.meets(1.0))
        self.assertGreaterEqual(report.total, 45)  # ~50 RV64I constructs

    def test_out_of_scope_constructs_are_itemized(self):
        probes = {
            "MUL": {"image": image_from_words([asm.mul(3, 1, 2), asm.ecall()]), "init_regs": {}},
            "DIVU": {"image": image_from_words([asm.divu(3, 1, 2), asm.ecall()]), "init_regs": {}},
        }
        report = measure(translate, probes)
        self.assertEqual(report.fraction, 0.0)
        self.assertEqual(set(report.missing), {"MUL", "DIVU"})
        # the typed Unsupported construct shows up in the histogram
        self.assertIn("op.funct7=0x01", report.histogram)

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
        self.assertIs(get_pair("riscv-btor2").probes, RV64I_PROBES)


if __name__ == "__main__":
    unittest.main()
