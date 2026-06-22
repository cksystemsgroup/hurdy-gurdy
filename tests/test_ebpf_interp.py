"""Shared eBPF interpreter tests: ALU64 / ALU32 (with 32-bit zero-extension),
the kernel-defined DIV/MOD-by-zero edges, byte-swap (BPF_END), signed vs
unsigned jumps, LDDW, the memory core, and the legacy ABS/IND packet loads
(big-endian reads + the out-of-bounds drop edge). Hand-computed expected values
pin the oracle itself."""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.languages.ebpf import asm
from gurdy.languages.ebpf.interp import byteswap, program_from_words, run

# JMP op nibbles
JGT, JSGT = 0x2, 0x6


def last(words, mem=None):
    return run(program_from_words(words, mem))[-1]


class TestEbpfInterp(unittest.TestCase):
    def test_arithmetic(self):
        f = last([asm.mov64(1, 5), asm.mov64(2, 37), asm.add64_reg(1, 2), asm.exit_()])
        self.assertEqual(f["r1"], 42)

    def test_alu32_zero_extends(self):
        # 32-bit ALU writes clear the upper 32 bits of the destination.
        f = last([*asm.lddw(1, 0x1122334455667788), asm.alu32_imm(0x0, 1, 0), asm.exit_()])
        self.assertEqual(f["r1"], 0x55667788)

    def test_div_by_zero_is_zero(self):
        f = last([asm.mov64(1, 100), asm.mov64(2, 0), asm.div64_reg(1, 2), asm.exit_()])
        self.assertEqual(f["r1"], 0)

    def test_mod_by_zero_unchanged(self):
        f = last([asm.mov64(1, 100), asm.mov64(2, 0), asm.mod64_reg(1, 2), asm.exit_()])
        self.assertEqual(f["r1"], 100)

    def test_signed_jump_not_taken(self):
        # r1 = -1; JSGT (signed) -1 > 0 is false -> fall through, r0 set to 7.
        f = last([asm.mov64(1, -1), asm.mov64(0, 0),
                  asm.jmp_imm(JSGT, 1, 0, 1), asm.mov64(0, 7), asm.exit_()])
        self.assertEqual(f["r0"], 7)

    def test_unsigned_jump_taken(self):
        # same shape, JGT (unsigned): 0xFFFF.. > 0 is true -> skip, r0 stays 0.
        f = last([asm.mov64(1, -1), asm.mov64(0, 0),
                  asm.jmp_imm(JGT, 1, 0, 1), asm.mov64(0, 7), asm.exit_()])
        self.assertEqual(f["r0"], 0)

    def test_lddw(self):
        f = last([*asm.lddw(1, 0x1122334455667788), asm.exit_()])
        self.assertEqual(f["r1"], 0x1122334455667788)

    def test_memory_store_load(self):
        f = last([asm.mov64(1, 0x01020304),
                  asm.stx(4, 10, 1, -8), asm.ldx(4, 2, 10, -8), asm.exit_()])
        self.assertEqual(f["r2"], 0x01020304)

    def test_byteswap_helper(self):
        self.assertEqual(byteswap(0x1234, 16), 0x3412)
        self.assertEqual(byteswap(0x11223344, 32), 0x44332211)
        self.assertEqual(byteswap(0x1122334455667788, 64), 0x8877665544332211)

    def test_end_be_byteswaps_and_zero_extends(self):
        v = 0x1122334455667788
        self.assertEqual(last([*asm.lddw(1, v), asm.end_be(1, 16), asm.exit_()])["r1"], 0x8877)
        self.assertEqual(last([*asm.lddw(1, v), asm.end_be(1, 32), asm.exit_()])["r1"], 0x88776655)
        self.assertEqual(last([*asm.lddw(1, v), asm.end_be(1, 64), asm.exit_()])["r1"],
                         0x8877665544332211)

    def test_end_le_truncates_no_reorder(self):
        # On the little-endian host model, le is the width truncation (no swap).
        v = 0x1122334455667788
        self.assertEqual(last([*asm.lddw(1, v), asm.end_le(1, 16), asm.exit_()])["r1"], 0x7788)
        self.assertEqual(last([*asm.lddw(1, v), asm.end_le(1, 32), asm.exit_()])["r1"], 0x55667788)
        self.assertEqual(last([*asm.lddw(1, v), asm.end_le(1, 64), asm.exit_()])["r1"], v)

    def test_bswap_alu64_is_unconditional_swap(self):
        v = 0x1122334455667788
        self.assertEqual(last([*asm.lddw(1, v), asm.bswap(1, 64), asm.exit_()])["r1"],
                         0x8877665544332211)
        self.assertEqual(last([*asm.lddw(1, v), asm.bswap(1, 16), asm.exit_()])["r1"], 0x8877)

    def test_end_bad_width_aborts(self):
        with self.assertRaises(Unsupported):
            run(program_from_words([asm.end_be(1, 24), asm.exit_()]))

    def test_call_aborts(self):
        with self.assertRaises(Unsupported):
            run(program_from_words([asm.call(1), asm.exit_()]))

    def test_runs_off_end_halts(self):
        trace = run(program_from_words([asm.mov64(1, 1)]))  # no EXIT
        self.assertTrue(trace[-1]["halted"])

    # --- legacy packet loads (LD|ABS / LD|IND) ----------------------------
    _PKT = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]

    def test_ld_abs_big_endian(self):
        # ABS reads big-endian (network byte order) into r0.
        p = lambda *w: program_from_words(list(w), pkt=self._PKT)
        self.assertEqual(run(p(asm.ld_abs(4, 0), asm.exit_()))[-1]["r0"], 0x11223344)
        self.assertEqual(run(p(asm.ld_abs(2, 2), asm.exit_()))[-1]["r0"], 0x3344)
        self.assertEqual(run(p(asm.ld_abs(1, 7), asm.exit_()))[-1]["r0"], 0x88)

    def test_ld_ind_offset_from_register(self):
        # IND offset = src + imm; src=r6=2, imm=1 -> offset 3 -> bytes 0x44556677.
        prog = program_from_words([asm.ld_ind(4, 6, 1), asm.exit_()], pkt=self._PKT)
        self.assertEqual(run(prog, {"regs": {6: 2}})[-1]["r0"], 0x44556677)

    def test_ld_abs_oob_takes_drop_edge(self):
        # offset 6 + size 4 > len 8: the defined drop edge -> r0=0, halt at once
        # (the trailing MOV is never executed).
        prog = program_from_words(
            [asm.ld_abs(4, 6), asm.mov64(0, 99), asm.exit_()], pkt=self._PKT)
        trace = run(prog)
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[-1]["r0"], 0)
        self.assertTrue(trace[-1]["halted"])

    def test_ld_abs_negative_offset_is_oob(self):
        prog = program_from_words([asm.ld_abs(2, -1), asm.exit_()], pkt=self._PKT)
        last = run(prog)[-1]
        self.assertEqual(last["r0"], 0)
        self.assertTrue(last["halted"])

    def test_ld_abs_at_exact_end_in_bounds(self):
        # offset 6 + size 2 == len 8 is the last in-bounds read (boundary).
        prog = program_from_words([asm.ld_abs(2, 6), asm.exit_()], pkt=self._PKT)
        self.assertEqual(run(prog)[-1]["r0"], 0x7788)


if __name__ == "__main__":
    unittest.main()
