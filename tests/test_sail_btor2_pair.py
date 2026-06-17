"""sail-btor2 tests: the commuting square holds across the Sail-realized RV64
ALU slice (the independent Expr-tree lowering vs the independent Sail
interpreter), coverage is full over the slice, out-of-scope opcodes abort, and
the emitted bad decides through the btor2-smtlib bridge."""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import list_pairs
from gurdy.core.solver import Verdict
from gurdy.languages.btor2 import from_text, to_text
from gurdy.languages.riscv import asm
from gurdy.languages.sail import run as sail_run
from gurdy.pairs.sail_btor2 import square, translate
from gurdy.pairs.sail_btor2.inventory import coverage


def _prog(words, init_regs=None, prop=None):
    p = {"words": [*words, asm.ecall()], "entry": 0, "init_regs": init_regs or {}}
    if prop is not None:
        p["property"] = prop
    return p


def ok(self, words, init_regs=None):
    rep = square(_prog(words, init_regs))
    self.assertTrue(rep.ok, msg=str(rep.divergence))


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


class TestSailBtor2(unittest.TestCase):
    def test_registered(self):
        self.assertIn("sail-btor2", list_pairs())

    def test_arithmetic_and_logic(self):
        ok(self, [asm.addi(1, 0, 20), asm.addi(2, 0, 22), asm.add(3, 1, 2),
                  asm.sub(4, 2, 1), asm.xor(5, 1, 2), asm.and_(6, 1, 2), asm.or_(7, 1, 2)])

    def test_shifts_reg_and_imm(self):
        ok(self, [asm.addi(1, 0, -1), asm.slli(2, 1, 4), asm.srli(3, 1, 2),
                  asm.srai(4, 1, 2), asm.sll(5, 1, 2), asm.srl(6, 1, 2), asm.sra(7, 1, 2)])

    def test_compares(self):
        ok(self, [asm.addi(1, 0, -1), asm.addi(2, 0, 1),
                  asm.slt(3, 1, 2), asm.sltu(4, 1, 2), asm.slti(5, 1, 0), asm.sltiu(6, 1, 0)])

    def test_word_ops(self):
        ok(self, [asm.addi(1, 0, 100), asm.addi(2, 0, 7), asm.addw(3, 1, 2),
                  asm.subw(4, 1, 2), asm.sllw(5, 1, 2), asm.addiw(6, 1, 5)])

    def test_mul_div_rem(self):
        ok(self, [asm.addi(1, 0, 20), asm.addi(2, 0, 3), asm.mul(3, 1, 2),
                  asm.mulh(4, 1, 2), asm.div(5, 1, 2), asm.rem(6, 1, 2), asm.divu(7, 1, 2)])

    def test_div_edge_cases(self):
        # DIV/0 -> -1, REM/0 -> dividend, DIVU/0 -> all ones (Sail-realized)
        ok(self, [asm.addi(1, 0, 7), asm.addi(2, 0, 0),
                  asm.div(3, 1, 2), asm.rem(4, 1, 2), asm.divu(5, 1, 2)])
        # INT_MIN / -1 -> INT_MIN ; INT_MIN % -1 -> 0
        ok(self, [asm.addi(1, 0, 1), asm.slli(1, 1, 63), asm.addi(2, 0, -1),
                  asm.div(3, 1, 2), asm.rem(4, 1, 2)])

    def test_lui_auipc(self):
        ok(self, [asm.lui(1, 0x12345000), asm.auipc(2, 0x1000)])

    def test_branch_not_taken(self):
        ok(self, [asm.addi(1, 0, 3), asm.addi(2, 0, 5), asm.bge(1, 2, 8), asm.addi(4, 0, 7)])

    def test_branch_taken(self):
        ok(self, [asm.addi(1, 0, 5), asm.addi(2, 0, 5), asm.beq(1, 2, 8), asm.addi(3, 0, 99)])

    def test_jumps(self):
        ok(self, [asm.jal(1, 8), asm.addi(5, 0, 99)])   # jal skips the addi onto the ecall
        ok(self, [asm.jalr(1, 0, 4)])                    # jalr lands on the ecall

    def test_loop(self):
        # sum 1..5 = 15, exercising a taken branch each iteration
        loop = [asm.addi(1, 0, 0), asm.addi(2, 0, 1), asm.addi(3, 0, 5),
                asm.add(1, 1, 2), asm.addi(2, 2, 1), asm.bge(3, 2, -8)]
        ok(self, loop)
        final = sail_run({"words": [*loop, asm.ecall()], "entry": 0, "init_regs": {}})[-1]
        self.assertEqual(final["x1"], 15)

    def test_memory_roundtrip(self):
        # store r2 at [r1], load it back; byte store + zero-extended byte load
        mem = [asm.addi(1, 0, 512), asm.addi(2, 0, 0x123),
               asm.sw(2, 1, 0), asm.lw(3, 1, 0), asm.sb(2, 1, 8), asm.lbu(4, 1, 8)]
        ok(self, mem)
        final = sail_run({"words": [*mem, asm.ecall()], "entry": 0, "init_regs": {}, "mem": {}})[-1]
        self.assertEqual(final["x3"], 0x123)
        self.assertEqual(final["x4"], 0x23)

    def test_signed_byte_load(self):
        # store 0xFF, load as signed byte -> -1
        mem = [asm.addi(1, 0, 512), asm.addi(2, 0, 0xFF), asm.sb(2, 1, 0), asm.lb(3, 1, 0)]
        ok(self, mem)
        final = sail_run({"words": [*mem, asm.ecall()], "entry": 0, "init_regs": {}})[-1]
        self.assertEqual(final["x3"], (1 << 64) - 1)

    def test_coverage_full(self):
        report = coverage()
        self.assertEqual(report.missing, {})
        self.assertEqual(report.fraction, 1.0)
        self.assertGreaterEqual(report.total, 60)   # ALU/M + control flow + load/store

    def test_out_of_scope_aborts(self):
        # the A extension (AMO) and CSR access are out of this slice
        csrrw = (0xC00 << 20) | (1 << 12) | (1 << 7) | 0x73
        for word in (0x0000202F, csrrw):
            with self.assertRaises(Unsupported):
                translate(_prog([word]))

    def test_deterministic_canonical_btor2(self):
        p = _prog([asm.add(3, 1, 2)])
        a = translate(p)
        self.assertEqual(a, translate(p))
        self.assertEqual(to_text(from_text(a.decode())), a.decode())

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_via_bridge(self):
        from gurdy.pairs.btor2_smtlib import reach

        prog = _prog([asm.addi(1, 0, 20), asm.addi(2, 0, 22), asm.add(3, 1, 2)],
                     prop={"reg_eq": [3, 42]})
        info = reach(translate(prog), 4)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertEqual(reach(translate(_prog([asm.addi(1, 0, 1)], prop={"reg_eq": [1, 999]})), 3)["verdict"],
                         Verdict.UNREACHABLE)


if __name__ == "__main__":
    unittest.main()
