"""The abstraction benchmark's authored block (tools/abstraction_bench.py;
the paper's tab:abstraction): free-set havoc preserves verdicts while the
bridged artifact shrinks, the CEGAR loop converges to the advisor's free
set with every spurious counterexample caught by source replay, a true
counterexample is believed only after replay, and the free-set boundary
is sharp. The HWMCC block is network-gated and exercised by the harvest
run, not here; the witness-filtering helper is unit-tested offline."""

import importlib.util
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "abstraction_bench", os.path.join(_ROOT, "tools", "abstraction_bench.py"))
abstraction_bench = importlib.util.module_from_spec(_spec)
sys.modules["abstraction_bench"] = abstraction_bench
_spec.loader.exec_module(abstraction_bench)


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_z3(), "z3 absent")
class TestAuthoredBlock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = abstraction_bench.run_authored()

    def test_free_set_havoc_preserves_the_verdict(self):
        for r in self.report["decoys"]:
            self.assertTrue(r["verdicts_agree"], msg=str(r))
            self.assertTrue(r["transfers"], msg=str(r))

    def test_bridged_artifact_shrinks(self):
        for r in self.report["decoys"]:
            self.assertLess(r["smt_bytes"][1], r["smt_bytes"][0], msg=str(r))

    def test_cegar_converges_to_the_free_set(self):
        c = self.report["cegar"]
        self.assertEqual(c["verdict"], "unreachable", msg=str(c))
        self.assertTrue(c["converged_to_free_set"], msg=str(c))
        self.assertEqual(c["spurious"], 4)   # one per un-havocked rung
        self.assertTrue(c["transfers"])

    def test_true_counterexample_is_replay_confirmed(self):
        t = self.report["true_cex"]
        self.assertEqual(t["verdict"], "reachable")
        self.assertTrue(t["replay_confirms"], msg=str(t))

    def test_free_set_boundary_is_sharp(self):
        # the negative control: one cone state havocked -> spurious reach
        self.assertTrue(self.report["sharp_boundary"]["spurious_as_expected"],
                        msg=str(self.report["sharp_boundary"]))


class TestWitnessFiltering(unittest.TestCase):
    # source: one 1-bit input g driving the bad directly
    _SRC = "1 sort bitvec 1\n2 input 1 g\n3 state 1 s\n4 next 1 3 2\n5 bad 3\n"

    def _wit(self, g: str, extra: str = "") -> str:
        return f"sat\nb0\n@0\n0 {g} g\n{extra}@1\n0 {g} g\n.\n"

    def test_source_input_carries_by_symbol(self):
        hit = abstraction_bench._source_replay_hits_bad(
            self._SRC, self._wit("1"), 2)
        self.assertTrue(hit)
        miss = abstraction_bench._source_replay_hits_bad(
            self._SRC, self._wit("0"), 2)
        self.assertFalse(miss)

    def test_havoc_inputs_are_filtered_out(self):
        # a second witness input with a havoc_ symbol must be ignored,
        # not positionally misbound onto the source's input list
        wit = "sat\nb0\n@0\n0 1 havoc_s\n1 0 g\n@1\n0 1 havoc_s\n1 0 g\n.\n"
        self.assertFalse(abstraction_bench._source_replay_hits_bad(
            self._SRC, wit, 2))


class TestPins(unittest.TestCase):
    def test_slice_is_pinned(self):
        self.assertEqual(len(abstraction_bench.HWMCC), 6)
        for name, meta in abstraction_bench.HWMCC.items():
            self.assertEqual(len(meta["sha256"]), 64, msg=name)
            self.assertIn(meta["expected"], ("reachable", "unreachable"))
        self.assertEqual(len(abstraction_bench.HWMCC_COMMIT), 40)


if __name__ == "__main__":
    unittest.main()
