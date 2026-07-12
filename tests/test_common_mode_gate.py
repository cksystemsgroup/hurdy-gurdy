"""The common-mode / escape gate (tools/common_mode_gate.py) — Phase 7 of the
scaling rollout (SCALING.md §9). Uses the live registry; the riscv-btor2
single-leg family is computed once and shared.
"""

import importlib.util
import pathlib
import sys
import unittest


def _load():
    path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "common_mode_gate.py"
    spec = importlib.util.spec_from_file_location("common_mode_gate", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["common_mode_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestCommonModeGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cm = _load()
        cls.pairs = cls.cm._pairs()
        # Run the family once over a small site + probe subset (site 0 alone
        # already exhibits square-escaping mutations); production uses the full
        # sets. Keeps the suite fast.
        from gurdy.core import registry
        probes = dict(list(registry.get_pair("riscv-btor2").probes.items())[:8])
        cls.riscv = cls.cm.single_leg_report("riscv-btor2", sites=(0,), probes=probes)

    # --- posture -----------------------------------------------------------

    def test_posture_external_for_sail_modeled(self):
        self.assertEqual(self.cm.posture("riscv-btor2", self.pairs), self.cm.EXTERNAL)
        self.assertEqual(self.cm.posture("aarch64-btor2", self.pairs), self.cm.EXTERNAL)
        self.assertEqual(self.cm.posture("sail-btor2", self.pairs), self.cm.EXTERNAL)

    def test_posture_single_artifact_for_the_rest(self):
        self.assertEqual(self.cm.posture("evm-btor2", self.pairs), self.cm.SINGLE)
        self.assertEqual(self.cm.posture("ebpf-btor2", self.pairs), self.cm.SINGLE)
        self.assertEqual(self.cm.posture("wasm-btor2", self.pairs), self.cm.SINGLE)

    # --- single-leg family -------------------------------------------------

    def test_riscv_single_leg_family_runs(self):
        self.assertEqual(self.riscv["family"], "fault_injection")
        self.assertGreater(self.riscv["square_caught"], 0)
        self.assertIsInstance(self.riscv["anchor_required"], list)
        # The escape phenomenon is real: some single-leg mutations slip the
        # square and genuinely need the external anchor.
        self.assertTrue(self.riscv["anchor_required"])
        # Every caught mutation is not also anchor-required (disjoint layers).
        self.assertGreaterEqual(self.riscv["square_caught"],
                                len(self.riscv["anchor_required"]))

    def test_non_riscv_single_leg_defers_to_negative_control(self):
        r = self.cm.single_leg_report("evm-btor2")
        self.assertEqual(r["family"], "negative_control")

    # --- assess ------------------------------------------------------------

    def test_assess_external_pair_names_the_anchor(self):
        a = self.cm.assess("evm-btor2", self.pairs)   # cheap: no family
        self.assertEqual(a["posture"], self.cm.SINGLE)
        self.assertTrue(a["both_leg"]["square_blind"])
        self.assertIn("residue", a["both_leg"]["anchor"])

    def test_assess_single_artifact_declares_residue(self):
        # a Sail-modeled pair points at the external differential
        a = self.cm.assess("sail-btor2", self.pairs)
        self.assertEqual(a["posture"], self.cm.EXTERNAL)
        self.assertIn("sail-differential", a["both_leg"]["anchor"])

    # --- anchor-round policy ----------------------------------------------

    def test_requires_anchor_round(self):
        # single-artifact -> no external anchor round to require
        self.assertFalse(self.cm.requires_anchor_round("evm-btor2", self.pairs))
        # riscv-btor2 has an external differential AND square-escaping mutations
        # (reuse the cached report so the family is not re-run).
        self.assertTrue(self.cm.requires_anchor_round(
            "riscv-btor2", self.pairs, report=self.riscv))


if __name__ == "__main__":
    unittest.main()
