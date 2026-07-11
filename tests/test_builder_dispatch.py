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
        self.assertIn("evm-btor2", ids)              # a partial pair (< 144/144)
        for row in queue:
            self.assertLess(row["covered"], row["total"])
            self.assertEqual(len(row["uncovered"]), row["total"] - row["covered"])

    def test_worklist_matches_coverage_gap(self):
        # Widening-robust: the work-list is exactly the uncovered constructs, a
        # still-uncovered opcode is present and a covered one is absent (does not
        # re-break as evm-btor2 widens).
        bd = _load()
        wl = bd.work_list("evm-btor2")
        v = bd.self_verify("evm-btor2")
        self.assertEqual(len(wl), v["conjoined"][1] - v["conjoined"][0])
        self.assertIn("CALL", wl)                    # still out of scope
        self.assertNotIn("ADD", wl)                  # long covered

    def test_self_verify_reports_the_gate(self):
        # Widening-robust: coverage is over 144, non-trivial, and the gate flags
        # hold — without pinning the exact covered count.
        bd = _load()
        v = bd.self_verify("evm-btor2")
        self.assertEqual(v["conjoined"][1], 144)
        self.assertGreaterEqual(v["conjoined"][0], 91)
        self.assertLessEqual(v["conjoined"][0], 144)
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
