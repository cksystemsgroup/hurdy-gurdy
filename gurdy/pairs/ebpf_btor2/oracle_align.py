"""Alignment oracle for ebpf-btor2 per SCHEMA.md §14.

Compares source (EbpfSourceInterpreter) and reasoning
(EbpfReasoningInterpreter) traces step-by-step, checking that
reg_r0..reg_r9 agree at every step up to the first EXIT.
"""

from __future__ import annotations

from dataclasses import dataclass

from gurdy.core.interp.types import ReasoningTrace, SourceTrace
from gurdy.core.pair import CompiledArtifact
from gurdy.core.btor2.parser import from_text


ORACLE_VERSION = "1.0.0"
PAIR_ID = "ebpf-btor2"


@dataclass(frozen=True)
class AlignmentFailure:
    """One register mismatch between source and reasoning traces.

    ``step`` is the source step index (= reasoning step + 1).
    ``symbol`` is the BTOR2 state symbol, e.g. ``"reg_r0"``.
    ``src_val`` and ``r_val`` are the disagreeing values.
    """

    step: int
    symbol: str
    src_val: int
    r_val: int


def _sym_nids(artifact: CompiledArtifact) -> dict[str, int]:
    """Return ``{symbol: nid}`` for all state nodes in the artifact's BTOR2 text."""
    text = artifact.flattened.decode("utf-8", errors="replace")
    parsed = from_text(text)
    return {
        n.symbol: n.nid
        for n in parsed.model.nodes()
        if n.op == "state" and n.symbol
    }


def align(
    source_trace: SourceTrace,
    reasoning_trace: ReasoningTrace,
    artifact: CompiledArtifact,
) -> tuple[list[AlignmentFailure], bool]:
    """Compare source and reasoning traces for register agreement per SCHEMA.md §14.

    For each step k, checks that ``source_trace.steps[k+1].reg_rN``
    equals ``reasoning_trace.steps[k].layer_values["machine"][sym["reg_rN"]]``
    for N in 0..9, stopping at (and including) the first EXIT step.

    Source register values are reconstructed by accumulating deltas from
    ``source_trace.steps``, seeded at zero.  For correct results, every
    register whose initial value is non-zero must appear as a delta in
    ``source_trace.steps[1]`` (i.e., the first executed instruction must
    write it) or start at zero in the source binding.

    Returns:
        ``(failures, aligned)`` — ``aligned`` is ``True`` iff ``failures``
        is empty.
    """
    sym = _sym_nids(artifact)
    failures: list[AlignmentFailure] = []

    # Cumulative source register state, seeded at zero.
    src_regs: dict[int, int] = {n: 0 for n in range(10)}

    src_steps = source_trace.steps
    r_steps = reasoning_trace.steps
    max_k = min(len(src_steps) - 1, len(r_steps))

    for k in range(max_k):
        src_step = src_steps[k + 1]

        # Update accumulated source register state from this step's deltas.
        if src_step.deltas:
            for n in range(10):
                key = f"r{n}"
                if key in src_step.deltas:
                    src_regs[n] = int(src_step.deltas[key])

        # Compare reg_r0..reg_r9 against reasoning step k.
        machine = r_steps[k].layer_values.get("machine", {})
        for n in range(10):
            sym_name = f"reg_r{n}"
            nid = sym.get(sym_name)
            if nid is None:
                continue
            r_val = int(machine.get(nid, 0))
            src_val = src_regs[n]
            if src_val != r_val:
                failures.append(AlignmentFailure(
                    step=k + 1,
                    symbol=sym_name,
                    src_val=src_val,
                    r_val=r_val,
                ))

        if src_step.halted:
            break

    return failures, len(failures) == 0


__all__ = [
    "AlignmentFailure",
    "ORACLE_VERSION",
    "PAIR_ID",
    "align",
]
