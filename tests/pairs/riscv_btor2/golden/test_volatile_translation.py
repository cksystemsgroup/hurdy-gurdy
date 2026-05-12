"""Phase 2: volatile-layer emission (SCHEMA.md §14).

Covers ``BranchPin`` lowering (state + init + next + constraint, with
soft no-op for out-of-scope or non-branch PCs) and dual-role
``CycleInvariant`` companion ``bad`` clauses with the
``paired_with_nid`` annotation linkage.

The v1.0.0 byte-identical contract is enforced separately by
``test_v10_backcompat.py``: when no v1.1.0 vocabulary is used, the
volatile layer's body is empty bytes.
"""

from __future__ import annotations

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    BranchPin,
    CycleInvariant,
    Property,
    RegisterAt,
    RiscvBtor2Spec,
)
from gurdy.pairs.riscv_btor2.translation.translate import Translator

from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000
# Bytes for: addi a0, x0, 1 ; beq a0, x0, +4 ; ret
# 13050100 : addi a0, x0, 1   (4 bytes)
# 63040500 : beq a0, x0, +8   (4 bytes — taken target = PC+8)
# 67800000 : jalr x0, 0(ra)   (4 bytes; "ret")
BRANCH_BYTES = bytes.fromhex("13050100" "63040500" "67800000")
BEQ_PC = TEXT_BASE + 4


def _make_binary(tmp_path):
    funcs = [FuncDef(name="brfn", addr=TEXT_BASE, size=len(BRANCH_BYTES))]
    p = tmp_path / "brfn.elf"
    p.write_bytes(build_elf(BRANCH_BYTES, TEXT_BASE, funcs))
    return p


def _translate(spec, src):
    sidecar = AnnotationSidecar(schema_version="1.1.0", spec_hash=spec.spec_hash())
    return Translator().translate(spec, src, AnnotationEmitter(sidecar))


# ---------------------------------------------------------------------------
# v1.0.0-shaped spec: volatile layer body is empty (no marker bytes)
# ---------------------------------------------------------------------------


def test_volatile_empty_for_v10_spec(tmp_path):
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="brfn"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    art = _translate(spec, load_riscv_binary(p))
    assert "volatile" in art.layers
    assert art.layers["volatile"].body.strip() == b""


# ---------------------------------------------------------------------------
# BranchPin: active pin emits state + init + next + constraint
# ---------------------------------------------------------------------------


def test_branchpin_emits_step_counter_and_constraint(tmp_path):
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="brfn"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        assumptions=(BranchPin(step=1, taken=True, pc=BEQ_PC),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    art = _translate(spec, load_riscv_binary(p))
    body = art.layers["volatile"].body.decode("utf-8")
    assert "state " in body and "step_count" in body
    assert "init " in body
    assert "next " in body
    # The pin contributes one constraint clause.
    assert body.count("constraint ") == 1

    # The annotation records the pin's metadata.
    vol = [a for a in art.annotation.entries if a.layer == "volatile"]
    pin_entries = [
        a for a in vol if a.source_mapping and a.source_mapping.get("role") == "branch_pin"
    ]
    assert len(pin_entries) == 1
    assert pin_entries[0].source_mapping["step"] == 1
    assert pin_entries[0].source_mapping["pc"] == BEQ_PC
    assert pin_entries[0].source_mapping["taken"] is True


def test_branchpin_pc_out_of_scope_is_soft_noop(tmp_path):
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="brfn"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        assumptions=(BranchPin(step=1, taken=True, pc=0xFFFF0000),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    art = _translate(spec, load_riscv_binary(p))
    body = art.layers["volatile"].body.decode("utf-8")
    # Step counter is still declared (any BranchPin triggers it).
    assert "step_count" in body
    # ...but no `constraint` clause is emitted for this pin.
    assert body.count("constraint ") == 0
    vol = [a for a in art.annotation.entries if a.layer == "volatile"]
    soft = [
        a
        for a in vol
        if a.source_mapping
        and a.source_mapping.get("role") == "branch_pin_soft_noop"
    ]
    assert len(soft) == 1
    assert soft[0].source_mapping["reason"] == "pc_out_of_scope"


def test_branchpin_pc_in_scope_but_not_branch_is_soft_noop(tmp_path):
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="brfn"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        # TEXT_BASE is the ADDI, not a branch.
        assumptions=(BranchPin(step=0, taken=True, pc=TEXT_BASE),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    art = _translate(spec, load_riscv_binary(p))
    vol = [a for a in art.annotation.entries if a.layer == "volatile"]
    soft = [
        a
        for a in vol
        if a.source_mapping
        and a.source_mapping.get("role") == "branch_pin_soft_noop"
    ]
    assert len(soft) == 1
    assert soft[0].source_mapping["reason"] == "pc_not_branch"


# ---------------------------------------------------------------------------
# Dual-role CycleInvariant: paired constraint + bad with paired_with_nid
# ---------------------------------------------------------------------------


def test_dual_role_emits_paired_clauses(tmp_path):
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="brfn"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        assumptions=(
            CycleInvariant(expression="ltu(reg(10), 1000)", dual_role=True),
        ),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    art = _translate(spec, load_riscv_binary(p))

    # constraint layer holds the assumption clause, annotated dual_role=True.
    cstr = [a for a in art.annotation.entries if a.layer == "constraint"]
    dual_constraints = [
        a for a in cstr if a.source_mapping and a.source_mapping.get("dual_role") is True
    ]
    assert len(dual_constraints) == 1
    constraint_nid = dual_constraints[0].nid

    # volatile layer holds the negated bad clause linked back.
    vol = [a for a in art.annotation.entries if a.layer == "volatile"]
    bad_paired = [
        a
        for a in vol
        if a.source_mapping
        and a.source_mapping.get("role") == "dual_role_check"
    ]
    assert len(bad_paired) == 1
    assert bad_paired[0].source_mapping["paired_with_nid"] == constraint_nid
    assert bad_paired[0].source_mapping["expression"] == "ltu(reg(10), 1000)"

    body = art.layers["volatile"].body.decode("utf-8")
    assert "bad " in body  # one bad clause in volatile

    # The volatile-layer bad nid must not collide with any constraint nid.
    assert bad_paired[0].nid != constraint_nid


def test_non_dual_role_invariant_unchanged(tmp_path):
    """A CycleInvariant with dual_role=False emits only into constraint."""
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="brfn"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        assumptions=(CycleInvariant(expression="ltu(reg(10), 1000)"),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    art = _translate(spec, load_riscv_binary(p))
    # Volatile body is empty since nothing volatile is present.
    assert art.layers["volatile"].body.strip() == b""
