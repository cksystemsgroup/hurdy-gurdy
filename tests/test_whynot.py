"""``why_not`` — the four-obstacle answerability diagnosis
(core/whynot.py; POTENTIAL.md §1-2 as an API).

Each obstacle is exercised on the real registry: connectivity on SMILES
(whose only route ends at molecular-formula, not a reasoning language),
loss and shape on the riscv->hub routes, cost via a player-supplied
resource-out verdict. The diagnosis is read-only and advisory: it names a
generation target, it registers nothing, and the brief stub says in its
own text that registration is a human act.
"""

import unittest

from gurdy.core import registry
from gurdy.core.solver import Verdict
from gurdy.core.whynot import brief_stub, reasoning_languages, why_not

import gurdy.pairs.btor2_smtlib   # noqa: F401  (registration)
import gurdy.pairs.riscv_btor2    # noqa: F401
import gurdy.pairs.riscv_sail     # noqa: F401
import gurdy.pairs.sail_btor2     # noqa: F401
import gurdy.pairs.btor2_havoc    # noqa: F401  (the registered reduction)
import gurdy.pairs.smiles_formula  # noqa: F401  (hub-disconnected corner)


class TestObstacles(unittest.TestCase):
    def test_reasoning_languages_are_the_declaring_hubs(self):
        hubs = reasoning_languages()
        self.assertIn("btor2", hubs)
        self.assertIn("smtlib", hubs)
        self.assertNotIn("riscv", hubs)
        self.assertNotIn("molecular-formula", hubs)

    def test_connectivity_names_the_missing_edge(self):
        record = why_not("smiles")
        self.assertFalse(record["answerable"])
        self.assertEqual(record["obstacle"], "connectivity")
        target = record["generation_target"]
        self.assertEqual(target["kind"], "pair")
        self.assertEqual(target["from"], "smiles")
        self.assertTrue(target["into_any_of"])
        self.assertNotIn("smiles", target["into_any_of"])
        # the stub is a stub: AGENTS.md §1 fields named, human act stated
        self.assertIn("registration is a human act", record["brief_stub"])
        self.assertIn("Projection", record["brief_stub"])
        self.assertIn("Direction", record["brief_stub"])

    def test_loss_names_the_dropping_head_pairs(self):
        record = why_not("riscv", observables=["pc", "no_such_field"])
        self.assertFalse(record["answerable"])
        self.assertEqual(record["obstacle"], "loss")
        target = record["generation_target"]
        self.assertEqual(target["kind"], "wider-projection")
        self.assertEqual(target["missing_observables"], ["no_such_field"])
        self.assertTrue(set(target["pairs"]) <= {"riscv-btor2", "riscv-sail"})
        self.assertTrue(target["pairs"])

    def test_shape_charted_names_the_native_procedure(self):
        # liveness is charted (core/atlas.py): the demand is the named
        # family on a hub the program already reaches, the known
        # crossing beside it (SYNTHESIS.md §3).
        record = why_not("riscv", observables=["pc"], shape="liveness")
        self.assertFalse(record["answerable"])
        self.assertEqual(record["obstacle"], "shape")
        target = record["generation_target"]
        self.assertEqual(target["kind"], "native-procedure")
        self.assertIn("automata", target["family"])
        self.assertTrue(set(target["attach_to_any_of"])
                        <= {"btor2", "smtlib"})
        self.assertTrue(target["attach_to_any_of"])
        self.assertIn("liveness-to-safety", target["note"])
        declared = record["detail"]["declared_shapes"]
        self.assertIn("reachability", declared["smtlib"])
        self.assertEqual(record["detail"]["atlas"]["status"], "decidable")

    def test_shape_uncharted_names_the_missing_reasoning_language(self):
        # a shape the atlas does not know stays the honest discovery
        # demand — a reasoning language, never a guessed family.
        record = why_not("riscv", observables=["pc"], shape="epistemic-mu")
        self.assertFalse(record["answerable"])
        self.assertEqual(record["obstacle"], "shape")
        self.assertEqual(record["generation_target"]["kind"],
                         "reasoning-language")
        self.assertEqual(record["detail"]["atlas"]["status"], "uncharted")

    def test_cost_names_a_reduction_and_the_registered_dials(self):
        record = why_not("riscv", observables=["pc"], shape="reachability",
                         verdict=Verdict.RESOURCE_OUT)
        self.assertFalse(record["answerable"])
        self.assertEqual(record["obstacle"], "cost")
        target = record["generation_target"]
        self.assertEqual(target["kind"], "reduction")
        self.assertIn("btor2-havoc", target["registered_reductions"])
        self.assertNotIn("spent_reductions", target)  # nothing reported
        self.assertIn("measured_decide", record["detail"])

    def test_cost_advances_past_a_spent_reduction_to_the_charted_family(self):
        # The player reports the one registered dial played and spent:
        # the target advances — reachability is charted, so the demand
        # names the unbounded procedure family behind a solver brief.
        record = why_not("btor2", shape="reachability",
                         verdict=Verdict.RESOURCE_OUT,
                         spent_reductions=["btor2-havoc"])
        self.assertEqual(record["obstacle"], "cost")
        target = record["generation_target"]
        self.assertEqual(target["kind"], "native-procedure")
        self.assertEqual(target["shape"], "reachability")
        self.assertIn("k-induction", target["family"])
        self.assertEqual(target["spent_reductions"], ["btor2-havoc"])
        self.assertIn("btor2", target["attach_to_any_of"])
        self.assertEqual(record["detail"]["spent_reductions"],
                         ["btor2-havoc"])

    def test_cost_spent_but_uncharted_shape_demands_a_new_reduction(self):
        record = why_not("btor2", verdict=Verdict.RESOURCE_OUT,
                         spent_reductions=["btor2-havoc"])
        target = record["generation_target"]
        self.assertEqual(target["kind"], "reduction")
        self.assertEqual(target["registered_reductions"], [])
        self.assertEqual(target["spent_reductions"], ["btor2-havoc"])
        self.assertIn("NEW reduction", target["note"])

    def test_cost_unspent_dial_survives_a_stale_spent_report(self):
        # A reported name that is not a registered reduction on the
        # reachable hubs is not a spent dial: today's target stands.
        record = why_not("btor2", shape="reachability",
                         verdict=Verdict.RESOURCE_OUT,
                         spent_reductions=["no-such-pair"])
        target = record["generation_target"]
        self.assertEqual(target["kind"], "reduction")
        self.assertIn("btor2-havoc", target["registered_reductions"])
        self.assertNotIn("spent_reductions", target)

    def test_answerable_returns_the_feasible_routes(self):
        record = why_not("riscv", observables=["pc"], shape="reachability")
        self.assertTrue(record["answerable"])
        keys = {" -> ".join(e["route"]) for e in record["routes"]}
        self.assertIn("riscv-btor2 -> btor2-smtlib", keys)
        self.assertIn("riscv-sail -> sail-btor2 -> btor2-smtlib", keys)

    def test_obstacle_order_loss_before_shape(self):
        # both loss and shape would fail: loss must be named (it fails first)
        record = why_not("riscv", observables=["no_such_field"],
                         shape="liveness")
        self.assertEqual(record["obstacle"], "loss")

    def test_verdict_does_not_fire_cost_when_statics_fail(self):
        record = why_not("riscv", observables=["no_such_field"],
                         verdict="resource-out")
        self.assertEqual(record["obstacle"], "loss")

    def test_diagnosis_is_read_only(self):
        before = set(registry.list_pairs())
        why_not("smiles")
        why_not("riscv", observables=["pc"], shape="reachability",
                verdict="unknown")
        self.assertEqual(set(registry.list_pairs()), before)

    def test_brief_stub_carries_the_known_fields(self):
        stub = brief_stub("wasm", "btor2", ["stack0"], "reachability")
        self.assertIn("`wasm-btor2`", stub)
        self.assertIn("`stack0`", stub)
        self.assertIn("`reachability`", stub)


if __name__ == "__main__":
    unittest.main()
