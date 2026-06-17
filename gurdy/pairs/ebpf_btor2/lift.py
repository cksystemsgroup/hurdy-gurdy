"""Target-to-source interpreter ``L`` for ebpf-btor2.

Maps a BTOR2 behavior (state values keyed by the symbols the translator gave
them — ``pc``, ``r0..r10``, ``halted``) back to an eBPF behavior in the same
shape the source interpreter produces, so the commuting square can be checked
under the projection ``π``. A solver-witness decoder is the same shape once a
BTOR2 solver / the btor2-smtlib bridge supplies a model.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ...languages.ebpf.interp import NREG


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        rec: dict[str, Any] = {"pc": row.get("pc"), "halted": bool(row.get("halted", 0))}
        for i in range(NREG):
            rec[f"r{i}"] = row.get(f"r{i}")
        out.append(rec)
    return out
