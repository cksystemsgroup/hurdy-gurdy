"""Differential fuzzing of the RISC-V ⟂ Sail realizations (BENCHMARKS.md §3).

Random straight-line RV64IMC programs (mixed 2-/4-byte, random operands, random
initial registers — `tools/riscv_fuzz`) are run through the two *independent*
realizations; they must produce identical traces. This stresses the ALU/M/C
datapaths and the compressed-fetch path well past the curated coverage probes,
and a divergence is a real bug in one realization. Seeded ⇒ reproducible.
"""

import json
import unittest

from tools.riscv_fuzz import random_program
from gurdy.languages.riscv.interp import run as riscv_run
from gurdy.languages.sail.interp import run as sail_run
from gurdy.pairs.riscv_sail import translate as riscv_sail

_OBS = ("pc", "halted", *(f"x{r}" for r in range(1, 32)))


def _proj(trace):
    return [{k: s[k] for k in _OBS if k in s} for s in trace]


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


class TestInterpDifferential(unittest.TestCase):
    def test_riscv_vs_sail_agree_on_random_programs(self):
        for seed in range(120):
            image, init = random_program(seed, n_instr=24)
            rv = _proj(riscv_run(image, {"regs": init}))
            sail_prog = json.loads(riscv_sail({"image": image, "init_regs": init}).decode())
            sail = _proj(sail_run(sail_prog, {"regs": init}))
            self.assertEqual(rv, sail, msg=f"divergence at seed {seed}")

    def test_init_registers_actually_vary_state(self):
        # guard against a vacuous differential (both starting from zero).
        image, init = random_program(1, n_instr=24)
        self.assertNotEqual(list(riscv_run(image, {"regs": init})),
                            list(riscv_run(image, {})))


@unittest.skipUnless(_z3(), "z3 not installed")
class TestBranchAgreementUnderFuzz(unittest.TestCase):
    """The direct (riscv-btor2) and via-Sail routes must decide the same
    reachability question identically on random programs."""

    def test_routes_agree(self):
        from gurdy.pairs.btor2_smtlib import reach
        from gurdy.pairs.riscv_btor2 import translate as rv_btor2
        from gurdy.pairs.sail_btor2 import translate as sail_btor2

        for seed in range(4):
            n = 5
            image, init = random_program(seed, n_instr=n)
            final = list(riscv_run(image, {"regs": init}))[-1]
            reg = 1 + (seed % 31)
            actual = final[f"x{reg}"]
            for val, expect in [(actual, "reachable"), ((actual + 1) & ((1 << 64) - 1), "unreachable")]:
                prop = {"reg_eq": [reg, val]}
                prog = {"image": image, "init_regs": init, "property": prop}
                direct = reach(rv_btor2(prog), n + 1)["verdict"]
                via = reach(sail_btor2(riscv_sail(prog)), n + 1)["verdict"]
                self.assertEqual(direct, via, msg=f"seed {seed} x{reg}=={val}")
                self.assertEqual(direct.value, expect, msg=f"seed {seed} x{reg}=={val}")


if __name__ == "__main__":
    unittest.main()
