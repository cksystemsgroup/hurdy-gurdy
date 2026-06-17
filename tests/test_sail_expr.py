"""The Sail-derived semantics, checked two ways (the "single source, multiple
lowerings can't drift" guarantee from the v3 machine):

- broad: for every EXEC tree, the concrete evaluator (which matches the BTOR2
  evaluator op-for-op) agrees with the z3 lowering on random inputs;
- targeted: representative trees are *proven* equivalent to independent z3
  formulas for all inputs (incl. the div-by-zero / overflow corners).
"""

import random
import unittest

from gurdy.languages.sail.expr import Expr, evaluate, to_z3
from gurdy.languages.sail.rv64 import EXEC


def _vars(e: Expr, acc=None):
    acc = set() if acc is None else acc
    if e.op == "var":
        acc.add(e.attr[0])
    for c in e.args:
        _vars(c, acc)
    return acc


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_z3(), "z3 not installed")
class TestSailSemantics(unittest.TestCase):
    def test_evaluate_matches_z3_on_random_inputs(self):
        import z3
        rng = random.Random(0)
        for name, tree in EXEC.items():
            names = _vars(tree)
            for _ in range(25):
                env = {v: rng.getrandbits(64) for v in names}
                got = evaluate(tree, env)
                z = z3.simplify(to_z3(tree, {v: z3.BitVecVal(env[v], 64) for v in names}))
                want = z.as_long() & ((1 << tree.width) - 1)
                self.assertEqual(got, want, f"{name} disagreed: env={env}")

    def test_targeted_equivalence_proofs(self):
        import z3
        a, b = z3.BitVec("a", 64), z3.BitVec("b", 64)
        env = {"a": a, "b": b, "pc": z3.BitVec("pc", 64), "uimm": z3.BitVec("uimm", 64)}
        sh6 = b & z3.BitVecVal(63, 64)

        def prove(name, ref):
            s = z3.Solver()
            s.add(to_z3(EXEC[name], env) != ref)
            self.assertEqual(s.check(), z3.unsat, f"{name} not equivalent to reference")

        prove("ADD", a + b)
        prove("SUB", a - b)
        prove("MUL", a * b)
        prove("AND", a & b)
        prove("OR", a | b)
        prove("XOR", a ^ b)
        prove("SLL", a << sh6)
        prove("SRL", z3.LShR(a, sh6))
        prove("SRA", a >> sh6)
        prove("MULH", z3.Extract(127, 64, z3.SignExt(64, a) * z3.SignExt(64, b)))
        prove("MULHU", z3.Extract(127, 64, z3.ZeroExt(64, a) * z3.ZeroExt(64, b)))

    def test_division_corner_proofs(self):
        import z3
        a, b = z3.BitVec("a", 64), z3.BitVec("b", 64)
        env = {"a": a, "b": b, "pc": z3.BitVec("pc", 64), "uimm": z3.BitVec("uimm", 64)}
        intmin, minus1 = z3.BitVecVal(1 << 63, 64), z3.BitVecVal(-1, 64)

        def valid(claim):
            s = z3.Solver()
            s.add(z3.Not(claim))
            self.assertEqual(s.check(), z3.unsat)

        div = to_z3(EXEC["DIV"], env)
        rem = to_z3(EXEC["REM"], env)
        divu = to_z3(EXEC["DIVU"], env)
        valid(z3.Implies(b == 0, div == minus1))                         # DIV/0 -> -1
        valid(z3.Implies(b == 0, rem == a))                              # REM/0 -> dividend
        valid(z3.Implies(b == 0, divu == z3.BitVecVal(-1, 64)))          # DIVU/0 -> all ones
        valid(z3.Implies(z3.And(a == intmin, b == minus1), div == intmin))  # overflow
        valid(z3.Implies(z3.And(a == intmin, b == minus1), rem == z3.BitVecVal(0, 64)))


if __name__ == "__main__":
    unittest.main()
