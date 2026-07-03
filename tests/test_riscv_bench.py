"""The riscv-tests-derived reachability benchmark (tools/riscv_bench.py),
end to end on one slice program.

The full 10-program / 78-question sweep is the harvest's job
(paper/results/harvest.py --only bench); this test keeps the mechanism
honest in the suite: build one compliance program with the pinned
toolchain, derive its questions from a reference run, decide each along
BOTH RISC-V routes, and require full agreement and full ground-truth match.

Gated on the toolchain and z3."""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


def _load_tool(name: str):
    path = Path(__file__).resolve().parent.parent / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gcc():
    return shutil.which("riscv64-unknown-elf-gcc")


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_gcc() and _z3(), "needs riscv64-unknown-elf-gcc + z3")
class TestRiscvBench(unittest.TestCase):
    def test_jump_program_questions_agree_and_match_ground_truth(self):
        riscv_slice = _load_tool("riscv_slice")
        riscv_bench = _load_tool("riscv_bench")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "rv64ui-jump.s"
            elf = Path(d) / "rv64ui-jump"
            march, body = riscv_slice.SLICE["rv64ui-jump"]
            src.write_text(riscv_slice._source(body))
            import subprocess
            subprocess.run(
                [riscv_slice.find_gcc(), "-nostdlib", "-nostartfiles",
                 f"-march={march}", "-mabi=lp64", "-mno-relax",
                 "-Wl,--no-relax", "-Wl,-Ttext=0x80000000",
                 "-o", str(elf), str(src)],
                check=True, capture_output=True)
            src.unlink()   # run_benchmark walks extensionless files only
            report = riscv_bench.run_benchmark(d)
        self.assertEqual(len(report["programs"]), 1)
        totals = report["totals"]
        self.assertGreaterEqual(totals["questions"], 4)
        self.assertEqual(totals["agree"], totals["questions"])
        self.assertEqual(totals["correct"], totals["questions"])
        # Both expected verdicts occur (a reach and an unreach per register).
        expectations = {q["expected"]
                        for q in report["programs"][0]["questions"]}
        self.assertEqual(expectations, {"REACHABLE", "UNREACHABLE"})


if __name__ == "__main__":
    unittest.main()
