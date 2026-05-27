"""P4 smoke test: translate a trivial AArch64 ELF and verify end-to-end.

Tests:
1. translate() produces a non-empty BTOR2 artifact that parses cleanly.
2. Z3BMCSolver returns a verdict (not "error").
3. lift() returns a LiftedResult without raising.
4. simulate() runs correctly on a two-instruction program.
5. lift_invariant() produces an AArch64 glossary.
"""

from __future__ import annotations

import pytest

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.pair import CompiledArtifact
from gurdy.pairs.aarch64_btor2.lift.invariant import lift_invariant
from gurdy.pairs.aarch64_btor2.lift.lift import Lifter
from gurdy.pairs.aarch64_btor2.lift.simulator import State, fetch_from_memory_map, simulate
from gurdy.pairs.aarch64_btor2.lift.witness import lift_witness
from gurdy.pairs.aarch64_btor2.solvers.z3bmc import Z3BMCSolver
from gurdy.pairs.aarch64_btor2.source.loader import load_aarch64_binary
from gurdy.pairs.aarch64_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    Aarch64Btor2Spec,
    BinaryRef,
    Property,
)
from gurdy.pairs.aarch64_btor2.translation.translate import Translator
from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from tests.fixtures.elf_builder_aarch64 import FuncDef, build_elf

TEXT_BASE = 0x400000

# ADD X0, X0, #1 → 0x91000400; SVC #0 → 0xD4000001
_ADD_X0_1 = bytes.fromhex("00040091")
_SVC = bytes.fromhex("010000D4")


def _make_elf(code: bytes, tmp_path, name: str = "main"):
    p = tmp_path / "smoke.elf"
    p.write_bytes(build_elf(code, TEXT_BASE, [FuncDef(name, TEXT_BASE, len(code))]))
    return p


def _translate(spec: Aarch64Btor2Spec, source) -> CompiledArtifact:
    sidecar = AnnotationSidecar(schema_version="1.0.0", spec_hash=spec.spec_hash())
    return Translator().translate(spec, source, AnnotationEmitter(sidecar))


# ---------------------------------------------------------------------------
# 1. BTOR2 artifact is non-empty and parses cleanly
# ---------------------------------------------------------------------------


def test_translate_produces_parseable_btor2(tmp_path):
    elf_path = _make_elf(_ADD_X0_1 + _SVC, tmp_path)
    source = load_aarch64_binary(elf_path)
    spec = Aarch64Btor2Spec(
        binary=BinaryRef(path=str(elf_path)),
        scope=AnalysisScope(entry_function="main"),
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=4),
    )
    artifact = _translate(spec, source)
    text = artifact.flattened.decode("utf-8")
    assert len(text) > 100, "expected non-trivial BTOR2 output"
    result = from_text(text)
    assert not result.has_errors(), f"BTOR2 parse errors: {result.diagnostics[:3]}"


# ---------------------------------------------------------------------------
# 2. Z3BMCSolver returns a verdict (not "error")
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["find_spec"]).find_spec("z3") is None,
    reason="z3 not installed",
)
def test_z3bmc_returns_verdict(tmp_path):
    elf_path = _make_elf(_ADD_X0_1 + _SVC, tmp_path)
    source = load_aarch64_binary(elf_path)
    spec = Aarch64Btor2Spec(
        binary=BinaryRef(path=str(elf_path)),
        scope=AnalysisScope(entry_function="main"),
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=4),
    )
    artifact = _translate(spec, source)

    class _D:
        bound = 4

    raw = Z3BMCSolver().dispatch(artifact.flattened, _D())
    assert raw.verdict != "error", f"z3-bmc error: {raw.reason}"
    assert raw.verdict in ("reachable", "unreachable", "unknown")


# ---------------------------------------------------------------------------
# 3. Lifter.lift() returns LiftedResult without raising
# ---------------------------------------------------------------------------


def test_lifter_lift_no_raise(tmp_path):
    elf_path = _make_elf(_ADD_X0_1 + _SVC, tmp_path)
    source = load_aarch64_binary(elf_path)
    spec = Aarch64Btor2Spec(
        binary=BinaryRef(path=str(elf_path)),
        scope=AnalysisScope(entry_function="main"),
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=4),
    )
    artifact = _translate(spec, source)
    raw = RawSolverResult(verdict="unreachable", elapsed=0.1, engine="z3-bmc")
    result = Lifter().lift(artifact, raw, source=source)
    assert result.verdict == "unreachable"
    assert result.pair == "aarch64-btor2"


# ---------------------------------------------------------------------------
# 4. simulate() runs a two-instruction program correctly
# ---------------------------------------------------------------------------


def test_simulate_add_then_svc(tmp_path):
    elf_path = _make_elf(_ADD_X0_1 + _SVC, tmp_path)
    source = load_aarch64_binary(elf_path)
    bytemap = source.binary.loadable_byte_map()
    fetch = fetch_from_memory_map(bytemap)
    state = State()
    state.pc = TEXT_BASE
    state.regs[0] = 41
    final, trace = simulate(state, fetch, max_steps=10)
    assert len(trace) == 2
    assert trace[0].mnemonic == "ADD"
    assert trace[1].mnemonic == "SVC"
    assert final.regs[0] == 42
    assert final.halted is True


# ---------------------------------------------------------------------------
# 5. lift_invariant produces AArch64 glossary
# ---------------------------------------------------------------------------


def test_lift_invariant_aarch64_glossary():
    raw = "(and (bvult reg_x0 #x0000000000000064) (= pc #x400008))"
    inv = lift_invariant(raw)
    assert "reg_x0" in inv.glossary
    assert "x0" in inv.glossary["reg_x0"]
    assert "pc" in inv.glossary


def test_lift_invariant_sp_nzcv():
    raw = "(and (bvugt sp #x0) (= nzcv #x0))"
    inv = lift_invariant(raw)
    assert "sp" in inv.glossary
    assert "nzcv" in inv.glossary
