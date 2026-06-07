"""End-to-end tests for the C -> RV64 ELF -> BTOR2 chain composer.

Docker-guarded (hop 1 needs the pinned image). Dispatch uses z3-bmc, a
declared test dependency. One task / one solver at a time; no parallelism.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gurdy.chains.c_to_btor2 import compile_c_to_btor2
from gurdy.core.tools.dispatch import dispatch
from gurdy.hops.c_riscv import default_pin, toolchain_available

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"

pytestmark = pytest.mark.skipif(
    not toolchain_available(),
    reason="pinned bench Docker image not available (chain hop 1 needs it)",
)


def _c(task: str) -> bytes:
    return (CORPUS / task / "task.c").read_bytes()


def test_0100_unreachable():
    r = compile_c_to_btor2(_c("0100-c-add-trap-correct"), source_name="task.c")
    assert r.artifact.pair == "riscv-btor2"
    assert r.trap_pc > 0
    raw = dispatch(r.artifact, r.spec.analysis)
    assert raw.verdict == "unreachable", f"got {raw.verdict!r} ({raw.reason})"


def test_0101_reachable_and_source_mapped():
    r = compile_c_to_btor2(_c("0101-c-add-trap-bug"), source_name="task.c")
    raw = dispatch(r.artifact, r.spec.analysis)
    assert raw.verdict == "reachable", f"got {raw.verdict!r} ({raw.reason})"

    # The understanding payoff: the BTOR2 witness lifts back to C source
    # lines via the transitive map (BTOR2 nid -> pc -> C file:line).
    lifted = r.lift(raw)
    assert lifted.trace is not None, "reachable witness produced no trace"
    files = {s.file for s in lifted.trace.steps if s.file}
    lines = [s.line for s in lifted.trace.steps if s.line is not None]
    assert any(f.endswith("task.c") for f in files), f"no C file in trace: {files}"
    assert lines, "no C line numbers recovered from DWARF"


def test_provenance_records_both_hops():
    r = compile_c_to_btor2(_c("0100-c-add-trap-correct"), source_name="task.c")
    prov = r.provenance
    assert [h["hop"] for h in prov] == ["c-riscv", "riscv-btor2"]
    assert prov[0]["elf_sha256"]
    assert prov[0]["digest"].startswith("sha256:")
    assert prov[0]["compiler_version"] == default_pin().compiler_version
    assert prov[1]["schema_version"]
    assert prov[1]["spec_hash"]


def test_artifact_is_btor2_with_trap_property():
    r = compile_c_to_btor2(_c("0100-c-add-trap-correct"), source_name="task.c")
    text = r.artifact.flattened.decode("utf-8")
    assert "sort" in text  # BTOR2 sort declarations
    assert r.spec.analysis.engine == "z3-bmc"
    # The synthesized property targets the resolved trap PC.
    assert f"0x{r.trap_pc:x}" in r.spec.property.expression


def test_0101_witness_aligns_with_simulator():
    # Soundness, through the chain: replay the BTOR2 witness and walk it
    # against the RV64 source interpreter step-by-step; every projected
    # observable (pc, regs, halted) must agree. A divergence here would be
    # a real C->ELF->BTOR2 translation bug, localized to a step.
    from gurdy.core.btor2.parser import from_text
    from gurdy.pairs.riscv_btor2.lift.replayer import replay_witness
    from gurdy.pairs.riscv_btor2.source_interp.projection import make_projection

    r = compile_c_to_btor2(_c("0101-c-add-trap-bug"), source_name="task.c")
    raw = dispatch(r.artifact, r.spec.analysis)
    assert raw.verdict == "reachable", f"got {raw.verdict!r} ({raw.reason})"

    joined = replay_witness(r.artifact, raw, source=r.source)
    parsed = from_text(r.artifact.flattened.decode("utf-8", "replace"))
    sym_to_nid = {
        n.symbol: n.nid
        for n in parsed.model.nodes()
        if n.op == "state" and n.symbol
    }
    projection = make_projection(sym_to_nid)
    checked = 0
    for i, jstep in enumerate(joined.steps):
        for pf in projection(jstep.source, jstep.reasoning):
            checked += 1
            assert pf.agree, f"divergence at step {i} label={pf.label}"
    assert checked > 0, "no observables were checked"


def test_chain_is_deterministic():
    a = compile_c_to_btor2(_c("0100-c-add-trap-correct"), source_name="task.c")
    b = compile_c_to_btor2(_c("0100-c-add-trap-correct"), source_name="task.c")
    assert a.elf_bytes == b.elf_bytes
    assert a.artifact.flattened == b.artifact.flattened
    assert a.trap_pc == b.trap_pc


def test_chain_align_localizes_per_hop_and_skips_compile_hop():
    # The chain alignment oracle (paste lemma): the rv64-elf -> btor2 square
    # commutes for the reachable witness, and the opaque compile hop is
    # recorded as skipped rather than silently dropped.
    r = compile_c_to_btor2(_c("0101-c-add-trap-bug"), source_name="task.c")
    raw = dispatch(r.artifact, r.spec.analysis)
    assert raw.verdict == "reachable", f"got {raw.verdict!r} ({raw.reason})"

    report = r.align(raw)
    assert report.aligned, report.to_jsonable()
    assert report.diverging_hop is None
    assert [h for h, _ in report.segments] == ["riscv-btor2"]
    assert [s.hop for s in report.skipped] == ["c-riscv"]
    # not a vacuous pass: real observables were checked
    assert report.segments[0][1].fields_checked > 0


def test_chain_verify_reestablishes_trust():
    # The CBMC differential is a second path C -> verdict. On agreement it lifts
    # the opaque c-riscv hop reproducible -> checked, re-establishing the chain's
    # trust above its static meet.
    r = compile_c_to_btor2(_c("0100-c-add-trap-correct"), source_name="task.c")
    raw = dispatch(r.artifact, r.spec.analysis)
    assert raw.verdict == "unreachable", f"got {raw.verdict!r} ({raw.reason})"

    report = r.verify(raw)
    assert report.classification == "agree", report.to_jsonable()
    assert report.verified is True
    assert report.cbmc_verdict == "unreachable"
    assert report.declared_trust.value == "reproducible"  # static meet (weakest hop)
    assert report.effective_trust.value == "checked"  # lifted by the verifier
    assert report.verified_hops == ("c-riscv",)
