"""Target-to-source interpreter ``L`` for sail-btor2: re-project a BTOR2
behavior (``pc``, ``x1..x31``, ``halted``) into the Sail interpreter's shape so
the commuting square can be checked under ``π``."""

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
