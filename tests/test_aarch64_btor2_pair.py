"""aarch64-btor2 tests (the thin ADD-immediate slice).

Covers the PAIRING.md §7 minimum: twice-and-diff determinism for both the
translator and the new shared AArch64 interpreter; a per-construct translation
unit test against the spec; the commuting square ``I_s(p) ≡_π L(I_t(T(p)))``
through the framework oracle; carry-back of a BTOR2 witness through ``L`` to a
source-level fact; and a registration smoke test (the pair is listed and every
edge-op of its square is callable). Also pins the honest ``unsupported``
histogram and the rejection of out-of-scope constructs (BENCHMARKS.md §3).
"""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_pair, list_pairs
from gurdy.core.solver import Verdict
from gurdy.languages.aarch64 import asm
from gurdy.languages.aarch64.interp import SP_DEFAULT, decode, program_from_words, run
from gurdy.languages.btor2 import from_text, interpret, to_text
from gurdy.pairs.aarch64_btor2 import PROJECTION, square, translate
from gurdy.pairs.aarch64_btor2.inventory import IN_SCOPE, OUT_OF_SCOPE, coverage
from gurdy.pairs.aarch64_btor2.lift import lift


def img(*words):
    return program_from_words(list(words))


def prog(*words, **kw):
    return {"image": img(*words), **kw}


def ok(self, program):
    report = square(program)
    self.assertTrue(report.ok, msg=str(report.divergence))


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


class TestAarch64Btor2(unittest.TestCase):
    # --- registration smoke test (every edge-op callable) ------------------
    def test_registered(self):
        self.assertIn("aarch64-btor2", list_pairs())

    def test_edge_ops_callable(self):
        pair = get_pair("aarch64-btor2")
        self.assertEqual(pair.source, "aarch64")
        self.assertEqual(pair.target, "btor2")
        program = prog(asm.add_imm(0, 0, 7))
        # translate (T)
        artifact = pair.translator(program)
        self.assertIsInstance(artifact, bytes)
        # interpret-source (I_s)
        src = list(pair.source_interpreter(program["image"], {}))
        self.assertTrue(src)
        # interpret-target (I_t)
        tgt = list(pair.target_interpreter(artifact, {"steps": len(src) + 1}))
        self.assertTrue(tgt)
        # carry-back (L)
        carried = pair.target_to_source(tgt)
        self.assertEqual(len(carried), len(tgt))
        # cross-check (square)
        self.assertTrue(square(program).ok)

    # --- per-construct translation unit test (against the spec) ------------
    def test_decode_add_immediate_spec(self):
        # ADD X3, X5, #42  ->  rd=3, rn=5, imm=42 (no shift)
        d = decode(asm.add_imm(3, 5, 42))
        self.assertEqual((d.rd, d.rn, d.imm), (3, 5, 42))
        # LSL #12 multiplies the imm by 4096
        d2 = decode(asm.add_imm(3, 5, 2, lsl12=True))
        self.assertEqual((d2.rd, d2.rn, d2.imm), (3, 5, 2 << 12))
        # field 31 is SP for this encoding class
        d3 = decode(asm.add_imm(asm.SP, asm.SP, 16))
        self.assertEqual((d3.rd, d3.rn), (31, 31))

    def test_translate_emits_state(self):
        text = translate(prog(asm.add_imm(0, 0, 1))).decode()
        for sym in ("pc", "x0", "x30", "sp", "nzcv", "halted"):
            self.assertIn(f" {sym}", " " + text.replace("\n", " "))

    # --- commuting square on a small corpus --------------------------------
    def test_add_immediate(self):
        ok(self, prog(asm.add_imm(0, 0, 5)))

    def test_add_immediate_chain(self):
        # x0 = 5 ; x1 = x0 + 3 ; x2 = x1 + 0xFFF
        ok(self, prog(asm.add_imm(0, 0, 5), asm.add_imm(1, 0, 3),
                      asm.add_imm(2, 1, 0xFFF)))

    def test_add_immediate_lsl12(self):
        ok(self, prog(asm.add_imm(4, 0, 1, lsl12=True)))  # x4 = 4096

    def test_add_immediate_init_regs(self):
        # x0 = x1 + 0, with x1 seeded; exercises a register *source* operand.
        ok(self, prog(asm.add_imm(0, 1, 0), init_regs={1: 0xDEAD_BEEF}))

    def test_add_immediate_sp(self):
        # sp += 16 (Rn=Rd=31), then x5 = sp + 0 ; exercises SP read+write.
        ok(self, prog(asm.add_imm(asm.SP, asm.SP, 16), asm.add_imm(5, asm.SP, 0),
                      init_sp=100))

    def test_add_immediate_wraps_modulo_2_64(self):
        # 64-bit wraparound is part of the ISA semantics; the square must hold.
        ok(self, prog(asm.add_imm(0, 1, 1), init_regs={1: (1 << 64) - 1}))

    def test_nzcv_preserved(self):
        # ADD leaves NZCV unchanged; seed nonzero flags and require they survive.
        program = prog(asm.add_imm(0, 0, 1), init_nzcv=0b1010)
        ok(self, program)
        tr = run(program["image"], {"nzcv": 0b1010})
        self.assertTrue(all(row["nzcv"] == 0b1010 for row in tr))

    # --- twice-and-diff determinism (translator + interpreter) -------------
    def test_translator_deterministic(self):
        p = prog(asm.add_imm(7, 7, 0x123))
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        # canonical BTOR2 round-trips byte-exact (native-checker conformant)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_interpreter_deterministic(self):
        p = img(asm.add_imm(0, 0, 5), asm.add_imm(1, 0, 9))
        binding = {"regs": {2: 3}, "sp": 999, "nzcv": 0b0110}
        t1 = list(run(p, dict(binding)))
        t2 = list(run(p, dict(binding)))
        self.assertEqual(t1, t2)

    # --- carry-back: a BTOR2 witness replays through L to a source fact -----
    def test_lift_shapes_source_behavior(self):
        # Without a solver: the BTOR2 trace carries back into AArch64 observables.
        program = prog(asm.add_imm(0, 0, 42))
        artifact = translate(program)
        n = len(run(program["image"], {}))
        carried = lift(interpret(artifact, {"steps": n + 1}))
        self.assertEqual(set(PROJECTION.fields) - set(carried[-1]), set())
        self.assertTrue(any(row.get("x0") == 42 for row in carried))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge(self):
        # AArch64 -> BTOR2 (with a bad) -> SMT-LIB -> z3, witness replayed back
        # to the source-level fact x0 == 42 (the carry-back §7 requires).
        from gurdy.pairs.btor2_smtlib import reach

        program = prog(asm.add_imm(0, 0, 42), property={"reg_eq": [0, 42]})
        info = reach(translate(program), 3)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("x0") == 42 for row in info["behavior"]))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_unreachable_via_bridge(self):
        from gurdy.pairs.btor2_smtlib import reach

        program = prog(asm.add_imm(0, 0, 42), property={"reg_eq": [0, 999]})
        self.assertEqual(reach(translate(program), 3)["verdict"], Verdict.UNREACHABLE)

    # --- honest coverage + rejection of out-of-scope constructs ------------
    def test_in_scope_construct_covered(self):
        report = coverage()
        for name in IN_SCOPE:
            self.assertIn(name, report.covered)
        self.assertEqual(report.fraction, len(IN_SCOPE) / report.total)

    def test_out_of_scope_constructs_abort(self):
        for name, program in OUT_OF_SCOPE.items():
            with self.assertRaises(Unsupported, msg=name):
                translate(program)

    def test_unsupported_histogram(self):
        report = coverage()
        # Every out-of-scope probe is itemized, none silently dropped.
        self.assertEqual(sum(report.histogram.values()), len(OUT_OF_SCOPE))
        self.assertEqual(report.missing.keys(), OUT_OF_SCOPE.keys())

    def test_unsupported_is_typed_and_named(self):
        with self.assertRaises(Unsupported) as cm:
            run(img(0xD503_201F), {})        # NOP, via the interpreter
        self.assertEqual(cm.exception.language, "aarch64")
        self.assertTrue(cm.exception.construct)


if __name__ == "__main__":
    unittest.main()
