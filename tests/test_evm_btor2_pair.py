"""evm-btor2 tests: the commuting square holds across the stack/arithmetic slice
(validated against the shared EVM interpreter via the framework oracle),
construct coverage is the honest 71/144 over the spec-derived opcode inventory
(the full PUSH/DUP/SWAP families plus ADD/MUL/SUB/DIV/MOD/POP/STOP),
out-of-scope opcodes hard-abort with a typed ``unsupported: evm:<MNEMONIC>``,
both the translator and the EVM interpreter (v0.4) are deterministic, a BTOR2
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

    # --- new opcodes: per-construct commuting square ----------------------
    def _top(self, *fragments):
        """Run the EVM interpreter and return the top-of-stack value at halt."""
        code = asm.program(*fragments)
        t = run(program_from_bytes(code))
        last = t[-1]
        return last[f"s{last['sp'] - 1}"] if last["sp"] >= 1 else None

    def test_sub_top_minus_next(self):
        # PUSH1 7, PUSH1 35, SUB -> 35 - 7 = 28 (top minus next), square holds.
        p = prog(asm.push1(7), asm.push1(35), asm.sub(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(7), asm.push1(35), asm.sub(), asm.stop()), 28)

    def test_sub_wraps_mod_2_256(self):
        # 7 - 35 underflows the bv256 -> 2**256 - 28, mirrored by BTOR2 sub.
        p = prog(asm.push1(35), asm.push1(7), asm.sub(), asm.stop())
        ok(self, p)
        self.assertEqual(
            self._top(asm.push1(35), asm.push1(7), asm.sub(), asm.stop()),
            (1 << 256) - 28,
        )

    def test_mul(self):
        p = prog(asm.push1(7), asm.push1(6), asm.mul(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(7), asm.push1(6), asm.mul(), asm.stop()), 42)

    def test_mul_wraps_mod_2_256(self):
        # (2**128) * (2**128) = 2**256 == 0 mod 2**256 (push the high word, square it).
        hi = asm.push2(0x0100)  # 256 = 2**8; square -> 2**16 (in range, exercises mul)
        p = prog(hi, asm.dup1(), asm.mul(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(hi, asm.dup1(), asm.mul(), asm.stop()), 256 * 256)

    def test_pop(self):
        # PUSH 9, PUSH 5, POP -> top is 9, depth back to 1.
        p = prog(asm.push1(9), asm.push1(5), asm.pop(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(9), asm.push1(5), asm.pop(), asm.stop()), 9)

    def test_pop_underflow_halts(self):
        # POP on an empty stack: exceptional halt (a defined edge).
        ok(self, prog(asm.pop(), asm.stop()))

    def test_dup1(self):
        # PUSH 9, DUP1, ADD -> 18 (duplicate then add the copy).
        p = prog(asm.push1(9), asm.dup1(), asm.add(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(9), asm.dup1(), asm.add(), asm.stop()), 18)

    def test_dup1_underflow_halts(self):
        # DUP1 on an empty stack: nothing to duplicate -> exceptional halt.
        ok(self, prog(asm.dup1(), asm.stop()))

    # --- DIV / MOD: unsigned, with the EVM by-zero = 0 special case --------
    def test_div(self):
        # PUSH1 2, PUSH1 6, DIV -> a = top = 6, b = next = 2 -> 6 // 2 = 3.
        p = prog(asm.push1(2), asm.push1(6), asm.div(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(2), asm.push1(6), asm.div(), asm.stop()), 3)

    def test_div_truncates(self):
        # 7 // 2 = 3 (unsigned truncating division, not floating point / rounding).
        p = prog(asm.push1(2), asm.push1(7), asm.div(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(2), asm.push1(7), asm.div(), asm.stop()), 3)

    def test_div_by_zero_is_zero(self):
        # EVM defining special case: DIV by zero is 0 (not a trap). b = top? No:
        # PUSH1 0, PUSH1 6 -> a = top = 6, b = next = 0 -> 6 / 0 = 0.
        p = prog(asm.push1(0), asm.push1(6), asm.div(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(0), asm.push1(6), asm.div(), asm.stop()), 0)

    def test_div_underflow_halts(self):
        # DIV with one item: stack underflow -> exceptional halt (a defined edge).
        ok(self, prog(asm.push1(5), asm.div(), asm.stop()))

    def test_mod(self):
        # PUSH1 3, PUSH1 10, MOD -> a = top = 10, b = next = 3 -> 10 % 3 = 1.
        p = prog(asm.push1(3), asm.push1(10), asm.mod(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(3), asm.push1(10), asm.mod(), asm.stop()), 1)

    def test_mod_by_zero_is_zero(self):
        # EVM defining special case: MOD by zero is 0 (not a trap).
        p = prog(asm.push1(0), asm.push1(7), asm.mod(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(0), asm.push1(7), asm.mod(), asm.stop()), 0)

    def test_mod_underflow_halts(self):
        # MOD with one item: stack underflow -> exceptional halt.
        ok(self, prog(asm.push1(5), asm.mod(), asm.stop()))

    def test_div_mod_tiny_program_square(self):
        # A tiny program using DIV and MOD together: the commuting square holds.
        # PUSH1 3, PUSH1 20, DIV -> a=20, b=3 -> 20 // 3 = 6, stack = [6];
        # PUSH1 17 -> [6, 17]; MOD -> a=17, b=6 -> 17 % 6 = 5.
        ok(self, prog(
            asm.push1(3), asm.push1(20), asm.div(),
            asm.push1(17), asm.mod(),
            asm.stop(),
        ))
        self.assertEqual(
            self._top(asm.push1(3), asm.push1(20), asm.div(),
                      asm.push1(17), asm.mod(), asm.stop()),
            5,
        )

    def test_push2(self):
        p = prog(asm.push2(0x0102), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push2(0x0102), asm.stop()), 0x0102)

    def test_push4(self):
        p = prog(asm.push4(0x01020304), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push4(0x01020304), asm.stop()), 0x01020304)

    # --- the full PUSH family (PUSH3, PUSH5..PUSH32) ----------------------
    def test_push3(self):
        p = prog(asm.pushn(3, 0x010203), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.pushn(3, 0x010203), asm.stop()), 0x010203)

    def test_push32_wide_immediate(self):
        # A wide bv256 immediate (a value with bits above 2**128) round-trips.
        v = (1 << 200) | (1 << 8) | 5
        p = prog(asm.pushn(32, v), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.pushn(32, v), asm.stop()), v)

    def test_every_push_width_square(self):
        # PUSH1..PUSH32: each width translates and its square holds.
        for n in range(1, 33):
            v = (1 << (8 * n - 1)) | 1 if n <= 16 else 1   # fit in n bytes
            ok(self, prog(asm.pushn(n, v), asm.stop()))

    # --- the DUP family (DUP2..DUP16) ------------------------------------
    def test_dup2(self):
        # PUSH 1, PUSH 2, DUP2 -> duplicate the 2nd item (=1) onto the top.
        frags = (asm.push1(1), asm.push1(2), asm.dupn(2), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 1)

    def test_dup15(self):
        # Push 1..15 (sp=15), DUP15 copies the deepest (s0=1) onto the top.
        frags = tuple(asm.push1(i) for i in range(1, 16)) + (asm.dupn(15), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 1)

    def test_dup16_overflow_halts(self):
        # With STACK_SIZE=16, DUP16 needs depth 16 (so the n-th item exists) but
        # then overflows on the write -> exceptional halt. The square still holds.
        frags = tuple(asm.push1(i) for i in range(1, 17)) + (asm.dupn(16), asm.stop())
        ok(self, prog(*frags))

    def test_dup2_underflow_halts(self):
        # DUP2 with one item: nothing at depth 2 -> exceptional halt.
        ok(self, prog(asm.push1(1), asm.dupn(2), asm.stop()))

    def test_every_dup_square(self):
        # DUP1..DUP16: each translates and its square holds (deep ones halt).
        for n in range(1, 17):
            frags = tuple(asm.push1(i) for i in range(1, n + 1)) + (asm.dupn(n), asm.stop())
            ok(self, prog(*frags))

    # --- the SWAP family (SWAP1..SWAP16) ---------------------------------
    def test_swap1(self):
        # PUSH 7, PUSH 9, SWAP1 -> swap the top two; top becomes 7.
        frags = (asm.push1(7), asm.push1(9), asm.swapn(1), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 7)

    def test_swap1_depth_unchanged(self):
        # SWAP does not change the depth: after SWAP1 on [7,9] the depth is 2.
        code = asm.program(asm.push1(7), asm.push1(9), asm.swapn(1), asm.stop())
        last = run(program_from_bytes(code))[-1]
        self.assertEqual(last["sp"], 2)
        self.assertEqual(last["s0"], 9)   # bottom now holds the old top
        self.assertEqual(last["s1"], 7)

    def test_swap15(self):
        # Push 1..16 (sp=16), SWAP15 swaps the top (16) with s0 (1).
        frags = tuple(asm.push1(i) for i in range(1, 17)) + (asm.swapn(15), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 1)   # top now holds the old s0

    def test_swap16_underflow_halts(self):
        # With STACK_SIZE=16, SWAP16 needs depth 17 (top + 17th item), which the
        # bounded stack can never reach -> exceptional halt. The square holds.
        frags = tuple(asm.push1(i) for i in range(1, 17)) + (asm.swapn(16), asm.stop())
        ok(self, prog(*frags))

    def test_swap1_underflow_halts(self):
        # SWAP1 with one item: needs the top and the 2nd item -> exceptional halt.
        ok(self, prog(asm.push1(1), asm.swapn(1), asm.stop()))

    def test_every_swap_square(self):
        # SWAP1..SWAP16: each translates and its square holds (deep ones halt).
        for n in range(1, 17):
            frags = tuple(asm.push1(i) for i in range(1, n + 2)) + (asm.swapn(n), asm.stop())
            ok(self, prog(*frags))

    def test_stack_family_program_square(self):
        # A program threading PUSHn / DUPn / SWAPn together: the square holds.
        ok(self, prog(
            asm.pushn(3, 0x0A0B0C), asm.push1(5), asm.push1(7),
            asm.dupn(3),                                   # dup the PUSH3 value to top
            asm.swapn(2),                                  # swap top with 3rd item
            asm.pop(),
            asm.stop(),
        ))

    def test_mixed_program_square(self):
        # A program using every new opcode together: the commuting square holds.
        ok(self, prog(
            asm.push2(0x0100), asm.push1(0xFF), asm.add(),   # 256 + 255 = 511
            asm.dup1(), asm.push1(2), asm.mul(),             # dup 511, *2 -> 1022
            asm.sub(),                                        # 1022 - 511 = 511
            asm.push1(11), asm.pop(),                         # push then drop
            asm.stop(),
        ))

    # --- the projection is exactly π declared in the spec -----------------
    def test_projection_fields(self):
        expected = ("pc", "sp", *(f"s{i}" for i in range(STACK_SIZE)), "halted")
        self.assertEqual(PROJECTION.fields, expected)

    # --- honest-failure: unsupported opcodes hard-abort -------------------
    def test_unsupported_opcode_aborts(self):
        # The signed SDIV/SMOD, control flow, memory, storage, and PUSH0 stay
        # out of scope and must hard-abort with a typed evm:<MNEMONIC>. (The
        # full PUSH/DUP/SWAP families are now covered — see the family tests.)
        for op, name in [(0x05, "SDIV"), (0x07, "SMOD"), (0x56, "JUMP"),
                         (0x57, "JUMPI"), (0x52, "MSTORE"), (0x55, "SSTORE"),
                         (0x5F, "PUSH0"), (0x0A, "EXP"), (0x16, "AND")]:
            with self.assertRaises(Unsupported) as cm:
                translate({"code": bytes((op,))})
            self.assertEqual(cm.exception.construct, name)
            self.assertEqual(str(cm.exception), f"unsupported: evm:{name}")

    def test_unsupported_aborts_in_interpreter_too(self):
        # SDIV (signed division) stays out of scope in both translator and interp.
        with self.assertRaises(Unsupported) as cm:
            run(program_from_bytes(bytes((0x05,))))   # SDIV
        self.assertEqual(cm.exception.construct, "SDIV")

    def test_coverage_honest_partial(self):
        report = coverage()
        expected = (
            {"ADD", "MUL", "SUB", "DIV", "MOD", "POP", "STOP"}
            | {f"PUSH{n}" for n in range(1, 33)}    # PUSH1..PUSH32
            | {f"DUP{n}" for n in range(1, 17)}     # DUP1..DUP16
            | {f"SWAP{n}" for n in range(1, 17)}    # SWAP1..SWAP16
        )
        self.assertEqual(report.covered, expected)
        # 71 / 144: the stack family (32 PUSH + 16 DUP + 16 SWAP) plus the 7
        # arithmetic/control opcodes already covered.
        self.assertEqual(len(report.covered), 71)
        self.assertEqual(report.total, len(asm.OPCODE_NAMES))
        # The unsupported histogram is the visible gap (one task per opcode).
        self.assertNotIn("PUSH32", report.histogram)
        self.assertNotIn("DUP16", report.histogram)
        self.assertNotIn("SWAP16", report.histogram)
        self.assertIn("PUSH0", report.histogram)    # PUSH0 (no immediate) deferred
        self.assertIn("SDIV", report.histogram)     # signed division still deferred
        self.assertIn("SMOD", report.histogram)
        self.assertIn("JUMP", report.histogram)     # control flow still deferred
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

    def test_translator_deterministic_new_opcodes(self):
        # Twice-and-diff over a program exercising the widened opcode family.
        p = prog(asm.push2(0x0100), asm.push1(0xFF), asm.sub(),
                 asm.dup1(), asm.mul(), asm.push1(1), asm.pop(), asm.stop())
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_translator_deterministic_div_mod(self):
        # Twice-and-diff over a DIV/MOD program (incl. a by-zero guard branch).
        p = prog(asm.push1(0), asm.push1(9), asm.div(),
                 asm.push1(3), asm.push1(20), asm.mod(), asm.stop())
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_translator_deterministic_stack_family(self):
        # Twice-and-diff over a program exercising the widened PUSH/DUP/SWAP
        # families (a wide PUSH32 immediate, a deep DUP, a SWAP).
        p = prog(asm.pushn(32, (1 << 200) | 5), asm.pushn(3, 0x010203),
                 asm.push1(9), asm.dupn(3), asm.swapn(2), asm.pop(), asm.stop())
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

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

    def test_carry_back_new_opcodes(self):
        # PUSH1 6, PUSH1 7, MUL, STOP -> top of stack 42; the BTOR2 witness for
        # `s0 == 42` carries back through L to the reaching source behavior.
        code = asm.program(asm.push1(6), asm.push1(7), asm.mul(), asm.stop())
        system = translate({"code": code, "property": {"stack_eq": [0, 42]}})
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=5)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == 42 for r in src))   # the reaching run
        self.assertTrue(src[-1]["halted"])
        direct = run(program_from_bytes(code))
        n = len(direct)
        self.assertTrue(oracle.align(direct, src[1 : n + 1], PROJECTION).ok)

    def test_carry_back_div(self):
        # PUSH1 6, PUSH1 84, DIV, STOP -> a=84, b=6 -> 84 // 6 = 14; the BTOR2
        # witness for `s0 == 14` carries back through L to the reaching run.
        code = asm.program(asm.push1(6), asm.push1(84), asm.div(), asm.stop())
        system = translate({"code": code, "property": {"stack_eq": [0, 14]}})
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=5)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == 14 for r in src))   # the reaching run
        self.assertTrue(src[-1]["halted"])
        direct = run(program_from_bytes(code))
        n = len(direct)
        self.assertTrue(oracle.align(direct, src[1 : n + 1], PROJECTION).ok)

    def test_carry_back_stack_family(self):
        # PUSH1 21, DUP1, ADD, STOP duplicates 21 and adds -> s0 == 42; the BTOR2
        # witness for `s0 == 42` carries back through L to the reaching run. (Uses
        # the DUP family lowering; PUSH1 is the immediate.)
        code = asm.program(asm.push1(21), asm.dupn(1), asm.add(), asm.stop())
        system = translate({"code": code, "property": {"stack_eq": [0, 42]}})
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=6)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == 42 for r in src))   # the reaching run
        self.assertTrue(src[-1]["halted"])
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
