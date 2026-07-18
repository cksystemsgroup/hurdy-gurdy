"""The solver admission gate (SYNTHESIS.md §5; tools/solver_gate.py).

* An honest decider is admitted, with strong flips in both directions.
* Liars are caught from either side: always-reachable dies on the
  unreach canary, the census, and the masked mutants; always-unreachable
  dies on the reach canary and the census.
* An always-abstaining decider fails the canaries — the trivial case
  may not be abstained on — while an honest-but-abstaining-on-census
  decider is admitted (sound-and-slow), its abstentions counted.
* ``runs=2`` catches a verdict-nondeterministic decider.
* The mask mutant is semantically sound: replayed through the shared
  interpreter, a masked reachable system shows no bad.
* Real engines (gated on availability) clear the gate.
"""

from __future__ import annotations

import os
import sys
import unittest

from gurdy.core.solver import Verdict
from gurdy.languages.btor2.witness import corroborate_unreach
from gurdy.solvers.native_btor2 import find_btormc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
import solver_gate  # noqa: E402
from solver_gate import (  # noqa: E402
    CANARY_REACH,
    CANARY_UNREACH,
    bridged_decider,
    default_census,
    force_bad,
    gate,
    mask_bads,
    native_decider,
)

_R, _U, _K = Verdict.REACHABLE, Verdict.UNREACHABLE, Verdict.UNKNOWN


def _truth_table() -> dict[tuple[str, int], Verdict]:
    """Ground truth keyed by ``(text, k)`` — the census reuses one
    system text at two bounds with opposite truths (valid-prefix-reach
    vs bound-scoped-unreach), so the artifact alone is not the
    question; the bound is part of the claim."""
    table = {(CANARY_REACH, 1): _R, (CANARY_UNREACH, 1): _U}
    for e in default_census():
        v = _R if e["truth"] == "reachable" else _U
        table[(e["text"], e["k"])] = v
        if v is _R:
            table[(mask_bads(e["text"]), e["k"])] = _U
        else:
            table[(force_bad(e["text"]), e["k"])] = _R
    return table


def _oracle():
    table = _truth_table()
    return lambda text, k: table[(text, k)]


class TestMutants(unittest.TestCase):
    def test_mask_drops_all_bads_and_appends_dead_one(self):
        src = next(e for e in default_census() if e["truth"] == "reachable")
        masked = mask_bads(src["text"])
        bads = [ln for ln in masked.splitlines() if ln.split()[1] == "bad"]
        self.assertEqual(len(bads), 1)
        zero_id = bads[0].split()[2]
        self.assertIn(f"{zero_id} zero", masked)

    def test_mask_is_semantically_unreachable(self):
        # Replay through the shared interpreter (no external binaries):
        # the masked system's bad never fires within the bound.
        src = next(e for e in default_census() if e["truth"] == "reachable")
        self.assertTrue(corroborate_unreach(mask_bads(src["text"]), src["k"]))

    def test_force_appends_firing_bad(self):
        src = next(e for e in default_census() if e["truth"] == "unreachable")
        forced = force_bad(src["text"])
        tail = forced.splitlines()[-3:]
        self.assertEqual([ln.split()[1] for ln in tail],
                         ["sort", "one", "bad"])


class TestGate(unittest.TestCase):
    def test_honest_oracle_admitted(self):
        report = gate(_oracle(), candidate="oracle")
        self.assertTrue(report.canaries_ok)
        self.assertTrue(report.admitted)
        self.assertEqual(report.disagreements, [])
        self.assertEqual(report.contradictions, [])
        # sensitivity demonstrated in both directions
        self.assertGreater(report.strong_flips["masked"], 0)
        self.assertGreater(report.strong_flips["forced"], 0)

    def test_always_reachable_liar_caught(self):
        report = gate(lambda t, k: _R, candidate="liar-reach")
        self.assertFalse(report.admitted)
        self.assertFalse(report.canaries_ok)          # unreach canary
        self.assertTrue(report.disagreements)         # unreachable census
        self.assertTrue(report.contradictions)        # masked mutants

    def test_always_unreachable_liar_caught(self):
        report = gate(lambda t, k: _U, candidate="liar-unreach")
        self.assertFalse(report.admitted)
        self.assertFalse(report.canaries_ok)          # reach canary
        self.assertTrue(report.disagreements)         # reachable census
        self.assertTrue(report.contradictions)        # forced mutants

    def test_always_abstaining_fails_canaries(self):
        report = gate(lambda t, k: _K, candidate="mute")
        self.assertFalse(report.admitted)
        self.assertFalse(report.canaries_ok)
        self.assertEqual(report.disagreements, [])    # never lied, still out

    def test_sound_and_slow_admitted(self):
        # Right on the trivial cases and the flips; abstains on every
        # census entry: admitted, the abstentions on the record.
        table = _truth_table()
        census_keys = {(e["text"], e["k"]) for e in default_census()}
        decider = (lambda t, k:
                   _K if (t, k) in census_keys else table[(t, k)])
        report = gate(decider, candidate="slow")
        self.assertTrue(report.admitted)
        self.assertEqual(report.abstained, len(census_keys))

    def test_crash_is_abstention_not_lie(self):
        table = _truth_table()
        census_keys = {(e["text"], e["k"]) for e in default_census()}

        def decider(t, k):
            if (t, k) in census_keys:
                raise RuntimeError("boom")
            return table[(t, k)]

        report = gate(decider, candidate="fragile")
        self.assertTrue(report.admitted)              # never lied
        self.assertEqual(report.abstained, len(census_keys))
        self.assertTrue(any("error" in r for r in report.rows))

    def test_twice_and_diff_catches_nondeterminism(self):
        table = _truth_table()
        flip = {"n": 0}

        def decider(t, k):
            flip["n"] += 1
            return table[(t, k)] if flip["n"] % 2 else _K

        undemanded = gate(decider, candidate="coin", runs=1)
        demanded = gate(decider, candidate="coin", runs=2)
        self.assertTrue(demanded.nondeterministic)
        self.assertFalse(demanded.admitted)
        # with runs=1 the same decider is judged on verdicts alone
        self.assertEqual(undemanded.nondeterministic, [])


class TestRealEngines(unittest.TestCase):
    @unittest.skipUnless(find_btormc(), "btormc not installed")
    def test_native_composite_admitted(self):
        report = gate(native_decider(), candidate="native-btor2")
        self.assertTrue(report.admitted, msg=solver_gate.render(report))

    def test_bridged_z3_admitted(self):
        try:
            import z3  # noqa: F401
        except ImportError:
            self.skipTest("z3 python bindings not installed")
        report = gate(bridged_decider(), candidate="z3")
        self.assertTrue(report.admitted, msg=solver_gate.render(report))


if __name__ == "__main__":
    unittest.main()
