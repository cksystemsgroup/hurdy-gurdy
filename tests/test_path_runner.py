"""Path runner / route enumerator tests.

Enumerating routes over the registry graph, and composing the
``riscv-btor2 -> btor2-smtlib`` path automatically (the capstone, but driven
by the generic runner instead of hand-wiring).
"""

import unittest

from gurdy.core import route
from gurdy.core.solver import Verdict
from gurdy.languages.riscv.interp import image_from_words

# Import the pairs so they register (and so btor2-smtlib's compose_input wires
# the path).
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


def ECALL():
    return 0x73


def _head():
    return {
        "image": image_from_words([ADD(3, 1, 2), ECALL()]),
        "init_regs": {1: 20, 2: 22},
        "property": {"reg_eq": [3, 42]},
    }


class TestRoutes(unittest.TestCase):
    def test_enumerate_riscv_to_smtlib(self):
        # the direct route always enumerates (the Sail branch may add a second)
        self.assertIn(["riscv-btor2", "btor2-smtlib"], route.routes("riscv", "smtlib"))

    def test_enumerate_riscv_to_btor2(self):
        self.assertIn(["riscv-btor2"], route.routes("riscv", "btor2"))

    def test_no_route_backwards(self):
        self.assertEqual(route.routes("smtlib", "riscv"), [])

    def test_run_route_is_deterministic(self):
        r = ["riscv-btor2", "btor2-smtlib"]
        a = route.run_route(r, _head(), {"btor2-smtlib": {"k": 3}})
        b = route.run_route(r, _head(), {"btor2-smtlib": {"k": 3}})
        self.assertEqual(a["artifact"], b["artifact"])
        self.assertEqual([h["pair"] for h in a["provenance"]], r)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_composed_path_decides_reachability(self):
        # the whole C-less capstone, driven by the generic runner
        result = route.run_route(["riscv-btor2", "btor2-smtlib"], _head(),
                                 {"btor2-smtlib": {"k": 3}})
        from gurdy.solvers.z3_smt import Z3SmtBackend
        verdict = Z3SmtBackend().decide(result["artifact"]).verdict
        self.assertEqual(verdict, Verdict.REACHABLE)
        self.assertEqual(len(result["provenance"]), 2)


if __name__ == "__main__":
    unittest.main()
