"""RV64C (compressed) support: the decompressor expands to the right base
instruction, hand-built compressed programs round-trip through the riscv-btor2
square, and a real `-march=rv64imc` gcc binary (mixed 16-/32-bit stream) runs
in the interpreter and through the square — validating `expand` against the
toolchain (same source at rv64im vs rv64imc yields identical behavior)."""

import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from gurdy.core.errors import Unsupported
from gurdy.languages.riscv import asm, casm, image_from_bytes, load_elf, run
from gurdy.languages.riscv.compressed import expand, is_compressed
from gurdy.pairs.riscv_btor2 import square


def _gcc():
    return shutil.which("riscv64-unknown-elf-gcc")


def _img(halfwords, tail32=None):
    code = b"".join(struct.pack("<H", h & 0xFFFF) for h in halfwords)
    if tail32 is not None:
        code += struct.pack("<I", tail32)
    return image_from_bytes(code)


class TestExpand(unittest.TestCase):
    def test_is_compressed(self):
        self.assertTrue(is_compressed(casm.c_li(10, 1)))
        self.assertFalse(is_compressed(asm.addi(10, 0, 1)))  # base insns end in 0b11

    def test_expansion_matches_base(self):
        self.assertEqual(expand(casm.c_li(10, 5)), asm.addi(10, 0, 5))
        self.assertEqual(expand(casm.c_add(11, 10)), asm.add(11, 11, 10))
        self.assertEqual(expand(casm.c_mv(11, 10)), asm.add(11, 0, 10))
        self.assertEqual(expand(casm.c_jr(5)), asm.jalr(0, 5, 0))

    def test_reserved_and_float_abort(self):
        with self.assertRaises(Unsupported):
            expand(0x0000)            # illegal
        with self.assertRaises(Unsupported):
            expand((1 << 13) | 0x0)   # C.FLD (q0 funct3=1, float)


class TestCompressedInterp(unittest.TestCase):
    def test_li_add_mv(self):
        # c.li a0,20; c.li a1,22; c.add a0,a1; c.mv a2,a0; ebreak
        # (C.LI's immediate is 6-bit signed, range -32..31)
        img = _img([casm.c_li(10, 20), casm.c_li(11, 22), casm.c_add(10, 11),
                    casm.c_mv(12, 10), casm.c_ebreak()])
        f = run(img)[-1]
        self.assertEqual(f["x10"], 42)
        self.assertEqual(f["x12"], 42)
        self.assertTrue(f["halted"])

    def test_compressed_branch(self):
        # a8 = x8; c.li a0,0; c.beqz a8,+4 (skip); c.li a0,9; ebreak
        img = _img([casm.c_li(10, 0), casm.c_beqz(8, 4), casm.c_li(10, 9), casm.c_ebreak()])
        # x8 defaults to 0 -> branch taken -> skips c.li a0,9 -> a0 stays 0
        self.assertEqual(run(img)[-1]["x10"], 0)


class TestCompressedSquare(unittest.TestCase):
    def ok(self, halfwords, tail32=None, init_regs=None):
        report = square({"image": _img(halfwords, tail32), "init_regs": init_regs or {}})
        self.assertTrue(report.ok, msg=str(report.divergence))

    def test_arith_square(self):
        self.ok([casm.c_li(10, 5), casm.c_li(11, 37), casm.c_add(10, 11),
                 casm.c_mv(12, 10), casm.c_slli(12, 2), casm.c_ebreak()])

    def test_mixed_16_32_square(self):
        # compressed + a 32-bit ECALL tail: the variable-length walk must align
        self.ok([casm.c_li(10, 1), casm.c_addi(10, 4), casm.c_andi(8, 6)],
                tail32=asm.ecall())

    def test_branch_loop_square(self):
        # countdown: c.li a0,3; loop: c.addi a0,-1; c.bnez a0,loop; ebreak
        self.ok([casm.c_li(10, 3), casm.c_addi(10, -1), casm.c_bnez(10, -2), casm.c_ebreak()])


class TestToolchainCompressed(unittest.TestCase):
    SRC = (
        ".section .text\n.globl _start\n_start:\n"
        "  li t0, 0\n  li t1, 1\n  li t2, 5\n"
        "loop:\n  add t0, t0, t1\n  addi t1, t1, 1\n  ble t1, t2, loop\n"
        "  mv a0, t0\n  ecall\n"
    )

    def _compile(self, march):
        with tempfile.TemporaryDirectory() as d:
            s, elf = Path(d) / "p.s", Path(d) / "p.elf"
            s.write_text(self.SRC)
            subprocess.run(
                [_gcc(), "-nostdlib", "-nostartfiles", f"-march={march}", "-mabi=lp64",
                 "-o", str(elf), str(s)],
                check=True, capture_output=True,
            )
            return load_elf(elf.read_bytes())

    @unittest.skipUnless(_gcc(), "riscv64-unknown-elf-gcc not installed")
    def test_rv64imc_equivalent_to_rv64im(self):
        # same source, with and without the C extension -> identical behavior,
        # validating the decompressor against the toolchain.
        base = self._compile("rv64im")
        comp = self._compile("rv64imc")
        self.assertLess(comp.code_hi - comp.code_lo, base.code_hi - base.code_lo)  # smaller
        self.assertEqual(run(comp)[-1]["x10"], run(base)[-1]["x10"])
        self.assertEqual(run(comp)[-1]["x10"], 15)

    @unittest.skipUnless(_gcc(), "riscv64-unknown-elf-gcc not installed")
    def test_rv64imc_through_square(self):
        report = square({"image": self._compile("rv64imc"), "init_regs": {}})
        self.assertTrue(report.ok, msg=str(report.divergence))


if __name__ == "__main__":
    unittest.main()
