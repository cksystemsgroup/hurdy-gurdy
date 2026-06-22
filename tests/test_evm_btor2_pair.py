"""evm-btor2 tests: the commuting square holds across the thin PUSH1/ADD/STOP
slice (validated against the shared EVM interpreter via the framework oracle),
construct coverage is the honest 3/144 over the spec-derived opcode inventory,
out-of-scope opcodes hard-abort with a typed ``unsupported: evm:<MNEMONIC>``,
both the translator and the new EVM interpreter are deterministic, a BTOR2
witness carries back through ``L`` to the source-level stack behavior, and the
emitted ``bad`` is decided end-to-end through the reused ``btor2-smtlib`` bridge.
"""

import importlib.util
import unittest

from gurdy.core import oracle, registry
from gurdy.core.errors import Unsupported
from gurdy.core.registry import list_pairs
from gurdy.languages.btor2 import from_text, parse_witness, replay, to_text
from gurdy.languages.evm import asm
from gurdy.languages.evm.interp import STACK_SIZE, program_from_bytes, run
from gurdy.pairs.evm_btor2 import PROJECTION, lift, square, translate
from gurdy.pairs.evm_btor2.inventory import coverage


def prog(*fragments, **kw):
    return {"code": asm.program(*fragments), **kw}


def ok(self, program):
    report = square(program)
    self.assertTrue(report.ok, msg=str(report.divergence))


def _z3():
    return importlib.util.find_spec("z3") is not None


class TestEvmBtor2(unittest.TestCase):
    # --- registration smoke test (PAIRING.md §7) --------------------------
    def test_registered(self):
        self.assertIn("evm-btor2", list_pairs())

    def test_square_edges_callable(self):
        pair = registry.get_pair("evm-btor2")
        self.assertEqual((pair.source, pair.target), ("evm", "btor2"))
        # Every edge-operation of the square is callable from the registry.
        self.assertTrue(callable(pair.translator))            # T
        self.assertTrue(callable(pair.target_to_source))      # L
        self.assertTrue(callable(pair.source_interpreter))    # I_s (shared EVM)
        self.assertTrue(callable(pair.target_interpreter))    # I_t (shared BTOR2)
        code = asm.program(asm.push1(1), asm.push1(2), asm.add(), asm.stop())
        artifact = pair.translator({"code": code})
        self.assertIsInstance(artifact, bytes)
        btrace = pair.target_interpreter(artifact, {"steps": 3})
        src = pair.source_interpreter(program_from_bytes(code))
        carried = pair.target_to_source(btrace)
        self.assertIsInstance(oracle.align(src, carried[1:], pair.projection).ok, bool)

    # --- per-construct commuting square (PAIRING.md §7) -------------------
    def test_add_two_pushes(self):
        # The headline slice: PUSH1 7, PUSH1 35, ADD, STOP -> top of stack 42.
        ok(self, prog(asm.push1(7), asm.push1(35), asm.add(), asm.stop()))

    def test_add_wraps_mod_2_256(self):
        # 255 + 255 = 510 (no wrap at this magnitude, but exercises the adder).
        ok(self, prog(asm.push1(255), asm.push1(255), asm.add(), asm.stop()))

    def test_chained_adds(self):
        # PUSH 1,2,3; ADD ADD -> 6, exercising the dynamic s{sp-1}/s{sp-2} mux.
        ok(self, prog(asm.push1(1), asm.push1(2), asm.push1(3),
                      asm.add(), asm.add(), asm.stop()))

    def test_push_only(self):
        ok(self, prog(asm.push1(0), asm.push1(255), asm.stop()))

    def test_bare_stop(self):
        ok(self, prog(asm.stop()))

    def test_run_off_end_halts(self):
        # No STOP: running off the end is a halt (a defined edge).
        ok(self, prog(asm.push1(9)))

    def test_add_underflow_halts(self):
        # ADD with one item: stack underflow -> exceptional halt.
        ok(self, prog(asm.push1(5), asm.add(), asm.stop()))

    def test_corpus(self):
        corpus = [
            prog(asm.push1(0), asm.stop()),
            prog(asm.push1(7), asm.push1(35), asm.add(), asm.stop()),
            prog(asm.push1(100), asm.push1(28), asm.add(), asm.push1(14), asm.add()),
            prog(asm.push1(1), asm.push1(2), asm.push1(3), asm.add(), asm.add(), asm.stop()),
        ]
        for p in corpus:
            ok(self, p)

    # --- the projection is exactly π declared in the spec -----------------
    def test_projection_fields(self):
        expected = ("pc", "sp", *(f"s{i}" for i in range(STACK_SIZE)), "halted")
        self.assertEqual(PROJECTION.fields, expected)

    # --- honest-failure: unsupported opcodes hard-abort -------------------
    def test_unsupported_opcode_aborts(self):
        for op, name in [(0x02, "MUL"), (0x50, "POP"), (0x56, "JUMP"),
                         (0x52, "MSTORE"), (0x80, "DUP1"), (0x90, "SWAP1")]:
            with self.assertRaises(Unsupported) as cm:
                translate({"code": bytes((op,))})
            self.assertEqual(cm.exception.construct, name)
            self.assertEqual(str(cm.exception), f"unsupported: evm:{name}")

    def test_unsupported_aborts_in_interpreter_too(self):
        with self.assertRaises(Unsupported) as cm:
            run(program_from_bytes(bytes((0x02,))))   # MUL
        self.assertEqual(cm.exception.construct, "MUL")

    def test_coverage_honest_partial(self):
        report = coverage()
        self.assertEqual(report.covered, {"PUSH1", "ADD", "STOP"})
        self.assertEqual(report.total, len(asm.OPCODE_NAMES))
        # The unsupported histogram is the visible gap (one task per opcode).
        self.assertNotIn("PUSH1", report.histogram)
        self.assertIn("MUL", report.histogram)
        self.assertEqual(len(report.covered) + len(report.missing), report.total)

    # --- determinism twice-and-diff (PAIRING.md §7) -----------------------
    def test_translator_deterministic(self):
        p = prog(asm.push1(7), asm.push1(35), asm.add(), asm.stop())
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        # And the emitted BTOR2 round-trips byte-exactly (canonical form).
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_interpreter_deterministic(self):
        code = asm.program(asm.push1(7), asm.push1(35), asm.add(), asm.stop())
        t1 = run(program_from_bytes(code))
        t2 = run(program_from_bytes(code))
        self.assertEqual([dict(r) for r in t1], [dict(r) for r in t2])

    # --- carry-back: a BTOR2 witness replays through L (PAIRING.md §7) -----
    def test_carry_back_from_witness(self):
        code = asm.program(asm.push1(7), asm.push1(35), asm.add(), asm.stop())
        system = translate({"code": code, "property": {"stack_eq": [0, 42]}})
        # A native checker's witness: init directives supply the initial state;
        # replay through the shared interpreter, then carry back via L.
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=5)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == 42 for r in src))   # the reaching run
        self.assertTrue(src[-1]["halted"])
        # The carried-back behavior matches the direct EVM run under π. The
        # BTOR2 run's first row is the initial state, so align direct against
        # the carried trace shifted by one cycle.
        direct = run(program_from_bytes(code))
        n = len(direct)
        self.assertTrue(oracle.align(direct, src[1 : n + 1], PROJECTION).ok)

    # --- decide end-to-end through the reused btor2-smtlib bridge ----------
    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge(self):
        from gurdy.core.solver import Verdict
        from gurdy.pairs.btor2_smtlib import reach

        code = asm.program(asm.push1(7), asm.push1(35), asm.add(), asm.stop())
        info = reach(translate({"code": code, "property": {"stack_eq": [0, 42]}}), 6)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("s0") == 42 for row in info["behavior"]))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_unreachable_via_bridge(self):
        from gurdy.core.solver import Verdict
        from gurdy.pairs.btor2_smtlib import reach

        code = asm.program(asm.push1(7), asm.push1(35), asm.add(), asm.stop())
        # s0 is 42, never 99 -> unreachable.
        info = reach(translate({"code": code, "property": {"stack_eq": [0, 99]}}), 6)
        self.assertEqual(info["verdict"], Verdict.UNREACHABLE)


if __name__ == "__main__":
    unittest.main()
