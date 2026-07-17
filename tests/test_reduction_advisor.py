"""The reduction advisor (languages/btor2/coi.py): cone of influence over
bads *and constraints*, the free havoc set with its executable
zero-precision-loss lemma, the farthest-first refinement ladder, and
interval seeds as falsifiable candidates.

The lemma test is the load-bearing one: havocking every free state
through the real ``btor2-havoc`` pair and driving the fresh inputs with
arbitrary values must leave the question's signal byte-identical on
every run — the advisor's central claim, executed rather than asserted.
"""

import unittest

from gurdy.languages.btor2.build import Builder
from gurdy.languages.btor2.coi import cone_of_influence, suggest_reduction
from gurdy.languages.btor2.eval import interpret
from gurdy.languages.btor2.model import from_text

from gurdy.pairs.btor2_havoc import translate as havoc_translate
from gurdy.pairs.btor2_havoc.translate import havoc_plan


def _two_counters():
    """Counter ``a`` drives the bad; counter ``idle`` is independent."""
    b = Builder()
    a = b.state(4, "a")
    b.init(a, b.zero(4))
    b.next(a, b.op2("add", 4, a, b.one(4)))
    idle = b.state(4, "idle")
    b.init(idle, b.zero(4))
    b.next(idle, b.op2("add", 4, idle, b.one(4)))
    b.bad(b.op2("eq", 1, a, b.constd(4, 3)))
    return b.to_text()


def _chain():
    """s0 feeds s1 feeds s2; the bad reads s2 only."""
    b = Builder()
    s0 = b.state(4, "s0")
    s1 = b.state(4, "s1")
    s2 = b.state(4, "s2")
    b.init(s0, b.zero(4))
    b.init(s1, b.zero(4))
    b.init(s2, b.zero(4))
    b.next(s0, b.op2("add", 4, s0, b.one(4)))
    b.next(s1, s0)
    b.next(s2, s1)
    b.bad(b.op2("eq", 1, s2, b.constd(4, 2)))
    return b.to_text()


class TestConeOfInfluence(unittest.TestCase):
    def test_independent_state_is_outside_the_cone(self):
        sys = from_text(_two_counters())
        dist = cone_of_influence(sys)
        labels = {(n.symbol): d for n in sys.states()
                  for sid, d in dist.items() if n.id == sid}
        self.assertEqual(labels, {"a": 0})

    def test_chain_distances_and_ladder_order(self):
        report = suggest_reduction(_chain(), samples=0)
        self.assertEqual(report["cone"], {"s0": 2, "s1": 1, "s2": 0})
        self.assertEqual(report["refinement_ladder"], ["s0", "s1", "s2"])
        self.assertEqual(report["free_havoc"], [])

    def test_constraint_support_is_always_in_the_cone(self):
        b = Builder()
        a = b.state(4, "a")
        b.init(a, b.zero(4))
        b.next(a, b.op2("add", 4, a, b.one(4)))
        idle = b.state(4, "idle")
        b.init(idle, b.zero(4))
        b.next(idle, b.op2("add", 4, idle, b.one(4)))
        b.constraint(b.op2("ult", 1, idle, b.constd(4, 9)))
        b.bad(b.op2("eq", 1, a, b.constd(4, 3)))
        report = suggest_reduction(b.to_text(), samples=0)
        # idle gates run validity: havocking it is NOT free
        self.assertIn("idle", report["cone"])
        self.assertEqual(report["free_havoc"], [])

    def test_array_states_never_suggested_for_havoc(self):
        b = Builder()
        a = b.state(4, "a")
        b.init(a, b.zero(4))
        b.next(a, b.op2("add", 4, a, b.one(4)))
        mem = b.state_array(4, 8, "mem")
        b.next_array(mem, mem)
        b.bad(b.op2("eq", 1, a, b.constd(4, 3)))
        report = suggest_reduction(b.to_text(), samples=0)
        self.assertEqual(report["free_havoc"], [])
        self.assertEqual(report["free_array_states"], ["mem"])


class TestFreeSetLemma(unittest.TestCase):
    def test_havocking_the_free_set_never_moves_the_question(self):
        text = _two_counters()
        report = suggest_reduction(text, samples=0)
        self.assertEqual(report["free_havoc"], ["idle"])
        program = {"system": text, "havoc": tuple(report["free_havoc"])}
        artifact = havoc_translate(program)
        _sys, _text, plan = havoc_plan(program)
        (state, input_id, _next_id), = plan
        self.assertEqual(state.symbol, "idle")
        src_sys = from_text(text)
        bad_key = f"bad{src_sys.bads()[0].id}"
        steps = 6
        base = [row[bad_key] for row in interpret(text, {"steps": steps})]
        # any drive of the fresh havoc input leaves the bad column identical
        for fill in (0, 7, 15):
            binding = {"steps": steps,
                       "inputs": {c: {input_id: fill} for c in range(steps)}}
            got = [row[bad_key] for row in interpret(artifact, binding)]
            self.assertEqual(got, base, msg=f"fill={fill}")

    def test_cone_state_is_not_free_negative_control(self):
        # havocking the cone state CAN move the question — the advisor must
        # never have suggested it, and the lemma genuinely distinguishes.
        text = _two_counters()
        self.assertNotIn("a", suggest_reduction(text, samples=0)["free_havoc"])
        program = {"system": text, "havoc": ("a",)}
        artifact = havoc_translate(program)
        _sys, _text, plan = havoc_plan(program)
        (state, input_id, _next_id), = plan
        src_sys = from_text(text)
        bad_key = f"bad{src_sys.bads()[0].id}"
        steps = 6
        base = [row[bad_key] for row in interpret(text, {"steps": steps})]
        binding = {"steps": steps,
                   "inputs": {c: {input_id: 0} for c in range(steps)}}
        got = [row[bad_key] for row in interpret(artifact, binding)]
        self.assertNotEqual(got, base)


class TestIntervalSeeds(unittest.TestCase):
    def test_seeds_are_observed_bounds_and_deterministic(self):
        report = suggest_reduction(_two_counters(), k=4, samples=0)
        self.assertEqual(report["interval_seeds"]["a"], [0, 4])
        self.assertEqual(report["interval_seeds"]["idle"], [0, 4])
        again = suggest_reduction(_two_counters(), k=4, samples=0)
        self.assertEqual(report, again)

    def test_seeds_respect_constraint_truncation(self):
        b = Builder()
        a = b.state(4, "a")
        b.init(a, b.zero(4))
        b.next(a, b.op2("add", 4, a, b.one(4)))
        b.constraint(b.op2("ult", 1, a, b.constd(4, 3)))
        b.bad(b.op2("eq", 1, a, b.constd(4, 2)))
        report = suggest_reduction(b.to_text(), k=8, samples=0)
        # the run truncates at the violating row (a == 3): bounds stop there
        self.assertEqual(report["interval_seeds"]["a"], [0, 3])


if __name__ == "__main__":
    unittest.main()
