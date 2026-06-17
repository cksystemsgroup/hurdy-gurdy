"""The curated RV64IMC compliance slice (tools/riscv_slice.py), end to end.

The slice is the shared RISC-V interpreter's coverage anchor (languages/riscv
brief; BENCHMARKS.md §4): self-checking programs in the riscv-tests HTIF
``tohost`` convention, restricted to the user ISA the interpreter implements
(the upstream ``-p-`` binaries need M-mode CSR/trap support that is out of
scope -- see tools/riscv_slice.py). This test builds the slice with the pinned
toolchain, grades it all-pass, and -- when sail_riscv_sim is present -- runs the
differential across every program so the interpreter is validated step-for-step
against the gold oracle on the same images (the brief's coverage-slice
acceptance step).

Gated on the toolchain (build + grade) and additionally on sail_riscv_sim (the
differential)."""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

from gurdy.languages.riscv.differential import differential, find_sail
from gurdy.languages.riscv.suite import run_suite


def _load_slice_module():
    path = Path(__file__).resolve().parent.parent / "tools" / "riscv_slice.py"
    spec = importlib.util.spec_from_file_location("riscv_slice", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


riscv_slice = _load_slice_module()


def _gcc():
    return shutil.which("riscv64-unknown-elf-gcc")


@unittest.skipUnless(_gcc(), "riscv64-unknown-elf-gcc not installed")
class TestComplianceSlice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._d = tempfile.TemporaryDirectory()
        cls.elfs = riscv_slice.build(cls._d.name)

    @classmethod
    def tearDownClass(cls):
        cls._d.cleanup()

    def test_slice_covers_each_isa(self):
        # the human-set coverage target must not be silently shrunk
        isas = {name.split("-", 1)[0] for name in riscv_slice.SLICE}
        self.assertEqual(isas, {"rv64ui", "rv64um", "rv64uc"})

    def test_all_pass_under_htif_grading(self):
        report = run_suite(self._d.name)
        self.assertTrue(report.ok, msg=report.summary())
        self.assertEqual(report.total, len(riscv_slice.SLICE))
        # every ISA group fully passes
        for isa, (passed, total) in report.by_isa().items():
            self.assertEqual(passed, total, msg=f"{isa}: {passed}/{total}\n{report.summary()}")

    @unittest.skipUnless(find_sail(), "sail_riscv_sim not installed")
    def test_differential_against_sail_across_slice(self):
        for elf in self.elfs:
            data = elf.read_bytes()
            result = differential(elf_bytes=data)
            self.assertTrue(result.ok, msg=f"{elf.name}: {result.divergence}")


if __name__ == "__main__":
    unittest.main()
