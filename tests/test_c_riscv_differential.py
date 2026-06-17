"""The c-riscv cbmc differential: the opaque compile head cross-checked against
an independent C verifier (PATHS.md §3; SOLVERS.md §7).

The verdict/property parsers, the harness builders, and the divergence
classifier are tested hermetically (with an injected checker / reference). The
real cbmc runs are gated on the pinned binary; the full long-path corroboration
additionally needs the toolchain and z3 (DOCKER.md)."""

import shutil
import unittest

from gurdy.core.solver import Verdict
from gurdy.pairs.c_riscv.differential import (
    cbmc_reg_eq,
    cbmc_reg_eq_harness,
    differential,
    ub_classes,
    ub_probe_harness,
)
from gurdy.solvers.cbmc_c import (
    CbmcChecker,
    CbmcUnavailable,
    failed_property_classes,
    find_cbmc,
    parse_verdict,
)


def _gcc():
    return shutil.which("riscv64-unknown-elf-gcc")


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


class _FakeCbmc:
    """A checker stub: ``decide`` answers the reg_eq query, ``run`` returns the
    canned UB-probe output."""

    def __init__(self, verdict: Verdict, ub_output: str = ""):
        self._v, self._ub = verdict, ub_output

    def decide(self, source, extra_args=()):
        return self._v

    def run(self, source, extra_args=()):
        return self._ub


class TestParsers(unittest.TestCase):
    def test_parse_verdict(self):
        self.assertEqual(parse_verdict("...\nVERIFICATION FAILED\n"), Verdict.REACHABLE)
        self.assertEqual(parse_verdict("VERIFICATION SUCCESSFUL\n"), Verdict.UNREACHABLE)
        self.assertEqual(parse_verdict("nothing here\n"), Verdict.UNKNOWN)

    def test_failed_property_classes(self):
        out = ("[main.overflow.1] line 1 arithmetic overflow on signed + in a + 1: FAILURE\n"
               "[main.undefined-shift.2] line 2 shift distance too large: FAILURE\n"
               "[main.division-by-zero.1] line 3 division by zero: SUCCESS\n"
               "[main.assertion.1] reg_eq: SUCCESS\n")
        self.assertEqual(failed_property_classes(out), {"overflow", "undefined-shift"})

    def test_harness_shapes(self):
        self.assertIn("__CPROVER_assert", cbmc_reg_eq_harness("5*8+7", 47))
        self.assertIn("!= 47L", cbmc_reg_eq_harness("5*8+7", 47))
        self.assertNotIn("__CPROVER_assert", ub_probe_harness("a/b"))


class TestClassifier(unittest.TestCase):
    """All four divergence verdicts, with an injected checker + reference."""

    def test_clean_agreement(self):
        d = differential("x", 1, reference=Verdict.REACHABLE, checker=_FakeCbmc(Verdict.REACHABLE))
        self.assertEqual(d["status"], "agree")
        self.assertFalse(d["fault"])

    def test_agreement_under_riscv_definition(self):
        ub = "[main.overflow.1] arithmetic overflow on signed +: FAILURE\n"
        d = differential("x", 1, reference=Verdict.REACHABLE,
                         checker=_FakeCbmc(Verdict.REACHABLE, ub))
        self.assertEqual(d["status"], "agree-under-riscv-definition")
        self.assertEqual(d["ub_classes"], ["overflow"])
        self.assertFalse(d["fault"])

    def test_documented_c_undefined_divergence(self):
        ub = "[main.undefined-shift.1] shift distance too large: FAILURE\n"
        d = differential("x", 1, reference=Verdict.UNREACHABLE,
                         checker=_FakeCbmc(Verdict.REACHABLE, ub))
        self.assertEqual(d["status"], "c-undefined-divergence")
        self.assertFalse(d["fault"])   # documented, not a translator fault

    def test_localized_fault(self):
        # a value disagreement with NO undefined behavior is a real fault
        d = differential("x", 1, reference=Verdict.UNREACHABLE,
                         checker=_FakeCbmc(Verdict.REACHABLE, ""))
        self.assertEqual(d["status"], "localized-fault")
        self.assertTrue(d["fault"])


class TestAvailability(unittest.TestCase):
    def test_missing_cbmc_raises(self):
        checker = CbmcChecker(binary="/nonexistent/cbmc")
        self.assertFalse(checker.available())
        with self.assertRaises(CbmcUnavailable):
            checker.decide("int main(void){return 0;}")


@unittest.skipUnless(find_cbmc(), "cbmc not installed")
class TestRealCbmc(unittest.TestCase):
    def test_reg_eq_decides_concrete_value(self):
        self.assertEqual(cbmc_reg_eq("5*8 + 7", 47), Verdict.REACHABLE)
        self.assertEqual(cbmc_reg_eq("5*8 + 7", 99), Verdict.UNREACHABLE)

    def test_ub_detection(self):
        # the languages/riscv brief's documented C-undefined-but-RISC-V-defined
        # behaviors are flagged by cbmc's UB checks
        self.assertEqual(ub_classes("(int)(-2147483647 - 1) / (int)(-1)"), {"overflow"})
        self.assertEqual(ub_classes("(int)1 << 40"), {"undefined-shift"})
        self.assertEqual(ub_classes("5*8 + 7"), set())

    def test_differential_agreement_real_cbmc(self):
        # real cbmc, injected RISC-V reference (no long path): clean corroboration
        d = differential("5*8 + 7", 47, reference=Verdict.REACHABLE)
        self.assertEqual(d["status"], "agree")


@unittest.skipUnless(find_cbmc() and _gcc() and _z3(), "cbmc / gcc / z3 absent")
class TestLongPathCorroboration(unittest.TestCase):
    def test_cbmc_agrees_with_long_path(self):
        # the third corroboration layer: cbmc on the C source vs the long path
        # (both backend routes) on the lowered program -- they must agree.
        self.assertEqual(differential("5*8 + 7", 47)["status"], "agree")
        self.assertEqual(differential("5*8 + 7", 99)["status"], "agree")


if __name__ == "__main__":
    unittest.main()
