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


class TestCarriedOverSail(unittest.TestCase):
    """The Sail leg: a derived language (the Sail-derived Expr
    evaluator, checked against its parent riscv by the exact square)
    and the two edges that make the Sail-mediated RISC-V-to-BTOR2
    route independent of the direct one. Engine-free."""

    def test_sail_language_still_passes_the_gate(self):
        evidence = checker.check_language(
            os.path.join(REG, "languages", "sail"), wall_s=60)
        manifest = registry.load(REG)["languages"]["sail"]
        self.assertEqual(evidence, dict(manifest["admission"]))

    def test_riscv_sail_square_still_passes_the_gate(self):
        reg = registry.load(REG)
        evidence = checker.check_pair(
            reg, os.path.join(REG, "pairs", "riscv--sail"),
            reg["pairs"]["riscv--sail"], wall_s=60)
        self.assertEqual(evidence, dict(
            reg["pairs"]["riscv--sail"]["admission"]))

    def test_sail_btor2_square_still_passes_the_gate(self):
        reg = registry.load(REG)
        evidence = checker.check_pair(
            reg, os.path.join(REG, "pairs", "sail--btor2"),
            reg["pairs"]["sail--btor2"], wall_s=60)
        self.assertEqual(evidence, dict(
            reg["pairs"]["sail--btor2"]["admission"]))

    def test_both_riscv_routes_exist_but_neither_decides_halted(self):
        # the direct and the Sail-mediated route both reach the btor2
        # solvers; a riscv question about "halted" is refused by the
        # decides guard on every one of them until a spec pair reifies
        # halted into a bad property — the routing contract holding
        reg = registry.load(REG)
        routes = driver.enumerate_routes(reg, "riscv")
        ids = [[p["id"] for p in r] for r in routes]
        self.assertTrue(any(r[0] == "riscv--btor2" for r in ids))
        self.assertTrue(any(r[:2] == ["riscv--sail", "sail--btor2"]
                            for r in ids))
        for route in routes:
            observable = "halted"
            for hop in route[:-1]:
                observable = hop.get("maps", {}).get(observable,
                                                     observable)
            self.assertNotIn(observable, route[-1].get("decides", []))


_HAVE_AVR = bool(os.environ.get("AVR")) or os.path.isfile(
    os.path.expanduser("~/avr/avr.py"))
_HAVE_ABC = (bool(os.environ.get("ABC")) or shutil.which("abc")
             or os.path.isfile(os.path.expanduser("~/abc-route/abc/abc")))
_HAVE_BITWUZLA = bool(os.environ.get("BITWUZLA")
                      or shutil.which("bitwuzla"))


class TestCarriedOverBackends(unittest.TestCase):
    """The remaining engine backends, re-gated where their engines
    are present: AVR (the disjoint lineage that corroborates the
    unbounded claim), ABC's pdr (unreplayable cex books as evidence),
    and bitwuzla (verdict-only second SMT codebase)."""

    def _regate(self, pid):
        reg = registry.load(REG)
        evidence = checker.check_pair(
            reg, os.path.join(REG, "pairs", pid), reg["pairs"][pid],
            wall_s=45)
        self.assertEqual(evidence, dict(reg["pairs"][pid]["admission"]))

    @unittest.skipUnless(_HAVE_AVR, "avr not present")
    def test_avr_pair_still_passes_the_gate(self):
        self._regate("btor2--avr")

    @unittest.skipUnless(_HAVE_ABC, "abc not present")
    def test_abc_pair_still_passes_the_gate(self):
        self._regate("btor2--abc")

    @unittest.skipUnless(_HAVE_BITWUZLA, "bitwuzla not present")
    def test_bitwuzla_pair_still_passes_the_gate(self):
        self._regate("smtlib--bitwuzla")


class TestFanOutEntries(unittest.TestCase):
    """The fan-out's engine-free entries, re-gated generically: every
    language and translation pair named here must still pass exactly
    as admitted."""

    LANGUAGES = ("ebpf", "evm", "wasm", "python", "smiles", "formula")
    PAIRS = ("ebpf--btor2", "evm--btor2", "wasm--btor2",
             "python--smtlib", "smiles--formula", "btor2--enum")

    def test_languages_still_pass_the_gate(self):
        reg = registry.load(REG)
        for name in self.LANGUAGES:
            with self.subTest(language=name):
                evidence = checker.check_language(
                    os.path.join(REG, "languages", name), wall_s=60)
                self.assertEqual(evidence,
                                 dict(reg["languages"][name]["admission"]))

    def test_squares_still_close(self):
        reg = registry.load(REG)
        for pid in self.PAIRS:
            with self.subTest(pair=pid):
                evidence = checker.check_pair(
                    reg, os.path.join(REG, "pairs", pid),
                    reg["pairs"][pid], wall_s=60)
                self.assertEqual(evidence,
                                 dict(reg["pairs"][pid]["admission"]))

    def test_python_questions_have_a_full_route(self):
        # violated composes to sat across the hop, and z3 decides sat:
        # the first non-btor2 domain with an end-to-end road
        routes = driver.enumerate_routes(registry.load(REG), "python")
        ids = [[p["id"] for p in r] for r in routes]
        self.assertIn(["python--smtlib", "smtlib--z3"], ids)


class TestCarriedOverSmtlib(unittest.TestCase):
    """The smtlib language (the model evaluator as executor) and the
    bridge square at declared k=20, closed through Λ on observables
    (sat carried back as bad). Engine-free. No smtlib solver pair is
    admitted yet — routing needs decides/bound-cap declarations first
    — so no route can flow through this hop."""

    def test_smtlib_language_still_passes_the_gate(self):
        evidence = checker.check_language(
            os.path.join(REG, "languages", "smtlib"), wall_s=30)
        manifest = registry.load(REG)["languages"]["smtlib"]
        self.assertEqual(evidence, dict(manifest["admission"]))

    def test_bridge_square_still_closes_through_lam_obs(self):
        reg = registry.load(REG)
        evidence = checker.check_pair(
            reg, os.path.join(REG, "pairs", "btor2--smtlib"),
            reg["pairs"]["btor2--smtlib"], wall_s=45)
        self.assertEqual(evidence, dict(
            reg["pairs"]["btor2--smtlib"]["admission"]))

    def test_the_bridge_route_exists_under_the_routing_contract(self):
        # the two-hop route plays because the hop declares its map
        # (bad -> sat) and its bound cap, and the solver declares what
        # it decides; a universal crossing back is a bound-20 fact
        routes = driver.enumerate_routes(registry.load(REG), "btor2")
        ids = [[p["id"] for p in r] for r in routes]
        self.assertIn(["btor2--smtlib", "smtlib--z3"], ids)

    @unittest.skipUnless(_HAVE_Z3_PY, "z3 python module not available")
    def test_smtlib_z3_pair_still_passes_the_gate(self):
        reg = registry.load(REG)
        evidence = checker.check_pair(
            reg, os.path.join(REG, "pairs", "smtlib--z3"),
            reg["pairs"]["smtlib--z3"], wall_s=45)
        self.assertEqual(evidence, dict(
            reg["pairs"]["smtlib--z3"]["admission"]))


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
