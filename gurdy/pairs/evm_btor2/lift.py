"""Target-to-source interpreter ``L`` for evm-btor2.

Maps a BTOR2 behavior (state values keyed by the symbols the translator gave
them — ``pc``, ``s0..s{N-1}``, ``sp``, ``halted``) back to an EVM behavior in
the same shape the source interpreter produces, so the commuting square can be
checked under the projection ``π``. A solver-witness decoder is the same shape
once a BTOR2 solver / the btor2-smtlib bridge supplies a model.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ...languages.evm.interp import STACK_SIZE


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
        out.append(rec)
    return out
