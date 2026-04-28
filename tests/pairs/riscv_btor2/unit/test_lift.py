from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.pairs.riscv_btor2.lift.invariant import lift_invariant
from gurdy.pairs.riscv_btor2.lift.lift import Lifter
from gurdy.pairs.riscv_btor2.lift.witness import lift_witness


def test_lift_invariant_glossary_includes_abi_aliases():
    text = "(<= reg_x10 100)"
    out = lift_invariant(text)
    assert out.raw == text
    assert "reg_x10" in out.glossary
    assert "a0" in out.glossary["reg_x10"]


def test_lift_invariant_recognizes_pc_and_mem():
    text = "(and (not (= pc 0)) (= (select mem 0) 0))"
    out = lift_invariant(text)
    assert "pc" in out.glossary
    assert "mem" in out.glossary


def test_lifter_reachable_returns_lifted_result_with_verdict():
    artifact = CompiledArtifact(
        pair="riscv-btor2",
        layers={"header": Layer(name="header", body=b"", content_hash="x")},
        annotation=AnnotationSidecar(),
        flattened=b"",
        schema_version="1.0.0",
        spec_hash="abc",
    )
    raw = RawSolverResult(
        verdict="reachable",
        elapsed=0.1,
        engine="z3-bmc",
        payload={"witness_text": "no useful info here"},
    )
    out = Lifter().lift(artifact, raw)
    assert out.verdict == "reachable"
    assert out.engine == "z3-bmc"


def test_lifter_unknown_passes_through_reason():
    artifact = CompiledArtifact(
        pair="riscv-btor2",
        layers={},
        annotation=AnnotationSidecar(),
        flattened=b"",
        schema_version="1.0.0",
        spec_hash="z",
    )
    raw = RawSolverResult(
        verdict="unknown", elapsed=0.0, engine="z3-spacer", reason="not implemented"
    )
    out = Lifter().lift(artifact, raw)
    assert out.verdict == "unknown"
    assert out.reason == "not implemented"


def test_lifter_proved_with_string_payload_runs_invariant_lift():
    artifact = CompiledArtifact(
        pair="riscv-btor2",
        layers={},
        annotation=AnnotationSidecar(),
        flattened=b"",
        schema_version="1.0.0",
        spec_hash="z",
    )
    raw = RawSolverResult(
        verdict="proved",
        elapsed=0.0,
        engine="z3-spacer",
        payload="(<= reg_x10 0)",
    )
    out = Lifter().lift(artifact, raw)
    assert out.invariant is not None
    assert "reg_x10" in out.invariant.glossary
