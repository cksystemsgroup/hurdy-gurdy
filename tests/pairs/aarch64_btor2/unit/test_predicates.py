"""Tests for the aarch64-btor2 predicate evaluator (the ``check`` tool).

Mirrors ``tests/pairs/riscv_btor2/unit/test_predicates.py`` and adds
coverage for the AArch64-specific ``sp`` / ``nzcv`` state that has no
riscv analogue. Needs no solver: both the source interpreter and the
predicate evaluator run concretely.
"""

from __future__ import annotations

import importlib

import pytest

from gurdy.core.interp.types import PredicateKind
from gurdy.core.pair import _clear_registry_for_tests
from gurdy.core.tools.check import check
from gurdy.core.tools.describe import _reset_cache_for_tests
from gurdy.pairs.aarch64_btor2.source.loader import load_aarch64_binary
from gurdy.pairs.aarch64_btor2.source_interp.bindings import AArch64InputBinding
from gurdy.pairs.aarch64_btor2.source_interp.interpreter import (
    AArch64SourceInterpreter,
)
from gurdy.pairs.aarch64_btor2.source_interp.predicates import (
    evaluate_assumption,
    evaluate_observable,
    evaluate_property,
    evaluate_spec,
)
from gurdy.pairs.aarch64_btor2.spec import (
    Aarch64Btor2Spec,
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Comparison,
    CycleInvariant,
    Executed,
    NZCVInit,
    PCAtStep,
    Property,
    RegisterAt,
    RegisterInit,
    SPAt,
    SPInit,
)

from tests.fixtures.elf_builder_aarch64 import FuncDef, build_elf


TEXT_BASE = 0x400000
_ADD_X0_1 = bytes.fromhex("00040091")  # add x0, x0, #1
_SVC = bytes.fromhex("010000D4")  # svc #0 (halts)


@pytest.fixture(autouse=True)
def _clean_registry():
    _clear_registry_for_tests()
    _reset_cache_for_tests()
    import gurdy.pairs.aarch64_btor2 as pkg
    importlib.reload(pkg)
    yield
    _clear_registry_for_tests()
    _reset_cache_for_tests()


def _binary(tmp_path):
    # x0 += 1 ; x0 += 1 ; svc  (halt)
    code = _ADD_X0_1 + _ADD_X0_1 + _SVC
    p = tmp_path / "main.elf"
    p.write_bytes(
        build_elf(
            code,
            TEXT_BASE,
            [FuncDef(name="main", addr=TEXT_BASE, size=len(code))],
            entry=TEXT_BASE,
        )
    )
    return p


def _trace(tmp_path, binding):
    binary = _binary(tmp_path)
    source = load_aarch64_binary(binary)
    return AArch64SourceInterpreter().run(source, binding, max_steps=4)


# ---------------------------------------------------------------------------
# Observables
# ---------------------------------------------------------------------------


def test_register_at_observable_captures_pre_step_value(tmp_path):
    binding = AArch64InputBinding(register_init={0: 5})
    trace = _trace(tmp_path, binding)
    obs = RegisterAt(register=0, pc=TEXT_BASE + 4)  # before the second add
    res = evaluate_observable(obs, trace, binding)
    assert res.kind is PredicateKind.OBSERVABLE
    assert res.fired
    # x0 was 5+1=6 after step 0; pre-step value at the second add is 6.
    _, val = res.values[0]
    assert val == 6


def test_executed_observable(tmp_path):
    binding = AArch64InputBinding()
    trace = _trace(tmp_path, binding)
    assert evaluate_observable(Executed(pc=TEXT_BASE), trace, binding).fired
    assert not evaluate_observable(Executed(pc=0xDEAD), trace, binding).fired


def test_pc_at_step_observable(tmp_path):
    binding = AArch64InputBinding()
    trace = _trace(tmp_path, binding)
    res = evaluate_observable(PCAtStep(step=0), trace, binding)
    assert res.fired
    assert res.values[0][1] == TEXT_BASE


def test_sp_at_observable_reads_sp_state(tmp_path):
    binding = AArch64InputBinding(sp_init=0x8000)
    trace = _trace(tmp_path, binding)
    res = evaluate_observable(SPAt(pc=TEXT_BASE), trace, binding)
    assert res.fired
    assert res.values[0][1] == 0x8000


# ---------------------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------------------


def test_register_init_assumption_holds_and_violates(tmp_path):
    binding = AArch64InputBinding(register_init={11: 7})
    trace = _trace(tmp_path, binding)
    assert evaluate_assumption(
        RegisterInit(register=11, op=Comparison.EQ, value=7), trace, binding
    ).holds
    assert evaluate_assumption(
        RegisterInit(register=11, op=Comparison.EQ, value=8), trace, binding
    ).holds is False


def test_sp_init_assumption(tmp_path):
    binding = AArch64InputBinding(sp_init=0x8000)
    trace = _trace(tmp_path, binding)
    assert evaluate_assumption(
        SPInit(op=Comparison.EQ, value=0x8000), trace, binding
    ).holds
    assert evaluate_assumption(
        SPInit(op=Comparison.GTU, value=0x9000), trace, binding
    ).holds is False


def test_nzcv_init_assumption_masks_to_4_bits(tmp_path):
    binding = AArch64InputBinding(nzcv_init=0)
    trace = _trace(tmp_path, binding)
    assert evaluate_assumption(
        NZCVInit(op=Comparison.EQ, value=0), trace, binding
    ).holds


def test_cycle_invariant_over_sp_and_nzcv(tmp_path):
    # plain ADD does not touch SP or the flags, so both invariants hold.
    binding = AArch64InputBinding(sp_init=0x8000, nzcv_init=0)
    trace = _trace(tmp_path, binding)
    assert evaluate_assumption(
        CycleInvariant(expression="eq(sp, 0x8000)"), trace, binding
    ).holds
    assert evaluate_assumption(
        CycleInvariant(expression="eq(nzcv, 0)"), trace, binding
    ).holds


def test_cycle_invariant_violated(tmp_path):
    binding = AArch64InputBinding(register_init={0: 5})
    trace = _trace(tmp_path, binding)
    res = evaluate_assumption(
        CycleInvariant(expression="eq(reg(0), 5)"), trace, binding
    )
    assert res.holds is False
    assert len(res.violations) > 0


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------


def test_property_constant_false_holds(tmp_path):
    binding = AArch64InputBinding()
    trace = _trace(tmp_path, binding)
    assert evaluate_property(Property(expression="false"), trace, binding).holds is True


def test_property_constant_true_violated_at_step_zero(tmp_path):
    binding = AArch64InputBinding()
    trace = _trace(tmp_path, binding)
    res = evaluate_property(Property(expression="true"), trace, binding)
    assert res.holds is False
    assert 0 in res.violations


def test_property_expression_over_register(tmp_path):
    binding = AArch64InputBinding(register_init={0: 5})
    trace = _trace(tmp_path, binding)
    # pre-step x0 reaches 7 after both adds; bad fires there.
    res = evaluate_property(Property(expression="eq(reg(0), 7)"), trace, binding)
    assert res.holds is False
    assert 2 in res.violations


# ---------------------------------------------------------------------------
# Spec-level wrapper + the check tool
# ---------------------------------------------------------------------------


def test_evaluate_spec_emits_diagnostics(tmp_path):
    binding = AArch64InputBinding()
    trace = _trace(tmp_path, binding)
    binary = _binary(tmp_path)
    spec = Aarch64Btor2Spec(
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


def test_evaluate_spec_is_deterministic(tmp_path):
    binding = AArch64InputBinding(register_init={0: 5}, sp_init=0x8000)
    trace = _trace(tmp_path, binding)
    binary = _binary(tmp_path)
    spec = Aarch64Btor2Spec(
        binary=BinaryRef(path=str(binary)),
        scope=AnalysisScope(entry_function="main"),
        observables=(RegisterAt(register=0, pc=TEXT_BASE + 4), SPAt(pc=TEXT_BASE)),
        assumptions=(CycleInvariant(expression="eq(nzcv, 0)"),),
        property=Property(expression="eq(reg(0), 7)"),
        analysis=AnalysisDirective(engine="z3-bmc"),
    )
    a = evaluate_spec(spec, trace, binding)
    b = evaluate_spec(spec, trace, binding)
    assert a.to_jsonable() == b.to_jsonable()


def test_check_tool_invokes_predicate_evaluator(tmp_path):
    binary = _binary(tmp_path)
    spec = Aarch64Btor2Spec(
        binary=BinaryRef(path=str(binary)),
        scope=AnalysisScope(entry_function="main"),
        observables=(RegisterAt(register=0, pc=TEXT_BASE + 4),),
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc"),
    )
    se = check(spec, AArch64InputBinding(register_init={0: 5}), max_steps=4, source_payload=binary)
    assert se.property_result is not None
    assert se.property_result.holds is True
    assert len(se.observables) == 1
    assert se.observables[0].fired
    assert se.observables[0].values[0][1] == 6
