"""Target-to-source interpreter ``L`` for wasm-btor2.

Maps a BTOR2 behavior (state values keyed by the symbols the translator gave
them — ``pc``, ``halted``, ``sp``, the value-stack slots ``s0..s{D-1}`` and the
locals ``l0..l{N-1}``) back to a Wasm stack-machine behavior in the same shape
the source interpreter produces, so the commuting square can be checked under
the projection ``π``.

The Wasm value stack is reconstructed from the static-but-carried depth ``sp``:
the live stack is exactly slots ``s0 .. s{sp-1}`` (slots at or above ``sp`` hold
stale/cleared values and are not part of the source observable). A solver-witness
decoder is the same shape once a BTOR2 solver / the btor2-smtlib bridge supplies
a model.

The ``trapped`` observable (a defined Wasm div/rem trap) is carried back from the
BTOR2 ``trapped`` state var; a trap-free body has no such var, so ``trapped``
defaults to ``False`` — matching the source interpreter, which emits ``False`` on
every non-trapping state.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace


def _slot_count(row: dict[str, Any]) -> int:
    n = 0
    while f"s{n}" in row:
        n += 1
    return n


def _local_count(row: dict[str, Any]) -> int:
    n = 0
    while f"l{n}" in row:
        n += 1
    return n


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        nslots = _slot_count(row)
        nlocals = _local_count(row)
        sp = int(row.get("sp", 0) or 0)
        sp = max(0, min(sp, nslots))
        stack = tuple(row.get(f"s{j}") for j in range(sp))
        locals_ = tuple(row.get(f"l{k}") for k in range(nlocals))
        out.append({
            "pc": row.get("pc"),
            "halted": bool(row.get("halted", 0)),
            "trapped": bool(row.get("trapped", 0)),
            "sp": sp,
            "stack": stack,
            "locals": locals_,
        })
    return out
