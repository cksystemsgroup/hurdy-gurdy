"""The ``btor2-havoc`` pair — the first directional (over-approximating)
endo-pair. Covers: the lax square along the witness embedding, determinism,
typed partiality, the negative control, endo-route enumeration and running,
direction provenance — and the CEGAR story the pair exists to demonstrate
(spurious counterexample -> refinement -> transferred universal verdict).
"""

import unittest

from gurdy.core import cache, negative_control, registry, route
from gurdy.core.coverage import measure
from gurdy.core.errors import Unsupported
from gurdy.languages.btor2 import interpret

import gurdy.pairs.btor2_havoc as havoc_pair
import gurdy.pairs.btor2_smtlib  # noqa: F401  (registers the bridge)
from gurdy.pairs.btor2_havoc import embed, projection_for, square, translate
from gurdy.pairs.btor2_havoc.inventory import ALL_PROBES
from gurdy.pairs.btor2_havoc.translate import havoc_plan

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


def _bad_hit(trace):
    return any(row.get("bad8") == 1 for row in trace)


class TestSquare(unittest.TestCase):
    def test_square_passes_on_every_supported_probe(self):
        for name, probe in ALL_PROBES.items():
            if name == "havoc.array-state":
                continue
            result = square(probe)
            self.assertTrue(result.ok, f"{name}: {result.divergence}")

    def test_coverage_is_conjoined_with_one_honest_gap(self):
        pair = registry.get_pair("btor2-havoc")
        report = measure(pair.translator, pair.probes, faithful=pair.square)
        self.assertTrue(report.conjoined)
        self.assertEqual(report.unfaithful, {})
        self.assertEqual(set(report.missing), {"havoc.array-state"})
        self.assertEqual(len(report.covered), report.total - 1)

    def test_two_sided_negative_control(self):
        ctl = negative_control.two_sided_control(registry.get_pair("btor2-havoc"))
        self.assertIsNotNone(ctl)
        self.assertTrue(ctl.ok, ctl)

    def test_wrong_embedding_is_caught(self):
        # Feed zeros instead of the witness values: the square must diverge —
        # the check is not vacuous.
        probe = ALL_PROBES["havoc.state"]
        binding = dict(probe["binding"])
        sys, text, plan = havoc_plan(probe)
        src = list(interpret(text, binding))
        wrong = dict(binding)
        wrong["inputs"] = {c: {plan[0][1]: 0} for c in range(binding["steps"])}
        carried = havoc_pair.lift(interpret(translate(probe), wrong))
        from gurdy.core import oracle
        result = oracle.align(src, list(carried), projection_for(sys))
        self.assertFalse(result.ok)

    def test_determinism_recompile_and_diff(self):
        pair = registry.get_pair("btor2-havoc")
        for name, probe in ALL_PROBES.items():
            if name == "havoc.array-state":
                continue
            self.assertTrue(cache.recompile_and_diff(pair, probe), name)

    def test_typed_partiality_and_caller_errors(self):
        with self.assertRaises(Unsupported):
            translate(ALL_PROBES["havoc.array-state"])
        with self.assertRaises(ValueError):
            translate({"system": _COUNTER_BAD, "havoc": ("nope",)})

    def test_empty_havoc_is_the_identity(self):
        out = translate({"system": _COUNTER_BAD, "havoc": ()})
        self.assertEqual(out, _COUNTER_BAD.encode("utf-8"))


class TestDirectionalRegistration(unittest.TestCase):
    def test_registered_over_with_endo_shape(self):
        pair = registry.get_pair("btor2-havoc")
        self.assertEqual(pair.direction, "over")
        self.assertEqual((pair.source, pair.target), ("btor2", "btor2"))

    def test_existing_pairs_default_to_exact(self):
        self.assertEqual(registry.get_pair("btor2-smtlib").direction, "exact")

    def test_endo_routes_are_opt_in(self):
        plain = route.routes("btor2", "smtlib")
        self.assertNotIn(["btor2-havoc", "btor2-smtlib"], plain)
        endo = route.routes("btor2", "smtlib", endo=True)
        self.assertIn(["btor2-havoc", "btor2-smtlib"], endo)
        # And the plain enumeration is untouched by the endo-pair existing.
        self.assertIn(["btor2-smtlib"], plain)

    def test_run_route_reports_composed_direction(self):
        result = route.run_route(
            ["btor2-havoc", "btor2-smtlib"],
            {"system": _COUNTER_BAD, "havoc": ("c",)},
            params={"btor2-smtlib": {"k": _K}},
        )
        self.assertEqual(result["direction"], "over")
        self.assertEqual(result["provenance"][0]["direction"], "over")
        self.assertEqual(result["provenance"][1]["direction"], "exact")
        self.assertTrue(result["artifact"])  # an SMT-LIB artifact came out

    def test_route_direction_exact_route_stays_exact(self):
        self.assertEqual(route.route_direction(["btor2-smtlib"]), "exact")


class TestCegarStory(unittest.TestCase):
    """The refinement loop the direction exists for (POTENTIAL.md §6):
    abstract, get a spurious counterexample, refine, transfer the universal."""

    def test_source_is_safe_within_bound(self):
        src = interpret(_COUNTER_BAD, {"steps": _K})
        self.assertFalse(_bad_hit(src))

    def test_abstraction_reaches_bad_spuriously(self):
        program = {"system": _COUNTER_BAD, "havoc": ("c",)}
        artifact = translate(program)
        _sys, _text, plan = havoc_plan(program)
        input_id = plan[0][1]
        # A "solver counterexample" on the abstraction: jump c to 12.
        cex = {"steps": _K, "inputs": {0: {input_id: 12}}}
        self.assertTrue(_bad_hit(interpret(artifact, cex)))
        # Replay at the source (the only behavior it has): no bad — the
        # counterexample is spurious, a refinement demand on the havoc set.
        self.assertFalse(_bad_hit(interpret(_COUNTER_BAD, {"steps": _K})))

    def test_refined_abstraction_transfers_the_universal(self):
        from gurdy.core import direction
        # Refine: drop c from the havoc set. The abstraction is the identity,
        # bad is unreachable within k on the target for *any* input (the
        # system has none), and direction says that verdict transfers.
        refined = {"system": _COUNTER_BAD, "havoc": ()}
        self.assertFalse(_bad_hit(interpret(translate(refined), {"steps": _K})))
        self.assertTrue(direction.transfers(
            "unreachable", route.route_direction(["btor2-havoc"])))

    def test_witness_embedding_simulates_every_source_run(self):
        # The over-approximation claim, executed: the source trace is the
        # target trace under the embedding, on the kept observables.
        program = {"system": _COUNTER_BAD, "havoc": ("c",)}
        self.assertTrue(square({**program, "binding": {"steps": _K}}).ok)


if __name__ == "__main__":
    unittest.main()
