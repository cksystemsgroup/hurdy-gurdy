"""Tests for the riscv-btor2 predicate evaluator (PR4)."""

from __future__ import annotations

import importlib

import pytest

from gurdy.core.interp.types import PredicateKind
from gurdy.core.pair import _clear_registry_for_tests
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.describe import _reset_cache_for_tests
from gurdy.core.tools.check import check
from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding
from gurdy.pairs.riscv_btor2.source_interp.interpreter import RiscvSourceInterpreter
from gurdy.pairs.riscv_btor2.source_interp.predicates import (
    evaluate_assumption,
    evaluate_observable,
    evaluate_property,
    evaluate_spec,
)
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Comparison,
    CycleInvariant,
    Executed,
    PCAtStep,
    Property,
    RegisterAt,
    RegisterInit,
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
    # ADDI x10, x0, 5 ; ADDI x10, x10, 23 ; ECALL
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


def _trace(tmp_path, binding):
    binary = _binary(tmp_path)
    source = load_riscv_binary(binary)
    return RiscvSourceInterpreter().run(source, binding, max_steps=4)


def test_register_at_observable_captures_pre_step_value(tmp_path):
    binding = RiscvInputBinding()
    trace = _trace(tmp_path, binding)
    obs = RegisterAt(register=10, pc=TEXT_BASE + 4)  # before second ADDI
    res = evaluate_observable(obs, trace, binding)
    assert res.kind is PredicateKind.OBSERVABLE
    assert res.fired
    # x10 was set to 5 by step 0; pre-step state at the second ADDI is 5.
    step, val = res.values[0]
    assert val == 5


def test_executed_observable(tmp_path):
    binding = RiscvInputBinding()
    trace = _trace(tmp_path, binding)
    res = evaluate_observable(Executed(pc=TEXT_BASE), trace, binding)
    assert res.fired
    res2 = evaluate_observable(Executed(pc=0xDEAD), trace, binding)
    assert not res2.fired


def test_pc_at_step_observable(tmp_path):
    binding = RiscvInputBinding()
    trace = _trace(tmp_path, binding)
    res = evaluate_observable(PCAtStep(step=0), trace, binding)
    assert res.fired
    assert res.values[0][1] == TEXT_BASE


def test_register_init_assumption_holds_when_satisfied(tmp_path):
    binding = RiscvInputBinding(register_init={11: 7})
    trace = _trace(tmp_path, binding)
    asm = RegisterInit(register=11, op=Comparison.EQ, value=7)
    res = evaluate_assumption(asm, trace, binding)
    assert res.holds


def test_register_init_assumption_violated(tmp_path):
    binding = RiscvInputBinding(register_init={11: 7})
    trace = _trace(tmp_path, binding)
    asm = RegisterInit(register=11, op=Comparison.EQ, value=8)
    res = evaluate_assumption(asm, trace, binding)
    assert res.holds is False


def test_property_constant_false_holds(tmp_path):
    binding = RiscvInputBinding()
    trace = _trace(tmp_path, binding)
    res = evaluate_property(Property(expression="false"), trace, binding)
    assert res.holds is True


def test_property_constant_true_violated_at_step_zero(tmp_path):
    binding = RiscvInputBinding()
    trace = _trace(tmp_path, binding)
    res = evaluate_property(Property(expression="true"), trace, binding)
    assert res.holds is False
    assert 0 in res.violations


def test_property_expression_eq_register(tmp_path):
    binding = RiscvInputBinding()
    trace = _trace(tmp_path, binding)
    # x10 is 5 after step 0 and 28 after step 1; pre-step x10 at step 2 is 28.
    res = evaluate_property(Property(expression="eq(reg(10), 28)"), trace, binding)
    assert res.holds is False
    assert 2 in res.violations


def test_cycle_invariant_holds(tmp_path):
    binding = RiscvInputBinding()
    trace = _trace(tmp_path, binding)
    asm = CycleInvariant(expression="eq(reg(0), 0)")
    res = evaluate_assumption(asm, trace, binding)
    assert res.holds


def test_cycle_invariant_violated_in_concrete_trace(tmp_path):
    binding = RiscvInputBinding(register_init={1: 5})
    trace = _trace(tmp_path, binding)
    # Always wants x1 to be 0; with binding's x1=5 it never holds.
    asm = CycleInvariant(expression="eq(reg(1), 0)")
    res = evaluate_assumption(asm, trace, binding)
    assert res.holds is False
    assert len(res.violations) > 0


def test_evaluate_spec_emits_diagnostics(tmp_path):
    binding = RiscvInputBinding()
    trace = _trace(tmp_path, binding)

    binary = _binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(binary)),
        scope=AnalysisScope(entry_function="main"),
        observables=(Executed(pc=0xDEAD),),  # never fires
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc"),
    )
    se = evaluate_spec(spec, trace, binding)
    codes = {d["code"] for d in se.diagnostics}
    assert "check/observable_never_fires" in codes
    assert "check/property_holds_concretely" in codes


def test_check_tool_invokes_predicate_evaluator(tmp_path):
    binary = _binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(binary)),
        scope=AnalysisScope(entry_function="main"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE + 4),),
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc"),
    )
    se = check(spec, RiscvInputBinding(), max_steps=4, source_payload=binary)
    assert se.property_result is not None
    assert se.property_result.holds is True
    assert len(se.observables) == 1
    assert se.observables[0].fired
