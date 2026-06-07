"""Step-level alignment for aarch64-btor2 (Stage 7.E aarch64 Tier-2).

Compiles a tiny A64 program, runs the source simulator and the BTOR2 reasoning
interpreter on the same entry, joins the traces through the pair's projection,
and asserts they agree step-for-step. A divergence would localize an aarch64
translation bug to a (step, field). Mirrors riscv-btor2's cross-check oracle;
needs no z3 (both interpreters evaluate concretely).
"""

from __future__ import annotations

from gurdy.core.interp import CrossCheckOutcome, align_traces
from gurdy.core.pair import get_pair
from gurdy.core.tools.compile import compile_spec
from gurdy.pairs.aarch64_btor2 import spec as A
from gurdy.pairs.aarch64_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.aarch64_btor2.source_interp.bindings import AArch64InputBinding
from tests.fixtures.elf_builder_aarch64 import FuncDef, build_elf

TEXT_BASE = 0x400000
_ADD_X0_1 = bytes.fromhex("00040091")  # add x0, x0, #1
_SVC = bytes.fromhex("010000D4")  # svc #0  (halts)


def _build_binary(tmp_path):
    code = _ADD_X0_1 + _ADD_X0_1 + _SVC  # x0 += 1; x0 += 1; halt
    p = tmp_path / "main.elf"
    p.write_bytes(
        build_elf(code, TEXT_BASE, [FuncDef(name="main", addr=TEXT_BASE, size=len(code))], entry=TEXT_BASE)
    )
    return p


def test_source_and_reasoning_agree_step_for_step(tmp_path):
    binary = _build_binary(tmp_path)
    spec = A.Aarch64Btor2Spec(
        binary=A.BinaryRef(path=str(binary)),
        scope=A.AnalysisScope(entry_function="main"),
        property=A.Property(expression="false"),
        analysis=A.AnalysisDirective(engine="z3-bmc", bound=4),
    )
    artifact = compile_spec(spec, source_payload=binary)
    pair = get_pair("aarch64-btor2")

    src_trace = pair.source_interpreter.run(
        pair.source_loader(binary), AArch64InputBinding(), max_steps=4, spec=spec
    )
    reas_trace = pair.reasoning_interpreter.run(
        artifact, Btor2ReasoningBinding(state_init_by_symbol={"pc": TEXT_BASE}), max_steps=4
    )
    assert len(src_trace.steps) >= 2, "source did not execute the program"

    report = align_traces(src_trace, reas_trace, pair.projection(artifact))
    assert report.outcome is CrossCheckOutcome.AGREEMENT, (
        f"divergence at step {report.divergence_step} on {report.divergence_label!r}: "
        f"source={report.source_view!r} reasoning={report.reasoning_view!r}"
    )
    assert report.steps_checked >= 2
    assert report.fields_checked > 0
