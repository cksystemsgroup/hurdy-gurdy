"""Smoke test for the route-grader runner (tools/route_grader.py): the CI
entry that seeds the cost ledger through the instrumented call sites.
Run capped and solver-free in a subprocess (real argv handling, no
registry side effects in this process); the ledger must come back
populated with translate and cross_check records, and running without a
configured ledger must refuse rather than silently discard."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOL = os.path.join(_REPO, "tools", "route_grader.py")


class TestRouteGraderTool(unittest.TestCase):
    def test_capped_run_seeds_the_ledger(self):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        try:
            env = {**os.environ, "GURDY_LEDGER": path}
            proc = subprocess.run(
                [sys.executable, _TOOL, "--sources", "riscv",
                 "--max-probes", "2", "--no-decide"],
                capture_output=True, text=True, env=env, cwd=_REPO,
                timeout=300)
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertIn("capped", proc.stdout)  # a capped result says so
            self.assertIn("--- ledger profiles", proc.stdout)
            with open(path, encoding="utf-8") as f:
                kinds = {json.loads(line)["kind"] for line in f if line.strip()}
            self.assertIn("translate", kinds)
            self.assertIn("cross_check", kinds)
        finally:
            os.unlink(path)

    def test_refuses_to_run_without_a_ledger(self):
        env = {k: v for k, v in os.environ.items() if k != "GURDY_LEDGER"}
        proc = subprocess.run(
            [sys.executable, _TOOL, "--sources", "riscv",
             "--max-probes", "1", "--no-decide"],
            capture_output=True, text=True, env=env, cwd=_REPO, timeout=300)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("GURDY_LEDGER", proc.stderr)


if __name__ == "__main__":
    unittest.main()
