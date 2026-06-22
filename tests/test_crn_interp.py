"""Shared CRN interpreter tests (languages/crn): the discrete (Petri-net)
stepper, its determinism, the firing rule, and the text loader.

The interpreter is the source ``I_s`` for ``crn-smtlib`` and must satisfy the
ARCHITECTURE.md §5 conventions (post-step state, projectable observables,
determinism).
"""

import unittest

from gurdy.core.errors import Unsupported  # noqa: F401  (import path sanity)
from gurdy.languages.crn import FiringError, from_text, interpret, step
from gurdy.languages.crn.model import CrnSyntaxError, Network, Reaction

UNI = "species A B\ninit A 3 B 0\nrxn A -> B\n"


class TestCrnLoader(unittest.TestCase):
    def test_parses_species_init_reaction(self):
        net = from_text(UNI)
        self.assertEqual(net.species, ("A", "B"))
        self.assertEqual(net.init_map, {"A": 3, "B": 0})
        self.assertEqual(len(net.reactions), 1)
        self.assertEqual(net.reactions[0].reactants, (("A", 1),))
        self.assertEqual(net.reactions[0].products, (("B", 1),))

    def test_round_trips_text(self):
        net = from_text(UNI)
        # canonical re-print parses back to the same network
        self.assertEqual(from_text(net.to_text()), net)

    def test_comments_and_blank_lines_ignored(self):
        src = "# a network\nspecies A B\n\ninit A 1   # start\nrxn A -> B\n"
        self.assertEqual(from_text(src), from_text("species A B\ninit A 1\nrxn A -> B\n"))

    def test_coefficients_and_multisets(self):
        net = from_text("species A B C\nrxn 2 A + B -> 3 C\n")
        r = net.reactions[0]
        self.assertEqual(r.reactants, (("A", 2), ("B", 1)))
        self.assertEqual(r.products, (("C", 3),))
        self.assertEqual(r.reactant_tokens, 3)
        self.assertEqual(r.product_tokens, 3)

    def test_empty_sides(self):
        self.assertEqual(from_text("species A\nrxn 0 -> A\n").reactions[0].reactants, ())
        self.assertEqual(from_text("species A\nrxn A -> 0\n").reactions[0].products, ())

    def test_undeclared_species_is_syntax_error(self):
        with self.assertRaises(CrnSyntaxError):
            from_text("species A\nrxn A -> Z\n")

    def test_missing_arrow_is_syntax_error(self):
        with self.assertRaises(CrnSyntaxError):
            from_text("species A B\nrxn A B\n")


class TestCrnInterpreter(unittest.TestCase):
    def test_fires_unimolecular_reaction(self):
        trace = interpret(UNI, {"steps": 3, "schedule": [0, 0, 0]})
        self.assertEqual(trace, [{"A": 2, "B": 1}, {"A": 1, "B": 2}, {"A": 0, "B": 3}])

    def test_stutter_preserves_marking(self):
        trace = interpret(UNI, {"steps": 2, "schedule": [None, 0]})
        self.assertEqual(trace, [{"A": 3, "B": 0}, {"A": 2, "B": 1}])

    def test_minus_one_is_a_stutter(self):
        self.assertEqual(
            interpret(UNI, {"steps": 1, "schedule": [-1]}),
            interpret(UNI, {"steps": 1, "schedule": [None]}),
        )

    def test_marking_override(self):
        trace = interpret(UNI, {"marking": {"A": 1, "B": 0}, "steps": 1, "schedule": [0]})
        self.assertEqual(trace, [{"A": 0, "B": 1}])

    def test_post_step_state_and_observables(self):
        # observables are exactly the species names, recorded after each step
        trace = interpret(UNI, {"steps": 1, "schedule": [0]})
        self.assertEqual(set(trace[0].keys()), {"A", "B"})

    def test_disabled_firing_is_rejected(self):
        # A starts at 0: firing A -> B is not enabled
        with self.assertRaises(FiringError):
            interpret(UNI, {"marking": {"A": 0}, "steps": 1, "schedule": [0]})

    def test_out_of_range_reaction_rejected(self):
        with self.assertRaises(FiringError):
            interpret(UNI, {"steps": 1, "schedule": [5]})

    def test_spectator_species_preserved(self):
        net = "species A B C\ninit A 2 B 0 C 7\nrxn A -> B\n"
        trace = interpret(net, {"steps": 1, "schedule": [0]})
        self.assertEqual(trace[0], {"A": 1, "B": 1, "C": 7})

    def test_fires_bimolecular_homo(self):
        # 2 A -> B consumes two A per firing (multiset stoichiometry)
        net = "species A B\ninit A 4 B 0\nrxn 2 A -> B\n"
        trace = interpret(net, {"steps": 2, "schedule": [0, 0]})
        self.assertEqual(trace, [{"A": 2, "B": 1}, {"A": 0, "B": 2}])

    def test_fires_bimolecular_hetero(self):
        # A + B -> C consumes one of each reactant per firing
        net = "species A B C\ninit A 2 B 2 C 0\nrxn A + B -> C\n"
        trace = interpret(net, {"steps": 2, "schedule": [0, 0]})
        self.assertEqual(trace, [{"A": 1, "B": 1, "C": 1}, {"A": 0, "B": 0, "C": 2}])

    def test_bimolecular_enabledness_by_coefficient(self):
        # 2 A -> B needs two A; with A=1 the firing is not enabled
        with self.assertRaises(FiringError):
            interpret("species A B\ninit A 1 B 0\nrxn 2 A -> B\n", {"steps": 1, "schedule": [0]})

    def test_determinism_twice_and_diff(self):
        binding = {"steps": 3, "schedule": [0, None, 0]}
        self.assertEqual(interpret(UNI, binding), interpret(UNI, binding))

    def test_schedule_length_defaults_steps(self):
        # with no explicit steps, the schedule length is k
        trace = step(Network(("A", "B"), (("A", 2),), (Reaction((("A", 1),), (("B", 1),)),)),
                     {"schedule": [0, 0]})
        self.assertEqual(len(trace), 2)


if __name__ == "__main__":
    unittest.main()
