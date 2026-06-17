"""Differential harness for the RISC-V interpreter vs `sail_riscv_sim`.

The trace parser and the executed-stream comparison are tested hermetically
(against a representative sail-log fixture and an injected oracle); the real
emulator invocation is gated on the pinned binary being present (DOCKER.md)."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gurdy.core.oracle import align
from gurdy.languages.riscv import asm, image_from_words, load_elf, run
from gurdy.languages.riscv.differential import (
    PROJECTION,
    OracleUnavailable,
    SailRiscvOracle,
    differential,
    executed_stream,
    find_sail,
    parse_sail_log,
)

# A representative sail-riscv instruction/register trace for
#   addi x1, x0, 8 ; addi x2, x1, 1 ; ecall      (loaded at 0x80000000)
SAMPLE_LOG = """\
[0] [M]: 0x0000000080000000 (0x00800093) addi ra, zero, 8
x1 <- 0x0000000000000008
[1] [M]: 0x0000000080000004 (0x00108113) addi sp, ra, 1
x2 <- 0x0000000000000009
[2] [M]: 0x0000000080000008 (0x00000073) ecall
"""

PROG = [asm.addi(1, 0, 8), asm.addi(2, 1, 1), asm.ecall()]
BASE = 0x80000000


def _gcc():
    return shutil.which("riscv64-unknown-elf-gcc")


class TestParse(unittest.TestCase):
    def test_parse_executed_stream(self):
        rows = parse_sail_log(SAMPLE_LOG)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["pc_exec"], 0x80000000)
        self.assertEqual(rows[0]["x1"], 8)
        self.assertEqual(rows[1]["x2"], 9)
        self.assertEqual(rows[2]["pc_exec"], 0x80000008)
        self.assertEqual(rows[2]["x1"], 8)   # register file persists

    def test_parser_reproduces_interpreter_stream(self):
        ours = executed_stream(run(image_from_words(PROG, base=BASE)), BASE)
        self.assertEqual(parse_sail_log(SAMPLE_LOG), ours)
        self.assertTrue(align(ours, parse_sail_log(SAMPLE_LOG), PROJECTION).ok)


class TestDifferential(unittest.TestCase):
    def test_agreement_via_injected_oracle(self):
        image = image_from_words(PROG, base=BASE)
        result = differential(image=image, oracle_fn=lambda *_: parse_sail_log(SAMPLE_LOG))
        self.assertTrue(result.ok, msg=str(result.divergence))

    def test_divergence_is_localized(self):
        image = image_from_words(PROG, base=BASE)
        wrong = SAMPLE_LOG.replace("x2 <- 0x0000000000000009", "x2 <- 0x000000000000000a")
        result = differential(image=image, oracle_fn=lambda *_: parse_sail_log(wrong))
        self.assertFalse(result.ok)
        self.assertEqual(result.divergence.step, 1)
        self.assertEqual(result.divergence.field, "x2")
        self.assertEqual((result.divergence.left, result.divergence.right), (9, 10))


class TestOracleAvailability(unittest.TestCase):
    def test_missing_binary_raises(self):
        oracle = SailRiscvOracle(binary="/nonexistent/sail_riscv_sim")
        self.assertFalse(oracle.available())
        with self.assertRaises(OracleUnavailable):
            oracle.trace(b"\x7fELF", 10)

    def test_args_from_env(self):
        os.environ["SAIL_RISCV_ARGS"] = "--trace --foo"
        try:
            self.assertEqual(SailRiscvOracle(binary="/x").args, ("--trace", "--foo"))
        finally:
            del os.environ["SAIL_RISCV_ARGS"]


@unittest.skipUnless(find_sail() and _gcc(), "sail_riscv_sim and/or gcc not installed")
class TestRealOracle(unittest.TestCase):
    def test_differential_against_sail(self):
        src = (
            ".section .text\n.globl _start\n_start:\n"
            "  li t0, 0\n  li t1, 1\n  li t2, 5\n"
            "loop:\n  add t0, t0, t1\n  addi t1, t1, 1\n  ble t1, t2, loop\n"
            "  mv a0, t0\n  ecall\n"
        )
        with tempfile.TemporaryDirectory() as d:
            s, elf = Path(d) / "p.s", Path(d) / "p.elf"
            s.write_text(src)
            subprocess.run(
                [_gcc(), "-nostdlib", "-nostartfiles", "-march=rv64im", "-mabi=lp64",
                 "-o", str(elf), str(s)],
                check=True, capture_output=True,
            )
            data = elf.read_bytes()
        # sanity: our interpreter computes the sum
        self.assertEqual(run(load_elf(data))[-1]["x10"], 15)
        result = differential(elf_bytes=data)
        self.assertTrue(result.ok, msg=str(result.divergence))


if __name__ == "__main__":
    unittest.main()
