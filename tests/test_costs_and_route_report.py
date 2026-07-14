"""The cost ledger (core/ledger.py) and the enriched route report
(core/route.py::route_report) — phase A+B of the tradeoff work.

The ledger is opt-in observability: disabled by default (no env var, no
configure()), records only on success, host-tagged, and never touches a
deterministic output. The route report annotates the enumerated routes
with the four axes — fidelity/assurance, direction, feasibility, measured
cost — and marks (never hides) Pareto-dominated routes, only ever between
fully measured routes. The platform still enumerates; the player still
chooses (ROUTES.md §6).
"""

import os
import tempfile
import unittest

from gurdy.core import cache, ledger as costs, registry, route

import gurdy.pairs.btor2_smtlib  # noqa: F401  (registration)
import gurdy.pairs.riscv_btor2   # noqa: F401
import gurdy.pairs.riscv_sail    # noqa: F401
import gurdy.pairs.sail_btor2    # noqa: F401

DIRECT = ["riscv-btor2", "btor2-smtlib"]
SAIL = ["riscv-sail", "sail-btor2", "btor2-smtlib"]
DIRECT_KEY = " -> ".join(DIRECT)
SAIL_KEY = " -> ".join(SAIL)


class _LedgerCase(unittest.TestCase):
    """Base: a fresh temp ledger per test, cleared afterward."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        costs.configure(self.path)

    def tearDown(self):
        costs._reset()
        os.unlink(self.path)


class TestLedger(_LedgerCase):
    def test_disabled_by_default_and_none_profile(self):
        costs._reset()
        self.assertIsNone(costs.ledger_path()) if not os.environ.get(
            "GURDY_LEDGER") else self.skipTest("ledger env set externally")
        costs.record("decide", "k", wall_s=1.0, engine="x")  # no-op
        self.assertIsNone(costs.profile("decide", engine="x"))

    def test_record_profile_roundtrip(self):
        for w in (0.1, 0.2, 0.3):
            costs.record("translate", "k1", wall_s=w, pair="p1")
        prof = costs.profile("translate", pair="p1")
        self.assertEqual(prof["n"], 3)
        self.assertAlmostEqual(prof["wall_median_s"], 0.2)
        self.assertAlmostEqual(prof["wall_total_s"], 0.6)
        # a different pair's records don't leak in
        self.assertIsNone(costs.profile("translate", pair="p2"))

    def test_profiles_are_host_scoped(self):
        costs.record("decide", "k", wall_s=1.0, engine="z3", language="smtlib")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write('{"kind": "decide", "key": "k", "wall_s": 9.0, '
                    '"engine": "z3", "language": "smtlib", "host": "other-host"}\n')
        prof = costs.profile("decide", engine="z3")
        self.assertEqual(prof["n"], 1)  # the other host's record is filtered
        pooled = costs.profile("decide", engine="z3", host=None)
        self.assertEqual(pooled["n"], 2)

    def test_timed_records_success_only(self):
        with costs.timed("decide", "k", engine="e") as extra:
            extra["verdict"] = "unsat"
        self.assertEqual(costs.profile("decide", engine="e")["n"], 1)
        with self.assertRaises(RuntimeError):
            with costs.timed("decide", "k2", engine="e"):
                raise RuntimeError("solver died")
        # the failed block recorded nothing
        self.assertEqual(costs.profile("decide", engine="e")["n"], 1)

    def test_compile_records_on_miss_only(self):
        pair = registry.get_pair("riscv-btor2")
        program = next(iter(pair.probes.values()))  # a real inventory probe
        cache.compile(pair, program)
        first = costs.profile("translate", pair="riscv-btor2")
        self.assertGreaterEqual(first["n"], 1)
        self.assertEqual(costs._records()[-1]["kind"], "translate")
        self.assertIn("size", costs._records()[-1])
        cache.compile(pair, program)  # cache hit: no second record
        second = costs.profile("translate", pair="riscv-btor2")
        self.assertEqual(first["n"], second["n"])


class TestRouteReport(_LedgerCase):
    def test_axes_and_honest_unmeasured_default(self):
        report = route.route_report("riscv", "smtlib")
        keys = {" -> ".join(e["route"]) for e in report}
        self.assertIn(DIRECT_KEY, keys)
        self.assertIn(SAIL_KEY, keys)
        for e in report:
            # weakest link: every riscv->smtlib route runs through the
            # predicted-grade bridge, but the checked hops rank lower.
            self.assertEqual(e["assurance"], "per-run")
            self.assertEqual(e["fidelity"], "checked")
            self.assertEqual(e["direction"], "exact")
            self.assertFalse(e["cost"]["measured"])
            self.assertIsNone(e["cost"]["translate_total_median_s"])
            self.assertEqual(e["dominated_by"], [])  # no data, no dis-ranking

    def test_feasibility_observables_and_shape(self):
        report = route.route_report("riscv", "smtlib",
                                    observables=["pc"], shape="reachability")
        for e in report:
            self.assertEqual(e["feasibility"]["observables"], True)
            self.assertEqual(e["feasibility"]["shape"], True)
            self.assertEqual(e["feasibility"]["feasible"], True)
        report = route.route_report("riscv", "smtlib",
                                    observables=["no_such_field"],
                                    shape="liveness")
        for e in report:
            self.assertEqual(e["feasibility"]["observables"], False)
            self.assertEqual(e["feasibility"]["observables_missing"],
                             ["no_such_field"])
            self.assertEqual(e["feasibility"]["shape"], False)
            self.assertEqual(e["feasibility"]["feasible"], False)

    def test_dominance_requires_complete_measurement(self):
        # measure the direct route only: no dominance either way.
        for pid in DIRECT:
            costs.record("translate", "k", wall_s=0.01, pair=pid)
        report = {" -> ".join(e["route"]): e
                  for e in route.route_report("riscv", "smtlib")}
        self.assertEqual(report[DIRECT_KEY]["dominated_by"], [])
        self.assertEqual(report[SAIL_KEY]["dominated_by"], [])
        self.assertTrue(report[DIRECT_KEY]["cost"]["measured"])
        self.assertFalse(report[SAIL_KEY]["cost"]["measured"])

    def test_dominated_route_is_marked_never_hidden(self):
        for pid in DIRECT:
            costs.record("translate", "k", wall_s=0.01, pair=pid)
        for pid in SAIL:
            costs.record("translate", "k", wall_s=5.0, pair=pid)
        report = {" -> ".join(e["route"]): e
                  for e in route.route_report("riscv", "smtlib")}
        # equal assurance and direction, strictly cheaper -> direct dominates
        self.assertIn(DIRECT_KEY, report[SAIL_KEY]["dominated_by"])
        self.assertEqual(report[DIRECT_KEY]["dominated_by"], [])
        # both routes still present: marked, never hidden
        self.assertEqual(len(report), 2)


class TestShapeDeclarations(unittest.TestCase):
    def test_hubs_declare_shapes_others_default_empty(self):
        self.assertIn("reachability",
                      registry.get_language("smtlib").question_shapes)
        self.assertIn("bounded-unreachability",
                      registry.get_language("btor2").question_shapes)
        self.assertEqual(registry.get_language("riscv").question_shapes, ())


if __name__ == "__main__":
    unittest.main()
