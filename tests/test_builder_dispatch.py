"""The builder-dispatch harness (tools/builder_dispatch.py) — Phase 4 of the
scaling rollout (SCALING.md §12.4). Dogfoods the pieces an orchestrator drives:
the work queue, the per-construct self-verify gate, and the builder brief.
"""

import importlib.util
import pathlib
import sys
import unittest


def _load():
    path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "builder_dispatch.py"
    spec = importlib.util.spec_from_file_location("builder_dispatch", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["builder_dispatch"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestBuilderDispatch(unittest.TestCase):
    def test_queue_lists_partial_pairs(self):
        bd = _load()
        queue = bd.partial_pairs()
        ids = {r["pair"] for r in queue}
        self.assertIn("evm-btor2", ids)              # 86/144 today
        for row in queue:
            self.assertLess(row["covered"], row["total"])
            self.assertEqual(len(row["uncovered"]), row["total"] - row["covered"])

    def test_worklist_matches_coverage_gap(self):
        bd = _load()
        wl = bd.work_list("evm-btor2")
        self.assertEqual(len(wl), 58)
        self.assertIn("AND", wl)
        self.assertIn("XOR", wl)

    def test_self_verify_reports_the_gate(self):
        bd = _load()
        v = bd.self_verify("evm-btor2")
        self.assertEqual(v["conjoined"], [86, 144])
        self.assertTrue(v["determinism_ok"])
        self.assertTrue(v["negative_control_ok"])
        self.assertTrue(v["gate_ok"])

    def test_brief_is_self_contained(self):
        bd = _load()
        brief = bd.build_brief("evm-btor2", ["AND", "OR", "XOR"])
        for needle in ("evm-btor2", "AND, OR, XOR", "translate.py",
                       "inventory.py", "operand-framed", "verify evm-btor2",
                       "must NOT change", "square must pass"):
            self.assertIn(needle, brief, needle)


if __name__ == "__main__":
    unittest.main()
