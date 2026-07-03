"""Target-to-source interpreter ``L`` for sail-btor2: re-project a BTOR2
behavior into the Sail interpreter's shape so the commuting square can be
checked under ``π``.

Two arms, keyed on the trace's own state symbols (each Sail arm's BTOR2 system
carries its architectural state under distinct names):

- **RISC-V** (the default — byte-for-byte unchanged): rows re-project onto
  ``pc``, ``x1..x31``, ``halted``.
- **AArch64** (additive, translator ``0.2``): a row from the A64 lowering
  carries the ``nzcv`` state symbol (the RISC-V arm never emits one), and
  re-projects onto ``pc``, ``x0..x30``, ``sp``, ``nzcv``, the memory-window
  bytes ``m0..m{MEM_WINDOW-1}`` (zero-filled when the program has no memory op
  — the mem array and window states are emitted conditionally, matching the
  source's zero-initialized window), and ``halted`` — the same shape the Sail
  interpreter's A64 arm records, and ``aarch64-btor2``'s ``L`` shape, so the
  branch cross-check compares like with like.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        if "nzcv" in row:                  # the AArch64 arm's state space
            out.append(_lift_aarch64_row(row))
            continue
        rec: dict[str, Any] = {"pc": row.get("pc"), "halted": bool(row.get("halted", 0))}
        for i in range(1, 32):
            rec[f"x{i}"] = row.get(f"x{i}")
        out.append(rec)
    return out


def _lift_aarch64_row(row: Any) -> dict[str, Any]:
    from ...languages.aarch64.interp import MEM_WINDOW, NREG

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
    return rec
