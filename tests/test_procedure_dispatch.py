"""The solver-synthesis lane, shadow-first (SYNTHESIS.md §7;
tools/procedure_dispatch.py, gurdy/solvers/enum_btor2.py).

* The work list splits native-procedure entries by atlas chartedness:
  charted is workable, uncharted is frontier — never worked.
* The work item carries the hull, the family, the crossing, and the
  human-act discipline; the draft brief deliberately fails validation
  until a human completes it.
* The reference inhabitant — exhaustive bounded enumeration through
  the shared interpreter — clears the lane's gate end to end at
  runs=2, with no external binaries; its declared path budget reads
  resource-out beyond the cap, never a silent answer.
* Under a mandate the kind escalates: in scope, design not mechanical
  — the creative act stays human.
"""

from __future__ import annotations

import os
import sys
import unittest

import gurdy.cli  # noqa: F401  (registers the full graph)
from gurdy.core import registry
from gurdy.core.solver import Verdict
from gurdy.solvers.brief import BRIEFS, validate
from gurdy.solvers.enum_btor2 import EnumBtor2Solver

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
import procedure_dispatch as pd  # noqa: E402
from mandate import Mandate, in_scope, mechanical_design  # noqa: E402


def _records():
    return [
        {"kind": "demand", "ts": 1.0, "origin": "campaign",
         "suite": "toy",
         "question": {"source": "riscv", "observables": ["pc"],
                      "shape": "liveness"},
         "obstacle": "shape",
         "target": {"kind": "native-procedure", "shape": "liveness",
                    "family": "automata-theoretic model checking",
                    "attach_to_any_of": ["btor2", "smtlib"]}},
        {"kind": "demand", "ts": 2.0, "origin": "organic",
         "question": {"source": "riscv", "shape": "epistemic-mu"},
         "obstacle": "shape",
         "target": {"kind": "native-procedure",
                    "shape": "epistemic-mu"}},
        {"kind": "demand", "ts": 3.0, "origin": "campaign",
         "question": {"source": "smiles"},
         "obstacle": "connectivity",
         "target": {"kind": "pair", "from": "smiles",
                    "into_any_of": ["btor2"]}},
    ]


class TestWorkList(unittest.TestCase):
    def test_split_by_chartedness_and_kind(self):
        queue = pd.work_list(_records(), registry.list_pairs())
        self.assertEqual(len(queue["workable"]), 1)
        self.assertEqual(queue["workable"][0]["target"]["shape"],
                         "liveness")
        self.assertEqual(len(queue["frontier"]), 1)
        self.assertEqual(queue["frontier"][0]["target"]["shape"],
                         "epistemic-mu")
        # the pair-kind entry belongs to the other lane

    def test_work_item_carries_the_operator_fields(self):
        queue = pd.work_list(_records(), registry.list_pairs())
        brief = pd.build_brief(queue["workable"][0])
        self.assertIn("registration is a human act", brief)
        self.assertIn("automata-theoretic model checking", brief)
        self.assertIn("liveness-to-safety", brief)      # the crossing
        self.assertIn("'riscv'", brief)                  # the hull
        self.assertIn("runs=2", brief)                   # the gate

    def test_hull_is_the_citing_questions_joined(self):
        queue = pd.work_list(_records(), registry.list_pairs())
        hull = pd.fragment_hull(queue["workable"][0])
        self.assertEqual(hull["shapes"], ["liveness"])
        self.assertEqual(hull["sources"], ["riscv"])
        self.assertEqual(hull["observables"], ["pc"])

    def test_draft_brief_fails_validation_until_human_completes(self):
        queue = pd.work_list(_records(), registry.list_pairs())
        draft = pd.draft_solver_brief(queue["workable"][0])
        problems = validate(draft)
        self.assertTrue(problems)  # the write line, in type form
        self.assertTrue(any("lineage" in p for p in problems))


class TestReferenceInhabitant(unittest.TestCase):
    def test_enum_solver_clears_the_lane_gate(self):
        s = EnumBtor2Solver()
        result = pd.self_verify(lambda t, k: s.decide(t, k),
                                BRIEFS["enum-btor2"])
        self.assertEqual(result["brief_problems"], [])
        self.assertTrue(result["gate"].admitted)
        self.assertTrue(result["admitted"])
        self.assertEqual(result["gate"].runs, 2)  # the strict gate

    def test_budget_reads_resource_out_never_silent(self):
        wide = ("1 sort bitvec 8\n2 input 1 x\n3 sort bitvec 1\n"
                "4 constd 1 7\n5 eq 3 2 4\n6 bad 5\n")
        self.assertEqual(EnumBtor2Solver(max_paths=16).decide(wide, 3),
                         Verdict.RESOURCE_OUT)
        # within budget the same question answers
        self.assertEqual(EnumBtor2Solver(max_paths=512).decide(wide, 0),
                         Verdict.REACHABLE)

    def test_reachable_carries_its_replayable_witness(self):
        s = EnumBtor2Solver()
        text = ("1 sort bitvec 1\n2 input 1 g\n3 constraint 2\n"
                "4 bad 2\n")
        verdict, witness = s.decide_witness(text, 2)
        self.assertEqual(verdict, Verdict.REACHABLE)
        self.assertIsNotNone(witness)
        self.assertIn("inputs", witness)

    def test_invalid_brief_blocks_self_verify(self):
        queue = pd.work_list(_records(), registry.list_pairs())
        draft = pd.draft_solver_brief(queue["workable"][0])
        s = EnumBtor2Solver()
        result = pd.self_verify(lambda t, k: s.decide(t, k), draft)
        self.assertTrue(result["brief_problems"])
        self.assertFalse(result["admitted"])   # even though the gate…
        self.assertTrue(result["gate"].admitted)  # …would admit it


class TestMandateEscalation(unittest.TestCase):
    def test_procedure_kind_escalates_even_in_scope(self):
        queue = pd.work_list(_records(), registry.list_pairs())
        obj = queue["workable"][0]
        mandate = Mandate(name="toy-shapes", benchmark="toy",
                          obstacles=("shape",),
                          languages=("btor2", "smtlib"))
        ok, reason = in_scope(mandate, obj)
        self.assertTrue(ok, msg=reason)
        self.assertIsNone(mechanical_design(obj))  # creative → human

    def test_language_scope_reads_attach_to(self):
        queue = pd.work_list(_records(), registry.list_pairs())
        obj = queue["workable"][0]
        narrow = Mandate(name="narrow", benchmark="toy",
                         obstacles=("shape",), languages=("btor2",))
        ok, reason = in_scope(narrow, obj)
        self.assertFalse(ok)
        self.assertIn("smtlib", reason)


if __name__ == "__main__":
    unittest.main()
