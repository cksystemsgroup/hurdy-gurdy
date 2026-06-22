"""Target-to-source interpreter ``L`` for aarch64-sail.

Carries a Sail-model behavior back to an AArch64 behavior by re-projecting the
Sail A64 arm's architectural state onto the AArch64 observables ``π`` =
``{pc, x0..x30, sp, nzcv, halted}``. Because both ends describe the same ISA
(the Sail object *is* A64 run through the Sail-derived semantics), this is
largely a re-projection — exactly the brief's "largely a re-projection" carry-back.

The Sail A64 arm already records post-step state keyed by those observable
names (``languages/sail/aarch64.py``), so ``L`` selects them and normalizes the
halt flag to a Python ``bool``, yielding the same shape the shared AArch64
interpreter produces — so the commuting-square oracle can align them under
``π``. A solver-witness decoder is the same shape once ``sail-btor2`` / a BTOR2
solver supplies a model: each witness row carries the same state symbols.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ...languages.aarch64.interp import NREG


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
        out.append(rec)
    return out
