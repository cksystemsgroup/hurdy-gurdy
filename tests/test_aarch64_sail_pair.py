"""aarch64-sail tests (interp 0.4: ADD/SUB/MOVZ + SUBS/CMP + B.cond).

Covers the PAIRING.md §7 minimum: twice-and-diff determinism for the translator
and for the *additive* AArch64 arm of the shared Sail interpreter; per-construct
translation unit tests against the spec (one per added op); the commuting square
``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle on programs using the
new ops; carry-back of a Sail-model behavior through ``L`` to a source-level
fact; and a registration smoke test (the pair is listed and every edge-op of its
square is callable). For the ``0.3`` → ``0.4`` widening specifically: ``SUBS``/
``CMP`` setting each of ``N``/``Z``/``C``/``V`` (incl. the ``CMP`` write-discard
and the SP-source case); ``B.cond`` taken vs not-taken across the full condition
table; a branching program (``CMP`` then ``B.EQ`` over two paths); a back-branch
loop; and carry-back of a branch-taken run. Also pins the honest ``unsupported``
histogram and the rejection of out-of-scope constructs (BENCHMARKS.md §3) — incl.
that a still-unsupported instruction keeps hard-aborting after the Sail interp
``0.3`` → ``0.4`` widening — and, the reason the pair exists, a branch-agreement
check that ``aarch64-btor2`` and ``aarch64-sail`` now agree on the *same* set of
constructs (ADD/SUB/MOVZ + SUBS/CMP + B.cond) under ``π`` (PATHS.md §4-5), with a
coverage-level equality check that the two routes' covered sets coincide exactly.
It also pins that the additive Sail change leaves the RISC-V Sail path untouched.
"""

import json
import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_pair, list_pairs
from gurdy.languages.aarch64 import asm
from gurdy.languages.aarch64.interp import (
    decode,
    decode_insn,
    decode_insn_v3,
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

    # --- SUBS / CMP (immediate), 64-bit: the first NZCV write (Sail interp 0.4)
    def test_decode_subs_cmp_spec(self):
        # SUBS X1, X0, #7  ->  rd=1, rn=0, imm=7, op=subs (the v3 gate this pair
        # now uses as its translate-edge rejection point).
        d = decode_insn_v3(asm.subs_imm(1, 0, 7))
        self.assertEqual((d.rd, d.rn, d.imm, d.op), (1, 0, 7, "subs"))
        # CMP X0, #5 == SUBS XZR, X0, #5  ->  rd=31 (XZR), op=subs.
        c = decode_insn_v3(asm.cmp_imm(0, 5))
        self.assertEqual((c.rd, c.rn, c.imm, c.op), (31, 0, 5, "subs"))
        d2 = decode_insn_v3(asm.subs_imm(1, asm.SP, 2, lsl12=True))
        self.assertEqual((d2.rn, d2.imm, d2.op), (31, 2 << 12, "subs"))
        # The 0.2 decoder still rejects SUBS (it was the *old* sail gate).
        with self.assertRaises(Unsupported):
            decode_insn(asm.subs_imm(1, 0, 7))

    def _subs_state(self, minuend, imm):
        # MOVZ x0,#minuend ; SUBS x1,x0,#imm — the post-SUBS state, run through
        # the Sail A64 arm (and square-checked), so the NZCV pack is the
        # Sail-derived Expr datapath, not hand Python.
        program = prog(asm.movz(0, minuend), asm.subs_imm(1, 0, imm))
        ok(self, program)
        tr = sail_run(_sail_obj(program), {})
        return tr[1]  # state after the SUBS

    def test_subs_flag_N(self):
        # 1 - 2 = -1 (bit63 set) => N=1, no Z; borrow so C=0; no signed overflow.
        s = self._subs_state(1, 2)
        self.assertEqual(s["x1"], (1 << 64) - 1)
        self.assertEqual(s["nzcv"], 0b1000)        # N only

    def test_subs_flag_Z(self):
        # 5 - 5 = 0 => Z=1, and no borrow so C=1.
        s = self._subs_state(5, 5)
        self.assertEqual(s["x1"], 0)
        self.assertEqual(s["nzcv"], 0b0110)        # Z and C

    def test_subs_flag_C_borrow(self):
        # 3 - 5 borrows (3 <u 5) => C=0 (and N=1 since the result is negative).
        s = self._subs_state(3, 5)
        self.assertEqual(s["nzcv"] & 0b0010, 0)    # C clear (borrow)
        self.assertEqual(s["nzcv"] & 0b1000, 0b1000)  # N set

    def test_subs_flag_V_signed_overflow(self):
        # INT64_MIN - 1 signed-overflows: V=1. minuend = 0x8000<<48 = 2^63.
        program = prog(asm.movz(0, 0x8000, hw=3), asm.subs_imm(1, 0, 1))
        ok(self, program)
        s = sail_run(_sail_obj(program), {})[1]
        self.assertEqual(s["nzcv"] & 0b0001, 0b0001)  # V set

    def test_cmp_discards_result_sets_flags(self):
        # CMP X0,#5 (= SUBS XZR): x0 unchanged, but NZCV reflects x0 - 5.
        program = prog(asm.movz(0, 5), asm.cmp_imm(0, 5))
        ok(self, program)
        s = sail_run(_sail_obj(program), {})[1]
        self.assertEqual(s["x0"], 5)               # the write is discarded (XZR)
        self.assertEqual(s["nzcv"], 0b0110)        # Z and C (5 - 5 == 0)

    def test_cmp_sp_source(self):
        # CMP SP, #16 reads the stack pointer as Rn (field 31 = SP for source).
        program = prog(asm.cmp_imm(asm.SP, 16), init_sp=16)
        ok(self, program)
        s = sail_run(_sail_obj(program), {})[0]
        self.assertEqual(s["sp"], 16)              # sp untouched
        self.assertEqual(s["nzcv"], 0b0110)        # 16 - 16 == 0 => Z, C

    # --- B.cond (conditional branch): the first conditional pc update (0.4) ---
    def test_decode_bcond_spec(self):
        d = decode_insn_v3(asm.b_cond("EQ", 8))
        self.assertEqual((d.op, d.cond, d.offset), ("bcond", asm.COND["EQ"], 8))
        d2 = decode_insn_v3(asm.b_cond("NE", -4))     # backward branch
        self.assertEqual((d2.op, d2.cond, d2.offset), ("bcond", asm.COND["NE"], -4))
        # The 0.2 decoder still rejects B.cond.
        with self.assertRaises(Unsupported):
            decode_insn(asm.b_cond("EQ", 8))

    def _bcond_prog(self, cond, init_regs):
        # @0 CMP x0,#5 ; @4 B.cond +8 ; @8 MOVZ x1,#100 ; @12 MOVZ x2,#200
        # Taken => skip the @8 write (x1 stays 0); not-taken => x1 = 100.
        return prog(asm.cmp_imm(0, 5), asm.b_cond(cond, 8),
                    asm.movz(1, 100), asm.movz(2, 200), init_regs=init_regs)

    def test_bcond_eq_taken_and_not_taken(self):
        # CMP x0,#5: x0==5 => Z=1 => B.EQ taken (x1 stays 0); x0==3 => not taken.
        taken = self._bcond_prog("EQ", {0: 5})
        ok(self, taken)
        self.assertEqual(sail_run(_sail_obj(taken), {})[-2]["x1"], 0)
        not_taken = self._bcond_prog("EQ", {0: 3})
        ok(self, not_taken)
        self.assertEqual(sail_run(_sail_obj(not_taken), {})[-2]["x1"], 100)

    def test_bcond_ne_taken_and_not_taken(self):
        not_taken = self._bcond_prog("NE", {0: 5})   # Z=1 => NE not taken
        ok(self, not_taken)
        self.assertEqual(sail_run(_sail_obj(not_taken), {})[-2]["x1"], 100)
        taken = self._bcond_prog("NE", {0: 3})       # Z=0 => NE taken
        ok(self, taken)
        self.assertEqual(sail_run(_sail_obj(taken), {})[-2]["x1"], 0)

    def test_bcond_full_condition_table_square(self):
        # CMP x0,#5 then each of the 16 conditions over two register values, so
        # both taken and not-taken arms are exercised, and the square must hold.
        for code in asm.COND:
            for x0 in (3, 5, 7):
                ok(self, self._bcond_prog(code, {0: x0}))

    def test_bcond_backward_loop(self):
        # A real loop: MOVZ x0,#3 ; (L) SUBS x0,x0,#1 ; B.NE L ; fall off end.
        program = prog(asm.movz(0, 3), asm.subs_imm(0, 0, 1), asm.b_cond("NE", -4))
        ok(self, program)
        self.assertEqual(a64_run(program["image"], {})[-2]["x0"], 0)

    def test_bcond_branching_square_two_paths(self):
        # The brief's commuting-square check: CMP then B.EQ over two paths, both
        # fully cross-checked through the Sail route under pi.
        ok(self, self._bcond_prog("EQ", {0: 5}))     # taken arm
        ok(self, self._bcond_prog("EQ", {0: 3}))     # fall-through arm

    # --- mixed program over the whole in-scope family ----------------------
    def test_mixed_alu_program(self):
        # x0 = 0x1000 ; x1 = x0 + 0x20 ; x1 = x1 - 0x10 ; sp = sp - 0x40
        ok(self, prog(asm.movz(0, 0x1000), asm.add_imm(1, 0, 0x20),
                      asm.sub_imm(1, 1, 0x10), asm.sub_imm(asm.SP, asm.SP, 0x40),
                      init_sp=0x2000))

    def test_mixed_program_with_flags_and_branch(self):
        # Exercise every in-scope op (incl. the 0.4 SUBS/CMP + B.cond) in one
        # program, fully square-checked through the Sail route.
        ok(self, prog(asm.movz(0, 0x1000), asm.add_imm(1, 0, 0x20),
                      asm.sub_imm(1, 1, 0x10), asm.movz(8, 0xFF),
                      asm.subs_imm(9, 8, 0x10), asm.cmp_imm(7, 1),
                      asm.b_cond("NE", -4)))

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
        # Exercise every in-scope op (incl. the 0.4 SUBS/CMP + B.cond) in the one
        # program the diff covers.
        p = prog(asm.add_imm(7, 7, 0x123), asm.sub_imm(7, 7, 0x10),
                 asm.movz(8, 0xFF), asm.subs_imm(9, 8, 0x10), asm.cmp_imm(7, 1),
                 asm.b_cond("NE", -4), init_sp=42, init_nzcv=0b0110)
        self.assertEqual(translate(p), translate(p))

    def test_sail_aarch64_arm_deterministic(self):
        obj = _sail_obj(prog(asm.movz(0, 5), asm.add_imm(1, 0, 9),
                             asm.sub_imm(1, 1, 2), asm.subs_imm(2, 1, 1),
                             asm.cmp_imm(0, 5), asm.b_cond("EQ", 8),
                             init_regs={3: 3}, init_sp=999, init_nzcv=0b0110))
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

    def test_carry_back_of_branch_taken_run(self):
        # Carry-back of a *branch-taken* run through L: MOVZ x0,#5 ; CMP x0,#5
        # (=> Z) ; B.EQ +8 (taken, skips MOVZ x1,#1) ; MOVZ x2,#2. So x1 stays 0
        # and x2 == 2, and the carried source behavior must show that (pc jumps).
        program = prog(asm.movz(0, 5), asm.cmp_imm(0, 5), asm.b_cond("EQ", 8),
                       asm.movz(1, 1), asm.movz(2, 2))
        ok(self, program)
        carried = lift(sail_run(_sail_obj(program), {}))
        # The branch was taken: x1 is never written (stays 0), x2 == 2 at the end.
        self.assertTrue(all(row.get("x1") == 0 for row in carried))
        self.assertEqual(carried[-1]["x2"], 2)
        # ...and a pc that jumps from the B.cond (@8) straight to @16 (skipping @12).
        self.assertIn(16, [row["pc"] for row in carried])
        self.assertNotIn(12, [row["pc"] for row in carried])

    # --- branch agreement: aarch64-btor2 vs aarch64-sail (the reason to exist) -
    def _assert_branch_agrees(self, program, init_sp, init_nzcv=0):
        # The two AArch64->BTOR2 routes must carry back identical behavior under
        # pi: the direct aarch64-btor2 route and the Sail-mediated aarch64-sail
        # route. aarch64-btor2 is read READ-ONLY here (we never modify it). The
        # program carries its own init_sp/init_nzcv/init_regs (so both translators
        # read the same initial state); we pass init_sp/init_nzcv to btor_translate
        # / the source-length computation to match.
        from gurdy.languages.btor2 import interpret
        from gurdy.pairs.aarch64_btor2 import translate as btor_translate
        from gurdy.pairs.aarch64_btor2.lift import lift as btor_lift

        init_regs = program.get("init_regs", {})
        n = len(a64_run(program["image"],
                        {"regs": init_regs, "sp": init_sp, "nzcv": init_nzcv}))
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

    def test_branch_agreement_subs_cmp(self):
        # The branch must agree on the *0.4* SUBS/CMP effects (the NZCV pack):
        # SUBS X1,X0,#7 sets the flags; CMP SP,#16 reads SP as source + discards.
        program = prog(asm.movz(0, 0x1000), asm.subs_imm(1, 0, 7),
                       asm.cmp_imm(asm.SP, 16), asm.subs_imm(2, 1, 0xFFF),
                       init_sp=16, init_nzcv=0b0000)
        self._assert_branch_agrees(program, init_sp=16)

    def test_branch_agreement_bcond_full_table(self):
        # The branch must agree on B.cond over the *full* condition table, both
        # taken and not-taken: CMP x0,#5 then B.cond +8 over three reg values.
        for code in asm.COND:
            for x0 in (3, 5, 7):
                program = prog(asm.cmp_imm(0, 5), asm.b_cond(code, 8),
                               asm.movz(1, 1), asm.movz(2, 2), init_regs={0: x0})
                self._assert_branch_agrees(program, init_sp=1 << 20)

    def test_branch_agreement_bcond_loop(self):
        # A back-branch loop must agree across both routes (the same pc trajectory
        # and final register state under pi).
        program = prog(asm.movz(0, 3), asm.subs_imm(0, 0, 1), asm.b_cond("NE", -4))
        self._assert_branch_agrees(program, init_sp=1 << 20)

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
        # The widening ratchet: SUBS/CMP + B.cond are covered now (interp 0.4),
        # the denominator only grew by the new in-scope probes, and nothing
        # previously covered dropped.
        report = coverage()
        self.assertEqual(report.total, 15)              # 12 -> 15 (3 new probes)
        self.assertEqual(len(report.covered), 11)       # 8/12 -> 11/15
        for name in ("ADD_imm", "SUB_imm", "SUB_imm_sp", "MOVZ", "MOVZ_lsl16",
                     "SUBS_imm", "CMP_imm", "Bcond"):
            self.assertIn(name, report.covered)

    def test_covered_set_coincides_with_aarch64_btor2(self):
        # Branch agreement at the coverage level: the two AArch64->BTOR2 routes
        # decide *exactly* the same constructs. aarch64-sail has now mirrored the
        # interp-0.3 ops aarch64-btor2 added (SUBS/CMP + B.cond — the first NZCV
        # write and the first conditional control flow), so the two routes'
        # covered sets COINCIDE exactly (full equality restored). (Read
        # aarch64-btor2 READ-ONLY.)
        from gurdy.pairs.aarch64_btor2.inventory import coverage as btor_coverage
        sail_covered = coverage().covered
        btor_covered = btor_coverage().covered
        self.assertEqual(sail_covered, btor_covered)

    def test_out_of_scope_constructs_abort(self):
        for name, program in OUT_OF_SCOPE.items():
            with self.assertRaises(Unsupported, msg=name):
                translate(program)

    def test_still_unsupported_branch_load_flagset_abort(self):
        # A still-unsupported instruction (unconditional branch / load / the
        # flag-setting ADDS / 32-bit form / move-wide sibling) keeps hard-aborting
        # after the 0.3 -> 0.4 widening (BENCHMARKS.md §3), via both the
        # translator and the Sail A64 arm — the rejection boundary moved only by
        # exactly SUBS/CMP + B.cond (so SUBS and B.cond are NO LONGER here).
        for word in (0x1400_0000,             # B .         (unconditional branch)
                     0xF940_0000,             # LDR X0,[X0] (memory)
                     asm.adds_imm(0, 0, 1),   # ADDS        (flag-setting ADD)
                     asm.add_imm_w(0, 0, 1),  # 32-bit ADD
                     asm.movn(0, 1),          # MOVN        (move-wide sibling)
                     asm.movk(0, 1)):         # MOVK        (move-wide sibling)
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
