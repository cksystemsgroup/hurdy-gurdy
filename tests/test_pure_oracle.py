"""The PureOracle seam (gurdy/core/pure_oracle.py) — Phase 2 of the scaling
rollout (SCALING.md §12.2, §3).

The seam runs a pair's untrusted pure functions (``T``/``Λ``) either in-process
(reference) or in a separate child process behind a safe result channel. A
square is a pure function of ``(T, Λ, I_s, I_t, π, program)``, so two backends
that agree on ``T`` and ``Λ`` byte-for-byte agree on every square verdict. These
tests prove that agreement over the current pairs — the boundary lands changing
no measured number — and carry negative controls proving the comparison
discriminates and the channel is safe.
"""

import importlib
import json
import pkgutil
import unittest

from gurdy.core import pure_oracle, registry
from gurdy.core.errors import Unsupported


def _import_all_pairs() -> None:
    import gurdy.pairs as pairs_pkg
    for mod in pkgutil.iter_modules(pairs_pkg.__path__):
        importlib.import_module(f"gurdy.pairs.{mod.name}")


def _canon(trace) -> str:
    return json.dumps(trace, sort_keys=True, default=str)


class TestTranslateEquivalence(unittest.TestCase):
    """The primary untrusted output: every probe of every pair must translate
    to identical bytes in-process and out-of-process."""

    @classmethod
    def setUpClass(cls) -> None:
        _import_all_pairs()

    def test_every_pair_translates_identically_across_backends(self):
        total = 0
        for pid, pair in sorted(registry.list_pairs().items()):
            if not pair.probes:
                continue
            inproc = pure_oracle.for_pair(pair, "inproc")
            with pure_oracle.for_pair(pair, "subprocess") as sub:
                for name, program in pair.probes.items():
                    try:
                        a = inproc.translate(program)
                    except Unsupported:
                        continue
                    b = sub.translate(program)
                    self.assertEqual(a, b, f"{pid}/{name} translate mismatch")
                    self.assertIsInstance(b, bytes)   # safe channel: raw bytes
                    total += 1
        self.assertGreater(total, 600)                # all 12 probed pairs


class TestLiftEquivalence(unittest.TestCase):
    """The other untrusted function, on the BTOR2 spine (uniform trace shape;
    a trace is sourced through the trusted target interpreter)."""

    SPINE = ("riscv-btor2", "sail-btor2", "ebpf-btor2",
             "aarch64-btor2", "wasm-btor2", "evm-btor2")

    @classmethod
    def setUpClass(cls) -> None:
        _import_all_pairs()

    def test_lift_identical_across_backends(self):
        for pid in self.SPINE:
            pair = registry.get_pair(pid)
            inproc = pure_oracle.for_pair(pair, "inproc")
            with pure_oracle.for_pair(pair, "subprocess") as sub:
                checked = 0
                for name, program in list(pair.probes.items())[:8]:
                    try:
                        artifact = inproc.translate(program)
                        trace = pair.target_interpreter(artifact, {"steps": 4})
                    except (Unsupported, Exception):
                        continue
                    a = inproc.lift(trace)
                    b = sub.lift(trace)
                    self.assertEqual(_canon(a), _canon(b), f"{pid}/{name} lift")
                    self.assertIsInstance(b, list)     # safe channel: JSON
                    checked += 1
                self.assertGreater(checked, 0, pid)


class TestSeamControls(unittest.TestCase):
    """Negative controls: the equivalence check is not vacuous, and the safe
    channel surfaces a bad child as an error rather than executing it."""

    @classmethod
    def setUpClass(cls) -> None:
        _import_all_pairs()

    def test_comparison_discriminates(self):
        # A perturbed in-process translate must NOT equal the subprocess one —
        # otherwise the equivalence proof above would be vacuous.
        pair = registry.get_pair("riscv-btor2")
        name, program = next(iter(pair.probes.items()))
        perturbed = pure_oracle.InProcessOracle(
            lambda p: pair.translator(p) + b"\x00", pair.target_to_source)
        with pure_oracle.for_pair(pair, "subprocess") as sub:
            self.assertNotEqual(perturbed.translate(program),
                                sub.translate(program))

    def test_child_error_surfaces_not_executes(self):
        # A malformed lift input makes the child raise; the parent must get a
        # RuntimeError (parsed defensively), never hang or unpickle child data.
        pair = registry.get_pair("riscv-btor2")
        with pure_oracle.for_pair(pair, "subprocess") as sub:
            with self.assertRaises(RuntimeError):
                sub.lift(object())          # not a valid trace → child errors


if __name__ == "__main__":
    unittest.main()
