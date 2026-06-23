"""Target-to-source interpreter ``L`` for ebpf-btor2.

Maps a BTOR2 behavior (state values keyed by the symbols the translator gave
them — ``pc``, ``r0..r10``, ``halted``) back to an eBPF behavior in the same
shape the source interpreter produces, so the commuting square can be checked
under the projection ``π``. A solver-witness decoder is the same shape once a
BTOR2 solver / the btor2-smtlib bridge supplies a model.

For ``CALL`` (helper calls) the carry-back also recovers the **helper-return
inputs** the run used: each call site's fresh BTOR2 inputs (``call{i}_r0``..
``call{i}_r5``) land in ``r0``–``r5`` at the post-cycle state, so the consumed
helper-effect stream is read straight off the lifted behavior
(``helper_inputs_from_behavior``). Replaying that stream through the shared
interpreter reproduces the BTOR2 run — the square commuting on the witness.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ...languages.ebpf.interp import CALL_CLOBBERED, NREG, _decode


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        rec: dict[str, Any] = {"pc": row.get("pc"), "halted": bool(row.get("halted", 0))}
        for i in range(NREG):
            rec[f"r{i}"] = row.get(f"r{i}")
        out.append(rec)
    return out


def _is_call(insn: int) -> bool:
    code, _dst, _src, _off, _imm = _decode(insn)
    return (code & 0x07) == 0x05 and ((code >> 4) & 0x0F) == 0x8  # JMP class, CALL op


def call_cycles(insns: list[int], target_trace: Trace) -> list[tuple[int, int]]:
    """The ``(cycle, pc)`` of every dynamic ``CALL`` execution in a BTOR2
    behavior, in execution order. Cycle ``c`` of the BTOR2 run executes the
    instruction at ``target_trace[c]['pc']`` (the *pre*-cycle pc), updating into
    ``target_trace[c + 1]``; a row is a CALL execution when that pc indexes a
    ``CALL`` and the machine has not already halted."""
    out: list[tuple[int, int]] = []
    for c in range(len(target_trace) - 1):
        if target_trace[c].get("halted"):
            break
        pc = target_trace[c].get("pc")
        if pc is not None and 0 <= pc < len(insns) and _is_call(insns[pc]):
            out.append((c, pc))
    return out


def helper_inputs_from_behavior(insns: list[int], target_trace: Trace) -> list[dict[int, int]]:
    """Reconstruct the interpreter's ``helper_inputs`` stream from a BTOR2
    behavior: at each ``CALL`` cycle the post-cycle ``r0``–``r5`` are exactly the
    helper inputs that were consumed (the call site wrote its fresh inputs into
    them). Returns one ``{reg: value}`` dict per dynamic CALL, in order — feeding
    it to the shared interpreter reproduces the BTOR2 run (carry-back)."""
    stream: list[dict[int, int]] = []
    for cycle, _pc in call_cycles(insns, target_trace):
        post = target_trace[cycle + 1]
        stream.append({r: int(post.get(f"r{r}", 0)) for r in CALL_CLOBBERED})
    return stream
