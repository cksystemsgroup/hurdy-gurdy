"""Witness replay adapter for the framework's ``replay`` tool.

Takes a Z3 / Bitwuzla / cvc5 raw payload, extracts the witness, builds
the framework's binding types, runs both interpreters, and joins the
two traces step-by-step into a ``JoinedTrace``.

The witness extraction uses the same logic as the legacy
``lift_witness`` (see ``witness.py``) so behaviour is unchanged for
existing callers.
"""

from __future__ import annotations

from typing import Any

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.interp.types import JoinedStep, JoinedTrace
from gurdy.core.pair import CompiledArtifact
from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.lift.witness import (
    _extract_initial_register_values,
    _state_symbol_to_nid,
)
from gurdy.pairs.riscv_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.riscv_btor2.reasoning_interp.interpreter import (
    Btor2ReasoningInterpreter,
)
from gurdy.pairs.riscv_btor2.source.loader import RISCVSource, load_riscv_binary
from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding
from gurdy.pairs.riscv_btor2.source_interp.interpreter import RiscvSourceInterpreter


def _bindings_from_witness(
    artifact: CompiledArtifact, raw: RawSolverResult
) -> tuple[RiscvInputBinding, Btor2ReasoningBinding]:
    """Decode initial register values from the raw payload's
    ``witness_text`` and build paired bindings the two interpreters
    can consume.
    """
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    text = payload.get("witness_text", "") if isinstance(payload, dict) else ""
    initial_by_nid = _extract_initial_register_values(text)

    btor2_text = artifact.flattened.decode("utf-8", errors="replace")
    sym_to_nid = _state_symbol_to_nid(btor2_text)
    nid_to_sym = {nid: sym for sym, nid in sym_to_nid.items()}

    register_init: dict[int, int] = {}
    halted = False
    pc: int | None = None
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
            if 1 <= idx < 32:
                register_init[idx] = value & ((1 << 64) - 1)
        elif sym == "pc":
            pc = value & ((1 << 64) - 1)
        elif sym == "halted":
            halted = bool(value)

    src_binding = RiscvInputBinding(
        register_init=register_init,
        memory_init={},
        pc=pc,
        halted=halted,
    )
    reas_binding = Btor2ReasoningBinding(
        state_init_by_symbol=state_init_by_symbol,
    )
    return src_binding, reas_binding


def _load_source_for_artifact(artifact: CompiledArtifact, raw: RawSolverResult) -> RISCVSource | None:
    """Best-effort source loading: prefer a binary path passed through
    on the raw payload (lift currently expects the harness to plumb
    this), then fall back to None — the caller can always pre-load
    and call the interpreters directly."""
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    if isinstance(payload, dict):
        path = payload.get("binary_path")
        if path:
            try:
                return load_riscv_binary(path)
            except Exception:
                return None
    return None


def replay_witness(
    artifact: CompiledArtifact, raw: RawSolverResult, *, source: RISCVSource | None = None
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

    src_interp = RiscvSourceInterpreter()
    reas_interp = Btor2ReasoningInterpreter()

    if source is None:
        # No source available — can't run the simulator; return an empty trace.
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
