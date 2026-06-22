"""aarch64-btor2 tests (the simple-ALU slice: ADD/SUB immediate + MOVZ).

Covers the PAIRING.md §7 minimum: twice-and-diff determinism for both the
translator and the shared AArch64 interpreter; per-construct translation unit
tests against the spec (one per added op); the commuting square
``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle on programs using the
new ops; carry-back of a BTOR2 witness through ``L`` to a source-level fact; and
a registration smoke test (the pair is listed and every edge-op of its square is
callable). Also pins the honest ``unsupported`` histogram and that a
still-unsupported instruction (a branch, a load, a flag-setting form) keeps
hard-aborting (BENCHMARKS.md §3) after the interpreter ``0.1`` → ``0.2``
widening.
"""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_pair, list_pairs
from gurdy.core.solver import Verdict
from gurdy.languages.aarch64 import asm
from gurdy.languages.aarch64.interp import (
    SP_DEFAULT,
    decode,
    decode_insn,
    program_from_words,
    run,
)
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

    def test_decode_sub_immediate_spec(self):
        # SUB X3, X5, #42  ->  rd=3, rn=5, imm=42, op=sub
        d = decode_insn(asm.sub_imm(3, 5, 42))
        self.assertEqual((d.rd, d.rn, d.imm, d.op), (3, 5, 42, "sub"))
        # LSL #12 multiplies the imm by 4096
        d2 = decode_insn(asm.sub_imm(3, 5, 2, lsl12=True))
        self.assertEqual((d2.rd, d2.rn, d2.imm, d2.op), (3, 5, 2 << 12, "sub"))
        # field 31 is SP for this encoding class
        d3 = decode_insn(asm.sub_imm(asm.SP, asm.SP, 16))
        self.assertEqual((d3.rd, d3.rn, d3.op), (31, 31, "sub"))

    def test_decode_movz_spec(self):
        # MOVZ X7, #42  ->  rd=7, imm=42, op=movz (and == the legacy 0xD2800540)
        self.assertEqual(asm.movz(0, 42), 0xD280_0540)
        d = decode_insn(asm.movz(7, 42))
        self.assertEqual((d.rd, d.imm, d.op), (7, 42, "movz"))
        # LSL #(16*hw) shifts the 16-bit immediate
        d2 = decode_insn(asm.movz(1, 0xABCD, hw=1))
        self.assertEqual((d2.rd, d2.imm, d2.op), (1, 0xABCD << 16, "movz"))
        d3 = decode_insn(asm.movz(2, 0x1, hw=3))
        self.assertEqual((d3.rd, d3.imm, d3.op), (2, 1 << 48, "movz"))

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

    # --- SUB (immediate), 64-bit -------------------------------------------
    def test_sub_immediate(self):
        # x0 = 100 ; x0 = x0 - 7 = 93
        program = prog(asm.movz(0, 100), asm.sub_imm(0, 0, 7))
        ok(self, program)
        self.assertEqual(run(program["image"], {})[-2]["x0"], 93)

    def test_sub_immediate_lsl12(self):
        # x0 = x1 - (1<<12), with x1 seeded
        ok(self, prog(asm.sub_imm(0, 1, 1, lsl12=True), init_regs={1: 0x2000}))

    def test_sub_immediate_sp(self):
        # sp -= 16 (Rn=Rd=31), then x5 = sp + 0 ; exercises SP read+write on SUB.
        program = prog(asm.sub_imm(asm.SP, asm.SP, 16), asm.add_imm(5, asm.SP, 0),
                       init_sp=100)
        ok(self, program)
        self.assertEqual(run(program["image"], {"sp": 100})[0]["sp"], 84)

    def test_sub_immediate_wraps_modulo_2_64(self):
        # 0 - 1 wraps to 2^64 - 1; the ISA-defined wrap, the square must hold.
        program = prog(asm.sub_imm(0, 0, 1))
        ok(self, program)
        self.assertEqual(run(program["image"], {})[0]["x0"], (1 << 64) - 1)

    # --- MOVZ (move wide immediate), 64-bit --------------------------------
    def test_movz(self):
        program = prog(asm.movz(3, 0x1234))
        ok(self, program)
        self.assertEqual(run(program["image"], {})[0]["x3"], 0x1234)

    def test_movz_lsl(self):
        # MOVZ X1, #0xABCD, LSL #16  and  MOVZ X2, #1, LSL #48
        ok(self, prog(asm.movz(1, 0xABCD, hw=1)))
        program = prog(asm.movz(2, 1, hw=3))
        ok(self, program)
        self.assertEqual(run(program["image"], {})[0]["x2"], 1 << 48)

    def test_movz_zeroes_prior_value(self):
        # MOVZ writes the immediate and zeroes every other bit (not OR/keep).
        program = prog(asm.movz(2, 5), init_regs={2: (1 << 64) - 1})
        ok(self, program)
        self.assertEqual(run(program["image"], {"regs": {2: (1 << 64) - 1}})[0]["x2"], 5)

    def test_movz_xzr_is_not_sp(self):
        # Rd == 31 is the zero register XZR for the move-wide class: the write is
        # discarded and sp is untouched (the SP-vs-XZR field-31 distinction).
        program = prog(asm.movz(31, 999), init_sp=100)
        ok(self, program)
        self.assertEqual(run(program["image"], {"sp": 100})[0]["sp"], 100)

    # --- mixed program over the whole in-scope family ----------------------
    def test_mixed_alu_program(self):
        # x0 = 0x1000 ; x1 = x0 + 0x20 ; x1 = x1 - 0x10 ; sp = sp - 0x40
        ok(self, prog(asm.movz(0, 0x1000), asm.add_imm(1, 0, 0x20),
                      asm.sub_imm(1, 1, 0x10), asm.sub_imm(asm.SP, asm.SP, 0x40),
                      init_sp=0x2000))

    def test_nzcv_preserved(self):
        # ADD/SUB/MOVZ all leave NZCV unchanged; seed nonzero flags, require they
        # survive across every in-scope op.
        program = prog(asm.add_imm(0, 0, 1), asm.sub_imm(0, 0, 1), asm.movz(1, 7),
                       init_nzcv=0b1010)
        ok(self, program)
        tr = run(program["image"], {"nzcv": 0b1010})
        self.assertTrue(all(row["nzcv"] == 0b1010 for row in tr))

    # --- twice-and-diff determinism (translator + interpreter) -------------
    def test_translator_deterministic(self):
        # Exercise every in-scope op in the one program the diff covers.
        p = prog(asm.add_imm(7, 7, 0x123), asm.sub_imm(7, 7, 0x10), asm.movz(8, 0xFF))
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        # canonical BTOR2 round-trips byte-exact (native-checker conformant)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_interpreter_deterministic(self):
        p = img(asm.movz(0, 5), asm.add_imm(1, 0, 9), asm.sub_imm(1, 1, 2))
        binding = {"regs": {2: 3}, "sp": 999, "nzcv": 0b0110}
        t1 = list(run(p, dict(binding)))
        t2 = list(run(p, dict(binding)))
        self.assertEqual(t1, t2)

    # --- carry-back: a BTOR2 witness replays through L to a source fact -----
    def test_lift_shapes_source_behavior(self):
        # Without a solver: the BTOR2 trace carries back into AArch64 observables.
        # Use SUB so the carried fact comes from a newly-covered op.
        program = prog(asm.movz(0, 50), asm.sub_imm(0, 0, 8))  # x0 = 50 - 8 = 42
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

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge_movz_sub(self):
        # A newly-covered op carries all the way through the reasoning path:
        # MOVZ x0,#50 ; SUB x0,x0,#8  =>  x0 == 42 is reachable, witness replayed.
        from gurdy.pairs.btor2_smtlib import reach

        program = prog(asm.movz(0, 50), asm.sub_imm(0, 0, 8),
                       property={"reg_eq": [0, 42]})
        info = reach(translate(program), 4)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("x0") == 42 for row in info["behavior"]))

    # --- honest coverage + rejection of out-of-scope constructs ------------
    def test_in_scope_construct_covered(self):
        report = coverage()
        for name in IN_SCOPE:
            self.assertIn(name, report.covered)
        self.assertEqual(report.fraction, len(IN_SCOPE) / report.total)

    def test_coverage_ratchet_grew(self):
        # The widening ratchet: ADD/SUB/MOVZ are all covered now (was ADD only),
        # the denominator is held fixed, and nothing previously covered dropped.
        report = coverage()
        self.assertEqual(report.total, 12)
        self.assertEqual(len(report.covered), 8)        # 4/12 -> 8/12
        for name in ("ADD_imm", "SUB_imm", "SUB_imm_sp", "MOVZ", "MOVZ_lsl16"):
            self.assertIn(name, report.covered)

    def test_out_of_scope_constructs_abort(self):
        for name, program in OUT_OF_SCOPE.items():
            with self.assertRaises(Unsupported, msg=name):
                translate(program)

    def test_still_unsupported_branch_load_flagset_abort(self):
        # A still-unsupported instruction (branch / load / flag-setting form)
        # keeps hard-aborting after the widening (BENCHMARKS.md §3), via both the
        # translator and the interpreter — the rejection boundary did not move.
        for word in (0x1400_0000,            # B .       (control flow)
                     0xF940_0000,            # LDR X0,[X0] (memory)
                     asm.adds_imm(0, 0, 1),  # ADDS      (flag-setting)
                     asm.subs_imm(0, 0, 1),  # SUBS      (flag-setting)
                     asm.add_imm_w(0, 0, 1), # 32-bit ADD
                     asm.movn(0, 1),         # MOVN      (move-wide sibling)
                     asm.movk(0, 1)):        # MOVK      (move-wide sibling)
            with self.assertRaises(Unsupported):
                translate(prog(word))
            with self.assertRaises(Unsupported):
                run(img(word), {})

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
