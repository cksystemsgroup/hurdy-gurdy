"""evm-btor2 tests: the commuting square holds across the stack/arithmetic slice
plus the byte-addressed memory ops, the persistent storage ops, the control-flow
ops JUMP/JUMPI/JUMPDEST/PC (the first non-linear control flow), and the
terminal/halt ops RETURN/REVERT/INVALID + PUSH0 (which record *why* a run halted
in the ``status`` observable — success / revert / exceptional), validated against
the shared EVM interpreter via the framework oracle. Construct coverage is the
honest 86/144 over the spec-derived opcode inventory (the full PUSH/DUP/SWAP
families plus PUSH0, ADD/MUL/SUB/DIV/MOD, the signed SDIV/SMOD, POP/STOP,
MLOAD/MSTORE/MSTORE8, SLOAD/SSTORE, JUMP/JUMPI/JUMPDEST/PC, and
RETURN/REVERT/INVALID), out-of-scope opcodes hard-abort with a typed
``unsupported: evm:<MNEMONIC>``, both the translator and the EVM interpreter
(v0.9) are deterministic, a BTOR2 witness carries back through ``L`` to the
source-level stack behavior, and the emitted ``bad`` is decided end-to-end
through the reused ``btor2-smtlib`` bridge.
"""

import importlib.util
import unittest

from gurdy.core import oracle, registry
from gurdy.core.errors import Unsupported
from gurdy.core.registry import list_pairs
from gurdy.languages.btor2 import from_text, parse_witness, replay, to_text
from gurdy.languages.evm import asm
from gurdy.languages.evm.interp import (
    INT_MIN,
    MASK256,
    MEM_WINDOW,
    STACK_SIZE,
    STATUS_EXCEPTIONAL,
    STATUS_REVERT,
    STATUS_SUCCESS,
    STORE_WINDOW,
    jumpdests,
    program_from_bytes,
    run,
)
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

    # --- SDIV / SMOD: signed, truncating, with the EVM special cases ---------
    def _signed_top(self, *fragments):
        """The top-of-stack value at halt, read as a two's-complement signed int."""
        v = self._top(*fragments)
        return v - (1 << 256) if v is not None and v >= INT_MIN else v

    @staticmethod
    def _w(value):
        """A bv256 PUSH32 of a (possibly negative) value, as a 256-bit word."""
        return asm.pushn(32, value & MASK256)

    def test_sdiv_positive(self):
        # PUSH1 2, PUSH1 6, SDIV -> a = top = 6, b = next = 2 -> 6 / 2 = 3.
        p = prog(asm.push1(2), asm.push1(6), asm.sdiv(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(2), asm.push1(6), asm.sdiv(), asm.stop()), 3)

    def test_sdiv_truncates_toward_zero(self):
        # -7 / 3 = -2 (truncating, NOT Python's flooring -3). a = top = -7, b = 3.
        frags = (self._w(3), self._w(-7), asm.sdiv(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._signed_top(*frags), -2)

    def test_sdiv_negative_divisor(self):
        # 7 / -3 = -2 (truncating). a = top = 7, b = next = -3.
        frags = (self._w(-3), asm.push1(7), asm.sdiv(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._signed_top(*frags), -2)

    def test_sdiv_both_negative(self):
        # -7 / -3 = 2 (truncating, both negative -> positive quotient).
        frags = (self._w(-3), self._w(-7), asm.sdiv(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._signed_top(*frags), 2)

    def test_sdiv_by_zero_is_zero(self):
        # EVM defining special case: SDIV by zero is 0. a = top = 6, b = next = 0.
        frags = (asm.push1(0), self._w(-6), asm.sdiv(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 0)

    def test_sdiv_int_min_over_neg_one_wraps(self):
        # The signed-overflow special case: INT_MIN / -1 = INT_MIN (it wraps,
        # there is NO trap; 2**255 truncated to 256 bits is INT_MIN itself).
        frags = (self._w(-1), self._w(INT_MIN), asm.sdiv(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), INT_MIN)
        # And as a signed value it reads back as INT_MIN, not +2**255.
        self.assertEqual(self._signed_top(*frags), -INT_MIN)

    def test_sdiv_underflow_halts(self):
        # SDIV with one item: stack underflow -> exceptional halt (a defined edge).
        ok(self, prog(asm.push1(5), asm.sdiv(), asm.stop()))

    def test_smod_positive(self):
        # PUSH1 3, PUSH1 10, SMOD -> a = top = 10, b = next = 3 -> 10 % 3 = 1.
        p = prog(asm.push1(3), asm.push1(10), asm.smod(), asm.stop())
        ok(self, p)
        self.assertEqual(self._top(asm.push1(3), asm.push1(10), asm.smod(), asm.stop()), 1)

    def test_smod_sign_of_dividend_negative(self):
        # SMOD takes the sign of the DIVIDEND: -7 % 3 = -1 (a = top = -7).
        frags = (self._w(3), self._w(-7), asm.smod(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._signed_top(*frags), -1)

    def test_smod_sign_of_dividend_positive(self):
        # Contrast: 7 % -3 = +1 — the sign follows the dividend (7), not the
        # divisor (-3); this is the case that distinguishes SMOD from MOD.
        frags = (self._w(-3), asm.push1(7), asm.smod(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._signed_top(*frags), 1)

    def test_smod_by_zero_is_zero(self):
        # EVM defining special case: SMOD by zero is 0 (not a trap).
        frags = (asm.push1(0), self._w(-7), asm.smod(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 0)

    def test_smod_underflow_halts(self):
        # SMOD with one item: stack underflow -> exceptional halt.
        ok(self, prog(asm.push1(5), asm.smod(), asm.stop()))

    def test_sdiv_smod_tiny_program_square(self):
        # A tiny program using SDIV and SMOD together over negative operands: the
        # commuting square holds. -20 / 3 = -6 (trunc), then -6 % 4 = -2.
        frags = (self._w(3), self._w(-20), asm.sdiv(),   # a=-20,b=3 -> -6, stack=[-6]
                 self._w(4), asm.smod(),                  # a=4? No: a=top=4,b=next=-6
                 asm.stop())
        ok(self, prog(*frags))
        # a = top = 4, b = next = -6 -> 4 % -6 = 4 (sign of dividend 4 -> +4).
        self.assertEqual(self._signed_top(*frags), 4)

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

    # --- byte-addressed memory: MLOAD / MSTORE / MSTORE8 ------------------
    def _mem_at(self, *fragments, addr=0):
        """Run the EVM interpreter and return the post-halt memory window byte
        at ``addr`` (the observable ``m{addr}``)."""
        code = asm.program(*fragments)
        return run(program_from_bytes(code))[-1][f"m{addr}"]

    def test_mstore_then_mload_round_trips(self):
        # PUSH v, PUSH off, MSTORE, PUSH off, MLOAD -> v back on the stack.
        frags = (asm.push1(42), asm.push1(0), asm.mstore(),
                 asm.push1(0), asm.mload(), asm.stop())
        ok(self, prog(*frags))
        # The 32-byte big-endian store of 42 puts 42 in the LSB (mem[31]).
        self.assertEqual(self._top(*frags), 42)
        self.assertEqual(self._mem_at(*frags, addr=31), 42)
        self.assertEqual(self._mem_at(*frags, addr=0), 0)

    def test_mload_from_never_written_is_zero(self):
        # A load from never-written memory returns 0 (zero-initialized memory).
        frags = (asm.push1(0), asm.mload(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 0)

    def test_mstore_big_endian_byte_layout(self):
        # MSTORE writes 32-byte big-endian: the MSB lands at mem[off], LSB at
        # mem[off+31]. Store a value with distinct high/low bytes and check both.
        v = (0x11 << 248) | 0xEE     # MSB byte 0x11, LSB byte 0xEE
        frags = (asm.pushn(32, v), asm.push1(0), asm.mstore(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._mem_at(*frags, addr=0), 0x11)    # most significant
        self.assertEqual(self._mem_at(*frags, addr=31), 0xEE)   # least significant

    def test_mstore8_writes_one_byte(self):
        # MSTORE8 writes only the low byte of value to mem[off]; neighbors stay 0.
        frags = (asm.push1(0xABCD & 0xFF), asm.push1(5), asm.mstore8(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._mem_at(*frags, addr=5), 0xCD)
        self.assertEqual(self._mem_at(*frags, addr=4), 0)
        self.assertEqual(self._mem_at(*frags, addr=6), 0)

    def test_mstore8_takes_low_byte_only(self):
        # The high bytes of a wide value are dropped — only the low byte is stored.
        frags = (asm.pushn(32, 0x1122334455667788), asm.push1(3),
                 asm.mstore8(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._mem_at(*frags, addr=3), 0x88)

    def test_mstore_at_second_word_offset(self):
        # MSTORE/MLOAD at offset 32 (the second word) round-trips and the square
        # holds; the window (64 bytes) still observes it (mem[63] = LSB).
        frags = (asm.push1(0x99), asm.push1(32), asm.mstore(),
                 asm.push1(32), asm.mload(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 0x99)
        self.assertEqual(self._mem_at(*frags, addr=63), 0x99)

    def test_mstore_mload_beyond_window_square(self):
        # A store/load at offset 100 (past the 64-byte observable window) still
        # commutes: the loaded value lands on the stack (already observed) even
        # though the written bytes are outside the window.
        frags = (asm.push1(0x77), asm.push1(100), asm.mstore(),
                 asm.push1(100), asm.mload(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 0x77)

    def test_mstore8_overwrites_a_byte_of_a_word_square(self):
        # MSTORE a full word, then MSTORE8 over its top byte, then MLOAD: the
        # square holds and the merged value is observed.
        frags = (asm.push1(0xFF), asm.push1(0), asm.mstore(),
                 asm.push1(0xAA), asm.push1(0), asm.mstore8(),
                 asm.push1(0), asm.mload(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._mem_at(*frags, addr=0), 0xAA)
        self.assertEqual(self._mem_at(*frags, addr=31), 0xFF)
        # The loaded word has 0xAA in the MSB and 0xFF in the LSB.
        self.assertEqual(self._top(*frags), (0xAA << 248) | 0xFF)

    def test_mstore_underflow_halts(self):
        # MSTORE with one item: needs offset + value -> exceptional halt.
        ok(self, prog(asm.push1(0), asm.mstore(), asm.stop()))

    def test_mload_underflow_halts(self):
        # MLOAD on an empty stack: needs the offset -> exceptional halt.
        ok(self, prog(asm.mload(), asm.stop()))

    def test_mstore8_underflow_halts(self):
        # MSTORE8 with one item -> exceptional halt.
        ok(self, prog(asm.push1(0), asm.mstore8(), asm.stop()))

    def test_memory_program_square(self):
        # A program threading all three memory ops with arithmetic: the square
        # holds across the whole run (memory observable + stack).
        ok(self, prog(
            asm.push1(0x10), asm.push1(0), asm.mstore(),     # mem[0..31] = 0x10
            asm.push1(0x20), asm.push1(32), asm.mstore(),    # mem[32..63] = 0x20
            asm.push1(0), asm.mload(),                        # load word 0 -> 0x10
            asm.push1(32), asm.mload(), asm.add(),            # + load word 1 -> 0x30
            asm.push1(7), asm.push1(63), asm.mstore8(),       # mem[63] low byte = 7
            asm.stop(),
        ))

    def test_carry_back_mload(self):
        # PUSH 42, PUSH 0, MSTORE, PUSH 0, MLOAD, STOP -> top of stack 42; the
        # BTOR2 witness for `s0 == 42` carries back through L to the reaching run
        # (the MLOAD result threads memory through the array and back to the stack).
        code = asm.program(asm.push1(42), asm.push1(0), asm.mstore(),
                           asm.push1(0), asm.mload(), asm.stop())
        system = translate({"code": code, "property": {"stack_eq": [0, 42]}})
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=8)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == 42 for r in src))   # the reaching run
        self.assertTrue(src[-1]["halted"])
        # The memory observable also carries back: mem[31] (LSB of the word) = 42.
        self.assertTrue(any(r["m31"] == 42 for r in src))
        direct = run(program_from_bytes(code))
        n = len(direct)
        self.assertTrue(oracle.align(direct, src[1 : n + 1], PROJECTION).ok)

    def test_translator_deterministic_memory(self):
        # Twice-and-diff over a program exercising all three memory ops.
        p = prog(asm.pushn(32, (1 << 200) | 0xBEEF), asm.push1(0), asm.mstore(),
                 asm.push1(7), asm.push1(8), asm.mstore8(),
                 asm.push1(0), asm.mload(), asm.stop())
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    # --- persistent storage: SLOAD / SSTORE ------------------------------
    def _store_at(self, *fragments, key=0):
        """Run the EVM interpreter and return the post-halt storage-window value
        at ``key`` (the observable ``s_at_{key}``)."""
        code = asm.program(*fragments)
        return run(program_from_bytes(code))[-1][f"s_at_{key}"]

    def test_sstore_then_sload_round_trips(self):
        # PUSH v, PUSH key, SSTORE, PUSH key, SLOAD -> v back on the stack.
        frags = (asm.push1(42), asm.push1(7), asm.sstore(),
                 asm.push1(7), asm.sload(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 42)
        self.assertEqual(self._store_at(*frags, key=7), 42)
        self.assertEqual(self._store_at(*frags, key=0), 0)

    def test_sload_from_never_written_is_zero(self):
        # A load from a never-written key returns 0 (zero-initialized storage).
        frags = (asm.push1(5), asm.sload(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 0)

    def test_sstore_overwrite(self):
        # Two SSTOREs to the same key: the later value wins. PUSH 1, key 2,
        # SSTORE; PUSH 9, key 2, SSTORE; key 2, SLOAD -> 9.
        frags = (asm.push1(1), asm.push1(2), asm.sstore(),
                 asm.push1(9), asm.push1(2), asm.sstore(),
                 asm.push1(2), asm.sload(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 9)
        self.assertEqual(self._store_at(*frags, key=2), 9)

    def test_sstore_full_word_value(self):
        # SSTORE / SLOAD carry a full bv256 word (unlike byte-addressed memory):
        # a value with bits above 2**128 round-trips, and the storage window
        # observes the full word.
        v = (1 << 200) | (1 << 8) | 5
        frags = (asm.pushn(32, v), asm.push1(3), asm.sstore(),
                 asm.push1(3), asm.sload(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), v)
        self.assertEqual(self._store_at(*frags, key=3), v)

    def test_sstore_sload_beyond_window_square(self):
        # A store/load at key 100 (past the STORE_WINDOW observable window) still
        # commutes: the loaded value lands on the stack (already observed) even
        # though the written key is outside the window.
        frags = (asm.push1(0x77), asm.push1(100), asm.sstore(),
                 asm.push1(100), asm.sload(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 0x77)

    def test_sload_underflow_halts(self):
        # SLOAD on an empty stack: needs the key -> exceptional halt.
        ok(self, prog(asm.sload(), asm.stop()))

    def test_sstore_underflow_halts(self):
        # SSTORE with one item: needs key + value -> exceptional halt.
        ok(self, prog(asm.push1(0), asm.sstore(), asm.stop()))

    def test_storage_program_square(self):
        # A program threading storage with arithmetic: store two keys, load both,
        # add, store the sum to a third key; the square holds across the run
        # (storage observable + stack).
        ok(self, prog(
            asm.push1(0x10), asm.push1(0), asm.sstore(),     # storage[0] = 0x10
            asm.push1(0x20), asm.push1(1), asm.sstore(),     # storage[1] = 0x20
            asm.push1(0), asm.sload(),                        # load key 0 -> 0x10
            asm.push1(1), asm.sload(), asm.add(),             # + load key 1 -> 0x30
            asm.push1(2), asm.sstore(),                       # storage[2] = 0x30
            asm.stop(),
        ))

    def test_storage_and_memory_together_square(self):
        # A program using both memory and storage: the conditional arrays + both
        # observable windows coexist and the square holds.
        ok(self, prog(
            asm.push1(0xAA), asm.push1(0), asm.mstore(),     # mem[0..31] = 0xAA
            asm.push1(0xBB), asm.push1(4), asm.sstore(),     # storage[4] = 0xBB
            asm.push1(0), asm.mload(),                        # load mem word 0
            asm.push1(4), asm.sload(), asm.add(),             # + storage[4]
            asm.stop(),
        ))

    def test_carry_back_sload(self):
        # PUSH 42, PUSH 7, SSTORE, PUSH 7, SLOAD, STOP -> top of stack 42; the
        # BTOR2 witness for `s0 == 42` carries back through L to the reaching run
        # (the SLOAD result threads storage through the array and back to the
        # stack), and the storage window also carries back (s_at_7 == 42).
        code = asm.program(asm.push1(42), asm.push1(7), asm.sstore(),
                           asm.push1(7), asm.sload(), asm.stop())
        system = translate({"code": code, "property": {"stack_eq": [0, 42]}})
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=8)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == 42 for r in src))   # the reaching run
        self.assertTrue(src[-1]["halted"])
        # The storage observable also carries back: storage[7] = 42.
        self.assertTrue(any(r["s_at_7"] == 42 for r in src))
        direct = run(program_from_bytes(code))
        n = len(direct)
        self.assertTrue(oracle.align(direct, src[1 : n + 1], PROJECTION).ok)

    def test_translator_deterministic_storage(self):
        # Twice-and-diff over a program exercising both storage ops (incl. a wide
        # bv256 value and an overwrite), and the emitted BTOR2 round-trips.
        p = prog(asm.pushn(32, (1 << 200) | 0xBEEF), asm.push1(0), asm.sstore(),
                 asm.push1(7), asm.push1(0), asm.sstore(),
                 asm.push1(0), asm.sload(), asm.stop())
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_interpreter_deterministic_storage(self):
        code = asm.program(asm.push1(42), asm.push1(7), asm.sstore(),
                           asm.push1(7), asm.sload(), asm.stop())
        t1 = run(program_from_bytes(code))
        t2 = run(program_from_bytes(code))
        self.assertEqual([dict(r) for r in t1], [dict(r) for r in t2])

    # --- control flow: JUMP / JUMPI / JUMPDEST / PC (the first non-linear cf) ---
    def test_jumpdests_scan_skips_push_immediates(self):
        # The JUMPDEST scanner must skip PUSH-immediate bytes: a 0x5b that falls
        # inside a PUSH immediate is NOT a valid target.
        # 0: PUSH2 0x5b5b (3 bytes; the two 0x5b are immediate bytes, not dests)
        # 3: JUMPDEST   <- the only valid target
        code = asm.program(asm.push2(0x5B5B), asm.jumpdest(), asm.stop())
        self.assertEqual(jumpdests(code), frozenset({3}))

    def test_jump_skips_an_instruction(self):
        # Unconditional JUMP to a JUMPDEST that skips a PUSH1 99: the square holds
        # and the skipped value never lands on the stack.
        # 0:PUSH1 7, 2:PUSH1 7 (dest), 4:JUMP, 5:PUSH1 99 (skipped), 7:JUMPDEST,
        # 8:PUSH1 5, 10:STOP
        frags = (asm.push1(7), asm.push1(7), asm.jump(),
                 asm.push1(99), asm.jumpdest(), asm.push1(5), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertEqual(last["sp"], 2)            # [7, 5]; the 99 was skipped
        self.assertEqual(last["s0"], 7)
        self.assertEqual(last["s1"], 5)

    def test_jumpi_taken(self):
        # JUMPI with cond != 0 jumps to the JUMPDEST, skipping PUSH1 99.
        # 0:PUSH1 1 (cond), 2:PUSH1 7 (dest), 4:JUMPI, 5:PUSH1 99 (skipped),
        # 7:JUMPDEST, 8:STOP
        frags = (asm.push1(1), asm.push1(7), asm.jumpi(),
                 asm.push1(99), asm.jumpdest(), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertEqual(last["sp"], 0)            # both popped; 99 skipped

    def test_jumpi_not_taken(self):
        # JUMPI with cond == 0 falls through; PUSH1 99 runs.
        frags = (asm.push1(0), asm.push1(7), asm.jumpi(),
                 asm.push1(99), asm.jumpdest(), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertEqual(last["sp"], 1)            # the 99 was pushed
        self.assertEqual(last["s0"], 99)

    def test_jump_to_non_jumpdest_halts(self):
        # A JUMP to a position that is not a JUMPDEST is an exceptional halt
        # (a defined edge). dest=5 lands inside the PUSH1 99, never a dest.
        frags = (asm.push1(5), asm.jump(), asm.jumpdest(), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertTrue(last["halted"])

    def test_jumpi_taken_to_non_jumpdest_halts(self):
        # JUMPI taken but with an invalid destination: exceptional halt.
        frags = (asm.push1(1), asm.push1(99), asm.jumpi(),
                 asm.jumpdest(), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertTrue(last["halted"])

    def test_jump_underflow_halts(self):
        # JUMP on an empty stack: no destination -> exceptional halt.
        ok(self, prog(asm.jump(), asm.jumpdest(), asm.stop()))

    def test_jumpi_underflow_halts(self):
        # JUMPI with one item: needs dest + cond -> exceptional halt.
        ok(self, prog(asm.push1(7), asm.jumpi(), asm.jumpdest(), asm.stop()))

    def test_pc_pushes_instruction_offset(self):
        # PC pushes the byte offset of the PC instruction itself.
        # 0:PUSH1 1 (2 bytes), 2:PC, 3:STOP -> s1 == 2 (the offset of PC).
        frags = (asm.push1(1), asm.pc(), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertEqual(last["sp"], 2)
        self.assertEqual(last["s0"], 1)
        self.assertEqual(last["s1"], 2)            # the byte offset of the PC opcode

    def test_jumpdest_is_a_noop(self):
        # A bare JUMPDEST is a no-op (pc advances, stack unchanged).
        frags = (asm.push1(9), asm.jumpdest(), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertEqual(last["sp"], 1)
        self.assertEqual(last["s0"], 9)

    def test_back_edge_loop_square(self):
        # A back-edge loop (JUMPI to an earlier JUMPDEST) decided over a bounded
        # unrolling: count a stack counter down from 3 to 0; the square holds the
        # whole way. The counter c is decremented as c-1 = SUB(top=c, next=1) after
        # PUSH1 1 / SWAP1, then DUP1'd for the JUMPI test.
        # 0:PUSH1 3, 2:JUMPDEST(loop), 3:PUSH1 1, 5:SWAP1, 6:SUB, 7:DUP1,
        # 8:PUSH1 2(dest), 10:JUMPI, 11:STOP
        frags = (asm.push1(3), asm.jumpdest(), asm.push1(1), asm.swapn(1),
                 asm.sub(), asm.dup1(), asm.push1(2), asm.jumpi(), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertTrue(last["halted"])
        self.assertEqual(last[f"s{last['sp'] - 1}"], 0)   # the counter reached 0

    def test_forward_branch_diamond_square(self):
        # A forward conditional with a join (an if/else diamond over JUMPI/JUMP):
        # 0:PUSH1 1(cond), 2:PUSH1 9(then-dest), 4:JUMPI, 5:PUSH1 11(else val),
        # 7:PUSH1 12(join-dest), 9... wait keep it simple: branch then join.
        # 0:PUSH1 1, 2:PUSH1 8, 4:JUMPI, 5:PUSH1 0xEE, 7:STOP, 8:JUMPDEST,
        # 9:PUSH1 0xAA, 11:STOP
        frags = (asm.push1(1), asm.push1(8), asm.jumpi(),
                 asm.push1(0xEE), asm.stop(),
                 asm.jumpdest(), asm.push1(0xAA), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertEqual(last["s0"], 0xAA)         # took the JUMPDEST branch

    def test_control_flow_program_square(self):
        # A program threading JUMP, JUMPI, PC, and JUMPDEST with arithmetic.
        ok(self, prog(
            asm.pc(),                  # 0  push 0 (this PC's offset)
            asm.push1(6),              # 1  dest of the first JUMP
            asm.jump(),                # 3
            asm.push1(0xFF),           # 4  skipped
            asm.jumpdest(),            # 6
            asm.push1(1),              # 7  cond (truthy)
            asm.push1(14),             # 9  dest (the second JUMPDEST, at 14)
            asm.jumpi(),               # 11
            asm.push1(0xEE),           # 12 skipped (cond was 1)
            asm.jumpdest(),            # 14
            asm.stop(),                # 15
        ))

    def test_carry_back_jump(self):
        # A JUMP control-flow run carries back through L: PUSH1 21, jump over a
        # PUSH1 99, land on a JUMPDEST, DUP1+ADD -> s0 == 42. The BTOR2 witness for
        # `s0 == 42` carries back to the reaching control-flow run.
        # 0:PUSH1 21, 2:PUSH1 6(dest), 4:JUMP, 5:PUSH1 99(skipped), ... need
        # JUMPDEST at 6 then the compute. Layout:
        # 0:PUSH1 21, 2:PUSH1 7, 4:JUMP, 5:PUSH1 99, 7:JUMPDEST, 8:DUP1, 9:ADD, 10:STOP
        code = asm.program(asm.push1(21), asm.push1(7), asm.jump(),
                           asm.push1(99), asm.jumpdest(),
                           asm.dupn(1), asm.add(), asm.stop())
        system = translate({"code": code, "property": {"stack_eq": [0, 42]}})
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=10)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == 42 for r in src))   # the reaching run
        self.assertTrue(src[-1]["halted"])
        direct = run(program_from_bytes(code))
        n = len(direct)
        self.assertTrue(oracle.align(direct, src[1 : n + 1], PROJECTION).ok)

    def test_translator_deterministic_control_flow(self):
        # Twice-and-diff over a program exercising all four control-flow ops.
        p = prog(asm.push1(2), asm.jumpdest(), asm.pc(), asm.pop(),
                 asm.push1(1), asm.swapn(1), asm.sub(), asm.dupn(1),
                 asm.push1(2), asm.jumpi(), asm.stop())
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_interpreter_deterministic_control_flow(self):
        code = asm.program(asm.push1(3), asm.jumpdest(), asm.push1(1),
                           asm.swapn(1), asm.sub(), asm.dupn(1),
                           asm.push1(2), asm.jumpi(), asm.stop())
        t1 = run(program_from_bytes(code))
        t2 = run(program_from_bytes(code))
        self.assertEqual([dict(r) for r in t1], [dict(r) for r in t2])

    # --- PUSH0 + the terminal/halt ops RETURN/REVERT/INVALID (the status model) ---
    def _status(self, *fragments):
        """The post-halt ``status`` of an interpreter run."""
        return run(program_from_bytes(asm.program(*fragments)))[-1]["status"]

    def test_push0_pushes_zero(self):
        # PUSH0 pushes the constant 0; the square holds (interpreter + square).
        frags = (asm.push0(), asm.stop())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertEqual(last["sp"], 1)
        self.assertEqual(last["s0"], 0)

    def test_push0_then_arithmetic(self):
        # PUSH1 5, PUSH0, ADD -> 5 + 0 = 5 (PUSH0 is a real stack op).
        frags = (asm.push1(5), asm.push0(), asm.add(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._top(*frags), 5)

    def test_push0_overflow_halts(self):
        # PUSH0 on a full stack (depth 16) overflows -> exceptional halt.
        frags = tuple(asm.push1(i) for i in range(1, 17)) + (asm.push0(), asm.stop())
        ok(self, prog(*frags))
        self.assertEqual(self._status(*frags), STATUS_EXCEPTIONAL)

    def test_stop_status_is_success(self):
        # STOP is a SUCCESS halt; the existing STOP behavior is unchanged.
        self.assertEqual(self._status(asm.push1(7), asm.stop()), STATUS_SUCCESS)

    def test_off_end_status_is_success(self):
        # Running off the end is an implicit STOP -> SUCCESS status.
        self.assertEqual(self._status(asm.push1(9)), STATUS_SUCCESS)

    def test_underflow_status_is_exceptional(self):
        # A stack underflow halt now records the EXCEPTIONAL status.
        self.assertEqual(self._status(asm.add(), asm.stop()), STATUS_EXCEPTIONAL)

    def test_return_halts_success_and_data_matches_memory(self):
        # Store 0xAB at mem[0], then RETURN offset 0, length 1: a SUCCESS halt,
        # and the return data range memory[0..1] is observable via the window.
        # PUSH 0xAB, PUSH 0, MSTORE; PUSH 1 (len), PUSH 0 (off), RETURN.
        frags = (asm.push1(0xAB), asm.push1(0), asm.mstore(),
                 asm.push1(1), asm.push1(0), asm.ret())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertTrue(last["halted"])
        self.assertEqual(last["status"], STATUS_SUCCESS)
        self.assertEqual(last["sp"], 0)              # offset + length consumed
        # The 32-byte big-endian store of 0xAB puts it in the LSB (mem[31]); the
        # return data window memory[0..] is observable.
        self.assertEqual(last["m31"], 0xAB)

    def test_revert_halts_revert_status(self):
        # REVERT pops offset + length and halts with the REVERT status (distinct
        # from a successful halt).
        frags = (asm.push1(1), asm.push1(0), asm.revert())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertTrue(last["halted"])
        self.assertEqual(last["status"], STATUS_REVERT)
        self.assertEqual(last["sp"], 0)

    def test_invalid_halts_exceptional_status(self):
        # INVALID halts exceptionally, consuming no operands.
        frags = (asm.push1(7), asm.invalid())
        ok(self, prog(*frags))
        last = run(program_from_bytes(asm.program(*frags)))[-1]
        self.assertTrue(last["halted"])
        self.assertEqual(last["status"], STATUS_EXCEPTIONAL)
        self.assertEqual(last["sp"], 1)              # the 7 is untouched

    def test_return_underflow_halts_exceptional(self):
        # RETURN with one item: needs offset + length -> exceptional halt (not
        # a success: the operands were not available).
        frags = (asm.push1(0), asm.ret())
        ok(self, prog(*frags))
        self.assertEqual(self._status(*frags), STATUS_EXCEPTIONAL)

    def test_revert_underflow_halts_exceptional(self):
        frags = (asm.push1(0), asm.revert())
        ok(self, prog(*frags))
        self.assertEqual(self._status(*frags), STATUS_EXCEPTIONAL)

    def test_terminal_statuses_are_distinct_square(self):
        # The three terminal kinds (success / revert / exceptional) are
        # distinguished in π — each program's square holds AND the carried-back
        # status differs, so the commuting square checks *why* the run halted.
        success = (asm.push1(1), asm.push1(0), asm.ret())
        revert = (asm.push1(1), asm.push1(0), asm.revert())
        exc = (asm.invalid(),)
        ok(self, prog(*success))
        ok(self, prog(*revert))
        ok(self, prog(*exc))
        self.assertEqual(self._status(*success), STATUS_SUCCESS)
        self.assertEqual(self._status(*revert), STATUS_REVERT)
        self.assertEqual(self._status(*exc), STATUS_EXCEPTIONAL)

    def test_carry_back_return(self):
        # A RETURN run carries back through L: PUSH 42, PUSH 0, MSTORE, then
        # RETURN offset 0 length 1. The BTOR2 witness for `s0 == 42` (the value
        # mid-run) carries back to the reaching run, ending in a SUCCESS halt.
        code = asm.program(asm.push1(42), asm.push1(0), asm.mstore(),
                           asm.push1(1), asm.push1(0), asm.ret())
        system = translate({"code": code, "property": {"stack_eq": [0, 42]}})
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=10)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == 42 for r in src))   # the reaching run
        self.assertTrue(src[-1]["halted"])
        self.assertEqual(src[-1]["status"], STATUS_SUCCESS)
        direct = run(program_from_bytes(code))
        n = len(direct)
        self.assertTrue(oracle.align(direct, src[1 : n + 1], PROJECTION).ok)

    def test_carry_back_revert(self):
        # A REVERT run carries back through L, ending in a REVERT halt.
        code = asm.program(asm.push1(7), asm.push1(1), asm.push1(0), asm.revert())
        system = translate({"code": code, "property": {"stack_eq": [0, 7]}})
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=8)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == 7 for r in src))    # the reaching run
        self.assertTrue(src[-1]["halted"])
        self.assertEqual(src[-1]["status"], STATUS_REVERT)
        direct = run(program_from_bytes(code))
        n = len(direct)
        self.assertTrue(oracle.align(direct, src[1 : n + 1], PROJECTION).ok)

    def test_translator_deterministic_terminal_ops(self):
        # Twice-and-diff over a program exercising PUSH0 + all three terminal ops
        # paths (RETURN with memory, plus the BTOR2 round-trips byte-exactly).
        p = prog(asm.push0(), asm.push1(0xAB), asm.push1(0), asm.mstore(),
                 asm.push1(1), asm.push1(0), asm.ret())
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    def test_interpreter_deterministic_terminal_ops(self):
        code = asm.program(asm.push1(0xAB), asm.push1(0), asm.mstore(),
                           asm.push1(1), asm.push1(0), asm.revert())
        t1 = run(program_from_bytes(code))
        t2 = run(program_from_bytes(code))
        self.assertEqual([dict(r) for r in t1], [dict(r) for r in t2])

    # --- the projection is exactly π declared in the spec -----------------
    def test_projection_fields(self):
        expected = (
            "pc", "sp",
            *(f"s{i}" for i in range(STACK_SIZE)),
            *(f"m{i}" for i in range(MEM_WINDOW)),       # the byte-memory window
            *(f"s_at_{i}" for i in range(STORE_WINDOW)),  # the storage window
            "halted",
            "status",                                    # the v0.9 halt-status observable
        )
        self.assertEqual(PROJECTION.fields, expected)

    # --- honest-failure: unsupported opcodes hard-abort -------------------
    def test_unsupported_opcode_aborts(self):
        # MSIZE / CALL / CREATE / LOG1 stay out of scope and must hard-abort with
        # a typed evm:<MNEMONIC>. (The full PUSH/DUP/SWAP families plus PUSH0, the
        # signed SDIV/SMOD, MLOAD/MSTORE/MSTORE8, SLOAD/SSTORE, the control-flow
        # ops JUMP/JUMPI/JUMPDEST/PC, and the terminal ops RETURN/REVERT/INVALID
        # are covered — see those tests.)
        for op, name in [(0x59, "MSIZE"), (0x0A, "EXP"), (0x16, "AND"),
                         (0xF1, "CALL"), (0xF0, "CREATE"), (0xA1, "LOG1")]:
            with self.assertRaises(Unsupported) as cm:
                translate({"code": bytes((op,))})
            self.assertEqual(cm.exception.construct, name)
            self.assertEqual(str(cm.exception), f"unsupported: evm:{name}")

    def test_unsupported_aborts_in_interpreter_too(self):
        # A still-unsupported opcode (MSIZE) hard-aborts in the interpreter too.
        with self.assertRaises(Unsupported) as cm:
            run(program_from_bytes(bytes((0x59,))))   # MSIZE
        self.assertEqual(cm.exception.construct, "MSIZE")
        # CALL / CREATE / LOG1 likewise stay out of scope in the interpreter.
        for op, name in [(0xF1, "CALL"), (0xF0, "CREATE"), (0xA1, "LOG1")]:
            with self.assertRaises(Unsupported) as cm:
                run(program_from_bytes(bytes((op,))))
            self.assertEqual(cm.exception.construct, name)

    def test_coverage_honest_partial(self):
        report = coverage()
        expected = (
            {"ADD", "MUL", "SUB", "DIV", "MOD", "SDIV", "SMOD", "POP", "STOP"}
            | {"MLOAD", "MSTORE", "MSTORE8"}        # byte-addressed memory
            | {"SLOAD", "SSTORE"}                   # persistent storage
            | {"JUMP", "JUMPI", "JUMPDEST", "PC"}   # control flow
            | {"RETURN", "REVERT", "INVALID"}       # terminal/halt ops (v0.9)
            | {"PUSH0"}                             # the constant-0 push (v0.9)
            | {f"PUSH{n}" for n in range(1, 33)}    # PUSH1..PUSH32
            | {f"DUP{n}" for n in range(1, 17)}     # DUP1..DUP16
            | {f"SWAP{n}" for n in range(1, 17)}    # SWAP1..SWAP16
        )
        self.assertEqual(report.covered, expected)
        # 86 / 144: the stack family (32 PUSH + 16 DUP + 16 SWAP) + PUSH0, the 9
        # arithmetic opcodes (ADD/MUL/SUB/DIV/MOD/SDIV/SMOD/POP/STOP), the 3
        # byte-addressed memory ops (MLOAD/MSTORE/MSTORE8), the 2 persistent
        # storage ops (SLOAD/SSTORE), the 4 control-flow ops
        # (JUMP/JUMPI/JUMPDEST/PC), plus the 3 terminal/halt ops
        # (RETURN/REVERT/INVALID).
        self.assertEqual(len(report.covered), 86)
        self.assertEqual(report.total, len(asm.OPCODE_NAMES))
        # The unsupported histogram is the visible gap (one task per opcode).
        self.assertNotIn("PUSH32", report.histogram)
        self.assertNotIn("DUP16", report.histogram)
        self.assertNotIn("SWAP16", report.histogram)
        self.assertNotIn("SDIV", report.histogram)   # signed division now covered
        self.assertNotIn("SMOD", report.histogram)
        self.assertNotIn("MLOAD", report.histogram)  # byte-memory now covered
        self.assertNotIn("MSTORE", report.histogram)
        self.assertNotIn("MSTORE8", report.histogram)
        self.assertNotIn("SLOAD", report.histogram)  # storage now covered
        self.assertNotIn("SSTORE", report.histogram)
        self.assertNotIn("JUMP", report.histogram)   # control flow now covered
        self.assertNotIn("JUMPI", report.histogram)
        self.assertNotIn("JUMPDEST", report.histogram)
        self.assertNotIn("PC", report.histogram)
        self.assertNotIn("PUSH0", report.histogram)   # PUSH0 now covered
        self.assertNotIn("RETURN", report.histogram)  # terminal ops now covered
        self.assertNotIn("REVERT", report.histogram)
        self.assertNotIn("INVALID", report.histogram)
        self.assertIn("MSIZE", report.histogram)     # MSIZE still deferred
        self.assertIn("CALL", report.histogram)      # CALL/CREATE/LOG deferred
        self.assertIn("CREATE", report.histogram)
        self.assertIn("LOG1", report.histogram)
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

    def test_translator_deterministic_sdiv_smod(self):
        # Twice-and-diff over a signed SDIV/SMOD program exercising both the
        # by-zero guard and the INT_MIN/-1 overflow guard (negative operands).
        p = prog(asm.pushn(32, (-1) & MASK256), asm.pushn(32, INT_MIN), asm.sdiv(),
                 asm.pushn(32, (-3) & MASK256), asm.pushn(32, (-7) & MASK256), asm.smod(),
                 asm.stop())
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

    def test_carry_back_sdiv(self):
        # PUSH32 3, PUSH32 -7, SDIV, STOP -> a=-7, b=3 -> -7 / 3 = -2 (trunc);
        # as a bv256 word that is (-2) & MASK256. The BTOR2 witness for that word
        # carries back through L to the reaching signed-division run.
        neg2 = (-2) & MASK256
        code = asm.program(asm.pushn(32, 3), asm.pushn(32, (-7) & MASK256),
                           asm.sdiv(), asm.stop())
        system = translate({"code": code, "property": {"stack_eq": [0, neg2]}})
        trace = replay(system, parse_witness("sat\nb0\n#0\n@0\n.\n"), k=5)
        src = lift(trace)
        self.assertTrue(any(r["s0"] == neg2 for r in src))   # the reaching run
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
