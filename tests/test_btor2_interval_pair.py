"""The ``btor2-interval`` pair — the second directional (over-approximating)
endo-pair. Covers: the lax square along the affine-decode witness embedding,
determinism, typed partiality (wraparound + array-state), the brief's three
controls — the two-sided negative control, the *unsound-interval* control (a
probe whose state provably leaves the declared range must fail the square),
and the CEGAR demonstration (loose interval -> spurious counterexample ->
tightened interval -> transferred ``unreachable``) — plus endo-route
enumeration and the registered direction.
"""

import unittest

from gurdy.core import cache, direction, negative_control, oracle, registry, route
from gurdy.core.coverage import measure
from gurdy.core.errors import Unsupported
from gurdy.languages.btor2 import interpret

import gurdy.pairs.btor2_interval as interval_pair
import gurdy.pairs.btor2_smtlib  # noqa: F401  (registers the bridge)
from gurdy.pairs.btor2_interval import projection_for, square, translate
from gurdy.pairs.btor2_interval.inventory import ALL_PROBES
from gurdy.pairs.btor2_interval.translate import interval_plan

# A 4-bit counter from 0; ``bad`` fires when it reaches 12 — unreachable
# within a 4-step bound, so the bound-k universal claim is genuinely true.
_COUNTER_BAD = """1 sort bitvec 4
2 state 1 c
3 one 1
4 add 1 2 3
5 next 1 2 4
6 constd 1 12
7 eq 1 2 6
8 bad 7
"""
_K = 4

_GAPS = {"interval.wraparound", "interval.array-state"}


def _bad_hit(trace):
    return any(row.get("bad8") == 1 for row in trace)


class TestSquare(unittest.TestCase):
    def test_square_passes_on_every_supported_probe(self):
        for name, probe in ALL_PROBES.items():
            if name in _GAPS:
                continue
            result = square(probe)
            self.assertTrue(result.ok, f"{name}: {result.divergence}")

    def test_coverage_is_conjoined_with_two_honest_gaps(self):
        pair = registry.get_pair("btor2-interval")
        report = measure(pair.translator, pair.probes, faithful=pair.square)
        self.assertTrue(report.conjoined)
        self.assertEqual(report.unfaithful, {})
        self.assertEqual(set(report.missing), _GAPS)
        self.assertEqual(len(report.covered), report.total - 2)

    def test_two_sided_negative_control(self):
        ctl = negative_control.two_sided_control(registry.get_pair("btor2-interval"))
        self.assertIsNotNone(ctl)
        self.assertTrue(ctl.ok, ctl)

    def test_unsound_interval_fails_the_square(self):
        # The brief's unsound-interval control: the counter provably leaves
        # the declared [0, 3] (it reaches 4 at step 4), so no input can
        # reproduce that value through the range decoder — the square along
        # W must fail, localized to the mapped state's label. Square failure
        # means *the declared interval is not invariant* (widen it).
        result = square({"system": _COUNTER_BAD,
                         "intervals": {"c": (0, 3)},
                         "binding": {"steps": 6}})
        self.assertFalse(result.ok)
        self.assertEqual(result.divergence.field, "c")

    def test_widened_interval_repairs_the_square(self):
        # The refinement demand answered: widening to a range the run stays
        # inside makes the same square pass — the two sides of the claim.
        result = square({"system": _COUNTER_BAD,
                         "intervals": {"c": (0, 6)},
                         "binding": {"steps": 6}})
        self.assertTrue(result.ok, result.divergence)

    def test_wrong_embedding_is_caught(self):
        # Feed zeros instead of the affine decode: the square must diverge —
        # the check is not vacuous.
        probe = ALL_PROBES["interval.subrange"]
        binding = dict(probe["binding"])
        sys, text, plan = interval_plan(probe)
        src = list(interpret(text, binding))
        wrong = dict(binding)
        wrong["inputs"] = {c: {plan[0][3][0]: 0} for c in range(binding["steps"])}
        carried = interval_pair.lift(interpret(translate(probe), wrong))
        result = oracle.align(src, list(carried), projection_for(sys))
        self.assertFalse(result.ok)

    def test_determinism_recompile_and_diff(self):
        pair = registry.get_pair("btor2-interval")
        for name, probe in ALL_PROBES.items():
            if name in _GAPS:
                continue
            self.assertTrue(cache.recompile_and_diff(pair, probe), name)

    def test_typed_partiality_and_caller_errors(self):
        with self.assertRaises(Unsupported):
            translate(ALL_PROBES["interval.array-state"])
        with self.assertRaises(Unsupported):
            translate(ALL_PROBES["interval.wraparound"])
        with self.assertRaises(ValueError):
            translate({"system": _COUNTER_BAD, "intervals": {"nope": (0, 3)}})
        with self.assertRaises(ValueError):
            translate({"system": _COUNTER_BAD, "intervals": {"c": (0, 16)}})

    def test_empty_interval_map_is_the_identity(self):
        out = translate({"system": _COUNTER_BAD, "intervals": {}})
        self.assertEqual(out, _COUNTER_BAD.encode("utf-8"))

    def test_full_range_bypasses_urem(self):
        # [0, 2^w − 1] is havoc's exact rewrite: next := iv directly — the
        # range-size constant 2^w does not fit at width w, so the emission
        # must not rest on the urem-by-zero edge.
        out = translate({"system": _COUNTER_BAD,
                         "intervals": {"c": (0, 15)}}).decode()
        self.assertNotIn(" urem ", out)
        self.assertIn("iv_c", out)

    def test_singleton_keeps_the_uniform_shape(self):
        # [c, c] still emits the const/urem/add nodes (urem(iv, 1) = 0):
        # one shape for every proper range, not a special case per rung.
        out = translate({"system": _COUNTER_BAD,
                         "intervals": {"c": (7, 7)}}).decode()
        self.assertIn(" urem ", out)
        self.assertIn(" constd 1 1", out)


class TestDirectionalRegistration(unittest.TestCase):
    def test_registered_over_with_endo_shape(self):
        pair = registry.get_pair("btor2-interval")
        self.assertEqual(pair.direction, "over")
        self.assertEqual((pair.source, pair.target), ("btor2", "btor2"))

    def test_endo_routes_are_opt_in(self):
        plain = route.routes("btor2", "smtlib")
        self.assertNotIn(["btor2-interval", "btor2-smtlib"], plain)
        endo = route.routes("btor2", "smtlib", endo=True)
        self.assertIn(["btor2-interval", "btor2-smtlib"], endo)

    def test_run_route_reports_composed_direction(self):
        result = route.run_route(
            ["btor2-interval", "btor2-smtlib"],
            {"system": _COUNTER_BAD, "intervals": {"c": (0, 13)}},
            params={"btor2-smtlib": {"k": _K}},
        )
        self.assertEqual(result["direction"], "over")
        self.assertEqual(result["provenance"][0]["direction"], "over")
        self.assertEqual(result["provenance"][1]["direction"], "exact")
        self.assertTrue(result["artifact"])  # an SMT-LIB artifact came out


class TestCegarStory(unittest.TestCase):
    """The refinement loop the direction exists for (POTENTIAL.md §6), on
    the interval ladder: a loose range admits a spurious counterexample;
    tightening the range — not deleting the abstraction — transfers the
    universal verdict."""

    def test_source_is_safe_within_bound(self):
        src = interpret(_COUNTER_BAD, {"steps": _K})
        self.assertFalse(_bad_hit(src))

    def test_loose_interval_reaches_bad_spuriously(self):
        program = {"system": _COUNTER_BAD, "intervals": {"c": (0, 13)}}
        artifact = translate(program)
        _sys, _text, plan = interval_plan(program)
        input_id = plan[0][3][0]
        # A "solver counterexample" on the abstraction: 12 ∈ [0, 13], so
        # driving iv with 12 jumps c straight onto the bad value.
        cex = {"steps": _K, "inputs": {0: {input_id: 12}}}
        self.assertTrue(_bad_hit(interpret(artifact, cex)))
        # Replay at the source (the only behavior it has): no bad — the
        # counterexample is spurious, a tighten-the-range demand.
        self.assertFalse(_bad_hit(interpret(_COUNTER_BAD, {"steps": _K})))

    def test_tightened_interval_transfers_the_universal(self):
        # Tighten to [0, 4]: the decoded update lands in [0, 4] for every
        # input value (exhaustively checked below — 4-bit iv), so c can
        # never be 12 and bad is unreachable on the abstraction for *any*
        # input; direction says that verdict transfers to the source.
        program = {"system": _COUNTER_BAD, "intervals": {"c": (0, 4)}}
        artifact = translate(program)
        _sys, _text, plan = interval_plan(program)
        input_id = plan[0][3][0]
        for v in range(16):
            trace = interpret(artifact, {"steps": 1, "inputs": {0: {input_id: v}}})
            self.assertLessEqual(trace[-1]["c"], 4)
            self.assertFalse(_bad_hit(trace))
        self.assertTrue(direction.transfers(
            "unreachable", route.route_direction(["btor2-interval"])))

    def test_witness_embedding_simulates_every_source_run(self):
        # The over-approximation claim, executed: the source trace is the
        # target trace under the embedding, on the kept observables.
        program = {"system": _COUNTER_BAD, "intervals": {"c": (0, 6)}}
        self.assertTrue(square({**program, "binding": {"steps": _K}}).ok)


if __name__ == "__main__":
    unittest.main()
