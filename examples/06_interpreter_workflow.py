"""Example 06: end-to-end interpreter-layer workflow.

Build a tiny RV64 ELF, then exercise the four deterministic-trace
tools added post-v1: ``simulate``, ``evaluate``, ``cross_check``, and
``check``. The fifth interpreter-layer tool, ``replay``, takes a real
solver witness; it follows the same shape as ``simulate`` and is
exercised in ``tests/pairs/riscv_btor2/integration/test_replay_tool.py``.

Run from the repo root:

    python examples/06_interpreter_workflow.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gurdy.pairs.riscv_btor2  # noqa: F401  (registers the pair)
from gurdy.core.tools.check import check
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.cross_check import cross_check
from gurdy.core.tools.evaluate import evaluate
from gurdy.core.tools.simulate import simulate
from gurdy.pairs.riscv_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Property,
    RiscvBtor2Spec,
)
from tests.fixtures.elf_builder import FuncDef, build_elf


# ADDI x10, x0, 5 ; ADDI x10, x10, 23 ; ECALL    →  x10 = 28 at halt
TEXT_BASE = 0x10000
PROGRAM = bytes.fromhex("13055000" "13057501" "73000000")


def _spec(path: Path, prop_expr: str) -> RiscvBtor2Spec:
    return RiscvBtor2Spec(
        binary=BinaryRef(path=str(path)),
        scope=AnalysisScope(entry_function="add28"),
        property=Property(expression=prop_expr),
        analysis=AnalysisDirective(engine="z3-bmc", bound=4),
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "add28.elf"
        path.write_bytes(
            build_elf(PROGRAM, TEXT_BASE, [FuncDef("add28", TEXT_BASE, len(PROGRAM))])
        )

        # 1. simulate — concrete trace through the source interpreter.
        spec_safe = _spec(path, "false")
        src_trace = simulate(
            spec_safe, RiscvInputBinding(), max_steps=4, source_payload=path
        )
        print(f"simulate: {len(src_trace.steps)} steps, halted={src_trace.halted}")
        for i, step in enumerate(src_trace.steps):
            mnemonic = step.location.get("mnemonic", "?")
            print(f"  step {i}: pc={step.location.get('pc'):#x} {mnemonic}")

        # 2. evaluate — concrete trace through the reasoning interpreter.
        artifact = compile_spec(spec_safe, source_payload=path)
        reas_trace = evaluate(
            artifact,
            Btor2ReasoningBinding(state_init_by_symbol={"pc": TEXT_BASE}),
            max_steps=3,
        )
        print(
            f"evaluate: {len(reas_trace.steps)} steps, "
            f"bad_fired_at={reas_trace.bad_fired_at}"
        )

        # 3. cross_check — align both traces post-step on pc/reg_x*/halted.
        report = cross_check(
            spec_safe,
            RiscvInputBinding(),
            Btor2ReasoningBinding(state_init_by_symbol={"pc": TEXT_BASE}),
            max_steps=3,
            source_payload=path,
            artifact=artifact,
        )
        print(f"cross_check: outcome={report.outcome.value}")

        # 4. check — predicate evaluation on the concrete trace.
        for prop_expr in ("false", "eq(reg(10), 28)"):
            se = check(
                _spec(path, prop_expr),
                RiscvInputBinding(),
                max_steps=4,
                source_payload=path,
            )
            holds = se.property_result.holds
            violations = list(se.property_result.violations)
            verdict = "holds" if holds else f"violated@{violations[0]}"
            print(f"check: property={prop_expr!r:24s} → {verdict}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
