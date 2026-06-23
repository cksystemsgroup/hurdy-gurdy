"""Target-to-source interpreter ``L`` for aarch64-btor2.

Maps a BTOR2 behavior (state values keyed by the symbols the translator gave
them — ``pc``, ``x0..x30``, ``sp``, ``nzcv``, the memory-window bytes
``m0..m{MEM_WINDOW-1}``, ``halted``) back to an AArch64 behavior in the same shape
the shared AArch64 interpreter produces, so the commuting square can be checked
under the projection ``π``. A solver-witness decoder is the same shape once a
BTOR2 solver / the ``btor2-smtlib`` bridge supplies a model: each witness row
carries the same state symbols.

The memory-window bytes ``m{i}`` appear in the BTOR2 trace only when the program
touches memory (the ``mem`` array + the window states are emitted conditionally,
mirroring ``evm-btor2`` / ``ebpf-btor2``); a program with no memory op leaves
memory all-zero, so the missing bytes carry back as ``0`` — matching the source's
zero-initialized memory window.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ...languages.aarch64.interp import MEM_WINDOW, NREG


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        rec: dict[str, Any] = {
            "pc": row.get("pc"),
            "sp": row.get("sp"),
            "nzcv": row.get("nzcv"),
            "halted": bool(row.get("halted", 0)),
        }
        for r in range(NREG):
            rec[f"x{r}"] = row.get(f"x{r}")
        for i in range(MEM_WINDOW):            # zero-fill the window when no mem op
            rec[f"m{i}"] = row.get(f"m{i}", 0)
        out.append(rec)
    return out
