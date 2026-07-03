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
    def test_covers_rv64imc(self):
        report = coverage()
        self.assertEqual(report.missing, {})
        self.assertEqual(report.fraction, 1.0)
        self.assertTrue(report.meets(1.0))
        self.assertGreaterEqual(report.total, 90)  # ~51 RV64I + 13 RV64M + 32 RV64C

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
        # low coverage over RV64I -- triviality is visible, not hidden. It
        # must scan the whole image: probes carry ADDI setup instructions
        # (the distinguishing operands of the hardened inventory), so
        # accepting on the first instruction alone would be a cheat.
        def trivial(program):
            image = program["image"]
            addr, end = image.code_lo, image.code_hi or image.code_lo
            while addr < end:
                instr = image.load(addr, 4)
                if (instr & 0x707F) != 0x13 and instr != asm.ecall():
                    raise Unsupported("trivial", "only-addi")
                addr += 4
            return b""

        report = measure(trivial, RV64I_PROBES)
        self.assertLess(report.fraction, 0.2)
        self.assertGreater(len(report.missing), 30)

    def test_pair_exposes_probes(self):
        from gurdy.core.registry import get_pair
        self.assertIs(get_pair("riscv-btor2").probes, ALL_PROBES)


class TestConjoinedCoverage(unittest.TestCase):
    """Definition 4.6's conjunction: covered means accepted AND faithful.

    Acceptance-only measurement is gamed by unsoundness (accept everything,
    translate it wrongly); the conjoined measurement runs the pair's square
    oracle on every accepted probe, so an accepted-but-wrong probe lands in
    ``unfaithful`` — localized to its first divergence — and is NOT covered.
    """

    def test_accepted_but_unfaithful_is_not_covered(self):
        class FakeResult:
            def __init__(self, ok):
                self.ok = ok
                self.divergence = None

        probes = {"GOOD": 1, "WRONG": 2, "OUT": 3}

        def translate(p):
            if p == 3:
                raise Unsupported("fake", "out-of-scope")
            return b"artifact"

        report = measure(translate, probes,
                         faithful=lambda p: FakeResult(p == 1))
        self.assertEqual(report.covered, {"GOOD"})
        self.assertEqual(set(report.missing), {"OUT"})
        self.assertEqual(set(report.unfaithful), {"WRONG"})
        self.assertTrue(report.conjoined)
        self.assertAlmostEqual(report.fraction, 1 / 3)

    def test_riscv_pairs_conjoin_on_language_inventory(self):
        # Both RISC-V-headed pairs measure the conjunction over the SAME
        # language-owned RV64IMC inventory (one yardstick, Definition 4.6).
        from gurdy.core.registry import get_pair
        from gurdy.languages.riscv.inventory import ALL_PROBES as LANG
        import gurdy.pairs.riscv_sail  # noqa: F401 (registers the pair)
        for pid in ("riscv-btor2", "riscv-sail"):
            pair = get_pair(pid)
            self.assertIs(pair.probes, LANG)
            self.assertIsNotNone(pair.square)
        self.assertEqual(len(LANG), 96)

    def test_taken_jump_probes_square_after_off_code_halt_fix(self):
        # I21: taken jumps whose target leaves the code got stuck not-halted
        # in the BTOR2 model while the reference interpreter halts on a fetch
        # miss. The square (hence the conjunction) must pass on them now.
        from gurdy.pairs.riscv_btor2 import square
        for name in ("JAL", "BEQ", "BGE", "C.J", "C.BEQZ"):
            self.assertTrue(square(ALL_PROBES[name]).ok, name)

    def test_riscv_sail_square_sees_initial_memory(self):
        # I20: riscv-sail dropped the program's initial memory, so loads from
        # initialized addresses read 0 on the Sail route. The artifact now
        # carries ``mem`` and the load-family squares pass.
        from gurdy.pairs.riscv_sail import square
        for name in ("LB", "LH", "LW", "LD", "LBU", "LHU", "LWU"):
            self.assertTrue(square(ALL_PROBES[name]).ok, name)


if __name__ == "__main__":
    unittest.main()
