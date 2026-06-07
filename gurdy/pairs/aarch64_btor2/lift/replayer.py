"""Witness replay adapter for the framework's ``replay`` tool.

Adapted from gurdy/pairs/riscv_btor2/lift/replayer.py (v2-bootstrap).
AArch64 differences vs riscv-btor2:
- 31 GPRs (reg_x0..reg_x30; keys 0–30).
- sp and nzcv are separate state variables.
- Uses AArch64SourceInterpreter and AArch64InputBinding.
"""

from __future__ import annotations

from typing import Any

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.interp.types import JoinedStep, JoinedTrace
from gurdy.core.pair import CompiledArtifact
from gurdy.core.btor2.parser import from_text
from gurdy.pairs.aarch64_btor2.lift.witness import (
    _extract_initial_register_values,
    _state_symbol_to_nid,
)
from gurdy.pairs.aarch64_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.aarch64_btor2.reasoning_interp.interpreter import (
    Btor2ReasoningInterpreter,
)
from gurdy.pairs.aarch64_btor2.source.loader import AArch64Source, load_aarch64_binary
from gurdy.pairs.aarch64_btor2.source_interp.bindings import AArch64InputBinding
from gurdy.pairs.aarch64_btor2.source_interp.interpreter import AArch64SourceInterpreter


def _bindings_from_witness(
    artifact: CompiledArtifact, raw: RawSolverResult
) -> tuple[AArch64InputBinding, Btor2ReasoningBinding]:
    """Decode initial values from the raw payload and build paired bindings."""
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    text = payload.get("witness_text", "") if isinstance(payload, dict) else ""
    initial_by_nid = _extract_initial_register_values(text)

    btor2_text = artifact.flattened.decode("utf-8", errors="replace")
    sym_to_nid = _state_symbol_to_nid(btor2_text)
    nid_to_sym = {nid: sym for sym, nid in sym_to_nid.items()}

    register_init: dict[int, int] = {}
    halted = False
    pc: int | None = None
    sp_init: int | None = None
    nzcv_init: int | None = None
    state_init_by_symbol: dict[str, int] = {}
    for nid, value in initial_by_nid.items():
        sym = nid_to_sym.get(nid)
        if sym is None:
            continue
        state_init_by_symbol[sym] = value
        if sym.startswith("reg_x"):
            try:
                idx = int(sym[len("reg_x"):])
            except ValueError:
                continue
            if 0 <= idx <= 30:
                register_init[idx] = value & ((1 << 64) - 1)
        elif sym == "pc":
            pc = value & ((1 << 64) - 1)
        elif sym == "sp":
            sp_init = value & ((1 << 64) - 1)
        elif sym == "nzcv":
            nzcv_init = value & 0xF
        elif sym == "halted":
            halted = bool(value)

    src_binding = AArch64InputBinding(
        register_init=register_init,
        sp_init=sp_init,
        nzcv_init=nzcv_init,
        memory_init={},
        pc=pc,
        halted=halted,
    )
    reas_binding = Btor2ReasoningBinding(
        state_init_by_symbol=state_init_by_symbol,
    )
    return src_binding, reas_binding


def _load_source_for_artifact(
    artifact: CompiledArtifact, raw: RawSolverResult
) -> AArch64Source | None:
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    if isinstance(payload, dict):
        path = payload.get("binary_path")
        if path:
            try:
                return load_aarch64_binary(path)
            except Exception:
                return None
    return None


def replay_witness(
    artifact: CompiledArtifact,
    raw: RawSolverResult,
    *,
    source: AArch64Source | None = None,
) -> JoinedTrace:
    """Build a JoinedTrace from a SAT-verdict witness."""
    src_binding, reas_binding = _bindings_from_witness(artifact, raw)
    if source is None:
        source = _load_source_for_artifact(artifact, raw)

    parsed = from_text(artifact.flattened.decode("utf-8", errors="replace"))
    bound_steps = 32
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    if isinstance(payload, dict) and isinstance(payload.get("anchor_step"), int):
        bound_steps = max(bound_steps, int(payload["anchor_step"]) + 4)

    src_interp = AArch64SourceInterpreter()
    reas_interp = Btor2ReasoningInterpreter()

    if source is None:
        reas_trace = reas_interp.run(artifact, reas_binding, bound_steps)
        return JoinedTrace(
            pair=artifact.pair,
            inputs_hash=src_binding.inputs_hash(),
            artifact_hash=reas_trace.artifact_hash,
            steps=(),
            halted=False,
            bad_fired_at=reas_trace.bad_fired_at,
        )

    src_trace = src_interp.run(source, src_binding, bound_steps)
    reas_trace = reas_interp.run(artifact, reas_binding, bound_steps)

    n = min(len(src_trace.steps), len(reas_trace.steps))
    joined = tuple(
        JoinedStep(step=i, source=src_trace.steps[i], reasoning=reas_trace.steps[i])
        for i in range(n)
    )
    return JoinedTrace(
        pair=artifact.pair,
        inputs_hash=src_binding.inputs_hash(),
        artifact_hash=reas_trace.artifact_hash,
        steps=joined,
        halted=src_trace.halted,
        bad_fired_at=reas_trace.bad_fired_at,
    )


__all__ = ["replay_witness", "_bindings_from_witness"]
