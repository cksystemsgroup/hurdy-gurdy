"""Path-grader tests: measured composition over the riscv -> smtlib route.

Branch agreement is exercised on the single route (trivially agreeing); it
becomes a real cross-check when a second route to BTOR2 (the Sail branch)
lands.
"""

import unittest

from gurdy.core import grade, route
from gurdy.core.solver import Verdict
from gurdy.languages.riscv.interp import image_from_words

import gurdy.pairs.btor2_smtlib  # noqa: F401
import gurdy.pairs.riscv_btor2   # noqa: F401


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
ROUTE = ["riscv-btor2", "btor2-smtlib"]


class TestPathGrader(unittest.TestCase):
    def test_composed_determinism(self):
        self.assertTrue(grade.composed_determinism(ROUTE, _head(42), PARAMS))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_branch_agreement_reachable(self):
        from gurdy.solvers.z3_smt import Z3SmtBackend

        def decide(artifact):
            return Z3SmtBackend().decide(artifact).verdict

        routes = route.routes("riscv", "smtlib")
        self.assertEqual(routes, [ROUTE])  # one route today; a branch adds more
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


if __name__ == "__main__":
    unittest.main()
