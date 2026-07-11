"""The two-sided negative-control harness (gurdy/core/negative_control.py) —
Phase 3 of the scaling rollout (SCALING.md §12.3, §3.2).

The harness proves a pair's square can catch a seeded defect on its probes.
These tests dogfood it: gross defects are caught on every checked pair, the
control is not vacuous (an identity mutant is not "caught"), a semantic op-swap
is caught (probe adequacy), predicted-grade pairs have no build-time control,
and grading leaves the pair module unperturbed.
"""

import importlib
import importlib.util
import pkgutil
import sys
import unittest

from gurdy.core import negative_control as nc
from gurdy.core import registry

CHECKED_WITH_SQUARE = (
    "riscv-btor2", "riscv-sail", "sail-btor2", "aarch64-btor2",
    "ebpf-btor2", "evm-btor2", "wasm-btor2", "smiles-formula",
)
PREDICTED_NO_SQUARE = ("btor2-smtlib", "crn-smtlib", "python-smtlib")


def _import_all_pairs() -> None:
    import gurdy.pairs as pairs_pkg
    for mod in pkgutil.iter_modules(pairs_pkg.__path__):
        importlib.import_module(f"gurdy.pairs.{mod.name}")


def _fault_injection():
    import pathlib
    path = str(pathlib.Path(__file__).resolve().parent.parent
               / "tools" / "fault_injection.py")
    spec = importlib.util.spec_from_file_location("fault_injection", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fault_injection"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestNegativeControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _import_all_pairs()

    def test_gross_defect_caught_on_every_checked_pair(self):
        for pid in CHECKED_WITH_SQUARE:
            res = nc.two_sided_control(registry.get_pair(pid))
            self.assertIsNotNone(res, pid)
            self.assertTrue(res.ok, f"{pid}: {res}")
            self.assertTrue(res.caught, pid)          # the defect was caught
            self.assertTrue(res.intact_ok, pid)       # intact passes all
            self.assertLess(res.mutant_pass, res.intact_pass, pid)

    def test_predicted_pairs_have_no_build_time_control(self):
        for pid in PREDICTED_NO_SQUARE:
            self.assertIsNone(nc.two_sided_control(registry.get_pair(pid)), pid)

    def test_control_is_not_vacuous(self):
        # An identity mutant introduces no defect, so the control must NOT
        # report it 'caught' — otherwise the gate would pass everything.
        pair = registry.get_pair("riscv-btor2")
        identity = importlib.import_module("gurdy.pairs.riscv_btor2").translate
        res = nc.two_sided_control(pair, mutant=identity)
        self.assertFalse(res.caught)
        self.assertFalse(res.ok)

    def test_semantic_op_swap_is_caught(self):
        # The strong (probe-adequacy) control: a valid-but-wrong artifact from
        # a semantic op-swap must be caught by the square (reusing the
        # fault-injection mutant machinery).
        fi = _fault_injection()
        pair = registry.get_pair("riscv-btor2")
        mut = fi._mutant_translate(
            fi.Mutation("uniform:add->sub", "op-swap", "add", "sub"))
        res = nc.two_sided_control(pair, mutant=mut)
        self.assertTrue(res.caught)
        self.assertLess(res.mutant_pass, res.intact_pass)

    def test_grading_restores_the_pair_module(self):
        # Grading rebinds the pair's translate; it must restore it, or later
        # runs would see the mutant.
        pair = registry.get_pair("riscv-btor2")
        mod = importlib.import_module("gurdy.pairs.riscv_btor2")
        before = mod.translate
        nc.two_sided_control(pair)                     # rebinds + restores
        self.assertIs(mod.translate, before)


if __name__ == "__main__":
    unittest.main()
