"""Target-to-source interpreter ``L`` for evm-btor2.

Maps a BTOR2 behavior (state values keyed by the symbols the translator gave
them — ``pc``, ``s0..s{N-1}``, ``sp``, the memory-window bytes ``m0..m{W-1}``,
the storage-window words ``s_at_0..s_at_{S-1}``, ``halted``, and the halt-status
``status``) back to an EVM behavior in the same shape the source interpreter
produces, so the commuting square can be checked under the projection ``π``. A
solver-witness decoder is the same shape once a BTOR2 solver / the btor2-smtlib
bridge supplies a model.

The memory-window bytes ``m{i}`` and the storage-window words ``s_at_{i}`` appear
in the BTOR2 trace only when the program touches memory / storage respectively
(each array + its window states are emitted conditionally, mirroring
``ebpf-btor2``); a program with no such op leaves that region all-zero, so the
missing fields carry back as ``0`` — matching the source's zero-initialized
memory and storage. The halt-status ``status`` byte (v0.9), by contrast, is
emitted in *every* program (every halt carries a *why*), so it carries back
directly — defaulting to ``running`` (0) if a trace ever omits it.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ...languages.evm.interp import (
    MEM_WINDOW,
    STACK_SIZE,
    STATUS_RUNNING,
    STORE_WINDOW,
)


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        rec: dict[str, Any] = {
            "pc": row.get("pc"),
            "sp": row.get("sp"),
            "halted": bool(row.get("halted", 0)),
            "status": row.get("status", STATUS_RUNNING),
        }
        for i in range(STACK_SIZE):
            rec[f"s{i}"] = row.get(f"s{i}")
        for i in range(MEM_WINDOW):            # zero-fill the window when no mem op
            rec[f"m{i}"] = row.get(f"m{i}", 0)
        for i in range(STORE_WINDOW):          # zero-fill when no storage op
            rec[f"s_at_{i}"] = row.get(f"s_at_{i}", 0)
        out.append(rec)
    return out
