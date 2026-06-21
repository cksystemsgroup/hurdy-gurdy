"""Csmith differential fuzzing of c-riscv (tools/csmith_fuzz; BENCHMARKS.md §3).

Gated on the full toolchain (csmith + native gcc + the pinned cross gcc), which
lives only in the dev image (DOCKER.md) — so this skips on the host and runs
in-container. Small Csmith programs (the tight `--no-arrays` config) are
compiled native vs riscv-and-interpreted; the CRC checksums must agree. A
program that exceeds the step cap is a first-class skip, not a failure.
"""

import unittest

from tools.csmith_fuzz import available, differential


@unittest.skipUnless(available(), "csmith toolchain absent (dev-image only)")
class TestCsmithDifferential(unittest.TestCase):
    def test_small_programs_match_native(self):
        compared = 0
        for seed in (1, 2, 3, 4, 5):
            r = differential(seed, step_cap=300_000)
            if r["status"] == "skip":
                continue  # too big for the pure-Python interp, or no symbol
            self.assertEqual(
                r["status"], "match",
                msg=f"seed {seed}: riscv={r['riscv']:#010x} native={r['native']:#010x}")
            compared += 1
        self.assertGreater(compared, 0, "no seed produced a runnable comparison")

    def test_skip_is_first_class(self):
        # a program over a tiny cap is reported as a skip, never a hang/failure.
        r = differential(2, step_cap=200)
        self.assertEqual(r["status"], "skip")
        self.assertIn("too-big", r["reason"])


if __name__ == "__main__":
    unittest.main()
