"""Target-to-source interpreter ``L`` for aarch64-sail.

Carries a Sail-model behavior back to an AArch64 behavior by re-projecting the
Sail A64 arm's architectural state onto the AArch64 observables ``π`` =
``{pc, x0..x30, sp, nzcv, m0..m{MEM_WINDOW-1}, halted}``. Because both ends
describe the same ISA (the Sail object *is* A64 run through the Sail-derived
semantics), this is largely a re-projection — exactly the brief's "largely a
re-projection" carry-back.

The Sail A64 arm already records post-step state keyed by those observable
names (``languages/sail/aarch64.py``), including the byte-memory window
``m0``–``m{MEM_WINDOW-1}`` (the additive ``0.6`` extension that mirrors
``aarch64-btor2``'s window), so ``L`` selects them and normalizes the halt flag
to a Python ``bool``, yielding the same shape the shared AArch64 interpreter
produces — so the commuting-square oracle can align them under ``π``. A
program with no memory op leaves memory all-zero, so each ``m{i}`` carries back
as ``0`` (matching the source's zero-initialized window). A solver-witness
decoder is the same shape once ``sail-btor2`` / a BTOR2 solver supplies a model:
each witness row carries the same state symbols.
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
