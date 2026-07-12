"""Shadow-mode ledger accumulation (tools/shadow_ledger.py) — SCALING.md §12.8.
Folds shadow trials of autonomy into the ledger autonomy.attained_level reads.
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


def _manifest(changed, pairs=(), shared=False, lane=None):
    return {
        "scope": {"changed_files": list(changed), "touched_pairs": list(pairs),
                  "touched_languages": [], "touches_shared_layer": shared,
                  "touches_protected": []},
        "verdict": {"measurement_errors": [], "determinism_failures": [],
                    "negative_control_failures": [], "shared_lane": lane,
                    "shared_non_additive": []},
    }


def _entry(cls="independent", shadow="EXECUTE", human="merged", outcome=None,
           nc=False, fanout=None):
    return {"ref": "r", "class": cls, "shadow_execution": shadow,
            "human_action": human, "outcome": outcome,
            "negative_control_fired": nc, "fanout": fanout}


class TestFold(unittest.TestCase):
    def setUp(self):
        self.sl = _load("shadow_ledger")
        self.au = _load("autonomy")

    def test_execute_and_merged_is_an_agreement(self):
        g = self.sl.fold(self.au.Ledger(), _entry(), self.au)
        self.assertEqual(g.independent_shadow_seen, 1)
        self.assertEqual(g.independent_shadow_disagreements, 0)

    def test_execute_but_not_merged_is_a_disagreement(self):
        g = self.sl.fold(self.au.Ledger(), _entry(human="rejected"), self.au)
        self.assertEqual(g.independent_shadow_seen, 1)
        self.assertEqual(g.independent_shadow_disagreements, 1)

    def test_propose_is_not_a_trial(self):
        g = self.sl.fold(self.au.Ledger(), _entry(shadow="PROPOSE"), self.au)
        self.assertEqual(g.independent_shadow_seen, 0)

    def test_escalate_class_none_is_not_a_trial(self):
        g = self.sl.fold(self.au.Ledger(), _entry(cls=None), self.au)
        self.assertEqual(g.independent_shadow_seen, 0)

    def test_negative_control_fired_counts(self):
        g = self.sl.fold(self.au.Ledger(), _entry(nc=True), self.au)
        self.assertEqual(g.negative_control_catches, 1)

    def test_fanout_regression_counts(self):
        g = self.sl.fold(self.au.Ledger(),
                         _entry(cls="fanout", fanout="reject-regression"), self.au)
        self.assertEqual(g.fanout_regressions_caught, 1)

    def test_revert_counts(self):
        g = self.sl.fold(self.au.Ledger(), _entry(outcome="reverted"), self.au)
        self.assertEqual(g.reverts_in_window, 1)

    def test_lane_a_shared_routes_to_its_bucket(self):
        g = self.sl.fold(self.au.Ledger(), _entry(cls="lane_a_shared"), self.au)
        self.assertEqual(g.additive_shared_shadow_seen, 1)


class TestAccumulate(unittest.TestCase):
    def setUp(self):
        self.sl = _load("shadow_ledger")
        self.au = _load("autonomy")

    def test_a_clean_stream_earns_L1(self):
        # 20 clean independent trials + 5 negative-control catches -> L1
        entries = [_entry(nc=(i < 5)) for i in range(20)]
        g = self.sl.accumulate(entries, au=self.au)
        self.assertEqual(g.independent_shadow_seen, 20)
        self.assertEqual(g.negative_control_catches, 5)
        self.assertEqual(self.au.attained_level(g), self.au.L1)

    def test_one_disagreement_holds_L0(self):
        entries = [_entry(nc=(i < 5)) for i in range(20)]
        entries.append(_entry(human="rejected"))     # a would-be false-go
        g = self.sl.accumulate(entries, au=self.au)
        self.assertEqual(self.au.attained_level(g), self.au.L0)

    def test_accumulate_extends_a_base_ledger(self):
        base = self.au.Ledger(independent_shadow_seen=10, negative_control_catches=5)
        g = self.sl.accumulate([_entry() for _ in range(10)], base=base, au=self.au)
        self.assertEqual(g.independent_shadow_seen, 20)
        self.assertEqual(self.au.attained_level(g), self.au.L1)


class TestEntryFromPlan(unittest.TestCase):
    def setUp(self):
        self.sl = _load("shadow_ledger")
        self.au = _load("autonomy")
        self.mq = _load("merge_queue")
        self.pairs = {"riscv-btor2": {"source": "riscv", "target": "btor2"}}

    def test_independent_plan_entry_shadows_execute(self):
        c = self.mq.Candidate.from_manifest(
            "widen", _manifest(["gurdy/pairs/riscv_btor2/t.py"], pairs=["riscv-btor2"]))
        plan = self.mq.build_plan([c], self.pairs)
        e = self.sl.entry_from_plan(plan, "widen", c, human_action="merged",
                                    negative_control_fired=True, au=self.au)
        self.assertEqual(e["class"], "independent")
        self.assertEqual(e["shadow_execution"], self.au.EXECUTE)

    def test_escalate_plan_entry_is_not_a_trial(self):
        # a protected-instrument change escalates -> class None, PROPOSE
        m = _manifest(["gurdy/languages/riscv/inventory.py"], shared=True, lane="A")
        m["scope"]["touches_protected"] = ["gurdy/languages/riscv/inventory.py"]
        c = self.mq.Candidate.from_manifest("prot", m)
        plan = self.mq.build_plan([c], self.pairs)
        e = self.sl.entry_from_plan(plan, "prot", c, human_action="merged", au=self.au)
        self.assertIsNone(e["class"])
        g = self.sl.fold(self.au.Ledger(), e, self.au)
        self.assertEqual(g.independent_shadow_seen, 0)


class TestProgress(unittest.TestCase):
    def setUp(self):
        self.sl = _load("shadow_ledger")
        self.au = _load("autonomy")

    def test_progress_reports_gaps(self):
        g = self.au.Ledger(negative_control_catches=5, independent_shadow_seen=12)
        p = self.sl.progress(g, self.au)
        self.assertEqual(p["attained_level"], self.au.L0)   # 12 < 20
        l1 = p["rungs"][self.au.L1]
        self.assertTrue(l1["negative_control_catches"]["met"])
        self.assertFalse(l1["independent_shadow"]["met"])
        self.assertEqual(l1["independent_shadow"]["need"], 20)


if __name__ == "__main__":
    unittest.main()
