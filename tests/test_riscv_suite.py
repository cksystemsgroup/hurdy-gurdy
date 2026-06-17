"""Coverage-slice loader for riscv-tests / riscv-arch-test.

The grading logic (HTIF tohost status, signature parse/extract, discovery) is
unit-tested hermetically; real self-checking tests built with the toolchain in
each suite's convention exercise the loader end-to-end (gated on gcc)."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gurdy.languages.riscv import RiscvImage, load_elf, run
from gurdy.languages.riscv.suite import (
    SuiteReport,
    TestResult,
    discover,
    extract_signature,
    parse_signature,
    run_elf_test,
    run_signature_test,
    run_suite,
    tohost_status,
)

TOHOST = (
    '.section .tohost,"aw",@progbits\n.align 3\n.globl tohost\ntohost:\n  .dword 0\n'
)


def _gcc():
    return shutil.which("riscv64-unknown-elf-gcc")


def _compile(src):
    with tempfile.TemporaryDirectory() as d:
        s, elf = Path(d) / "p.s", Path(d) / "p.elf"
        s.write_text(src)
        subprocess.run(
            [_gcc(), "-nostdlib", "-nostartfiles", "-march=rv64im", "-mabi=lp64",
             "-o", str(elf), str(s)],
            check=True, capture_output=True,
        )
        return elf.read_bytes()


class TestGradingLogic(unittest.TestCase):
    def test_tohost_status(self):
        self.assertEqual(tohost_status(1)[0], "pass")
        self.assertEqual(tohost_status(0)[0], "incomplete")
        self.assertEqual(tohost_status(7), ("fail", "failed test #3"))
        self.assertEqual(tohost_status(4)[0], "error")

    def test_parse_signature(self):
        self.assertEqual(parse_signature("deadbeef\n12345678\n"), [0xDEADBEEF, 0x12345678])

    def test_extract_signature(self):
        img = RiscvImage(entry=0, code_lo=0, code_hi=4,
                         symbols={"begin_signature": 0x100, "end_signature": 0x108})
        img.store(0x100, 4, 0xAABBCCDD)
        img.store(0x104, 4, 0x11223344)
        self.assertEqual(extract_signature(img), [0xAABBCCDD, 0x11223344])

    def test_discover(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "rv64ui-p-add").write_bytes(b"\x7fELF" + b"\x00" * 60)
            (Path(d) / "rv64ui-p-add.dump").write_text("disasm")
            (Path(d) / "notes.txt").write_text("hi")
            found = discover(d)
        self.assertEqual([p.name for p in found], ["rv64ui-p-add"])

    def test_report_summary(self):
        rep = SuiteReport([
            TestResult("rv64ui-p-add", "pass", isa="rv64ui"),
            TestResult("rv64ui-p-sub", "fail", "failed test #2", isa="rv64ui"),
            TestResult("rv64um-p-mul", "pass", isa="rv64um"),
        ])
        self.assertEqual((rep.total, rep.passed), (3, 2))
        self.assertFalse(rep.ok)
        self.assertEqual(rep.by_isa(), {"rv64ui": (1, 2), "rv64um": (1, 1)})


@unittest.skipUnless(_gcc(), "riscv64-unknown-elf-gcc not installed")
class TestSuiteEndToEnd(unittest.TestCase):
    def _tohost_prog(self, code_word):
        return (
            ".section .text\n.globl _start\n_start:\n"
            f"  li t0, {code_word}\n  la t1, tohost\n  sd t0, 0(t1)\n1:  j 1b\n" + TOHOST
        )

    def test_pass(self):
        r = run_elf_test(_compile(self._tohost_prog(1)), "rv64ui-p-demo")
        self.assertEqual(r.status, "pass", msg=r.detail)
        self.assertEqual(r.isa, "rv64ui")

    def test_fail_reports_test_number(self):
        r = run_elf_test(_compile(self._tohost_prog(7)), "rv64ui-p-demo")  # (3<<1)|1
        self.assertEqual((r.status, r.detail), ("fail", "failed test #3"))

    def test_incomplete(self):
        # ecalls without ever writing tohost
        src = ".section .text\n.globl _start\n_start:\n  li a0, 5\n  ecall\n" + TOHOST
        self.assertEqual(run_elf_test(_compile(src), "rv64ui-p-x").status, "incomplete")

    def test_signature(self):
        src = (
            ".section .text\n.globl _start\n_start:\n"
            "  la t0, begin_signature\n"
            "  li t1, 0xdeadbeef\n  sw t1, 0(t0)\n"
            "  li t1, 0x12345678\n  sw t1, 4(t0)\n"
            "  li t2, 1\n  la t3, tohost\n  sd t2, 0(t3)\n1:  j 1b\n"
            ".section .data\n.align 4\n"
            ".globl begin_signature\nbegin_signature:\n  .zero 8\n"
            ".globl end_signature\nend_signature:\n" + TOHOST
        )
        elf = _compile(src)
        self.assertEqual(run_signature_test(elf, "deadbeef\n12345678\n").status, "pass")
        bad = run_signature_test(elf, "deadbeef\n00000000\n")
        self.assertEqual(bad.status, "fail")
        self.assertIn("word 1", bad.detail)

    def test_run_suite(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "rv64ui-p-pass").write_bytes(_compile(self._tohost_prog(1)))
            Path(d, "rv64ui-p-fail").write_bytes(_compile(self._tohost_prog(7)))
            rep = run_suite(d)
        self.assertEqual((rep.total, rep.passed), (2, 1))
        self.assertEqual(rep.by_isa()["rv64ui"], (1, 2))


if __name__ == "__main__":
    unittest.main()
