"""Wiring the Sail interpreter to the gold oracle.

Hermetically, the two independent RISC-V interpreters (the hand-written one
and the Sail-derived one) must produce the *same* executed-instruction stream
on an RV64IM program. The real ``sail_riscv_sim`` comparison is gated on the
pinned emulator (and the toolchain to build a binary)."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gurdy.languages.riscv import asm
from gurdy.languages.riscv.differential import differential, executed_stream, find_sail
from gurdy.languages.riscv.interp import image_from_words
from gurdy.languages.riscv.interp import run as riscv_run
from gurdy.languages.sail.differential import sail_subject
from gurdy.languages.sail.interp import run as sail_run


def _gcc():
    return shutil.which("riscv64-unknown-elf-gcc")


def _compile(src, march="rv64im"):
    with tempfile.TemporaryDirectory() as d:
        s, elf = Path(d) / "p.s", Path(d) / "p.elf"
        s.write_text(src)
        subprocess.run(
            # link at 0x80000000 so the Sail model can fetch the image (its
            # default executable region); the gated differential below runs
            # the real sail_riscv_sim on this ELF.
            [_gcc(), "-nostdlib", "-nostartfiles", f"-march={march}", "-mabi=lp64",
             "-Wl,-Ttext=0x80000000", "-o", str(elf), str(s)],
            check=True, capture_output=True,
        )
        return elf.read_bytes()


# ALU + M + a taken branch + store/load, ending in ECALL
WORDS = [
    asm.addi(1, 0, 5), asm.addi(2, 0, 5), asm.beq(1, 2, 8), asm.addi(3, 0, 99),
    asm.addi(4, 0, 7), asm.mul(5, 1, 4), asm.addi(6, 0, 512),
    asm.sw(4, 6, 0), asm.lw(7, 6, 0), asm.ecall(),
]


class TestInterpretersAgree(unittest.TestCase):
    def test_sail_matches_riscv_executed_stream(self):
        # the Sail-derived interpreter and the hand-written RISC-V interpreter
        # are independent; on the same RV64IM program their executed streams
        # must coincide (the cross-check, hermetic).
        riscv_stream = executed_stream(riscv_run(image_from_words(WORDS)), 0)
        sail_stream = executed_stream(
            sail_run({"words": WORDS, "entry": 0, "init_regs": {}, "mem": {}}), 0)
        self.assertEqual(sail_stream, riscv_stream)
        self.assertEqual(sail_stream[-1]["x7"], 7)   # store->load roundtrip landed


@unittest.skipUnless(_gcc(), "riscv64-unknown-elf-gcc not installed")
class TestSailSubjectOnElf(unittest.TestCase):
    SRC = (
        ".section .text\n.globl _start\n_start:\n"
        "  li t0, 0\n  li t1, 1\n  li t2, 5\n"
        "loop:\n  add t0, t0, t1\n  addi t1, t1, 1\n  ble t1, t2, loop\n"
        "  mv a0, t0\n  ecall\n"
    )

    def test_sail_subject_matches_riscv_on_real_binary(self):
        from gurdy.languages.riscv.elf import load_elf
        elf = _compile(self.SRC)
        img = load_elf(elf)
        riscv_stream = executed_stream(riscv_run(img), img.entry)
        self.assertEqual(sail_subject(elf), riscv_stream)

    @unittest.skipUnless(find_sail(), "sail_riscv_sim not installed")
    def test_sail_interp_vs_sail_riscv_sim(self):
        # the Sail-derived interpreter, validated against the real Sail model
        result = differential(_compile(self.SRC), subject=sail_subject)
        self.assertTrue(result.ok, msg=str(result.divergence))


if __name__ == "__main__":
    unittest.main()
