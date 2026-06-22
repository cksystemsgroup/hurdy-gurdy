"""aarch64-sail tests (the simple-ALU slice: ADD/SUB immediate + MOVZ).

Covers the PAIRING.md §7 minimum: twice-and-diff determinism for the translator
and for the *additive* AArch64 arm of the shared Sail interpreter; per-construct
translation unit tests against the spec (one per added op); the commuting square
``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle on programs using the
new ops; carry-back of a Sail-model behavior through ``L`` to a source-level
fact; and a registration smoke test (the pair is listed and every edge-op of its
square is callable). Also pins the honest ``unsupported`` histogram and the
rejection of out-of-scope constructs (BENCHMARKS.md §3) — incl. that a
still-unsupported instruction keeps hard-aborting after the Sail interp
``0.2`` → ``0.3`` widening — and, the reason the pair exists, a branch-agreement
check that ``aarch64-btor2`` and ``aarch64-sail`` agree on the ADD/SUB/MOVZ
effects under ``π`` (PATHS.md §4-5). It also pins that the additive Sail change
leaves the RISC-V Sail path untouched.
"""

import json
import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_pair, list_pairs
from gurdy.languages.aarch64 import asm
from gurdy.languages.aarch64.interp import (
    decode,
    decode_insn,
    program_from_words,
    run as a64_run,
)
from gurdy.languages.sail import run as sail_run
from gurdy.pairs.aarch64_sail import PROJECTION, square, translate
from gurdy.pairs.aarch64_sail.inventory import IN_SCOPE, OUT_OF_SCOPE, coverage
from gurdy.pairs.aarch64_sail.lift import lift


def img(*words):
    return program_from_words(list(words))


def prog(*words, **kw):
    return {"image": img(*words), **kw}


def ok(self, program):
    report = square(program)
    self.assertTrue(report.ok, msg=str(report.divergence))


def _sail_obj(program):
    return json.loads(translate(program).decode())


class TestAarch64Sail(unittest.TestCase):
    # --- registration smoke test (every edge-op callable) ------------------
    def test_registered(self):
        self.assertIn("aarch64-sail", list_pairs())

    def test_edge_ops_callable(self):
        pair = get_pair("aarch64-sail")
        self.assertEqual(pair.source, "aarch64")
        self.assertEqual(pair.target, "sail")
        program = prog(asm.add_imm(0, 0, 7))
        # translate (T)
        artifact = pair.translator(program)
        self.assertIsInstance(artifact, bytes)
        # interpret-source (I_s)
        src = list(pair.source_interpreter(program["image"], {}))
        self.assertTrue(src)
        # interpret-target (I_t) — the shared Sail interpreter, A64 arm
        tgt = sail_run(json.loads(artifact.decode()), {})
        self.assertTrue(tgt)
        # carry-back (L)
        carried = pair.target_to_source(tgt)
        self.assertEqual(len(carried), len(tgt))
        # cross-check (square)
        self.assertTrue(square(program).ok)

    # --- projection is exactly aarch64-btor2's (the branch must compare like) -
    def test_projection_matches_aarch64_btor2(self):
        from gurdy.pairs.aarch64_btor2 import PROJECTION as BTOR_PROJ
        self.assertEqual(PROJECTION.fields, BTOR_PROJ.fields)

    # --- per-construct translation unit test (against the spec) ------------
    def test_translate_emits_sail_object(self):
        obj = _sail_obj(prog(asm.add_imm(3, 5, 42), init_sp=100, init_nzcv=0b1010))
        self.assertEqual(obj["isa"], "aarch64")
        self.assertEqual(obj["words"], [asm.add_imm(3, 5, 42)])
        self.assertEqual(obj["init_sp"], 100)
        self.assertEqual(obj["init_nzcv"], 0b1010)

    def test_decode_add_immediate_spec(self):
        d = decode(asm.add_imm(3, 5, 42))
        self.assertEqual((d.rd, d.rn, d.imm), (3, 5, 42))
        d2 = decode(asm.add_imm(3, 5, 2, lsl12=True))
        self.assertEqual((d2.rd, d2.rn, d2.imm), (3, 5, 2 << 12))

    def test_decode_sub_immediate_spec(self):
        # SUB X3, X5, #42  ->  rd=3, rn=5, imm=42, op=sub (the widened decoder
        # this pair now uses as its translate-edge rejection gate).
        d = decode_insn(asm.sub_imm(3, 5, 42))
        self.assertEqual((d.rd, d.rn, d.imm, d.op), (3, 5, 42, "sub"))
        d2 = decode_insn(asm.sub_imm(3, 5, 2, lsl12=True))
        self.assertEqual((d2.rd, d2.rn, d2.imm, d2.op), (3, 5, 2 << 12, "sub"))
        d3 = decode_insn(asm.sub_imm(asm.SP, asm.SP, 16))   # field 31 = SP
        self.assertEqual((d3.rd, d3.rn, d3.op), (31, 31, "sub"))

    def test_decode_movz_spec(self):
        # MOVZ X7, #42 -> rd=7, imm=42, op=movz (and == the legacy 0xD2800540).
        self.assertEqual(asm.movz(0, 42), 0xD280_0540)
        d = decode_insn(asm.movz(7, 42))
        self.assertEqual((d.rd, d.imm, d.op), (7, 42, "movz"))
        d2 = decode_insn(asm.movz(1, 0xABCD, hw=1))          # LSL #16
        self.assertEqual((d2.rd, d2.imm, d2.op), (1, 0xABCD << 16, "movz"))
        d3 = decode_insn(asm.movz(2, 0x1, hw=3))             # LSL #48
        self.assertEqual((d3.rd, d3.imm, d3.op), (2, 1 << 48, "movz"))

    # --- commuting square on a small corpus --------------------------------
    def test_add_immediate(self):
        ok(self, prog(asm.add_imm(0, 0, 5)))

    def test_add_immediate_chain(self):
        ok(self, prog(asm.add_imm(0, 0, 5), asm.add_imm(1, 0, 3),
                      asm.add_imm(2, 1, 0xFFF)))

    def test_add_immediate_lsl12(self):
        ok(self, prog(asm.add_imm(4, 0, 1, lsl12=True)))  # x4 = 4096

    def test_add_immediate_init_regs(self):
        ok(self, prog(asm.add_imm(0, 1, 0), init_regs={1: 0xDEAD_BEEF}))

    def test_add_immediate_sp(self):
        # sp += 16 (Rn=Rd=31), then x5 = sp + 0 ; exercises SP read+write.
        ok(self, prog(asm.add_imm(asm.SP, asm.SP, 16), asm.add_imm(5, asm.SP, 0),
                      init_sp=100))

    def test_add_immediate_wraps_modulo_2_64(self):
        ok(self, prog(asm.add_imm(0, 1, 1), init_regs={1: (1 << 64) - 1}))

    # --- SUB (immediate), 64-bit (Sail interp 0.3) -------------------------
    def test_sub_immediate(self):
        # x0 = 100 (movz) ; x0 = x0 - 7 = 93 — through the Sail Expr datapath.
        program = prog(asm.movz(0, 100), asm.sub_imm(0, 0, 7))
        ok(self, program)
        self.assertEqual(a64_run(program["image"], {})[-2]["x0"], 93)

    def test_sub_immediate_lsl12(self):
        ok(self, prog(asm.sub_imm(0, 1, 1, lsl12=True), init_regs={1: 0x2000}))

    def test_sub_immediate_sp(self):
        # sp -= 16 (Rn=Rd=31), then x5 = sp + 0 ; exercises SP read+write on SUB.
        program = prog(asm.sub_imm(asm.SP, asm.SP, 16), asm.add_imm(5, asm.SP, 0),
                       init_sp=100)
        ok(self, program)
        self.assertEqual(a64_run(program["image"], {"sp": 100})[0]["sp"], 84)

    def test_sub_immediate_wraps_modulo_2_64(self):
        # 0 - 1 wraps to 2^64 - 1; the ISA-defined wrap, the square must hold.
        program = prog(asm.sub_imm(0, 0, 1))
        ok(self, program)
        self.assertEqual(a64_run(program["image"], {})[0]["x0"], (1 << 64) - 1)

    # --- MOVZ (move wide immediate), 64-bit (Sail interp 0.3) --------------
    def test_movz(self):
        program = prog(asm.movz(3, 0x1234))
        ok(self, program)
        self.assertEqual(a64_run(program["image"], {})[0]["x3"], 0x1234)

    def test_movz_lsl(self):
        ok(self, prog(asm.movz(1, 0xABCD, hw=1)))
        program = prog(asm.movz(2, 1, hw=3))
        ok(self, program)
        self.assertEqual(a64_run(program["image"], {})[0]["x2"], 1 << 48)

    def test_movz_zeroes_prior_value(self):
        # MOVZ writes the immediate and zeroes every other bit (not OR/keep).
        program = prog(asm.movz(2, 5), init_regs={2: (1 << 64) - 1})
        ok(self, program)
        self.assertEqual(
            a64_run(program["image"], {"regs": {2: (1 << 64) - 1}})[0]["x2"], 5)

    def test_movz_xzr_is_not_sp(self):
        # Rd == 31 is the zero register XZR for the move-wide class: the write is
        # discarded and sp is untouched. This SP-vs-XZR field-31 distinction is
        # the only real subtlety; the Sail A64 arm must get it right.
        program = prog(asm.movz(31, 999), init_sp=100)
        ok(self, program)
        self.assertEqual(a64_run(program["image"], {"sp": 100})[0]["sp"], 100)
        # ...and through the Sail interpreter itself, sp stays 100 across the run.
        tr = sail_run(_sail_obj(program), {})
        self.assertTrue(all(row["sp"] == 100 for row in tr))

    # --- mixed program over the whole in-scope family ----------------------
    def test_mixed_alu_program(self):
        # x0 = 0x1000 ; x1 = x0 + 0x20 ; x1 = x1 - 0x10 ; sp = sp - 0x40
        ok(self, prog(asm.movz(0, 0x1000), asm.add_imm(1, 0, 0x20),
                      asm.sub_imm(1, 1, 0x10), asm.sub_imm(asm.SP, asm.SP, 0x40),
                      init_sp=0x2000))

    def test_nzcv_preserved(self):
        # ADD/SUB/MOVZ all leave NZCV unchanged; seed nonzero flags and require
        # they survive across every in-scope op through the Sail A64 arm.
        program = prog(asm.add_imm(0, 0, 1), asm.sub_imm(0, 0, 1), asm.movz(1, 7),
                       init_nzcv=0b1010)
        ok(self, program)
        tr = sail_run(_sail_obj(program), {})
        self.assertTrue(all(row["nzcv"] == 0b1010 for row in tr))

    # --- twice-and-diff determinism (translator + Sail A64 arm) ------------
    def test_translator_deterministic(self):
        # Exercise every in-scope op in the one program the diff covers.
        p = prog(asm.add_imm(7, 7, 0x123), asm.sub_imm(7, 7, 0x10),
                 asm.movz(8, 0xFF), init_sp=42, init_nzcv=0b0110)
        self.assertEqual(translate(p), translate(p))

    def test_sail_aarch64_arm_deterministic(self):
        obj = _sail_obj(prog(asm.movz(0, 5), asm.add_imm(1, 0, 9),
                             asm.sub_imm(1, 1, 2), init_regs={2: 3}, init_sp=999,
                             init_nzcv=0b0110))
        t1 = list(sail_run(json.loads(json.dumps(obj)), {}))
        t2 = list(sail_run(json.loads(json.dumps(obj)), {}))
        self.assertEqual(t1, t2)

    # --- carry-back: a Sail-model behavior replays through L to a source fact -
    def test_lift_shapes_source_behavior(self):
        # Use MOVZ+SUB so the carried fact comes from newly-covered ops.
        program = prog(asm.movz(0, 50), asm.sub_imm(0, 0, 8))  # x0 = 50 - 8 = 42
        carried = lift(sail_run(_sail_obj(program), {}))
        # Every projected observable is present in the carried behavior.
        self.assertEqual(set(PROJECTION.fields) - set(carried[-1]), set())
        self.assertTrue(any(row.get("x0") == 42 for row in carried))

    def test_carry_back_matches_source_under_pi(self):
        # The carried-back Sail behavior equals the source behavior under pi —
        # i.e. L(I_t(T(p))) is a genuine source-level behavior, not just shaped.
        program = prog(asm.add_imm(5, asm.SP, 8), init_sp=200)
        src = list(a64_run(program["image"], {"sp": 200}))
        carried = lift(sail_run(_sail_obj(program), {}))
        sel = lambda rows: [PROJECTION.select(r) for r in rows]
        self.assertEqual(sel(src), sel(carried))

    # --- branch agreement: aarch64-btor2 vs aarch64-sail (the reason to exist) -
    def _assert_branch_agrees(self, program, init_sp, init_nzcv=0):
        # The two AArch64->BTOR2 routes must carry back identical behavior under
        # pi: the direct aarch64-btor2 route and the Sail-mediated aarch64-sail
        # route. aarch64-btor2 is read READ-ONLY here (we never modify it).
        from gurdy.languages.btor2 import interpret
        from gurdy.pairs.aarch64_btor2 import translate as btor_translate
        from gurdy.pairs.aarch64_btor2.lift import lift as btor_lift

        n = len(a64_run(program["image"], {"sp": init_sp, "nzcv": init_nzcv}))
        b_carried = btor_lift(interpret(btor_translate({**program, "init_sp": init_sp}),
                                        {"steps": n + 1}))[1:n + 1]
        s_carried = lift(sail_run(_sail_obj(program), {}))
        sel = lambda rows: [PROJECTION.select(r) for r in rows]
        self.assertEqual(sel(b_carried), sel(s_carried))

    def test_branch_agreement_with_aarch64_btor2(self):
        program = prog(asm.add_imm(asm.SP, asm.SP, 16), asm.add_imm(5, asm.SP, 0),
                       asm.add_imm(0, 0, 5), init_sp=100, init_nzcv=0b0110)
        self._assert_branch_agrees(program, init_sp=100, init_nzcv=0b0110)

    def test_branch_agreement_sub_movz(self):
        # The branch must agree on the *newly mirrored* SUB/MOVZ effects too,
        # including the SP-vs-XZR field-31 distinction (MOVZ to Rd=31 is XZR, so
        # sp is left untouched while SUB on field 31 writes sp).
        program = prog(asm.movz(0, 0x1000), asm.sub_imm(0, 0, 0x10),
                       asm.movz(31, 999), asm.sub_imm(asm.SP, asm.SP, 0x40),
                       asm.movz(1, 0xABCD, hw=1), init_sp=0x2000, init_nzcv=0b1010)
        self._assert_branch_agrees(program, init_sp=0x2000, init_nzcv=0b1010)

    # --- the additive Sail change leaves the RISC-V path untouched ----------
    def test_riscv_sail_path_unaffected(self):
        # A RISC-V Sail object (no `isa` key) still runs the RISC-V executor and
        # produces the RISC-V trace shape {pc, x1..x31, halted} — no x0/sp/nzcv.
        from gurdy.languages.riscv import asm as rvasm
        prog_rv = {"words": [rvasm.addi(1, 0, 7), rvasm.ecall()], "entry": 0}
        tr = list(sail_run(prog_rv, {}))
        self.assertEqual(tr[0]["x1"], 7)
        self.assertNotIn("sp", tr[0])
        self.assertNotIn("nzcv", tr[0])

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

    def test_covered_set_coincides_with_aarch64_btor2(self):
        # Branch agreement at the coverage level: the two AArch64->BTOR2 routes
        # must now cover the *same* constructs on the same yardstick. (Read
        # aarch64-btor2 READ-ONLY.)
        from gurdy.pairs.aarch64_btor2.inventory import coverage as btor_coverage
        self.assertEqual(coverage().covered, btor_coverage().covered)

    def test_out_of_scope_constructs_abort(self):
        for name, program in OUT_OF_SCOPE.items():
            with self.assertRaises(Unsupported, msg=name):
                translate(program)

    def test_still_unsupported_branch_load_flagset_abort(self):
        # A still-unsupported instruction (branch / load / flag-setting / 32-bit
        # / move-wide sibling) keeps hard-aborting after the 0.2 -> 0.3 widening
        # (BENCHMARKS.md §3), via both the translator and the Sail A64 arm — the
        # rejection boundary moved only by exactly SUB + MOVZ.
        for word in (0x1400_0000,             # B .        (control flow)
                     0xF940_0000,             # LDR X0,[X0] (memory)
                     asm.adds_imm(0, 0, 1),   # ADDS       (flag-setting)
                     asm.subs_imm(0, 0, 1),   # SUBS       (flag-setting)
                     asm.add_imm_w(0, 0, 1),  # 32-bit ADD
                     asm.movn(0, 1),          # MOVN       (move-wide sibling)
                     asm.movk(0, 1)):         # MOVK       (move-wide sibling)
            with self.assertRaises(Unsupported):
                translate(prog(word))
            with self.assertRaises(Unsupported):
                sail_run({"isa": "aarch64", "words": [word], "entry": 0}, {})

    def test_unsupported_histogram(self):
        report = coverage()
        self.assertEqual(sum(report.histogram.values()), len(OUT_OF_SCOPE))
        self.assertEqual(report.missing.keys(), OUT_OF_SCOPE.keys())

    def test_unsupported_is_typed_and_named(self):
        with self.assertRaises(Unsupported) as cm:
            translate(prog(0xD503_201F))     # NOP, via the translator
        self.assertEqual(cm.exception.language, "aarch64")
        self.assertTrue(cm.exception.construct)


if __name__ == "__main__":
    unittest.main()
