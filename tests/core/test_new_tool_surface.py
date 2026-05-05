"""Tests for the five new LLM-facing tools.

Each tool is a thin wrapper over the pair's interpreter; these tests
confirm the wrapper routes correctly, raises sensible errors when
prerequisites are missing, and round-trips through JSON.
"""

from __future__ import annotations

import importlib

import pytest

from gurdy.core.interp.types import (
    CrossCheckOutcome,
    PredicateKind,
    SourceTrace,
    SpecEvaluation,
)
from gurdy.core.pair import _clear_registry_for_tests, get_pair
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.cross_check import cross_check
from gurdy.core.tools.describe import _reset_cache_for_tests
from gurdy.core.tools.evaluate import evaluate
from gurdy.core.tools.simulate import simulate
from gurdy.core.tools.check import check
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


def _binary(tmp_path):
    # ADDI x10, x0, 5; ADDI x10, x10, 7; ECALL
    code = bytes.fromhex("13055000" "13057501" "73000000")
    p = tmp_path / "main.elf"
    p.write_bytes(
        build_elf(
            code,
            TEXT_BASE,
            [FuncDef(name="main", addr=TEXT_BASE, size=len(code))],
        )
    )
    return p


def _spec(binary):
    return RiscvBtor2Spec(
        binary=BinaryRef(path=str(binary)),
        scope=AnalysisScope(entry_function="main"),
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=4),
    )


def test_simulate_runs_source_interpreter(tmp_path):
    binary = _binary(tmp_path)
    spec = _spec(binary)
    trace = simulate(spec, RiscvInputBinding(), max_steps=4, source_payload=binary)
    assert isinstance(trace, SourceTrace)
    assert trace.pair == "riscv-btor2"
    # Three real instructions: two ADDIs and an ECALL.
    assert len(trace.steps) == 3
    assert trace.halted is True


def test_evaluate_runs_reasoning_interpreter(tmp_path):
    binary = _binary(tmp_path)
    spec = _spec(binary)
    artifact = compile_spec(spec, source_payload=binary)
    binding = Btor2ReasoningBinding(state_init_by_symbol={"pc": TEXT_BASE})
    trace = evaluate(artifact, binding, max_steps=3)
    assert trace.pair == "riscv-btor2"
    assert len(trace.steps) == 3


def test_cross_check_agrees_on_simple_program(tmp_path):
    binary = _binary(tmp_path)
    spec = _spec(binary)
    artifact = compile_spec(spec, source_payload=binary)
    report = cross_check(
        spec,
        RiscvInputBinding(),
        Btor2ReasoningBinding(state_init_by_symbol={"pc": TEXT_BASE}),
        max_steps=3,
        source_payload=binary,
        artifact=artifact,
    )
    assert report.outcome is CrossCheckOutcome.AGREEMENT, (
        f"divergence step={report.divergence_step} "
        f"label={report.divergence_label!r} src={report.source_view!r} "
        f"reas={report.reasoning_view!r}"
    )


def test_check_returns_unsupported_diagnostic_when_no_evaluator_wired(tmp_path):
    binary = _binary(tmp_path)
    spec = _spec(binary)
    se = check(spec, RiscvInputBinding(), max_steps=4, source_payload=binary)
    assert isinstance(se, SpecEvaluation)
    assert se.steps_executed >= 1
    # PR3 ships the wrapper; PR4 wires the predicate evaluator.
    assert se.property_result is not None
    assert se.property_result.kind is PredicateKind.PROPERTY
    assert any(d.get("code") == "check/property_unsupported" for d in se.diagnostics)


def test_simulate_errors_when_pair_lacks_source_interpreter(tmp_path):
    """A spec routed to a pair without a source_interpreter raises."""
    from dataclasses import dataclass
    from pathlib import Path

    from gurdy.core.pair import Pair, register_pair
    from gurdy.core.spec.base import BaseSpec
    from tests.core._synthetic_pair import (
        SyntheticSpec,
        install,
    )

    schema = tmp_path / "S.md"
    schema.write_text("# X\n## A\nB\n")
    install(schema)  # synthetic pair has no interpreters

    spec = SyntheticSpec(name="x")
    with pytest.raises(ValueError, match="no source_interpreter"):
        simulate(spec, RiscvInputBinding(), max_steps=2, source_payload=b"")
