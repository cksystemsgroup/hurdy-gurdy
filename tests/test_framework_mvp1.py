"""MVP-1 acceptance (FRAMEWORK.md §6): a trivial registered pair can be
compiled, decided through z3, and its square aligned — deterministically.

Run with: ``python -m unittest`` (no third-party test runner needed).
"""

import unittest

import gurdy.demo  # noqa: F401  (registers demo-nat-smt)
from gurdy.core import cache, oracle, registry
from gurdy.core.solver import Verdict


def _z3_available() -> bool:
    try:
        import z3  # noqa: F401

        return True
    except ImportError:
        return False


class TestRegistry(unittest.TestCase):
    def test_demo_pair_registered(self):
        self.assertIn("demo-nat-smt", registry.list_pairs())
        pair = registry.get_pair("demo-nat-smt")
        # Interpreters are wired from the languages it touches (shared).
        self.assertIsNotNone(pair.source_interpreter)
        self.assertIsNotNone(pair.target_interpreter)

    def test_unregistered_language_rejected(self):
        from gurdy.core.registry import Pair
        from gurdy.core.types import Projection

        bad = Pair(
            id="x-y",
            source="nope-src",
            target="nope-tgt",
            translator=lambda p: b"",
            target_to_source=lambda t: t,
            projection=Projection(("x",)),
        )
        with self.assertRaises(ValueError):
            registry.register_pair(bad)


class TestDeterminism(unittest.TestCase):
    def test_compile_is_byte_identical(self):
        pair = registry.get_pair("demo-nat-smt")
        a1 = cache.compile(pair, 42)
        a2 = cache.compile(pair, 42)
        self.assertEqual(a1, a2)                       # twice-and-diff (cached)
        self.assertTrue(cache.recompile_and_diff(pair, 42))  # bypassing cache
        self.assertNotEqual(cache.compile(pair, 7), a1)      # input-sensitive


class TestSquareAndSolver(unittest.TestCase):
    @unittest.skipUnless(_z3_available(), "z3 not installed")
    def test_decide_reachable_with_model(self):
        pair = registry.get_pair("demo-nat-smt")
        from gurdy.solvers.z3_smt import Z3SmtBackend

        artifact = cache.compile(pair, 42)
        result = Z3SmtBackend().decide(artifact)
        self.assertEqual(result.verdict, Verdict.REACHABLE)
        self.assertEqual(result.model["x"], 42)
        self.assertEqual(result.provenance["solver"], "z3")

    @unittest.skipUnless(_z3_available(), "z3 not installed")
    def test_square_commutes(self):
        pair = registry.get_pair("demo-nat-smt")
        from gurdy.solvers.z3_smt import Z3SmtBackend

        for n in (0, 1, 42, 255):
            artifact = cache.compile(pair, n)
            result = Z3SmtBackend().decide(artifact)
            self.assertEqual(result.verdict, Verdict.REACHABLE)
            # solver seeds the deterministic core; interpreter + carry-back
            # regrow and project; the square must commute under π.
            target_trace = pair.target_interpreter(result.model)
            carried = pair.target_to_source(target_trace)
            source_trace = pair.source_interpreter(n)
            report = oracle.align(source_trace, carried, pair.projection)
            self.assertTrue(report.ok, msg=str(report.divergence))

    def test_align_localizes_divergence(self):
        # A deliberately broken carry-back must be caught and localized.
        from gurdy.core.types import Projection

        proj = Projection(("x",))
        ok = oracle.align([{"x": 5}], [{"x": 5}], proj)
        self.assertTrue(ok.ok)
        bad = oracle.align([{"x": 5}], [{"x": 6}], proj)
        self.assertFalse(bad.ok)
        self.assertEqual(bad.divergence.step, 0)
        self.assertEqual(bad.divergence.field, "x")


if __name__ == "__main__":
    unittest.main()
