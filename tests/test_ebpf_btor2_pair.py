"""ebpf-btor2 tests: the commuting square holds across the ALU/JMP/load-store
core plus the legacy ABS/IND packet loads (validated against the shared eBPF
interpreter via the framework oracle), construct coverage is 100% over the
spec-derived inventory, out-of-scope opcodes (CALL) hard-abort, and the emitted
BTOR2 ``bad`` is decided end-to-end through the reused ``btor2-smtlib``
bridge."""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import list_pairs
from gurdy.core.solver import Verdict
from gurdy.languages.btor2 import from_text, to_text
from gurdy.languages.ebpf import asm
from gurdy.languages.ebpf.interp import program_from_words
from gurdy.pairs.ebpf_btor2 import square, translate
from gurdy.pairs.ebpf_btor2.inventory import coverage

# op nibbles used below
ADD, SUB, LSH, ARSH, XOR = 0x0, 0x1, 0x6, 0xC, 0xA
JEQ, JGT, JSGT, JSET = 0x1, 0x2, 0x6, 0x4


def prog(words, init_regs=None, mem=None, pkt=None):
    return {"prog": program_from_words(words, mem, pkt=pkt),
            "init_regs": init_regs or {}}


def ok(self, words, init_regs=None, mem=None, pkt=None):
    report = square(prog(words, init_regs, mem, pkt))
    self.assertTrue(report.ok, msg=str(report.divergence))


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


class TestEbpfBtor2(unittest.TestCase):
    def test_registered(self):
        self.assertIn("ebpf-btor2", list_pairs())

    def test_arithmetic(self):
        ok(self, [asm.mov64(1, 5), asm.mov64(2, 37), asm.add64_reg(1, 2),
                  asm.alu64_reg(SUB, 2, 1), asm.exit_()])

    def test_alu32_and_shifts(self):
        ok(self, [asm.mov64(1, -1), asm.alu32_imm(ADD, 1, 0),       # zero-extend
                  asm.alu64_imm(LSH, 1, 70), asm.alu64_imm(ARSH, 2, 3),
                  asm.alu64_imm(XOR, 3, 0xFF), asm.exit_()])

    def test_div_mod_edges(self):
        # DIV/0 -> 0, MOD/0 -> dst unchanged (the eBPF-defined edges).
        ok(self, [asm.mov64(1, 100), asm.mov64(2, 0),
                  asm.div64_reg(1, 2), asm.mod64_reg(3, 2), asm.exit_()],
           init_regs={3: 55})

    def test_signed_vs_unsigned_jumps(self):
        ok(self, [asm.mov64(1, -1), asm.mov64(0, 0), asm.jmp_imm(JSGT, 1, 0, 1),
                  asm.mov64(0, 7), asm.exit_()])
        ok(self, [asm.mov64(1, -1), asm.mov64(0, 0), asm.jmp_imm(JGT, 1, 0, 1),
                  asm.mov64(0, 7), asm.exit_()])

    def test_jset_and_jeq(self):
        ok(self, [asm.mov64(1, 0b1010), asm.jmp_imm(JSET, 1, 0b0100, 1),
                  asm.mov64(0, 1), asm.jmp_imm(JEQ, 1, 0b1010, 1),
                  asm.mov64(0, 2), asm.exit_()])

    def test_jmp32(self):
        ok(self, [asm.mov64(1, 0xFFFFFFFF), asm.jmp32_imm(JGT, 1, 0, 1),
                  asm.mov64(0, 9), asm.exit_()])

    def test_loop_with_ja(self):
        # countdown loop: r1 = 3; while r1 != 0 { r1-- }; exit
        ok(self, [asm.mov64(1, 3), asm.jmp_imm(JEQ, 1, 0, 2),
                  asm.alu64_imm(SUB, 1, 1), asm.ja(-3), asm.exit_()])

    def test_lddw(self):
        ok(self, [*asm.lddw(1, 0x1122334455667788), asm.exit_()])

    def test_byteswap_square(self):
        # le/be/bswap at 16/32/64 all commute with the interpreter under pi.
        v = 0x1122334455667788
        ok(self, [*asm.lddw(1, v), asm.end_be(1, 16), asm.end_be(2, 32),
                  asm.end_be(3, 64), asm.exit_()], init_regs={2: v, 3: v})
        ok(self, [*asm.lddw(1, v), asm.end_le(1, 16), asm.end_le(2, 32),
                  asm.end_le(3, 64), asm.exit_()], init_regs={2: v, 3: v})
        ok(self, [*asm.lddw(1, v), asm.bswap(1, 16), asm.bswap(2, 32),
                  asm.bswap(3, 64), asm.exit_()], init_regs={2: v, 3: v})

    def test_byteswap_translation_matches_spec(self):
        # T applied then BTOR2-interpreted equals the interpreter's value
        # (be32 of v -> 0x88776655, zero-extended).
        v = 0x1122334455667788
        words = [*asm.lddw(1, v), asm.end_be(1, 32), asm.exit_()]
        report = square(prog(words))
        self.assertTrue(report.ok, msg=str(report.divergence))

    def test_byteswap_bad_width_aborts(self):
        with self.assertRaises(Unsupported):
            translate(prog([asm.end_be(1, 24), asm.exit_()]))
        with self.assertRaises(Unsupported):
            translate(prog([asm.bswap(1, 13), asm.exit_()]))

    def test_memory_roundtrip(self):
        ok(self, [asm.mov64(1, 0x01020304), asm.stx(4, 10, 1, -8),
                  asm.ldx(4, 2, 10, -8), asm.stx(8, 10, 2, -16),
                  asm.ldx(8, 3, 10, -16), asm.exit_()])

    def test_store_immediate(self):
        ok(self, [asm.st(2, 10, 0xBEEF, -4), asm.ldx(2, 1, 10, -4), asm.exit_()])

    # --- legacy packet loads (LD|ABS / LD|IND) ----------------------------
    _PKT = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]

    def test_packet_load_square(self):
        # ABS/IND big-endian reads (B/H/W) all commute with the interpreter.
        ok(self, [asm.ld_abs(4, 0), asm.exit_()], pkt=self._PKT)
        ok(self, [asm.ld_abs(2, 2), asm.exit_()], pkt=self._PKT)
        ok(self, [asm.ld_abs(1, 7), asm.exit_()], pkt=self._PKT)
        ok(self, [asm.ld_ind(4, 6, 1), asm.exit_()], init_regs={6: 2}, pkt=self._PKT)
        ok(self, [asm.ld_ind(2, 6, 0), asm.exit_()], init_regs={6: 5}, pkt=self._PKT)

    def test_packet_load_then_arithmetic_square(self):
        ok(self, [asm.ld_abs(4, 0), asm.alu64_imm(ADD, 0, 1), asm.exit_()],
           pkt=self._PKT)

    def test_packet_oob_drop_edge_square(self):
        # offset+size past the packet end, and a negative offset, both take the
        # defined drop edge (r0=0, halt) and must commute under pi.
        ok(self, [asm.ld_abs(4, 6), asm.mov64(0, 99), asm.exit_()], pkt=self._PKT)
        ok(self, [asm.ld_abs(2, -1), asm.exit_()], pkt=self._PKT)
        ok(self, [asm.ld_ind(4, 6, 0), asm.exit_()], init_regs={6: 100}, pkt=self._PKT)

    def test_packet_ind_address_wraps_mod_2_64(self):
        # The indirect address is 64-bit register arithmetic: src = 2**64 - 1,
        # imm = 1 wraps the address to 0, a valid in-bounds read (interp and the
        # bv64 lowering must wrap identically, not diverge).
        ok(self, [asm.ld_ind(4, 6, 1), asm.exit_()],
           init_regs={6: (1 << 64) - 1}, pkt=self._PKT)

    def test_packet_load_translation_matches_spec(self):
        # T applied then BTOR2-interpreted equals the interpreter's big-endian
        # value (absW at 0 over 0x11,0x22,0x33,0x44 -> 0x11223344).
        report = square(prog([asm.ld_abs(4, 0), asm.exit_()], pkt=self._PKT))
        self.assertTrue(report.ok, msg=str(report.divergence))

    def test_packet_double_size_aborts(self):
        # Packet loads are B/H/W only; the LD|ABS|DW form (code 0x38) is not a
        # valid packet load and must hard-abort (still-unsupported ld opcode).
        ld_abs_dw = asm._insn(0x00 | 0x20 | 0x18, 0, 0, 0, 0)  # LD | ABS | DW
        with self.assertRaises(Unsupported):
            translate(prog([ld_abs_dw, asm.exit_()], pkt=self._PKT))

    def test_call_aborts(self):
        with self.assertRaises(Unsupported):
            translate(prog([asm.call(1), asm.exit_()]))

    def test_coverage_full(self):
        report = coverage()
        self.assertEqual(report.missing, {})
        self.assertEqual(report.fraction, 1.0)
        # ratchet: ALU/JMP/mem core + byte-swap + ABS/IND packet loads (was 118).
        self.assertGreaterEqual(report.total, 124)
        # byte-swap and the packet loads are covered constructs (the widenings).
        for name in ("LE16", "BE32", "BSWAP64",
                     "LDABSW", "LDABSB", "LDINDW", "LDINDB"):
            self.assertIn(name, report.covered)

    def test_deterministic_canonical_btor2(self):
        p = prog([asm.mov64(0, 42), asm.exit_()])
        a1, a2 = translate(p), translate(p)
        self.assertEqual(a1, a2)
        self.assertEqual(to_text(from_text(a1.decode())), a1.decode())

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_reachable_via_bridge(self):
        # eBPF -> BTOR2 (with a bad) -> SMT-LIB -> z3, witness replayed.
        from gurdy.pairs.btor2_smtlib import reach

        program = prog([asm.mov64(0, 42), asm.exit_()])
        program["property"] = {"reg_eq": [0, 42]}
        info = reach(translate(program), 3)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("r0") == 42 for row in info["behavior"]))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_decide_unreachable_via_bridge(self):
        from gurdy.pairs.btor2_smtlib import reach

        program = prog([asm.mov64(0, 42), asm.exit_()])
        program["property"] = {"reg_eq": [0, 999]}  # r0 is 42, never 999
        self.assertEqual(reach(translate(program), 3)["verdict"], Verdict.UNREACHABLE)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_byteswap_carry_back_via_bridge(self):
        # A BTOR2 witness for the byte-swapped result replays through L.
        from gurdy.pairs.btor2_smtlib import reach

        v = 0x1122334455667788
        program = prog([*asm.lddw(1, v), asm.end_be(1, 32), asm.exit_()])
        program["property"] = {"reg_eq": [1, 0x88776655]}  # be32(v)
        info = reach(translate(program), 5)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("r1") == 0x88776655 for row in info["behavior"]))

        program["property"] = {"reg_eq": [1, 0xDEADBEEF]}  # never byte-swapped to this
        self.assertEqual(reach(translate(program), 5)["verdict"], Verdict.UNREACHABLE)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_packet_drop_carry_back_via_bridge(self):
        # With an empty packet every load is out of bounds, so the drop edge
        # forces r0=0 (reachable, witness replays through L) and any nonzero
        # r0 is unreachable regardless of the symbolic packet bytes.
        from gurdy.pairs.btor2_smtlib import reach

        program = prog([asm.ld_abs(4, 0), asm.exit_()], pkt=[])
        program["property"] = {"reg_eq": [0, 0]}
        info = reach(translate(program), 4)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(any(row.get("r0") == 0 for row in info["behavior"]))

        program["property"] = {"reg_eq": [0, 5]}  # drop forces r0=0, never 5
        self.assertEqual(reach(translate(program), 4)["verdict"], Verdict.UNREACHABLE)


if __name__ == "__main__":
    unittest.main()
