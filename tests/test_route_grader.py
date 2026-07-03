"""Route-grader tests: measured composition over the riscv -> smtlib route.

Branch agreement is exercised on the single route (trivially agreeing); it
becomes a real cross-check when a second route to BTOR2 (the Sail branch)
lands.
"""

import unittest

from gurdy.core import grade, route
from gurdy.core.coverage import measure
from gurdy.core.solver import Verdict
from gurdy.languages.riscv.interp import image_from_words

import gurdy.pairs.btor2_smtlib  # noqa: F401
import gurdy.pairs.riscv_btor2   # noqa: F401
import gurdy.pairs.riscv_sail    # noqa: F401  (the indirect Sail branch)
import gurdy.pairs.sail_btor2    # noqa: F401
from gurdy.pairs.riscv_btor2 import translate as rv_translate
from gurdy.pairs.riscv_btor2.inventory import ALL_PROBES


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


def ADD(d, a, c):
    return ((c << 20) | (a << 15) | (d << 7) | 0x33) & 0xFFFFFFFF


def _head(target_value):
    return {
        "image": image_from_words([ADD(3, 1, 2), 0x73]),  # x3 = x1 + x2; ecall
        "init_regs": {1: 20, 2: 22},                       # -> x3 == 42
        "property": {"reg_eq": [3, target_value]},
    }


PARAMS = {"btor2-smtlib": {"k": 3}}
ROUTE = ["riscv-btor2", "btor2-smtlib"]                       # direct
SAIL_ROUTE = ["riscv-sail", "sail-btor2", "btor2-smtlib"]     # indirect (independent)


class TestPathGrader(unittest.TestCase):
    def test_two_routes_exist(self):
        self.assertEqual(route.routes("riscv", "smtlib"), [ROUTE, SAIL_ROUTE])

    def test_composed_determinism(self):
        self.assertTrue(grade.composed_determinism(ROUTE, _head(42), PARAMS))
        self.assertTrue(grade.composed_determinism(SAIL_ROUTE, _head(42), PARAMS))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_branch_agreement_reachable(self):
        # the headline cross-check: the direct and Sail-mediated routes are
        # *independent* lowerings of RISC-V; deciding the same property along
        # each must agree.
        from gurdy.solvers.z3_smt import Z3SmtBackend

        def decide(artifact):
            return Z3SmtBackend().decide(artifact).verdict

        routes = route.routes("riscv", "smtlib")
        self.assertEqual(len(routes), 2)
        ba = grade.branch_agreement(routes, _head(42), decide, PARAMS)
        self.assertTrue(ba.agree)
        self.assertEqual(set(ba.verdicts.values()), {Verdict.REACHABLE})

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_branch_agreement_unreachable(self):
        from gurdy.solvers.z3_smt import Z3SmtBackend

        def decide(artifact):
            return Z3SmtBackend().decide(artifact).verdict

        ba = grade.branch_agreement(route.routes("riscv", "smtlib"), _head(999), decide, PARAMS)
        self.assertTrue(ba.agree)
        self.assertEqual(set(ba.verdicts.values()), {Verdict.UNREACHABLE})

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_branch_agreement_over_a_loop(self):
        # the cross-check now spans control flow: both routes agree that the
        # sum-1..5 loop reaches x1 == 15 (and never 99).
        from gurdy.solvers.z3_smt import Z3SmtBackend
        from gurdy.languages.riscv import asm

        def decide(artifact):
            return Z3SmtBackend().decide(artifact).verdict

        loop = [asm.addi(1, 0, 0), asm.addi(2, 0, 1), asm.addi(3, 0, 5),
                asm.add(1, 1, 2), asm.addi(2, 2, 1), asm.bge(3, 2, -8), 0x73]

        def head(v):
            return {"image": image_from_words(loop), "init_regs": {}, "property": {"reg_eq": [1, v]}}

        routes = route.routes("riscv", "smtlib")
        params = {"btor2-smtlib": {"k": 25}}
        self.assertTrue(grade.branch_agreement(routes, head(15), decide, params).agree)
        ba = grade.branch_agreement(routes, head(15), decide, params)
        self.assertEqual(set(ba.verdicts.values()), {Verdict.REACHABLE})
        self.assertEqual(set(grade.branch_agreement(routes, head(99), decide, params).verdicts.values()),
                         {Verdict.UNREACHABLE})

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_branch_agreement_over_memory(self):
        # both routes agree a store-then-load returns the stored value (and not
        # something else) -- the memory model is consistent across the two.
        from gurdy.solvers.z3_smt import Z3SmtBackend
        from gurdy.languages.riscv import asm

        def decide(artifact):
            return Z3SmtBackend().decide(artifact).verdict

        mem = [asm.addi(1, 0, 512), asm.addi(2, 0, 0x123),
               asm.sw(2, 1, 0), asm.lw(3, 1, 0), 0x73]

        def head(v):
            return {"image": image_from_words(mem), "init_regs": {}, "property": {"reg_eq": [3, v]}}

        routes = route.routes("riscv", "smtlib")
        params = {"btor2-smtlib": {"k": 10}}
        self.assertEqual(set(grade.branch_agreement(routes, head(0x123), decide, params).verdicts.values()),
                         {Verdict.REACHABLE})
        self.assertEqual(set(grade.branch_agreement(routes, head(0x999), decide, params).verdicts.values()),
                         {Verdict.UNREACHABLE})


class TestComposedCoverage(unittest.TestCase):
    def test_full_composition_to_smtlib(self):
        # every RV64IMC construct riscv-btor2 lowers survives the bridge to SMT
        report = grade.composed_coverage(ROUTE, k=1)
        self.assertEqual(report.missing, {})
        self.assertEqual(report.fraction, 1.0)
        self.assertGreaterEqual(report.total, 90)

    def test_composed_equals_direct_when_bridge_total(self):
        composed = grade.composed_coverage(ROUTE, k=1)
        direct = measure(rv_translate, ALL_PROBES)
        self.assertEqual(composed.total, direct.total)
        self.assertEqual(composed.fraction, direct.fraction)

    def test_gap_is_localized_to_the_stage(self):
        # an out-of-scope source construct dies at the first hop and says so
        amo = {"AMOADD.W": {"image": image_from_words([0x0000202F, 0x73]), "init_regs": {}}}
        report = grade.composed_coverage(ROUTE, head_probes=amo, k=1)
        self.assertEqual(report.fraction, 0.0)
        self.assertTrue(report.missing["AMOADD.W"].startswith("riscv-btor2:"))

    def test_by_route(self):
        reports = grade.composed_coverage_by_route("riscv", "smtlib", k=1)
        self.assertEqual(set(reports), {tuple(ROUTE), tuple(SAIL_ROUTE)})
        self.assertEqual(reports[tuple(ROUTE)].fraction, 1.0)            # RV64IMC
        self.assertEqual(reports[tuple(SAIL_ROUTE)].fraction, 1.0)       # Sail ALU slice


if __name__ == "__main__":
    unittest.main()
