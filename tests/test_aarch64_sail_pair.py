"""aarch64-sail tests (the thin ADD-immediate slice).

Covers the PAIRING.md §7 minimum: twice-and-diff determinism for the translator
and for the *additive* AArch64 arm of the shared Sail interpreter; a
per-construct translation unit test against the spec; the commuting square
``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle; carry-back of a
Sail-model behavior through ``L`` to a source-level fact; and a registration
smoke test (the pair is listed and every edge-op of its square is callable).
Also pins the honest ``unsupported`` histogram and the rejection of out-of-scope
constructs (BENCHMARKS.md §3), and — the reason the pair exists — a
branch-agreement sanity check that ``aarch64-btor2`` and ``aarch64-sail`` agree
on ADD-immediate's effect under ``π`` (PATHS.md §4-5). It also pins that the
additive Sail change leaves the RISC-V Sail path untouched.
"""

import json
import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_pair, list_pairs
from gurdy.languages.aarch64 import asm
from gurdy.languages.aarch64.interp import decode, program_from_words, run as a64_run
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

    def test_nzcv_preserved(self):
        # ADD leaves NZCV unchanged; seed nonzero flags and require they survive
        # through the Sail A64 arm.
        program = prog(asm.add_imm(0, 0, 1), init_nzcv=0b1010)
        ok(self, program)
        tr = sail_run(_sail_obj(program), {})
        self.assertTrue(all(row["nzcv"] == 0b1010 for row in tr))

    # --- twice-and-diff determinism (translator + Sail A64 arm) ------------
    def test_translator_deterministic(self):
        p = prog(asm.add_imm(7, 7, 0x123), init_sp=42, init_nzcv=0b0110)
        self.assertEqual(translate(p), translate(p))

    def test_sail_aarch64_arm_deterministic(self):
        obj = _sail_obj(prog(asm.add_imm(0, 0, 5), asm.add_imm(1, 0, 9),
                             init_regs={2: 3}, init_sp=999, init_nzcv=0b0110))
        t1 = list(sail_run(json.loads(json.dumps(obj)), {}))
        t2 = list(sail_run(json.loads(json.dumps(obj)), {}))
        self.assertEqual(t1, t2)

    # --- carry-back: a Sail-model behavior replays through L to a source fact -
    def test_lift_shapes_source_behavior(self):
        program = prog(asm.add_imm(0, 0, 42))
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
    def test_branch_agreement_with_aarch64_btor2(self):
        from gurdy.languages.btor2 import interpret
        from gurdy.pairs.aarch64_btor2 import translate as btor_translate
        from gurdy.pairs.aarch64_btor2.lift import lift as btor_lift

        program = prog(asm.add_imm(asm.SP, asm.SP, 16), asm.add_imm(5, asm.SP, 0),
                       asm.add_imm(0, 0, 5), init_sp=100, init_nzcv=0b0110)
        n = len(a64_run(program["image"], {"sp": 100, "nzcv": 0b0110}))
        # direct route
        b_carried = btor_lift(interpret(btor_translate({**program, "init_sp": 100}),
                                        {"steps": n + 1}))[1:n + 1]
        # sail-mediated route
        s_carried = lift(sail_run(_sail_obj(program), {}))
        sel = lambda rows: [PROJECTION.select(r) for r in rows]
        self.assertEqual(sel(b_carried), sel(s_carried))

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

    def test_out_of_scope_constructs_abort(self):
        for name, program in OUT_OF_SCOPE.items():
            with self.assertRaises(Unsupported, msg=name):
                translate(program)

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
