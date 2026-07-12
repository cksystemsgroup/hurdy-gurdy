"""Graduating autonomy (tools/autonomy.py) — the propose→autonomous ladder
(SCALING.md §12.6). Pure engine, git-free.
"""

import importlib.util
import pathlib
import sys
import unittest


def _load(name):
    path = pathlib.Path(__file__).resolve().parent.parent / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _manifest(changed, pairs=(), shared=False, protected=(), lane=None):
    return {
        "scope": {"changed_files": list(changed), "touched_pairs": list(pairs),
                  "touched_languages": [], "touches_shared_layer": shared,
                  "touches_protected": list(protected)},
        "verdict": {"measurement_errors": [], "determinism_failures": [],
                    "negative_control_failures": [], "shared_lane": lane,
                    "shared_non_additive": []},
    }


class TestAttainedLevel(unittest.TestCase):
    def setUp(self):
        self.au = _load("autonomy")

    def test_empty_ledger_is_L0(self):
        self.assertEqual(self.au.attained_level(self.au.Ledger()), self.au.L0)

    def test_L1_earned(self):
        g = self.au.Ledger(negative_control_catches=5, independent_shadow_seen=20)
        self.assertEqual(self.au.attained_level(g), self.au.L1)

    def test_L1_withheld_on_a_disagreement(self):
        g = self.au.Ledger(negative_control_catches=5, independent_shadow_seen=20,
                           independent_shadow_disagreements=1)
        self.assertEqual(self.au.attained_level(g), self.au.L0)

    def test_L1_withheld_on_vacuous_control(self):
        # the negative control has never fired -> not proven non-vacuous
        g = self.au.Ledger(negative_control_catches=0, independent_shadow_seen=99)
        self.assertEqual(self.au.attained_level(g), self.au.L0)

    def test_L2_earned(self):
        g = self.au.Ledger(negative_control_catches=5, independent_shadow_seen=20,
                           additive_shared_shadow_seen=15)
        self.assertEqual(self.au.attained_level(g), self.au.L2)

    def test_L3_requires_fanout_to_have_caught_real_regressions(self):
        # everything but the fan-out non-vacuity -> capped at L2
        g = self.au.Ledger(negative_control_catches=5, independent_shadow_seen=20,
                           additive_shared_shadow_seen=15,
                           fanout_shadow_seen=10, fanout_regressions_caught=0)
        self.assertEqual(self.au.attained_level(g), self.au.L2)
        g.fanout_regressions_caught = 3
        self.assertEqual(self.au.attained_level(g), self.au.L3)

    def test_kill_switch_collapses_to_L0(self):
        g = self.au.Ledger(negative_control_catches=9, independent_shadow_seen=99,
                           additive_shared_shadow_seen=99, fanout_shadow_seen=99,
                           fanout_regressions_caught=9, reverts_in_window=1)
        self.assertEqual(self.au.attained_level(g), self.au.L0)


class TestExecutionFor(unittest.TestCase):
    def setUp(self):
        self.au = _load("autonomy")

    def _mode(self, flags, level):
        return self.au.execution_for(flags, level)[0]

    def test_reject_never_merges(self):
        self.assertEqual(self._mode({"kind": self.au.REJECT}, self.au.L3),
                         self.au.REJECT)

    def test_escalate_is_always_proposed(self):
        self.assertEqual(self._mode({"kind": self.au.ESCALATE}, self.au.L3),
                         self.au.PROPOSE)

    def test_protected_is_always_proposed(self):
        f = {"kind": self.au.MERGE, "independent": True, "touches_protected": True}
        self.assertEqual(self._mode(f, self.au.L3), self.au.PROPOSE)

    def test_independent_graduates_at_L1(self):
        f = {"kind": self.au.MERGE, "independent": True}
        self.assertEqual(self._mode(f, self.au.L0), self.au.PROPOSE)
        self.assertEqual(self._mode(f, self.au.L1), self.au.EXECUTE)

    def test_lane_a_shared_graduates_at_L2(self):
        f = {"kind": self.au.MERGE, "lane_a_shared": True, "anchor_resolved": True}
        self.assertEqual(self._mode(f, self.au.L1), self.au.PROPOSE)
        self.assertEqual(self._mode(f, self.au.L2), self.au.EXECUTE)

    def test_unconfirmed_anchor_holds_even_at_high_level(self):
        f = {"kind": self.au.MERGE, "lane_a_shared": True, "anchor_resolved": False}
        self.assertEqual(self._mode(f, self.au.L3), self.au.PROPOSE)

    def test_fanout_graduates_at_L3_only_when_accepted(self):
        accepted = {"kind": self.au.FAN_OUT, "fanout_accepts": True, "anchor_resolved": True}
        self.assertEqual(self._mode(accepted, self.au.L2), self.au.PROPOSE)
        self.assertEqual(self._mode(accepted, self.au.L3), self.au.EXECUTE)
        rejected = {"kind": self.au.FAN_OUT, "fanout_accepts": False}
        self.assertEqual(self._mode(rejected, self.au.L3), self.au.PROPOSE)


class TestAnnotateIntegration(unittest.TestCase):
    def setUp(self):
        self.au = _load("autonomy")
        self.mq = _load("merge_queue")

    def test_annotate_marks_independent_execute_at_L1(self):
        pairs = {"riscv-btor2": {"source": "riscv", "target": "btor2"}}
        indep = self.mq.Candidate.from_manifest(
            "widen", _manifest(["gurdy/pairs/riscv_btor2/t.py"], pairs=["riscv-btor2"]))
        shared = self.mq.Candidate.from_manifest(
            "add", _manifest(["gurdy/languages/riscv/interp.py"], shared=True, lane="A"))
        plan = self.mq.build_plan([indep, shared], pairs)
        g = self.au.Ledger(negative_control_catches=5, independent_shadow_seen=20)  # L1
        self.au.annotate(plan, [indep, shared], g)
        self.assertEqual(plan["autonomy_level"], self.au.L1)
        # independent auto-executes; the Lane-A shared change waits for L2
        self.assertEqual(plan["decisions"]["widen"]["execution"], self.au.EXECUTE)
        self.assertEqual(plan["decisions"]["add"]["execution"], self.au.PROPOSE)

    def test_annotate_default_ledger_proposes_everything(self):
        pairs = {"riscv-btor2": {"source": "riscv", "target": "btor2"}}
        indep = self.mq.Candidate.from_manifest(
            "widen", _manifest(["gurdy/pairs/riscv_btor2/t.py"], pairs=["riscv-btor2"]))
        plan = self.mq.build_plan([indep], pairs)
        self.au.annotate(plan, [indep], self.au.Ledger())
        self.assertEqual(plan["autonomy_level"], self.au.L0)
        self.assertEqual(plan["decisions"]["widen"]["execution"], self.au.PROPOSE)


if __name__ == "__main__":
    unittest.main()
