"""Shared eBPF interpreter tests: ALU64 / ALU32 (with 32-bit zero-extension),
the kernel-defined DIV/MOD-by-zero edges, signed vs unsigned jumps, LDDW, and
the memory core. Hand-computed expected values pin the oracle itself."""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.languages.ebpf import asm
from gurdy.languages.ebpf.interp import program_from_words, run

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

    def test_call_aborts(self):
        with self.assertRaises(Unsupported):
            run(program_from_words([asm.call(1), asm.exit_()]))

    def test_runs_off_end_halts(self):
        trace = run(program_from_words([asm.mov64(1, 1)]))  # no EXIT
        self.assertTrue(trace[-1]["halted"])


if __name__ == "__main__":
    unittest.main()
