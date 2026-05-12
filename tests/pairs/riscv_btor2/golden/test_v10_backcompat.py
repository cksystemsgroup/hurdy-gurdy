"""v1.0.0 byte-identical regression for the v1.1.0 increment.

SCHEMA.md §14 introduced the ``volatile`` layer between
``constraint`` and ``bad`` and added new spec vocabulary
(``BranchPin``, ``CycleInvariant.dual_role``, ``Free`` binding
cells). The contract is that a v1.0.0-shaped spec — one using none
of that vocabulary — compiles to byte-identical artifacts under
1.1.0. This test pins the SHA-256 of two representative artifacts;
the hashes were captured before any translator changes for v1.1.0
landed, so re-passing here proves the v1.0.0 path is unchanged.
"""

from __future__ import annotations

import hashlib

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Comparison,
    CycleInvariant,
    Property,
    RegisterAt,
    RegisterInit,
    RiscvBtor2Spec,
)
from gurdy.pairs.riscv_btor2.translation.translate import Translator

from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000
# addi a0, x0, 1 ; addi a0, a0, 1 ; ret
ADD2_BYTES = bytes.fromhex("13050100" "13051500" "67800000")


# Baseline hashes captured at the start of Phase 1, before any v1.1.0
# translator code lands. If a test below fails, the message reports the
# actual hash so the constant can be updated (which should only ever
# happen as part of a deliberate, schema-bumping change).
EXPECTED_HASH_BASIC = "3cd1018c541b6b0fc06642e7bfb0dfadd89f1979d64eacd9adcd46f0fa307ac2"
EXPECTED_HASH_WITH_ASSUMPTIONS = "7a17b31a258facd71c028224acd480f24c087d00d47bd6c39550b07fc764dbd4"


def _make_binary(tmp_path):
    funcs = [FuncDef(name="add2", addr=TEXT_BASE, size=len(ADD2_BYTES))]
    p = tmp_path / "add2.elf"
    p.write_bytes(build_elf(ADD2_BYTES, TEXT_BASE, funcs))
    return p


def _translate(spec, src):
    sidecar = AnnotationSidecar(schema_version="1.0.0", spec_hash=spec.spec_hash())
    emitter = AnnotationEmitter(sidecar)
    return Translator().translate(spec, src, emitter)


def _hash_flattened(art) -> str:
    return hashlib.sha256(art.flattened).hexdigest()


def test_basic_spec_flattened_bytes(tmp_path):
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="add2"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    art = _translate(spec, load_riscv_binary(p))
    got = _hash_flattened(art)
    assert got == EXPECTED_HASH_BASIC, (
        f"basic v1.0.0 spec produced unexpected bytes: {got}"
    )


def test_spec_with_assumptions_flattened_bytes(tmp_path):
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="add2"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        assumptions=(
            RegisterInit(register=2, op=Comparison.EQ, value=0),
            CycleInvariant(expression="ltu(reg(2), 65536)"),
        ),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    art = _translate(spec, load_riscv_binary(p))
    got = _hash_flattened(art)
    assert got == EXPECTED_HASH_WITH_ASSUMPTIONS, (
        f"v1.0.0 spec with assumptions produced unexpected bytes: {got}"
    )


def test_compile_is_deterministic_under_v110_framework(tmp_path):
    """Recompiling twice produces byte-identical bytes."""
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="add2"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    src = load_riscv_binary(p)
    a = _translate(spec, src)
    b = _translate(spec, src)
    assert a.flattened == b.flattened
