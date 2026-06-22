"""wasm-btor2 tests (PAIRING.md §7): the commuting square holds across the
i32-stack core (``i32.const`` / ``local.get`` / ``i32.add``) — validated against
the shared Wasm interpreter via the framework oracle — construct coverage is
100% over the in-scope inventory, every out-of-scope opcode hard-aborts with a
typed ``Unsupported`` (the histogram is attached), the translator and the new
Wasm interpreter are deterministic (twice-and-diff), a BTOR2 witness carries back
to a Wasm result, and the pair is registered with every square edge callable."""

import unittest

from gurdy.core import oracle, registry
from gurdy.core.errors import Unsupported
from gurdy.core.registry import list_pairs
from gurdy.core.solver import Verdict
from gurdy.languages.btor2 import from_text, to_text
from gurdy.languages.wasm import asm, module, run
from gurdy.languages.wasm.interp import Instr
from gurdy.pairs.wasm_btor2 import PROJECTION, lift, square, translate
from gurdy.pairs.wasm_btor2.inventory import (
    IN_SCOPE_PROBES,
    UNSUPPORTED_PROBES,
    coverage,
    unsupported_histogram,
)


def prog(body, nlocals=0, init_locals=None, property=None):
    p = {"mod": module(body, nlocals=nlocals), "init_locals": init_locals or {}}
    if property is not None:
        p["property"] = property
    return p


def ok(self, body, nlocals=0, init_locals=None):
    report = square(prog(body, nlocals, init_locals))
    self.assertTrue(report.ok, msg=str(report.divergence))


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


class TestWasmBtor2(unittest.TestCase):
    # --- registration smoke test (PAIRING.md §7) ---------------------------
    def test_registered(self):
        self.assertIn("wasm-btor2", list_pairs())

    def test_square_edges_callable(self):
        pair = registry.get_pair("wasm-btor2")
        self.assertEqual((pair.source, pair.target), ("wasm", "btor2"))
        p = prog([asm.i32_const(1), asm.i32_const(2), asm.i32_add()])
        artifact = pair.translator(p)                     # T
        src = list(pair.source_interpreter(p["mod"], {"locals": {}}))  # I_s
        tgt = pair.target_interpreter(artifact, {"steps": len(src) + 1})  # I_t
        carried = pair.target_to_source(tgt)              # L
        res = oracle.align(src, carried[1 : len(src) + 1], pair.projection)  # cross-check
        self.assertTrue(res.ok, msg=str(res.divergence))

    # --- per-construct translation against the spec (PAIRING.md §7) --------
    def test_construct_i32_const(self):
        ok(self, [asm.i32_const(42)])

    def test_construct_local_get(self):
        ok(self, [asm.local_get(0), asm.local_get(1)], nlocals=2,
           init_locals={0: 11, 1: 22})

    def test_construct_i32_add(self):
        # 7 + 35 == 42
        ok(self, [asm.local_get(0), asm.local_get(1), asm.i32_add()],
           nlocals=2, init_locals={0: 7, 1: 35})

    def test_add_modular_wraparound(self):
        # 0xFFFFFFFF + 2 == 1 (mod 2^32) — the Wasm iadd_32 rule
        body = [asm.i32_const(0xFFFFFFFF), asm.i32_const(2), asm.i32_add()]
        self.assertEqual(run(module(body))[-1]["stack"], (1,))
        ok(self, body)

    def test_deep_fold(self):
        # ((1+2)+3)+4 == 10, with running adds (intermediate slot reuse)
        body = [asm.i32_const(1), asm.i32_const(2), asm.i32_add(),
                asm.i32_const(3), asm.i32_add(), asm.i32_const(4), asm.i32_add()]
        self.assertEqual(run(module(body))[-1]["stack"], (10,))
        ok(self, body)

    def test_multiple_live_values(self):
        # two values left on the stack (no final fold) — sp and live slots agree
        ok(self, [asm.i32_const(5), asm.i32_const(9)])

    def test_locals_and_consts_mixed(self):
        ok(self, [asm.local_get(0), asm.i32_const(100), asm.i32_add(),
                  asm.local_get(1), asm.i32_add()],
           nlocals=2, init_locals={0: 1, 1: 2})

    # --- the conditional construct: select (+ the i32.eqz it consumes) -----
    def test_construct_select_true(self):
        # select(11, 22, 1) -> 11 (condition non-zero picks the first operand)
        body = [asm.i32_const(11), asm.i32_const(22), asm.i32_const(1), asm.select()]
        self.assertEqual(run(module(body))[-1]["stack"], (11,))
        ok(self, body)

    def test_construct_select_false(self):
        # select(11, 22, 0) -> 22 (zero condition picks the second operand)
        body = [asm.i32_const(11), asm.i32_const(22), asm.i32_const(0), asm.select()]
        self.assertEqual(run(module(body))[-1]["stack"], (22,))
        ok(self, body)

    def test_construct_select_nonzero_condition(self):
        # any non-zero condition (not just 1) picks the first operand
        body = [asm.i32_const(11), asm.i32_const(22), asm.i32_const(5), asm.select()]
        self.assertEqual(run(module(body))[-1]["stack"], (11,))
        ok(self, body)

    def test_construct_i32_eqz(self):
        self.assertEqual(run(module([asm.i32_const(0), asm.i32_eqz()]))[-1]["stack"], (1,))
        self.assertEqual(run(module([asm.i32_const(7), asm.i32_eqz()]))[-1]["stack"], (0,))
        ok(self, [asm.i32_const(0), asm.i32_eqz()])
        ok(self, [asm.i32_const(7), asm.i32_eqz()])

    def test_select_consumes_eqz_condition(self):
        # select(100, 200, i32.eqz(x)): the comparison produces the condition.
        true_body = [asm.i32_const(100), asm.i32_const(200),
                     asm.i32_const(0), asm.i32_eqz(), asm.select()]   # eqz(0)=1 -> 100
        false_body = [asm.i32_const(100), asm.i32_const(200),
                      asm.i32_const(9), asm.i32_eqz(), asm.select()]  # eqz(9)=0 -> 200
        self.assertEqual(run(module(true_body))[-1]["stack"], (100,))
        self.assertEqual(run(module(false_body))[-1]["stack"], (200,))
        ok(self, true_body)
        ok(self, false_body)

    def test_select_over_locals_and_add(self):
        # select picks between two computed values, with a local condition
        ok(self, [asm.local_get(0), asm.i32_const(1), asm.i32_add(),
                  asm.local_get(1), asm.local_get(2), asm.select()],
           nlocals=3, init_locals={0: 40, 1: 99, 2: 1})

    def test_select_carry_back(self):
        # a BTOR2 behavior for select replays through L to the chosen value
        for cond, want in ((1, 11), (0, 22)):
            p = prog([asm.i32_const(11), asm.i32_const(22),
                      asm.i32_const(cond), asm.select()])
            btrace = registry.get_pair("wasm-btor2").target_interpreter(
                translate(p), {"steps": 7})
            final = lift(btrace)[-1]
            self.assertTrue(final["halted"])
            self.assertEqual(final["stack"], (want,))

    def test_select_translator_deterministic(self):
        p = prog([asm.i32_const(11), asm.i32_const(22), asm.i32_const(1), asm.select()])
        self.assertEqual(translate(p), translate(p))            # twice-and-diff

    def test_interp_version_bumped(self):
        # the additive select / i32.eqz change bumped the shared interp version
        from gurdy.languages.wasm.interp import INTERP_VERSION
        self.assertEqual(INTERP_VERSION, "0.2")

    # --- honest-failure / coverage (BENCHMARKS.md §3) ----------------------
    def test_out_of_scope_aborts(self):
        with self.assertRaises(Unsupported):
            translate(prog([asm.i32_const(1), asm.i32_const(2), Instr("i32.sub")]))
        with self.assertRaises(Unsupported):
            translate(prog([asm.local_get(0), Instr("i64.add")], nlocals=1))
        with self.assertRaises(Unsupported):
            translate(prog([Instr("call", 0)]))

    def test_abort_names_construct(self):
        with self.assertRaises(Unsupported) as cm:
            translate(prog([asm.i32_const(1), asm.i32_const(2), Instr("i32.mul")]))
        self.assertEqual(cm.exception.construct, "i32.mul")

    def test_interp_rejects_out_of_scope(self):
        with self.assertRaises(Unsupported):
            run(module([Instr("i32.sub")]))

    def test_still_unsupported_after_widening(self):
        # widening to select / i32.eqz leaves the rest of the space aborting:
        # a binop and a structured-control opcode still hard-abort, named.
        with self.assertRaises(Unsupported) as cm:
            translate(prog([asm.i32_const(1), asm.i32_const(2), Instr("i32.sub")]))
        self.assertEqual(cm.exception.construct, "i32.sub")
        with self.assertRaises(Unsupported) as cm2:
            translate(prog([asm.i32_const(0), Instr("if")]))
        self.assertEqual(cm2.exception.construct, "if")
        # and the interpreter rejects them too
        with self.assertRaises(Unsupported):
            run(module([asm.i32_const(0), Instr("if")]))

    def test_coverage_full(self):
        report = coverage()
        self.assertEqual(report.missing, {})
        self.assertEqual(report.fraction, 1.0)
        self.assertEqual(set(report.covered), set(IN_SCOPE_PROBES))

    def test_unsupported_histogram(self):
        hist = unsupported_histogram()
        # every out-of-scope probe aborted (no silent drops)
        self.assertEqual(sum(hist.values()), len(UNSUPPORTED_PROBES))
        for op in ("i32.sub", "i32.mul", "i64.add", "call", "block", "i32.load"):
            self.assertIn(op, hist)

    # --- determinism twice-and-diff (PAIRING.md §7) ------------------------
    def test_translator_deterministic_canonical(self):
        p = prog([asm.local_get(0), asm.i32_const(8), asm.i32_add()],
                 nlocals=1, init_locals={0: 34})
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        # byte-exact canonical round-trip through the shared BTOR2 I/O
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_interpreter_deterministic(self):
        m = module([asm.local_get(0), asm.local_get(1), asm.i32_add()], nlocals=2)
        t1 = run(m, {"locals": {0: 3, 1: 4}})
        t2 = run(m, {"locals": {0: 3, 1: 4}})
        self.assertEqual(t1, t2)

    # --- carry-back: a BTOR2 behavior replays to a Wasm result -------------
    def test_carry_back_shape(self):
        p = prog([asm.local_get(0), asm.local_get(1), asm.i32_add()],
                 nlocals=2, init_locals={0: 40, 1: 2})
        artifact = translate(p)
        pair = registry.get_pair("wasm-btor2")
        btrace = pair.target_interpreter(artifact, {"steps": 6})
        carried = lift(btrace)
        final = carried[-1]
        self.assertTrue(final["halted"])
        self.assertEqual(final["stack"], (42,))           # 40 + 2 carried back

    def test_projection_fields(self):
        self.assertEqual(PROJECTION.fields, ("pc", "halted", "sp", "stack", "locals"))

    # --- the bad/property bridge (decide end-to-end) -----------------------
    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge(self):
        # Wasm (7 + 35 == 42) -> BTOR2 (bad) -> SMT-LIB -> z3, witness replayed.
        from gurdy.pairs.btor2_smtlib import reach

        p = prog([asm.local_get(0), asm.local_get(1), asm.i32_add()],
                 nlocals=2, init_locals={0: 7, 1: 35}, property={"top_eq": 42})
        info = reach(translate(p), 5)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("s0") == 42 and row.get("halted")
                            for row in info["behavior"]))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_unreachable_via_bridge(self):
        from gurdy.pairs.btor2_smtlib import reach

        p = prog([asm.local_get(0), asm.local_get(1), asm.i32_add()],
                 nlocals=2, init_locals={0: 7, 1: 35}, property={"top_eq": 999})
        self.assertEqual(reach(translate(p), 5)["verdict"], Verdict.UNREACHABLE)


if __name__ == "__main__":
    unittest.main()
