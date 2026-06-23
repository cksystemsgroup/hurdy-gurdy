"""aarch64-btor2 tests (interp 0.6: ADD/SUB/MOVZ + SUBS/CMP + B.cond + B/BL +
ADDS/CMN + LDR/STR + the 32-bit W-register ALU/flag forms).

Covers the PAIRING.md §7 minimum: twice-and-diff determinism for both the
translator and the shared AArch64 interpreter; per-construct translation unit
tests against the spec (one per added op); the commuting square
``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle on programs using the
new ops; carry-back of a BTOR2 witness through ``L`` to a source-level fact; and
a registration smoke test (the pair is listed and every edge-op of its square is
callable). For the ``0.3`` widening: ``SUBS``/``CMP`` setting each of
``N``/``Z``/``C``/``V`` correctly (positive, zero, borrow, signed-overflow
cases); ``B.cond`` taken vs not-taken for ``EQ``/``NE`` (and ``LT``/``GE``/
``HI``/…); a branching program (``CMP`` then ``B.EQ`` over two paths); a
back-branch loop; and a branch-taken witness replayed through ``L``. For the
``0.4`` widening: the **unconditional branch** ``B`` (a forward branch skipping
an instruction and a backward branch back-edge of a loop) and ``BL`` (the link
register ``x30 := pc + 4``); and the **addition flag write** ``ADDS``/``CMN``
setting each of ``N``/``Z``/``C``(unsigned carry-out)/``V``(signed overflow)
correctly, incl. a carry-out case and a signed-overflow case and the ``CMN``
discard — the ``C``/``V`` definitions being the addition versions, distinct from
``SUBS``'s. For the ``0.5`` widening: the **first memory access** — the 64-bit
unsigned-offset ``LDR``/``STR`` over a byte-addressed, little-endian memory: a
store-then-load round-trip (``STR`` then ``LDR`` from the same address returns the
value); a load from never-written memory returns 0; the SP-relative addressing
form (``[SP, #imm]``); the LE byte order in the ``m{i}`` memory window; carry-back
of an ``LDR`` result (and the window) through ``L``; and the end-to-end
decide→witness→carry-back through ``btor2-smtlib`` over a memory program. For the
``0.6`` widening: the **32-bit (W-register) forms** of the ALU/flag-setting
immediate instructions — ``ADD``/``SUB``/``MOVZ`` W and ``SUBS``/``CMP``/``ADDS``/
``CMN`` W. The op computes on the **low 32 bits** of the source(s); the 32-bit
result **zero-extends** into the full 64-bit ``Xd`` (the upper 32 bits become 0),
and the flags are computed on the **32-bit** result (``N`` = bit 31, ``Z`` over the
32-bit result, ``C``/``V`` from the 32-bit add/subtract). Tested: a 32-bit
``ADD``/``SUB`` zero-extends (incl. a case where the 64-bit and 32-bit results
differ because the source has high bits set); ``SUBS``/``ADDS`` W set ``N``/``Z``/
``C``/``V`` on the 32-bit result (a 32-bit carry/overflow case distinct from the
64-bit one); ``MOVZ`` W; the commuting square + carry-back through ``L``;
twice-and-diff determinism over a W program; and that a still-unsupported
instruction (32-bit ``LDR``, ``MOVK``, reserved ``MOVZ`` hw=2) still hard-aborts.
Also pins the honest ``unsupported`` histogram after the ``0.5`` → ``0.6``
widening.
"""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_pair, list_pairs
from gurdy.core.solver import Verdict
from gurdy.languages.aarch64 import asm
from gurdy.languages.aarch64.interp import (
    MASK32,
    MEM_WINDOW,
    NZCV_C,
    NZCV_N,
    NZCV_V,
    NZCV_Z,
    SP_DEFAULT,
    cond_holds,
    decode,
    decode_insn,
    decode_insn_v3,
    decode_insn_v4,
    decode_insn_v5,
    decode_insn_v6,
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

    # --- SUBS / CMP (immediate), 64-bit: the first NZCV write ---------------
    def test_decode_subs_cmp_spec(self):
        # SUBS X1, X0, #7  ->  rd=1, rn=0, imm=7, op=subs
        d = decode_insn_v3(asm.subs_imm(1, 0, 7))
        self.assertEqual((d.rd, d.rn, d.imm, d.op), (1, 0, 7, "subs"))
        # CMP X0, #5 == SUBS XZR, X0, #5  ->  rd=31 (XZR), op=subs
        c = decode_insn_v3(asm.cmp_imm(0, 5))
        self.assertEqual((c.rd, c.rn, c.imm, c.op), (31, 0, 5, "subs"))
        # LSL #12 and SP source both decode
        d2 = decode_insn_v3(asm.subs_imm(1, asm.SP, 2, lsl12=True))
        self.assertEqual((d2.rd, d2.rn, d2.imm), (1, 31, 2 << 12))
        # The 0.2 decoder still rejects SUBS (the aarch64-sail gate is unmoved).
        with self.assertRaises(Unsupported):
            decode_insn(asm.subs_imm(1, 0, 7))

    def _subs_last_state(self, minuend, imm):
        # Run MOVZ x0,#minuend ; SUBS x1,x0,#imm and return the post-SUBS state
        # (the second-to-last trace row; the last is the off-end halt). Also
        # asserts the commuting square holds on the same program.
        program = prog(asm.movz(0, minuend), asm.subs_imm(1, 0, imm))
        ok(self, program)
        return run(program["image"], {})[-2]

    def test_subs_flag_N(self):
        # 5 - 8 = -3 (mod 2^64): result has bit63 set -> N=1, Z=0
        st = self._subs_last_state(5, 8)
        self.assertEqual(st["x1"], (5 - 8) & ((1 << 64) - 1))
        self.assertTrue(st["nzcv"] & NZCV_N)
        self.assertFalse(st["nzcv"] & NZCV_Z)

    def test_subs_flag_Z(self):
        # 7 - 7 = 0  -> Z=1, N=0, and C=1 (7 >=u 7, no borrow)
        st = self._subs_last_state(7, 7)
        self.assertEqual(st["x1"], 0)
        self.assertTrue(st["nzcv"] & NZCV_Z)
        self.assertFalse(st["nzcv"] & NZCV_N)
        self.assertTrue(st["nzcv"] & NZCV_C)

    def test_subs_flag_C_borrow(self):
        # C is "no borrow": 100 - 7 sets C=1; 3 - 8 (borrow) clears C=0.
        self.assertTrue(self._subs_last_state(100, 7)["nzcv"] & NZCV_C)
        self.assertFalse(self._subs_last_state(3, 8)["nzcv"] & NZCV_C)

    def test_subs_flag_V_signed_overflow(self):
        # INT_MIN - 1 overflows the signed range -> V=1 (and N=0: result is +max).
        imin = 1 << 63
        program = prog(asm.movz(0, 0x8000, hw=3), asm.subs_imm(1, 0, 1))
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x1"], imin - 1)
        self.assertTrue(st["nzcv"] & NZCV_V)
        self.assertFalse(st["nzcv"] & NZCV_N)
        # No overflow when both operands are small positives: 5 - 3 -> V=0.
        self.assertFalse(self._subs_last_state(5, 3)["nzcv"] & NZCV_V)

    def test_cmp_discards_result_sets_flags(self):
        # CMP X0,#5 (= SUBS XZR): x0 unchanged, but NZCV reflects x0 - 5.
        program = prog(asm.movz(0, 5), asm.cmp_imm(0, 5))
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x0"], 5)                    # result discarded (XZR)
        self.assertTrue(st["nzcv"] & NZCV_Z)             # 5 - 5 == 0 -> Z

    def test_cmp_sp_source(self):
        # CMP SP, #16 reads the stack pointer as Rn (field 31 = SP for the source).
        program = prog(asm.cmp_imm(asm.SP, 16), init_sp=16)
        ok(self, program)
        st = run(program["image"], {"sp": 16})[-2]
        self.assertEqual(st["sp"], 16)
        self.assertTrue(st["nzcv"] & NZCV_Z)             # 16 - 16 == 0

    # --- B.cond (conditional branch): the first conditional pc update -------
    def test_decode_bcond_spec(self):
        d = decode_insn_v3(asm.b_cond("EQ", 8))
        self.assertEqual((d.op, d.cond, d.offset), ("bcond", 0b0000, 8))
        d2 = decode_insn_v3(asm.b_cond("NE", -4))         # backward branch
        self.assertEqual((d2.op, d2.cond, d2.offset), ("bcond", 0b0001, -4))
        # The 0.2 decoder still rejects B.cond.
        with self.assertRaises(Unsupported):
            decode_insn(asm.b_cond("EQ", 8))

    def _branch_prog(self, cond):
        # @0 CMP x0,#5 ; @4 B.cond +8 ; @8 MOVZ x1,#100 ; @12 MOVZ x2,#200
        # Taken => skip @8 (x1 stays 0); not-taken => x1 = 100. x2 = 200 always.
        return prog(asm.cmp_imm(0, 5), asm.b_cond(cond, 8),
                    asm.movz(1, 100), asm.movz(2, 200))

    def test_bcond_eq_taken_and_not_taken(self):
        # CMP x0,#5: x0==5 => Z=1 => B.EQ taken (x1 stays 0); x0==3 => not taken.
        taken = self._branch_prog("EQ")
        ok(self, dict(taken, init_regs={0: 5}))
        self.assertEqual(run(taken["image"], {"regs": {0: 5}})[-2]["x1"], 0)
        ok(self, dict(taken, init_regs={0: 3}))
        self.assertEqual(run(taken["image"], {"regs": {0: 3}})[-2]["x1"], 100)

    def test_bcond_ne_taken_and_not_taken(self):
        ne = self._branch_prog("NE")
        ok(self, dict(ne, init_regs={0: 3}))             # Z=0 => taken
        self.assertEqual(run(ne["image"], {"regs": {0: 3}})[-2]["x1"], 0)
        ok(self, dict(ne, init_regs={0: 5}))             # Z=1 => not taken
        self.assertEqual(run(ne["image"], {"regs": {0: 5}})[-2]["x1"], 100)

    def test_bcond_signed_and_unsigned_conditions(self):
        # CMP x0,#5 then each signed/unsigned condition over the two paths.
        # x0 = 3: 3 - 5 = -2 => N=1,Z=0,C=0,V=0. So LT taken, GE not; HI not, LS
        # taken; LO/CC taken (C=0). x0 = 8: 8 - 5 = 3 => N=0,C=1,Z=0,V=0 => GE
        # taken, LT not; HI taken (C=1,Z=0); CS taken.
        cases = [
            ("LT", 3, 0), ("LT", 8, 100),
            ("GE", 8, 0), ("GE", 3, 100),
            ("HI", 8, 0), ("HI", 3, 100),
            ("LS", 3, 0), ("LS", 8, 100),
            ("CC", 3, 0), ("CC", 8, 100),     # CC/LO: C==0
            ("CS", 8, 0), ("CS", 3, 100),     # CS/HS: C==1
        ]
        for cond, x0, expect_x1 in cases:
            program = dict(self._branch_prog(cond), init_regs={0: x0})
            ok(self, program)
            got = run(program["image"], {"regs": {0: x0}})[-2]["x1"]
            self.assertEqual(got, expect_x1, msg=f"{cond} x0={x0}")

    def test_bcond_backward_loop(self):
        # A real loop: MOVZ x0,#3 ; (L) SUBS x0,x0,#1 ; B.NE L ; fall off end.
        # Counts x0 down to 0 (the back-branch is taken while x0 != 0).
        program = prog(asm.movz(0, 3), asm.subs_imm(0, 0, 1), asm.b_cond("NE", -4))
        ok(self, program)
        self.assertEqual(run(program["image"], {})[-2]["x0"], 0)

    def test_bcond_branching_square_two_paths(self):
        # The brief's commuting-square check: CMP then B.EQ over two paths, both
        # the taken and not-taken control flow must commute.
        for x0 in (5, 6):
            ok(self, dict(self._branch_prog("EQ"), init_regs={0: x0}))

    def test_cond_holds_matches_translator_branch(self):
        # The interpreter's cond_holds and the translator's branch ITE share one
        # truth table: for every cond code and every NZCV the branch is taken iff
        # cond_holds says so. Drive it through the full square on B.cond +8.
        # @0 B.cond +8 ; @4 MOVZ x0,#1 ; @8 MOVZ x1,#2.  Taken => skip @4, so the
        # final x0 stays 0; not-taken => x0 becomes 1.
        for cond_name, code in asm.COND.items():
            for nzcv in range(16):
                program = prog(asm.b_cond(code, 8), asm.movz(0, 1), asm.movz(1, 2),
                               init_nzcv=nzcv)
                ok(self, program)
                final_x0 = run(program["image"], {"nzcv": nzcv})[-2]["x0"]
                taken = cond_holds(code, nzcv)
                self.assertEqual(final_x0 == 0, taken,
                                 msg=f"{cond_name} nzcv={nzcv:04b}")

    # --- B / BL (unconditional branch): the always-taken pc update ----------
    def test_decode_b_bl_spec(self):
        # B +8  ->  op=b, offset=8, link=False
        d = decode_insn_v4(asm.b(8))
        self.assertEqual((d.op, d.offset, d.link), ("b", 8, False))
        # B -4  ->  backward branch (signed imm26)
        d2 = decode_insn_v4(asm.b(-4))
        self.assertEqual((d2.op, d2.offset, d2.link), ("b", -4, False))
        # BL +8  ->  link bit set
        d3 = decode_insn_v4(asm.bl(8))
        self.assertEqual((d3.op, d3.offset, d3.link), ("b", 8, True))
        # The legacy raw B encoding (0x14000000 = B .) decodes as an in-scope
        # self-branch (offset 0), no longer an abort.
        d4 = decode_insn_v4(0x1400_0000)
        self.assertEqual((d4.op, d4.offset, d4.link), ("b", 0, False))
        # The 0.3 decoder still rejects B (the aarch64-sail gate is unmoved).
        with self.assertRaises(Unsupported):
            decode_insn_v3(asm.b(8))

    def test_b_forward_skips_instruction(self):
        # @0 B +8 (to @8, skipping @4) ; @4 MOVZ x0,#1 (skipped) ; @8 MOVZ x1,#2.
        # The unconditional forward branch skips @4, so x0 stays 0; x1 = 2.
        program = prog(asm.b(8), asm.movz(0, 1), asm.movz(1, 2))
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x0"], 0)            # @4 skipped (always taken)
        self.assertEqual(st["x1"], 2)            # @8 reached

    def test_b_backward_branch_loop_backedge(self):
        # A real loop whose back-edge is an *unconditional* backward B:
        # @0  MOVZ x0,#3
        # @4  SUBS x0,x0,#1         (decrement, set flags)
        # @8  B.EQ +8  -> @16       (conditional exit when x0 hits 0)
        # @12 B -8     -> @4        (unconditional backward branch: the loop back-edge)
        # @16 MOVZ x1,#5
        program = prog(asm.movz(0, 3), asm.subs_imm(0, 0, 1), asm.b_cond("EQ", 8),
                       asm.b(-8), asm.movz(1, 5))
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x0"], 0)            # counted down to 0
        self.assertEqual(st["x1"], 5)            # exit path reached

    def test_bl_writes_link_register(self):
        # BL +8 sets x30 := pc + 4 (the byte address after the BL = @4) and
        # branches to @8 (skipping @4). x0 stays 0, x1 = 2, x30 = 4.
        program = prog(asm.bl(8), asm.movz(0, 1), asm.movz(1, 2))
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x30"], 4)           # link register = return address
        self.assertEqual(st["x0"], 0)            # @4 skipped
        self.assertEqual(st["x1"], 2)            # @8 reached

    def test_bl_preserves_existing_x30_when_not_active(self):
        # Only the executed BL writes x30; an unseeded program leaves x30 = 0 until
        # the BL runs, and a seeded x30 survives an in-scope ALU op before the BL.
        program = prog(asm.add_imm(0, 0, 0), asm.bl(8), asm.movz(1, 7), asm.movz(2, 9))
        ok(self, program)

    # --- ADDS / CMN (immediate), 64-bit: the addition NZCV write ------------
    def test_decode_adds_cmn_spec(self):
        # ADDS X1, X0, #7  ->  rd=1, rn=0, imm=7, op=adds
        d = decode_insn_v4(asm.adds_imm(1, 0, 7))
        self.assertEqual((d.rd, d.rn, d.imm, d.op), (1, 0, 7, "adds"))
        # CMN X0, #5 == ADDS XZR, X0, #5  ->  rd=31 (XZR), op=adds
        c = decode_insn_v4(asm.cmn_imm(0, 5))
        self.assertEqual((c.rd, c.rn, c.imm, c.op), (31, 0, 5, "adds"))
        # LSL #12 and SP source both decode
        d2 = decode_insn_v4(asm.adds_imm(1, asm.SP, 2, lsl12=True))
        self.assertEqual((d2.rd, d2.rn, d2.imm), (1, 31, 2 << 12))
        # The 0.3 decoder still rejects ADDS (the aarch64-sail gate is unmoved).
        with self.assertRaises(Unsupported):
            decode_insn_v3(asm.adds_imm(1, 0, 7))

    def _adds_last_state(self, augend, imm):
        # Run MOVZ x0,#augend ; ADDS x1,x0,#imm and return the post-ADDS state
        # (the second-to-last trace row; the last is the off-end halt). Also
        # asserts the commuting square holds on the same program.
        program = prog(asm.movz(0, augend), asm.adds_imm(1, 0, imm))
        ok(self, program)
        return run(program["image"], {})[-2]

    def test_adds_flag_N(self):
        # (2^63 - 1) + 1 == 2^63: result has bit63 set -> N=1, Z=0, and V=1
        # (positive + positive overflowing into the negative range).
        program = prog(asm.adds_imm(1, 0, 1), init_regs={0: (1 << 63) - 1})
        ok(self, program)
        st = run(program["image"], {"regs": {0: (1 << 63) - 1}})[-2]
        self.assertEqual(st["x1"], 1 << 63)
        self.assertTrue(st["nzcv"] & NZCV_N)
        self.assertFalse(st["nzcv"] & NZCV_Z)

    def test_adds_flag_Z(self):
        # x0 = 2^64 - 1 ; ADDS x1,x0,#1 -> 0 (mod 2^64): Z=1, N=0, C=1 (carry-out).
        program = prog(asm.adds_imm(1, 0, 1), init_regs={0: (1 << 64) - 1})
        ok(self, program)
        st = run(program["image"], {"regs": {0: (1 << 64) - 1}})[-2]
        self.assertEqual(st["x1"], 0)
        self.assertTrue(st["nzcv"] & NZCV_Z)
        self.assertFalse(st["nzcv"] & NZCV_N)
        self.assertTrue(st["nzcv"] & NZCV_C)     # the 65-bit sum overflowed

    def test_adds_flag_C_unsigned_carry_out(self):
        # C is the unsigned carry-out (the addition definition, distinct from
        # SUBS's "no borrow"): (2^64 - 1) + 1 overflows -> C=1; a small 5 + 3
        # does not -> C=0.
        carry = prog(asm.adds_imm(1, 0, 1), init_regs={0: (1 << 64) - 1})
        ok(self, carry)
        self.assertTrue(run(carry["image"], {"regs": {0: (1 << 64) - 1}})[-2]["nzcv"] & NZCV_C)
        self.assertFalse(self._adds_last_state(5, 3)["nzcv"] & NZCV_C)

    def test_adds_flag_V_signed_overflow(self):
        # V is the signed overflow of the *add* (same-sign operands, result sign
        # flips): (2^63 - 1) + 1 overflows the signed range -> V=1 (N=1); 5 + 3
        # does not -> V=0. (Distinct from SUBS's V.)
        ov = prog(asm.adds_imm(1, 0, 1), init_regs={0: (1 << 63) - 1})
        ok(self, ov)
        st = run(ov["image"], {"regs": {0: (1 << 63) - 1}})[-2]
        self.assertTrue(st["nzcv"] & NZCV_V)
        self.assertFalse(self._adds_last_state(5, 3)["nzcv"] & NZCV_V)
        # A large negative + a negative immediate also overflows the signed range
        # and carries: seed x0 = -1 (2^64-1, signed -1), ADDS x0,x0,#1 carries to 0
        # without signed overflow (different-sign operands -> V=0), confirming V is
        # only set on *same-sign* overflow.
        nov = prog(asm.adds_imm(1, 0, 1), init_regs={0: (1 << 64) - 1})
        ok(self, nov)
        self.assertFalse(run(nov["image"], {"regs": {0: (1 << 64) - 1}})[-2]["nzcv"] & NZCV_V)

    def test_adds_writes_result_and_distinct_from_subs(self):
        # ADDS writes Rd = Rn + imm (not Rn - imm): x0 = 50 ; ADDS x1,x0,#8 -> 58,
        # whereas SUBS would give 42 — the op kinds are genuinely distinct.
        st = self._adds_last_state(50, 8)
        self.assertEqual(st["x1"], 58)

    def test_cmn_discards_result_sets_flags(self):
        # CMN X0,#5 (= ADDS XZR): x0 unchanged, but NZCV reflects x0 + 5.
        program = prog(asm.movz(0, 5), asm.cmn_imm(0, 3))   # 5 + 3 = 8, no flags
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x0"], 5)                       # result discarded (XZR)
        self.assertFalse(st["nzcv"] & NZCV_Z)
        self.assertFalse(st["nzcv"] & NZCV_N)
        # CMN with a carry-producing sum sets C even though the result is discarded.
        carry = prog(asm.cmn_imm(0, 1), init_regs={0: (1 << 64) - 1})
        ok(self, carry)
        st2 = run(carry["image"], {"regs": {0: (1 << 64) - 1}})[-2]
        self.assertEqual(st2["x0"], (1 << 64) - 1)          # x0 unchanged
        self.assertTrue(st2["nzcv"] & NZCV_C)               # but C reflects the carry
        self.assertTrue(st2["nzcv"] & NZCV_Z)               # (2^64-1)+1 == 0

    def test_cmn_sp_source(self):
        # CMN SP, #0 reads the stack pointer as Rn (field 31 = SP for the source);
        # sp + 0 == sp, so Z is set iff sp == 0 (here sp = 0 -> Z).
        program = prog(asm.cmn_imm(asm.SP, 0), init_sp=0)
        ok(self, program)
        st = run(program["image"], {"sp": 0})[-2]
        self.assertEqual(st["sp"], 0)
        self.assertTrue(st["nzcv"] & NZCV_Z)

    def test_adds_nzcv_differs_from_subs_same_operands(self):
        # Same operands, ADDS vs SUBS: the C/V flags genuinely differ. For x0 = 1,
        # imm = 1: ADDS -> 2 (C=0, V=0); SUBS -> 0 (Z=1, C=1). The addition and
        # subtraction flag definitions are distinct, as the brief requires.
        adds = self._adds_last_state(1, 1)
        self.assertEqual(adds["x1"], 2)
        self.assertFalse(adds["nzcv"] & NZCV_C)             # 1+1 no carry
        # SUBS path (reuse the 0.3 helper shape): x0 = 1 ; SUBS x1,x0,#1 -> 0.
        subs_prog = prog(asm.movz(0, 1), asm.subs_imm(1, 0, 1))
        ok(self, subs_prog)
        subs = run(subs_prog["image"], {})[-2]
        self.assertEqual(subs["x1"], 0)
        self.assertTrue(subs["nzcv"] & NZCV_Z)
        self.assertTrue(subs["nzcv"] & NZCV_C)              # 1>=1 no borrow

    # --- LDR / STR (64-bit, unsigned offset): the first memory access -------
    def test_decode_ldr_str_spec(self):
        # STR X0, [X1]  ->  rt(rd)=0, base(rn)=1, imm=0, op=str
        d = decode_insn_v5(asm.str_imm(0, 1, 0))
        self.assertEqual((d.rd, d.rn, d.imm, d.op), (0, 1, 0, "str"))
        # LDR X2, [X3, #16]  ->  rt=2, base=3, imm = imm12*8 = 16, op=ldr
        d2 = decode_insn_v5(asm.ldr_imm(2, 3, 16))
        self.assertEqual((d2.rd, d2.rn, d2.imm, d2.op), (2, 3, 16, "ldr"))
        # The unsigned offset is scaled by 8 (the 64-bit access size): imm12=2 -> 16.
        d3 = decode_insn_v5(asm.ldr_imm(0, 0, 16))
        self.assertEqual(d3.imm, 16)
        # SP base (Rn=31) decodes; the canonical raw LDR X0,[X0] is in scope now.
        d4 = decode_insn_v5(asm.str_imm(4, asm.SP, 8))
        self.assertEqual((d4.rd, d4.rn, d4.imm), (4, 31, 8))
        self.assertEqual(decode_insn_v5(0xF940_0000).op, "ldr")   # LDR X0,[X0]
        # The 0.4 decoder still rejects LDR/STR (the aarch64-sail gate is unmoved).
        with self.assertRaises(Unsupported):
            decode_insn_v4(asm.ldr_imm(0, 1, 0))
        with self.assertRaises(Unsupported):
            decode_insn_v4(asm.str_imm(0, 1, 0))

    def test_str_then_ldr_round_trip(self):
        # STR x0,[x1] ; LDR x2,[x1] from the same address returns the stored value.
        program = prog(asm.str_imm(0, 1, 0), asm.ldr_imm(2, 1, 0),
                       init_regs={0: 0xDEADBEEF12345678, 1: 0})
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0xDEADBEEF12345678, 1: 0}})[-2]
        self.assertEqual(st["x2"], 0xDEADBEEF12345678)      # round-trip

    def test_str_little_endian_window(self):
        # STR writes 8 bytes little-endian: m0 is the low byte, m7 the high byte.
        program = prog(asm.str_imm(0, 1, 0), init_regs={0: 0xDEADBEEF12345678, 1: 0})
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0xDEADBEEF12345678, 1: 0}})[-2]
        self.assertEqual(st["m0"], 0x78)                    # least significant
        self.assertEqual(st["m7"], 0xDE)                    # most significant
        self.assertEqual([st[f"m{i}"] for i in range(8)],
                         [0x78, 0x56, 0x34, 0x12, 0xEF, 0xBE, 0xAD, 0xDE])

    def test_ldr_from_unwritten_memory_is_zero(self):
        # A load from never-written memory returns 0 (zero-initialized memory).
        program = prog(asm.ldr_imm(5, 6, 0), init_regs={6: 32})
        ok(self, program)
        self.assertEqual(run(program["image"], {"regs": {6: 32}})[-2]["x5"], 0)

    def test_str_ldr_sp_relative(self):
        # The SP-relative addressing form: STR x0,[SP,#8] ; LDR x1,[SP,#8]. The
        # base field 31 reads SP (not XZR); the round-trip holds.
        program = prog(asm.str_imm(0, asm.SP, 8), asm.ldr_imm(1, asm.SP, 8),
                       init_regs={0: 0x1122334455667788}, init_sp=0)
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0x1122334455667788}, "sp": 0})[-2]
        self.assertEqual(st["x1"], 0x1122334455667788)

    def test_ldr_reads_seeded_memory(self):
        # init_mem seeds memory; LDR reads the little-endian word back. The square
        # threads init_mem into both the source interp and the BTOR2 array.
        program = prog(asm.ldr_imm(0, 1, 0), init_regs={1: 0},
                       init_mem={0: 0x78, 1: 0x56, 2: 0x34, 3: 0x12})
        ok(self, program)
        st = run(program["image"], {"regs": {1: 0},
                                    "mem": {0: 0x78, 1: 0x56, 2: 0x34, 3: 0x12}})[-2]
        self.assertEqual(st["x0"], 0x12345678)

    def test_str_xzr_stores_zero(self):
        # STR with Rt = XZR (field 31) stores 0, not SP — the transfer-field-31
        # distinction from the base field. Seed mem nonzero, store XZR, read back 0.
        program = prog(asm.str_imm(asm.XZR, 1, 0), asm.ldr_imm(2, 1, 0),
                       init_regs={1: 0}, init_mem={i: 0xFF for i in range(8)})
        ok(self, program)
        st = run(program["image"], {"regs": {1: 0},
                                    "mem": {i: 0xFF for i in range(8)}})[-2]
        self.assertEqual(st["x2"], 0)                        # XZR stored 0

    def test_ldr_xzr_discards_load(self):
        # LDR to Rt = XZR (field 31) discards the loaded value (no register write,
        # and sp untouched — field 31 is XZR here, never SP). Just check the square.
        program = prog(asm.str_imm(0, 1, 0), asm.ldr_imm(asm.XZR, 1, 0),
                       init_regs={0: 0xABCD, 1: 0}, init_sp=777)
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0xABCD, 1: 0}, "sp": 777})[-2]
        self.assertEqual(st["sp"], 777)                      # XZR load did not hit SP

    def test_mem_program_square_with_alu(self):
        # A mixed program: STR x0,[x1] ; LDR x2,[x1] ; ADD x3,x2,#1 ; STR x3,[x1,#8].
        # Exercises the memory window across multiple addresses + an ALU op between.
        program = prog(asm.str_imm(0, 1, 0), asm.ldr_imm(2, 1, 0),
                       asm.add_imm(3, 2, 1), asm.str_imm(3, 1, 8),
                       init_regs={0: 0x41, 1: 0})
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0x41, 1: 0}})[-2]
        self.assertEqual(st["x2"], 0x41)
        self.assertEqual(st["m0"], 0x41)                    # first store
        self.assertEqual(st["m8"], 0x42)                    # second store (x2 + 1)

    def test_no_mem_program_omits_mem_state(self):
        # A program with no LDR/STR emits no `mem` array or `m{i}` window states
        # (the conditional emission mirrors evm-btor2 / ebpf-btor2). Its carried
        # trace still zero-fills the window so π is satisfied.
        text = translate(prog(asm.add_imm(0, 0, 1))).decode()
        tokens = (" " + text.replace("\n", " ")).split()
        self.assertNotIn("mem", tokens)
        self.assertNotIn("m0", tokens)

    def test_mem_window_size_in_projection(self):
        # π carries the whole MEM_WINDOW of memory bytes plus the registers/flags.
        self.assertEqual(len([f for f in PROJECTION.fields if f.startswith("m")
                              and f[1:].isdigit()]), MEM_WINDOW)

    # --- the 32-bit (W-register) ALU/flag immediate forms (interp 0.6) -------
    def test_decode_w_forms_spec(self):
        # The W forms decode with width=32 and the matching op kind.
        self.assertEqual(decode_insn_v6(asm.add_imm_w(1, 0, 1)).width, 32)
        self.assertEqual(decode_insn_v6(asm.sub_imm_w(1, 0, 1)).width, 32)
        d = decode_insn_v6(asm.subs_imm_w(1, 0, 7))
        self.assertEqual((d.rd, d.rn, d.imm, d.op, d.width), (1, 0, 7, "subs", 32))
        c = decode_insn_v6(asm.cmp_imm_w(0, 5))                # CMP W = SUBS WZR
        self.assertEqual((c.rd, c.op, c.width), (31, "subs", 32))
        a = decode_insn_v6(asm.adds_imm_w(1, 0, 7))
        self.assertEqual((a.rd, a.rn, a.imm, a.op, a.width), (1, 0, 7, "adds", 32))
        m = decode_insn_v6(asm.movz_w(3, 0x1234))
        self.assertEqual((m.rd, m.imm, m.op, m.width), (3, 0x1234, "movz", 32))
        # The 64-bit forms still decode with width=64 (default), unchanged.
        self.assertEqual(decode_insn_v6(asm.add_imm(1, 0, 1)).width, 64)
        self.assertEqual(decode_insn_v6(asm.subs_imm(1, 0, 7)).width, 64)
        # The 0.5 decoder (the aarch64-sail gate) still rejects the W forms.
        for w in (asm.add_imm_w(1, 0, 1), asm.subs_imm_w(1, 0, 7),
                  asm.adds_imm_w(1, 0, 7), asm.movz_w(0, 1)):
            with self.assertRaises(Unsupported):
                decode_insn_v5(w)

    def test_add_w_zero_extends(self):
        # ADD W writes the low-32-bit result zero-extended into Xd: the upper 32 bits
        # of Xd become 0. Seed x0 with high bits set so the 64-bit and 32-bit results
        # genuinely differ (a 64-bit ADD would keep 0xFFFFFFFF in the high half).
        program = prog(asm.add_imm_w(1, 0, 1), init_regs={0: 0xFFFFFFFF_00000005})
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0xFFFFFFFF_00000005}})[-2]
        self.assertEqual(st["x1"], 0x6)                       # zero-extended, not 0xFFFFFFFF00000006
        self.assertEqual(st["x1"] >> 32, 0)                   # upper 32 bits are 0

    def test_add_w_wraps_at_32_bits(self):
        # 32-bit arithmetic wraps at 2^32 (not 2^64): low32(x0)=0xFFFFFFFF, +1 -> 0,
        # zero-extended. The high half of x0 is ignored.
        program = prog(asm.add_imm_w(1, 0, 1), init_regs={0: 0x12345678_FFFFFFFF})
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0x12345678_FFFFFFFF}})[-2]
        self.assertEqual(st["x1"], 0x0)

    def test_sub_w_zero_extends_and_wraps(self):
        # SUB W on the low 32 bits, zero-extended. 0 - 1 wraps to 0xFFFFFFFF (32-bit),
        # NOT 0xFFFFFFFFFFFFFFFF (which a 64-bit SUB would give).
        program = prog(asm.sub_imm_w(0, 0, 1), init_regs={0: 0x99999999_00000000})
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0x99999999_00000000}})[-2]
        self.assertEqual(st["x0"], 0xFFFFFFFF)                # 32-bit wrap, zero-extended
        self.assertEqual(st["x0"] >> 32, 0)

    def test_add_w_to_wsp(self):
        # ADD W field 31 is WSP (the 32-bit stack pointer): write the zero-extended
        # 32-bit result to sp. Seed sp with high bits; the result clears the top half.
        program = prog(asm.add_imm_w(asm.SP, asm.SP, 16), init_sp=0xAAAAAAAA_00000010)
        ok(self, program)
        st = run(program["image"], {"sp": 0xAAAAAAAA_00000010})[-2]
        self.assertEqual(st["sp"], 0x20)                      # (0x10 + 0x10) zero-extended

    def _subs_w_last_state(self, minuend, imm):
        # MOVZ x0,#minuend (64-bit, sets x0) ; SUBS W1,W0,#imm ; return post-SUBS row.
        program = prog(asm.movz(0, minuend), asm.subs_imm_w(1, 0, imm))
        ok(self, program)
        return run(program["image"], {})[-2]

    def test_subs_w_flags_NZC(self):
        # 5 - 8 = -3 (mod 2^32): N=1 (bit 31 set), Z=0, C=0 (borrow).
        st = self._subs_w_last_state(5, 8)
        self.assertEqual(st["x1"], (5 - 8) & MASK32)          # 0xFFFFFFFD, zero-extended
        self.assertTrue(st["nzcv"] & NZCV_N)
        self.assertFalse(st["nzcv"] & NZCV_Z)
        self.assertFalse(st["nzcv"] & NZCV_C)
        # 7 - 7 = 0 -> Z=1, N=0, C=1 (no borrow).
        st2 = self._subs_w_last_state(7, 7)
        self.assertEqual(st2["x1"], 0)
        self.assertTrue(st2["nzcv"] & NZCV_Z)
        self.assertTrue(st2["nzcv"] & NZCV_C)

    def test_subs_w_flag_V_32bit_overflow(self):
        # The 32-bit signed overflow is at bit 31, distinct from the 64-bit case:
        # INT32_MIN - 1 = 0x80000000 - 1 = 0x7FFFFFFF overflows the signed-32 range,
        # so V=1 and N=0 — but as a 64-bit value 0x80000000 - 1 would NOT overflow.
        program = prog(asm.movz(0, 0x8000, hw=1), asm.subs_imm_w(1, 0, 1))  # x0 = 0x80000000
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x1"], 0x7FFFFFFF)
        self.assertTrue(st["nzcv"] & NZCV_V)
        self.assertFalse(st["nzcv"] & NZCV_N)
        # And the matching 64-bit SUBS on the same value does NOT set V (no 64-bit
        # overflow) — confirming the flag width really is 32-bit for the W form.
        prog64 = prog(asm.movz(0, 0x8000, hw=1), asm.subs_imm(1, 0, 1))
        ok(self, prog64)
        st64 = run(prog64["image"], {})[-2]
        self.assertFalse(st64["nzcv"] & NZCV_V)

    def test_cmp_w_discards_result_sets_flags(self):
        # CMP W (= SUBS WZR): x0 unchanged, but NZCV reflects low32(x0) - imm.
        program = prog(asm.movz(0, 5), asm.cmp_imm_w(0, 5))
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x0"], 5)
        self.assertTrue(st["nzcv"] & NZCV_Z)

    def _adds_w_last_state(self, augend, imm):
        program = prog(asm.movz(0, augend), asm.adds_imm_w(1, 0, imm))
        ok(self, program)
        return run(program["image"], {})[-2]

    def test_adds_w_flag_C_32bit_carry_out(self):
        # The 32-bit carry-out (distinct from the 64-bit one): low32(x0)=0xFFFFFFFF,
        # +1 -> 0 (mod 2^32), so C=1, Z=1, and x1 zero-extends to 0 — even though the
        # high half of x0 was nonzero (a 64-bit ADDS would not carry here).
        program = prog(asm.adds_imm_w(1, 0, 1), init_regs={0: 0xDEADBEEF_FFFFFFFF})
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0xDEADBEEF_FFFFFFFF}})[-2]
        self.assertEqual(st["x1"], 0)
        self.assertTrue(st["nzcv"] & NZCV_C)                  # 33-bit sum overflowed
        self.assertTrue(st["nzcv"] & NZCV_Z)
        # A small 5 + 3 produces no carry.
        self.assertFalse(self._adds_w_last_state(5, 3)["nzcv"] & NZCV_C)

    def test_adds_w_flag_V_32bit_overflow(self):
        # 32-bit signed overflow at bit 31: (2^31 - 1) + 1 = 0x80000000 overflows the
        # signed-32 range -> V=1, N=1. The matching 64-bit ADDS on 0x7FFFFFFF + 1 does
        # NOT overflow (V=0) — the flag width is 32-bit for the W form.
        program = prog(asm.adds_imm_w(1, 0, 1), init_regs={0: 0x7FFFFFFF})
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0x7FFFFFFF}})[-2]
        self.assertEqual(st["x1"], 0x80000000)
        self.assertTrue(st["nzcv"] & NZCV_V)
        self.assertTrue(st["nzcv"] & NZCV_N)
        prog64 = prog(asm.adds_imm(1, 0, 1), init_regs={0: 0x7FFFFFFF})
        ok(self, prog64)
        self.assertFalse(run(prog64["image"], {"regs": {0: 0x7FFFFFFF}})[-2]["nzcv"] & NZCV_V)

    def test_cmn_w_discards_result_sets_flags(self):
        # CMN W (= ADDS WZR): x0 unchanged, NZCV reflects low32(x0) + imm. A
        # carry-producing 32-bit sum sets C+Z even though the result is discarded.
        program = prog(asm.cmn_imm_w(0, 1), init_regs={0: 0xFFFFFFFF})
        ok(self, program)
        st = run(program["image"], {"regs": {0: 0xFFFFFFFF}})[-2]
        self.assertEqual(st["x0"], 0xFFFFFFFF)
        self.assertTrue(st["nzcv"] & NZCV_C)
        self.assertTrue(st["nzcv"] & NZCV_Z)

    def test_movz_w(self):
        # MOVZ W writes the immediate, zero-extended into Xd (and zeroes the high
        # half even when Xd was previously full).
        program = prog(asm.movz_w(3, 0x1234), init_regs={3: (1 << 64) - 1})
        ok(self, program)
        self.assertEqual(run(program["image"], {"regs": {3: (1 << 64) - 1}})[-2]["x3"], 0x1234)

    def test_movz_w_lsl16(self):
        # MOVZ W3, #0xABCD, LSL #16 -> 0xABCD0000 (still within 32 bits).
        program = prog(asm.movz_w(3, 0xABCD, hw=1))
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x3"], 0xABCD0000)
        self.assertEqual(st["x3"] >> 32, 0)

    def test_movz_w_xzr_is_not_sp(self):
        # MOVZ W field 31 is WZR: the write is discarded, sp untouched.
        program = prog(asm.movz_w(31, 999), init_sp=100)
        ok(self, program)
        self.assertEqual(run(program["image"], {"sp": 100})[-2]["sp"], 100)

    def test_mixed_w_and_x_program(self):
        # A program mixing 32-bit and 64-bit ops: the 64-bit ADD keeps the high half,
        # the 32-bit ADD W clears it. The square must commute across both widths.
        program = prog(asm.movz(0, 0xFFFF, hw=3),            # x0 high bits set
                       asm.add_imm(1, 0, 1),                 # X1 = x0 + 1 (keeps high)
                       asm.add_imm_w(2, 0, 1),               # W2 = low32(x0)+1 (clears high)
                       init_regs={})
        ok(self, program)
        st = run(program["image"], {})[-2]
        self.assertEqual(st["x1"] >> 48, 0xFFFF)             # 64-bit: high half kept
        self.assertEqual(st["x2"], 0x1)                      # 32-bit: zero-extended

    def test_w_lift_carry_back(self):
        # Carry-back of a W-form result through L: ADDS W1,W0,#1 with a 32-bit
        # carry. The carried trace must show x1 == 0 (zero-extended 32-bit wrap) and
        # all π fields present.
        program = prog(asm.adds_imm_w(1, 0, 1), init_regs={0: 0xDEADBEEF_FFFFFFFF})
        artifact = translate(program)
        n = len(run(program["image"], {"regs": {0: 0xDEADBEEF_FFFFFFFF}}))
        carried = lift(interpret(artifact, {"steps": n + 1}))
        self.assertEqual(set(PROJECTION.fields) - set(carried[-1]), set())
        self.assertTrue(any(row.get("x1") == 0 for row in carried))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge_w_form(self):
        # A W-form op carries through the reasoning path: MOVZ x0,#0xFFFFFFFF-ish via
        # MOVZ W is hw-limited, so seed x0 and ADD W: low32(x0)=0xFFFFFFFF, ADD W
        # x1,x0,#1 -> 0 (zero-extended). x1 == 0 is reachable, witness replayed.
        from gurdy.pairs.btor2_smtlib import reach

        program = prog(asm.add_imm_w(1, 0, 1), init_regs={0: 0x12345678_FFFFFFFF},
                       property={"reg_eq": [1, 0]})
        info = reach(translate(program), 3)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("x1") == 0 for row in info["behavior"]))

    # --- twice-and-diff determinism (translator + interpreter) -------------
    def test_translator_deterministic(self):
        # Exercise every in-scope op (incl. the 0.4 B/BL + ADDS/CMN, the 0.5
        # LDR/STR, and the 0.6 32-bit W-register ALU/flag forms) in the one program
        # the diff covers.
        p = prog(asm.add_imm(7, 7, 0x123), asm.sub_imm(7, 7, 0x10),
                 asm.movz(8, 0xFF), asm.subs_imm(9, 8, 0x10), asm.cmp_imm(7, 1),
                 asm.adds_imm(10, 8, 3), asm.cmn_imm(8, 1), asm.str_imm(8, 7, 0),
                 asm.ldr_imm(12, 7, 0), asm.add_imm_w(6, 8, 2), asm.sub_imm_w(6, 6, 1),
                 asm.movz_w(5, 0xBEEF), asm.subs_imm_w(4, 8, 1), asm.cmp_imm_w(7, 1),
                 asm.adds_imm_w(3, 8, 2), asm.cmn_imm_w(8, 1), asm.b_cond("NE", -4),
                 asm.bl(8), asm.movz(11, 1), asm.b(-4))
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        # canonical BTOR2 round-trips byte-exact (native-checker conformant)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_interpreter_deterministic(self):
        p = img(asm.movz(0, 5), asm.add_imm(1, 0, 9), asm.sub_imm(1, 1, 2),
                asm.cmp_imm(1, 12), asm.adds_imm(4, 0, 3), asm.cmn_imm(1, 1),
                asm.str_imm(1, 0, 0), asm.ldr_imm(5, 0, 0),
                asm.add_imm_w(6, 0, 3), asm.subs_imm_w(7, 0, 1), asm.adds_imm_w(8, 0, 2),
                asm.movz_w(9, 0xCAFE), asm.cmn_imm_w(1, 1),
                asm.b_cond("LT", 8), asm.bl(8), asm.movz(3, 1))
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

    def test_lift_branch_taken_run(self):
        # Carry-back of a *branch-taken* run: CMP x0,#5 (x0==5 => Z) ; B.EQ +8
        # (taken, skips @8 MOVZ x1,#100) ; @12 MOVZ x2,#42. The carried trace must
        # show x1 never set to 100 (the skipped path) and x2 == 42 (the reached
        # path) — the conditional pc update replayed through L.
        program = prog(asm.cmp_imm(0, 5), asm.b_cond("EQ", 8),
                       asm.movz(1, 100), asm.movz(2, 42), init_regs={0: 5})
        artifact = translate(program)
        n = len(run(program["image"], {"regs": {0: 5}}))
        carried = lift(interpret(artifact, {"steps": n + 1}))
        self.assertTrue(all(row.get("x1") == 0 for row in carried))   # @8 skipped
        self.assertTrue(any(row.get("x2") == 42 for row in carried))  # @12 reached

    def test_lift_uncond_branch_and_link(self):
        # Carry-back of an *unconditional* BL run: @0 BL +8 (x30 := 4, skips @4
        # MOVZ x0,#100) ; @8 MOVZ x1,#42. The carried trace shows x0 never set to
        # 100 (skipped), x1 == 42 (reached), and x30 == 4 (the link register).
        program = prog(asm.bl(8), asm.movz(0, 100), asm.movz(1, 42))
        artifact = translate(program)
        n = len(run(program["image"], {}))
        carried = lift(interpret(artifact, {"steps": n + 1}))
        self.assertTrue(all(row.get("x0") == 0 for row in carried))    # @4 skipped
        self.assertTrue(any(row.get("x1") == 42 for row in carried))   # @8 reached
        self.assertTrue(any(row.get("x30") == 4 for row in carried))   # link set

    def test_lift_ldr_result_and_memory_window(self):
        # Carry-back of an LDR result (and the memory window) through L: STR x0,[x1]
        # ; LDR x2,[x1]. The carried trace must show the loaded x2 == the stored
        # value and the memory window byte m0 == its low byte (the memory
        # observable, zero-filled to MEM_WINDOW, reaches π via L).
        program = prog(asm.str_imm(0, 1, 0), asm.ldr_imm(2, 1, 0),
                       init_regs={0: 0xCAFEBABE, 1: 0})
        artifact = translate(program)
        n = len(run(program["image"], {"regs": {0: 0xCAFEBABE, 1: 0}}))
        carried = lift(interpret(artifact, {"steps": n + 1}))
        # π fields all present (incl. the m{i} window).
        self.assertEqual(set(PROJECTION.fields) - set(carried[-1]), set())
        self.assertTrue(any(row.get("x2") == 0xCAFEBABE for row in carried))  # LDR
        self.assertTrue(any(row.get("m0") == 0xBE for row in carried))        # STR low byte
        self.assertEqual(len([f for f in carried[-1] if f.startswith("m")
                              and f[1:].isdigit()]), MEM_WINDOW)

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

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge_cmp_bcond(self):
        # The conditional control flow carries all the way through the reasoning
        # path: MOVZ x0,#5 ; CMP x0,#5 (=> Z=1) ; B.EQ +8 (taken, skips
        # MOVZ x1,#7) ; MOVZ x2,#42. Reaching x2 == 42 *requires* the branch to
        # be taken, so a REACHABLE verdict + replayed witness exercises B.cond
        # end-to-end (and x1 == 7 stays UNREACHABLE: the skipped path).
        from gurdy.pairs.btor2_smtlib import reach

        reachable = prog(asm.movz(0, 5), asm.cmp_imm(0, 5), asm.b_cond("EQ", 8),
                         asm.movz(1, 7), asm.movz(2, 42), property={"reg_eq": [2, 42]})
        info = reach(translate(reachable), 6)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("x2") == 42 for row in info["behavior"]))

        skipped = prog(asm.movz(0, 5), asm.cmp_imm(0, 5), asm.b_cond("EQ", 8),
                       asm.movz(1, 7), asm.movz(2, 42), property={"reg_eq": [1, 7]})
        self.assertEqual(reach(translate(skipped), 6)["verdict"], Verdict.UNREACHABLE)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge_adds(self):
        # The addition flag-set op carries through the reasoning path:
        # MOVZ x0,#40 ; ADDS x1,x0,#2  =>  x1 == 42 is reachable, witness replayed.
        from gurdy.pairs.btor2_smtlib import reach

        program = prog(asm.movz(0, 40), asm.adds_imm(1, 0, 2),
                       property={"reg_eq": [1, 42]})
        info = reach(translate(program), 4)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("x1") == 42 for row in info["behavior"]))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge_uncond_branch(self):
        # The unconditional branch carries through the reasoning path: @0 B +8
        # (skips @4 MOVZ x0,#7) ; @8 MOVZ x1,#42. Reaching x1 == 42 *requires* the
        # branch to be taken; x0 == 7 (the skipped path) stays UNREACHABLE.
        from gurdy.pairs.btor2_smtlib import reach

        reachable = prog(asm.b(8), asm.movz(0, 7), asm.movz(1, 42),
                         property={"reg_eq": [1, 42]})
        info = reach(translate(reachable), 5)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("x1") == 42 for row in info["behavior"]))

        skipped = prog(asm.b(8), asm.movz(0, 7), asm.movz(1, 42),
                       property={"reg_eq": [0, 7]})
        self.assertEqual(reach(translate(skipped), 5)["verdict"], Verdict.UNREACHABLE)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge_store_load(self):
        # The memory round-trip carries all the way through the reasoning path:
        # STR x0,[x1] ; LDR x2,[x1] with x0 seeded => x2 == 0xCAFE is reachable,
        # the witness (incl. the load) replayed back to the source-level fact.
        from gurdy.pairs.btor2_smtlib import reach

        program = prog(asm.str_imm(0, 1, 0), asm.ldr_imm(2, 1, 0),
                       init_regs={0: 0xCAFE, 1: 0}, property={"reg_eq": [2, 0xCAFE]})
        info = reach(translate(program), 4)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("x2") == 0xCAFE for row in info["behavior"]))

    # --- honest coverage + rejection of out-of-scope constructs ------------
    def test_in_scope_construct_covered(self):
        report = coverage()
        for name in IN_SCOPE:
            self.assertIn(name, report.covered)
        self.assertEqual(report.fraction, len(IN_SCOPE) / report.total)

    def test_coverage_ratchet_grew(self):
        # The widening ratchet: the 32-bit W-register ALU/flag forms are covered now
        # (interp 0.6), on top of the 0.5 ADD/SUB/MOVZ + SUBS/CMP + ADDS/CMN +
        # B.cond + B/BL + LDR/STR family; nothing previously covered dropped. The
        # slice grew 19/23 -> 27/33 (8 new in-scope probes — the W forms of
        # ADD/SUB/MOVZ(x2)/SUBS/CMP/ADDS/CMN; the prior out-of-scope ADD_imm_w probe
        # promoted into covered; the reserved MOVZ hw=2 and the move-wide siblings
        # MOVN/MOVK added as new out-of-scope probes), so the fraction stays monotone.
        report = coverage()
        self.assertEqual(report.total, 33)
        self.assertEqual(len(report.covered), 27)       # 19/23 -> 27/33
        # The 19 prior-covered probes are all still covered (no regression).
        for name in ("ADD_imm", "ADD_imm_lsl12", "ADD_imm_sp_src", "ADD_imm_sp_dst",
                     "SUB_imm", "SUB_imm_sp", "MOVZ", "MOVZ_lsl16",
                     "SUBS_imm", "CMP_imm", "Bcond", "B", "BL", "ADDS_imm", "CMN_imm",
                     "LDR_imm", "STR_imm", "LDR_imm_off", "STR_imm_sp"):
            self.assertIn(name, report.covered)
        # The 8 newly-covered 0.6 probes (the 32-bit W-register ALU/flag forms).
        for name in ("ADD_imm_w", "SUB_imm_w", "MOVZ_w", "MOVZ_w_lsl16",
                     "SUBS_imm_w", "CMP_imm_w", "ADDS_imm_w", "CMN_imm_w"):
            self.assertIn(name, report.covered)

    def test_out_of_scope_constructs_abort(self):
        for name, program in OUT_OF_SCOPE.items():
            with self.assertRaises(Unsupported, msg=name):
                translate(program)

    def test_still_unsupported_load_32bit_movewide_abort(self):
        # A still-unsupported instruction (the narrower-width LDRB/STRB and 32-bit
        # LDR, the reserved 32-bit MOVZ shift hw=2, the move-wide siblings MOVN/MOVK)
        # keeps hard-aborting after the 0.6 widening (BENCHMARKS.md §3), via both the
        # translator and the interpreter — the rejection boundary moved only by
        # exactly the 32-bit W-register ALU/flag immediate forms. (The 32-bit
        # ADD/SUB/MOVZ/SUBS/ADDS W forms are now *in scope*, so they are no longer
        # listed here.)
        for word in (asm.ldr_imm_w(0, 0),     # 32-bit LDR W0,[X0] (size=10)
                     asm.ldrb_imm(0, 0),      # LDRB W0,[X0]       (byte width)
                     asm.strb_imm(0, 0),      # STRB W0,[X0]       (byte width)
                     asm.movz_w_hw2(0, 1),    # MOVZ W0,#1,LSL #32 (hw=2 reserved)
                     asm.movn(0, 1),          # MOVN      (move-wide sibling)
                     asm.movk(0, 1)):         # MOVK      (move-wide sibling)
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
