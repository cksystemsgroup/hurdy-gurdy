"""End-to-end cross-check: source vs reasoning interpreter agreement.

Compiles a tiny RV64 binary, runs both interpreters on the same
concrete inputs, walks the joined trace through the pair-supplied
projection, and asserts agreement. This is the translator-soundness
oracle the framework now exposes as a tool (cross_check, in PR3).
"""

from __future__ import annotations

import importlib

import pytest

from gurdy.core.interp import align_traces, CrossCheckOutcome
from gurdy.core.pair import _clear_registry_for_tests, get_pair
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.describe import _reset_cache_for_tests
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


TEXT_BASE = 0x10000


@pytest.fixture(autouse=True)
def _clean_registry():
    _clear_registry_for_tests()
    _reset_cache_for_tests()
    import gurdy.pairs.riscv_btor2 as pkg
    importlib.reload(pkg)
    yield
    _clear_registry_for_tests()
    _reset_cache_for_tests()


def _build_binary(tmp_path):
    # ADDI x10, x0, 1; ADDI x10, x10, 20; ECALL — halts cleanly.
    code = bytes.fromhex("13051000" "13054501" "73000000")
    p = tmp_path / "main.elf"
    p.write_bytes(
        build_elf(
            code,
            TEXT_BASE,
            [FuncDef(name="main", addr=TEXT_BASE, size=len(code))],
        )
    )
    return p


def test_source_and_reasoning_agree_on_pc(tmp_path):
    binary = _build_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(binary)),
        scope=AnalysisScope(entry_function="main"),
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=4),
    )
    artifact = compile_spec(spec, source_payload=binary)

    pair = get_pair("riscv-btor2")
    src_trace = pair.source_interpreter.run(
        pair.source_loader(binary),
        RiscvInputBinding(),
        max_steps=4,
        spec=spec,
    )
    # Initialize BTOR2 state from concrete entry: pc must match.
    binding = Btor2ReasoningBinding(
        state_init_by_symbol={"pc": TEXT_BASE},
    )
    reas_trace = pair.reasoning_interpreter.run(artifact, binding, max_steps=4)

    # Sanity: source did execute the instructions.
    assert len(src_trace.steps) >= 2

    projection = pair.projection(artifact)
    report = align_traces(src_trace, reas_trace, projection)
    assert report.outcome is CrossCheckOutcome.AGREEMENT, (
        f"divergence at step {report.divergence_step} on "
        f"{report.divergence_label!r}: source={report.source_view!r}, "
        f"reasoning={report.reasoning_view!r}"
    )
    assert report.steps_checked >= 2
    assert report.fields_checked > 0
