"""The fault-injection harness (tools/fault_injection.py), one mutant end
to end: a systematic sext->uext mis-lowering (incident I2's family) must be
caught by the square gate — the conjoined probe suite — and a mutation that
changes nothing must be reported inapplicable.

The full 55-mutant experiment is the harvest's job (--only escape); this
keeps the mechanism honest in the suite at ~seconds cost."""

import importlib.util
import unittest
from pathlib import Path


def _load_tool(name: str):
    path = Path(__file__).resolve().parent.parent / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = mod   # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(mod)
    return mod


class TestFaultInjection(unittest.TestCase):
    def test_sext_to_uext_mutant_is_caught_by_the_square_gate(self):
        fi = _load_tool("fault_injection")
        import gurdy.pairs.riscv_btor2  # noqa: F401 (registers the pair)
        from gurdy.core import registry

        probes = registry.get_pair("riscv-btor2").probes
        mutant = fi.Mutation("uniform:sext->uext", "op-swap", "sext", "uext")
        self.assertTrue(fi._applicable(mutant, probes))
        caught = fi._gate_square(mutant, probes)
        self.assertIsNotNone(caught)
        self.assertTrue(caught.startswith("square:"), caught)

    def test_unmatched_rule_is_inapplicable(self):
        fi = _load_tool("fault_injection")
        import gurdy.pairs.riscv_btor2  # noqa: F401
        from gurdy.core import registry

        probes = registry.get_pair("riscv-btor2").probes
        mutant = fi.Mutation("uniform:nosuch", "op-swap", "nosuchop", "add")
        self.assertFalse(fi._applicable(mutant, probes))

    def test_srl_to_sra_mutant_is_caught_since_probe_hardening(self):
        # I23's regression: the round-1 escape. With mixed-sign operands the
        # SRLI/SRL probes distinguish logical from arithmetic shifts.
        fi = _load_tool("fault_injection")
        import gurdy.pairs.riscv_btor2  # noqa: F401
        from gurdy.core import registry

        probes = registry.get_pair("riscv-btor2").probes
        mutant = fi.Mutation("uniform:srl->sra", "op-swap", "srl", "sra")
        caught = fi._gate_square(mutant, probes)
        self.assertIsNotNone(caught)
        self.assertTrue(caught.startswith("square:"), caught)


class TestCommonMode(unittest.TestCase):
    """The both-leg harness (paper §6.7's common-mode block): every shared
    misreading loads its shadow modules (uniqueness-checked substitutions),
    and the square is structurally blind on the MUL/ADD class — both legs
    wrong identically, so the inner ring cannot see it. The outer-ring
    catches are the harvest's job (--only common)."""

    def test_all_common_modes_shadow_load(self):
        fi = _load_tool("fault_injection")
        for cm in fi._CM:
            run_fn, translate_fn = fi.cm_modules(cm)
            self.assertTrue(callable(run_fn) and callable(translate_fn),
                            cm.name)

    def test_mul_as_add_is_square_blind(self):
        # The historical incident, resurrected in both legs: the conjoined
        # suite must pass — blindness by construction, the finding the
        # common-mode experiment quantifies.
        fi = _load_tool("fault_injection")
        import gurdy.pairs.riscv_btor2  # noqa: F401
        run_fn, translate_fn = fi.cm_modules(fi._CM[0])
        self.assertIsNone(fi._cm_gate_square(run_fn, translate_fn))

    def test_mutated_leg_alone_is_caught(self):
        # Sanity for the harness itself: the same interpreter misreading
        # against the INTACT translator must diverge — the shadow module
        # really changes semantics, so blindness above is not vacuous.
        fi = _load_tool("fault_injection")
        import gurdy.pairs.riscv_btor2  # noqa: F401
        from gurdy.core import registry
        from gurdy.pairs.riscv_btor2 import translate
        run_fn, _ = fi.cm_modules(fi._CM[0])
        self.assertIsNotNone(
            fi._cm_gate_square(run_fn, translate))


if __name__ == "__main__":
    unittest.main()
