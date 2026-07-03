"""sail-btor2 AArch64-arm tests (translator 0.1 -> 0.2): the second
AArch64->BTOR2 route composes end-to-end.

Covers the PAIRING.md §7 minimum for the widening: the ``isa=aarch64`` dispatch
lowers an A64 Sail object (the ``aarch64-sail`` artifact) to a BTOR2 system
over ``aarch64-btor2``'s state space (``pc``, ``x0..x30``, ``sp``, ``nzcv``,
the ``m0..m63`` memory window, ``halted``), its datapaths derived from the SAME
Sail ``Expr`` trees the shared Sail interpreter's A64 arm evaluates; the
commuting square translate -> BTOR2-interpret -> carry-back vs the Sail run
holds under the A64 ``π`` across the whole in-scope family (ALU incl. SP
routing, the SUBS/ADDS flag packs, the full B.cond condition table, B/BL, a
back-branch loop, the LDR/STR memory ops with the little-endian window, and
the 32-bit W forms); twice-and-diff determinism + canonical BTOR2; the
``{"reg_eq": [field, val]}`` property (field 31 = sp) lowers to a ``bad`` and
decides through the btor2-smtlib bridge; out-of-scope words keep hard-aborting
with the typed ``Unsupported`` (BENCHMARKS.md §3); and the RISC-V arm's output
shape is untouched (the ratchet guard — the full RISC-V suite is the ratchet
proper).

Route-level (the reason the widening exists, PATHS.md §4-5): ``aarch64-sail``
threads an optional ``property`` into the Sail object (translator 0.1 -> 0.2,
exactly as ``riscv-sail`` does), so ``route.routes("aarch64", "smtlib")``
yields two composing routes; composed coverage is 27/33 along BOTH (the misses
exactly the 6 out-of-scope constructs, each localized to the shared aarch64
decode gate, and the covered sets coincide); composed determinism holds; and
z3 decides the same reg_eq questions along both routes with agreeing verdicts
(reach + unreach, over a MOVZ/ADD program, a SUBS/B.NE loop, and a field-31 =
sp question).
"""

import json
import unittest

from gurdy.core import grade, route
from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_pair, list_pairs
from gurdy.core.solver import Verdict
from gurdy.languages.aarch64 import asm
from gurdy.languages.aarch64.interp import MEM_WINDOW, program_from_words
from gurdy.languages.btor2 import from_text, interpret, to_text
from gurdy.languages.riscv import asm as rvasm
from gurdy.languages.sail import run as sail_run

import gurdy.pairs.aarch64_btor2  # noqa: F401  (the direct route, read READ-ONLY)
import gurdy.pairs.btor2_smtlib   # noqa: F401  (the bridge)
from gurdy.pairs.aarch64_sail import translate as a64_sail_translate
from gurdy.pairs.aarch64_sail.inventory import OUT_OF_SCOPE
from gurdy.pairs.sail_btor2 import aarch64_projection, square_aarch64, translate
from gurdy.pairs.sail_btor2.lift import lift

DIRECT_ROUTE = ["aarch64-btor2", "btor2-smtlib"]
SAIL_ROUTE = ["aarch64-sail", "sail-btor2", "btor2-smtlib"]


def img(*words):
    return program_from_words(list(words))


def prog(*words, **kw):
    return {"image": img(*words), **kw}


def _sail_obj(program):
    """The A64 Sail object as the aarch64-sail front actually emits it, so the
    tests exercise the real composed artifact, not a hand-rolled one."""
    return json.loads(a64_sail_translate(program).decode())


def ok(self, program):
    rep = square_aarch64(_sail_obj(program))
    self.assertTrue(rep.ok, msg=str(rep.divergence))


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


class TestSailBtor2Aarch64Arm(unittest.TestCase):
    # --- dispatch: the isa field selects the arm ----------------------------
    def test_registered_and_version_bumped(self):
        self.assertIn("sail-btor2", list_pairs())
        self.assertEqual(get_pair("sail-btor2").translator_version, "0.2")
        self.assertEqual(get_pair("aarch64-sail").translator_version, "0.2")

    def test_aarch64_dispatch_emits_a64_state_space(self):
        # The A64 arm's system carries the aarch64-btor2 state space: sp, nzcv,
        # x0 (which RISC-V never has as a state), and pc/halted.
        text = translate(_sail_obj(prog(asm.add_imm(0, 0, 1)))).decode()
        for sym in (" pc", " sp", " nzcv", " x0", " x30", " halted"):
            self.assertIn(sym, text)

    def test_riscv_arm_shape_untouched(self):
        # The ratchet guard in-file (the full RISC-V suite is the ratchet
        # proper): a RISC-V Sail program (no isa key) still lowers to the
        # RISC-V state space — x1..x31 and no sp/nzcv/x0 states.
        rv = {"words": [rvasm.addi(1, 0, 7), rvasm.ecall()], "entry": 0, "init_regs": {}}
        text = translate(rv).decode()
        self.assertIn(" x1", text)
        self.assertIn(" x31", text)
        self.assertNotIn(" sp", text)
        self.assertNotIn(" nzcv", text)
        self.assertNotIn(" x0", text)

    def test_projection_matches_aarch64_btor2(self):
        # The A64 π must equal the aarch64 pairs' projection so the branch
        # cross-check at BTOR2 compares like with like.
        from gurdy.pairs.aarch64_btor2 import PROJECTION as BTOR_PROJ
        self.assertEqual(aarch64_projection().fields, BTOR_PROJ.fields)

    # --- commuting squares over the in-scope family -------------------------
    def test_square_alu_and_sp_routing(self):
        # ALU chain + SP read/write (field 31) + the MOVZ XZR discard.
        ok(self, prog(asm.movz(0, 0x1000), asm.add_imm(1, 0, 0x20),
                      asm.sub_imm(1, 1, 0x10), asm.add_imm(asm.SP, asm.SP, 16),
                      asm.movz(31, 999), init_sp=100))

    def test_square_subs_adds_flag_packs(self):
        # SUBS/CMP and ADDS/CMN NZCV packs, incl. a signed overflow (2^63-1 + 1)
        # and the CMP/CMN write-discard with an SP source.
        ok(self, prog(asm.movz(0, 5), asm.subs_imm(1, 0, 7), asm.cmp_imm(asm.SP, 16),
                      asm.adds_imm(2, 3, 1), asm.cmn_imm(asm.SP, 0),
                      init_regs={3: (1 << 63) - 1}, init_sp=16))

    def test_square_bcond_full_condition_table(self):
        # CMP x0,#5 then each of the 16 conditions over three register values,
        # so both taken and not-taken arms are exercised through the new arm.
        for code in asm.COND:
            for x0 in (3, 5, 7):
                ok(self, prog(asm.cmp_imm(0, 5), asm.b_cond(code, 8),
                              asm.movz(1, 1), asm.movz(2, 2), init_regs={0: x0}))

    def test_square_subs_bne_loop(self):
        # A real back-branch loop: MOVZ x0,#3 ; SUBS x0,x0,#1 ; B.NE -4.
        program = prog(asm.movz(0, 3), asm.subs_imm(0, 0, 1), asm.b_cond("NE", -4))
        ok(self, program)
        self.assertEqual(sail_run(_sail_obj(program), {})[-2]["x0"], 0)

    def test_square_b_bl(self):
        # BL link register + B.EQ exit + backward unconditional B back-edge.
        ok(self, prog(asm.bl(8), asm.movz(0, 1), asm.subs_imm(1, 1, 1),
                      asm.b_cond("EQ", 8), asm.b(-8), asm.movz(2, 9),
                      init_regs={1: 2}))

    def test_square_memory(self):
        # STR/LDR round trip, SP-relative store, a load from an init_mem seed,
        # a zero-read of unwritten memory, and a store of XZR (writes 0) — the
        # LE byte assembly is the Sail-derived Expr datapath lowered to the
        # BTOR2 array, the window m{i} carrying it into π.
        ok(self, prog(asm.str_imm(0, 1, 0), asm.ldr_imm(2, 1, 0),
                      asm.str_imm(3, asm.SP, 8), asm.ldr_imm(4, 5, 0),
                      asm.ldr_imm(6, 7, 16), asm.str_imm(asm.XZR, 7, 16),
                      init_regs={0: 0x1122334455667788, 1: 0, 3: 0xABCDEF,
                                 5: 24, 7: 0},
                      init_mem={24: 0xAA, 25: 0xBB, 16: 0x01, 17: 0x02},
                      init_sp=0))

    def test_square_w_forms(self):
        # The 32-bit (W-register) forms: dirty-high-half sources (so the 64-bit
        # and 32-bit results differ), MOVZ W (LSL #0/#16), ADD W to WSP, a
        # 32-bit-only carry (0xFFFFFFFF + 1) and a 32-bit-only signed overflow
        # (INT32_MIN - 1), and the CMP/CMN W write-discard.
        ok(self, prog(asm.add_imm_w(0, 0, 1), asm.sub_imm_w(1, 1, 5),
                      asm.movz_w(2, 0x1234), asm.movz_w(3, 0xABCD, hw=1),
                      asm.add_imm_w(asm.SP, asm.SP, 0x10),
                      asm.adds_imm_w(4, 5, 1), asm.subs_imm_w(6, 7, 1),
                      asm.cmp_imm_w(0, 2), asm.cmn_imm_w(8, 1),
                      init_regs={0: 0xDEADBEEF_FFFFFFFF, 1: 0xFFFFFFFF_00000010,
                                 5: 0x12345678_FFFFFFFF, 7: 0x80000000, 8: 0xFF},
                      init_sp=0x1_00000020))

    # --- carry-back: the BTOR2 behavior lifts to the A64 shape --------------
    def test_lift_carries_a64_observables(self):
        program = prog(asm.str_imm(0, 1, 0), asm.ldr_imm(2, 1, 0),
                       init_regs={0: 0xCAFEBABE, 1: 0})
        obj = _sail_obj(program)
        artifact = translate(obj)
        n = len(sail_run(obj, {}))
        carried = lift(interpret(artifact, {"steps": n + 1}))
        self.assertEqual(set(aarch64_projection().fields) - set(carried[-1]), set())
        self.assertTrue(any(row.get("x2") == 0xCAFEBABE for row in carried))  # LDR
        self.assertTrue(any(row.get("m0") == 0xBE for row in carried))        # LE low byte
        self.assertEqual(len([f for f in carried[-1]
                              if f.startswith("m") and f[1:].isdigit()]), MEM_WINDOW)

    # --- twice-and-diff determinism + canonical BTOR2 -----------------------
    def test_translator_deterministic_and_canonical(self):
        # One program exercising every in-scope op class (ALU/flags/branches/
        # memory/W forms) plus a property: byte-identical twice, and the
        # canonical BTOR2 round-trips byte-exact.
        program = prog(asm.movz(0, 5), asm.add_imm(1, 0, 9), asm.sub_imm(1, 1, 2),
                       asm.subs_imm(2, 1, 1), asm.cmp_imm(0, 5), asm.adds_imm(4, 0, 3),
                       asm.cmn_imm(1, 1), asm.str_imm(0, 5, 0), asm.ldr_imm(6, 5, 0),
                       asm.add_imm_w(7, 0, 1), asm.subs_imm_w(8, 0, 1),
                       asm.movz_w(9, 0x1234), asm.b_cond("EQ", 8), asm.bl(8),
                       asm.movz(3, 1), asm.b(-4),
                       init_regs={5: 0}, init_sp=999, init_nzcv=0b0110,
                       property={"reg_eq": [1, 12]})
        obj = _sail_obj(program)
        a = translate(obj)
        self.assertEqual(a, translate(json.loads(json.dumps(obj))))
        self.assertEqual(to_text(from_text(a.decode())), a.decode())

    # --- property lowering (reg_eq -> bad, field 31 = sp) -------------------
    def test_property_lowers_to_bad(self):
        with_prop = _sail_obj(prog(asm.movz(0, 42), property={"reg_eq": [0, 42]}))
        without = _sail_obj(prog(asm.movz(0, 42)))
        self.assertIn("bad", translate(with_prop).decode())
        self.assertNotIn("bad", translate(without).decode())
        # Field 31 targets the sp state, not a general register.
        sp_prop = _sail_obj(prog(asm.add_imm(asm.SP, asm.SP, 16), init_sp=100,
                                 property={"reg_eq": [31, 116]}))
        self.assertIn("bad", translate(sp_prop).decode())

    def test_aarch64_sail_forwards_property(self):
        # The front pair threads the property into the Sail object (exactly as
        # riscv-sail does) — and stays byte-deterministic with it.
        program = prog(asm.movz(0, 42), property={"reg_eq": [0, 42]})
        obj = _sail_obj(program)
        self.assertEqual(obj["property"], {"reg_eq": [0, 42]})
        self.assertEqual(a64_sail_translate(program), a64_sail_translate(program))
        self.assertNotIn("property", _sail_obj(prog(asm.movz(0, 42))))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_via_bridge(self):
        # The A64 arm's bad decides through btor2-smtlib: reachable with a
        # replayed witness, and the never-value unreachable.
        from gurdy.pairs.btor2_smtlib import reach

        reachable = _sail_obj(prog(asm.movz(0, 40), asm.add_imm(1, 0, 2),
                                   property={"reg_eq": [1, 42]}))
        info = reach(translate(reachable), 4)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("x1") == 42 for row in info["behavior"]))
        unreachable = _sail_obj(prog(asm.movz(0, 40), asm.add_imm(1, 0, 2),
                                     property={"reg_eq": [1, 999]}))
        self.assertEqual(reach(translate(unreachable), 4)["verdict"],
                         Verdict.UNREACHABLE)

    # --- honest rejection of out-of-scope constructs ------------------------
    def test_out_of_scope_words_abort(self):
        # An out-of-scope word inside an A64 Sail object hard-aborts at the
        # shared decode gate with the typed Unsupported (the aarch64-sail front
        # would already have rejected it; this pins sail-btor2's own boundary).
        for word in (asm.movn(0, 1),          # move-wide sibling
                     asm.movk(0, 1),          # move-wide sibling
                     asm.ldrb_imm(0, 0),      # byte-width load
                     asm.ldr_imm_w(0, 0),     # 32-bit LDR (size=10)
                     0xD503_201F):            # NOP
            with self.assertRaises(Unsupported) as cm:
                translate({"isa": "aarch64", "words": [word], "entry": 0})
            self.assertEqual(cm.exception.language, "aarch64")
            self.assertTrue(cm.exception.construct)


class TestComposedAarch64Routes(unittest.TestCase):
    """The route-level payoff: aarch64 reaches smtlib two independent ways."""

    def test_two_routes_exist(self):
        self.assertEqual(route.routes("aarch64", "smtlib"),
                         [DIRECT_ROUTE, SAIL_ROUTE])

    def _head(self, words, prop, **kw):
        return {"image": img(*words), "init_regs": kw.pop("init_regs", {}),
                "property": prop, **kw}

    def test_composed_determinism(self):
        params = {"btor2-smtlib": {"k": 3}}
        head = self._head([asm.movz(0, 40), asm.add_imm(1, 0, 2)], {"reg_eq": [1, 42]})
        self.assertTrue(grade.composed_determinism(DIRECT_ROUTE, head, params))
        self.assertTrue(grade.composed_determinism(SAIL_ROUTE, head, params))

    def test_composed_coverage_both_routes_27_of_33(self):
        # Composed coverage aarch64 -> smtlib: 27/33 along BOTH routes, the
        # covered sets coinciding exactly and the misses exactly the 6
        # out-of-scope constructs, each localized to the shared aarch64 decode
        # gate (BENCHMARKS.md §3/§5; the sail route's gap was 0/33 before the
        # sail-btor2 A64 arm landed — every miss sat at the sail-btor2 hop).
        reports = grade.composed_coverage_by_route("aarch64", "smtlib", k=1)
        self.assertEqual(set(reports), {tuple(DIRECT_ROUTE), tuple(SAIL_ROUTE)})
        direct = reports[tuple(DIRECT_ROUTE)]
        sail = reports[tuple(SAIL_ROUTE)]
        for report in (direct, sail):
            self.assertEqual(report.total, 33)
            self.assertEqual(len(report.covered), 27)
            self.assertEqual(set(report.missing), set(OUT_OF_SCOPE))
            for construct, gap in report.missing.items():
                self.assertTrue(gap.startswith("aarch64:"), msg=f"{construct}: {gap}")
        self.assertEqual(direct.covered, sail.covered)

    @staticmethod
    def _decide(artifact):
        from gurdy.solvers.z3_smt import Z3SmtBackend
        return Z3SmtBackend().decide(artifact).verdict

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_branch_agreement_movz_add(self):
        # The headline cross-check: the direct and Sail-mediated AArch64 routes
        # are independent lowerings; deciding the same reg_eq along each must
        # agree — reach and unreach.
        routes = route.routes("aarch64", "smtlib")
        params = {"btor2-smtlib": {"k": 4}}
        head = self._head([asm.movz(0, 40), asm.add_imm(1, 0, 2)], {"reg_eq": [1, 42]})
        ba = grade.branch_agreement(routes, head, self._decide, params)
        self.assertTrue(ba.agree)
        self.assertEqual(set(ba.verdicts.values()), {Verdict.REACHABLE})
        never = self._head([asm.movz(0, 40), asm.add_imm(1, 0, 2)], {"reg_eq": [1, 999]})
        ba2 = grade.branch_agreement(routes, never, self._decide, params)
        self.assertTrue(ba2.agree)
        self.assertEqual(set(ba2.verdicts.values()), {Verdict.UNREACHABLE})

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_branch_agreement_subs_bne_loop(self):
        # The cross-check spans control flow: both routes agree the countdown
        # loop passes through x0 == 1 (mid-loop) and never x0 == 5.
        routes = route.routes("aarch64", "smtlib")
        params = {"btor2-smtlib": {"k": 12}}
        loop = [asm.movz(0, 3), asm.subs_imm(0, 0, 1), asm.b_cond("NE", -4)]
        ba = grade.branch_agreement(routes, self._head(loop, {"reg_eq": [0, 1]}),
                                    self._decide, params)
        self.assertTrue(ba.agree)
        self.assertEqual(set(ba.verdicts.values()), {Verdict.REACHABLE})
        ba2 = grade.branch_agreement(routes, self._head(loop, {"reg_eq": [0, 5]}),
                                     self._decide, params)
        self.assertTrue(ba2.agree)
        self.assertEqual(set(ba2.verdicts.values()), {Verdict.UNREACHABLE})

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_branch_agreement_sp_property(self):
        # The field-31 = sp property decides identically along both routes.
        routes = route.routes("aarch64", "smtlib")
        params = {"btor2-smtlib": {"k": 3}}
        head = self._head([asm.add_imm(asm.SP, asm.SP, 16)], {"reg_eq": [31, 116]},
                          init_sp=100)
        ba = grade.branch_agreement(routes, head, self._decide, params)
        self.assertTrue(ba.agree)
        self.assertEqual(set(ba.verdicts.values()), {Verdict.REACHABLE})


if __name__ == "__main__":
    unittest.main()
