"""Target-to-source interpreter ``L`` for evm-btor2.

Maps a BTOR2 behavior (state values keyed by the symbols the translator gave
them — ``pc``, ``s0..s{N-1}``, ``sp``, the memory-window bytes ``m0..m{W-1}``,
``halted``) back to an EVM behavior in the same shape the source interpreter
produces, so the commuting square can be checked under the projection ``π``. A
solver-witness decoder is the same shape once a BTOR2 solver / the btor2-smtlib
bridge supplies a model.

The memory-window bytes ``m{i}`` appear in the BTOR2 trace only when the program
touches memory (the ``mem`` array + the window states are emitted conditionally,
mirroring ``ebpf-btor2``); a program with no memory op leaves memory all-zero, so
the missing bytes carry back as ``0`` — matching the source's zero-initialized
memory.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ...languages.evm.interp import MEM_WINDOW, STACK_SIZE


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        rec: dict[str, Any] = {
            "pc": row.get("pc"),
            "sp": row.get("sp"),
            "halted": bool(row.get("halted", 0)),
        }
        for i in range(STACK_SIZE):
            rec[f"s{i}"] = row.get(f"s{i}")
        for i in range(MEM_WINDOW):            # zero-fill the window when no mem op
            rec[f"m{i}"] = row.get(f"m{i}", 0)
        out.append(rec)
    return out
