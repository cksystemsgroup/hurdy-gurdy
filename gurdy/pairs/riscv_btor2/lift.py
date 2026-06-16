"""Target-to-source interpreter ``L`` for riscv-btor2.

Maps a BTOR2 behavior (state values keyed by the symbols the translator gave
them — ``pc``, ``x1..x31``, ``halted``) back to a RISC-V behavior in the same
shape the source interpreter produces, so the commuting square can be checked
under the projection ``π``. For the thin slice this is a re-projection; a
solver-witness decoder is the same shape once a BTOR2 solver is wired.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        rec: dict[str, Any] = {"pc": row.get("pc"), "halted": bool(row.get("halted", 0))}
        for i in range(1, 32):
            rec[f"x{i}"] = row.get(f"x{i}")
        out.append(rec)
    return out
