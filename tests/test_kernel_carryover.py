"""The carried-over registry content, re-checked (KERNEL.md §7).

The committed ``registry/`` entries — the btor2 language wrapping v3's
shared interpreter, and btormc and pono as solver pairs — must still
pass the kernel's gate exactly as admitted, and the committed demo run
must replay: same verdicts, byte-identical report. Skipped where the
engines are not on the PATH (the language checks run everywhere)."""

import json
import os
import shutil
import tempfile
import unittest

from kernel import checker, driver, registry, results

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REG = os.path.join(ROOT, "registry")
DEMO = os.path.join(ROOT, "runs", "btor2-demo")

_HAVE_BTORMC = bool(os.environ.get("BTORMC") or shutil.which("btormc"))
# The pono pair's certificates discharge through z3 (discharge.py), so
# its gate — and the demo replay, whose grades depend on it — needs both.
_HAVE_PONO = bool((os.environ.get("PONO") or shutil.which("pono"))
                  and (os.environ.get("Z3") or shutil.which("z3")))
# The z3 bridge pair runs z3 through its python module, not the CLI.
_HAVE_Z3_PY = bool(__import__("importlib.util", fromlist=["util"])
                   .find_spec("z3"))


class TestCarriedOverLanguage(unittest.TestCase):
    def test_btor2_language_still_passes_the_gate(self):
        evidence = checker.check_language(
            os.path.join(REG, "languages", "btor2"), wall_s=60)
        manifest = registry.load(REG)["languages"]["btor2"]
        stamped = dict(manifest["admission"])
        self.assertEqual(evidence, stamped)


@unittest.skipUnless(_HAVE_BTORMC, "btormc not on PATH")
class TestCarriedOverSolver(unittest.TestCase):
    def test_btormc_pair_still_passes_the_gate(self):
        reg = registry.load(REG)
        evidence = checker.check_pair(
            reg, os.path.join(REG, "pairs", "btor2--btormc"),
            reg["pairs"]["btor2--btormc"], wall_s=60)
        self.assertEqual(evidence, dict(
            reg["pairs"]["btor2--btormc"]["admission"]))

    @unittest.skipUnless(_HAVE_PONO, "pono or z3 not on PATH")
    def test_demo_run_replays_to_the_same_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "btor2-demo")
            os.makedirs(run_dir)
            for name in ("benchmark.json", "counter.program",
                         "frozen.program"):
                shutil.copy(os.path.join(DEMO, name), run_dir)
            driver.play(run_dir, REG, wall_s=30)
            bench = results.load_benchmark(
                os.path.join(run_dir, "benchmark.json"))
            fresh = results.best(bench, results.load(
                os.path.join(run_dir, "log.jsonl")))
            committed = results.best(bench, results.load(
                os.path.join(DEMO, "log.jsonl")))
            self.assertEqual(
                {q: (r["value"], r["grade"]) for q, r in fresh.items()},
                {q: (r["value"], r["grade"]) for q, r in committed.items()})
            # The pono carry-over closed the inf ask: nothing stays open.
            self.assertEqual(results.frontier(bench, results.load(
                os.path.join(run_dir, "log.jsonl"))), [])

    def test_committed_report_regenerates_byte_identically(self):
        with open(os.path.join(DEMO, "frontier.md"), encoding="utf-8") as fh:
            committed = fh.read()
        bench = results.load_benchmark(os.path.join(DEMO, "benchmark.json"))
        log = results.load(os.path.join(DEMO, "log.jsonl"))
        self.assertEqual(results.report(bench, log), committed)


class TestCarriedOverRiscv(unittest.TestCase):
    """The spine's first leg: the RV64IMC interpreter as a root
    language and the rotor-lineage translation to btor2, both engine-
    free — the square is closed by running the two interpreters."""

    def test_riscv_language_still_passes_the_gate(self):
        evidence = checker.check_language(
            os.path.join(REG, "languages", "riscv"), wall_s=60)
        manifest = registry.load(REG)["languages"]["riscv"]
        self.assertEqual(evidence, dict(manifest["admission"]))

    def test_riscv_btor2_square_still_passes_the_gate(self):
        reg = registry.load(REG)
        evidence = checker.check_pair(
            reg, os.path.join(REG, "pairs", "riscv--btor2"),
            reg["pairs"]["riscv--btor2"], wall_s=60)
        self.assertEqual(evidence, dict(
            reg["pairs"]["riscv--btor2"]["admission"]))


@unittest.skipUnless(_HAVE_Z3_PY, "z3 python module not available")
class TestCarriedOverZ3(unittest.TestCase):
    def test_z3_bridge_pair_still_passes_the_gate(self):
        reg = registry.load(REG)
        evidence = checker.check_pair(
            reg, os.path.join(REG, "pairs", "btor2--z3"),
            reg["pairs"]["btor2--z3"], wall_s=45)
        self.assertEqual(evidence, dict(
            reg["pairs"]["btor2--z3"]["admission"]))


@unittest.skipUnless(_HAVE_PONO, "pono or z3 not on PATH")
class TestCarriedOverPono(unittest.TestCase):
    def test_pono_cert_pair_still_passes_the_gate(self):
        reg = registry.load(REG)
        evidence = checker.check_pair(
            reg, os.path.join(REG, "pairs", "btor2--pono-cert"),
            reg["pairs"]["btor2--pono-cert"], wall_s=45)
        self.assertEqual(evidence, dict(
            reg["pairs"]["btor2--pono-cert"]["admission"]))


if __name__ == "__main__":
    unittest.main()
