"""Pair-local helpers that compose existing primitives.

These are conveniences, not framework surface. They don't define
new tool verbs; they just stitch together what the translator-layer
and interpreter-layer tools already provide.

Today: ``trace_to_branch_pins`` converts a shadow-recorded
``SourceTrace`` (SCHEMA.md §14.6) into a tuple of ``BranchPin``s
ready to drop into ``RiscvBtor2Spec.assumptions``. Optionally flips
the direction of a single branch event (the classic concolic-style
"same prefix, opposite at step k" question).
"""

from __future__ import annotations

from typing import Iterable

from gurdy.core.interp.types import SourceTrace
from gurdy.pairs.riscv_btor2.spec import BranchPin


def trace_to_branch_pins(
    trace: SourceTrace,
    *,
    flip_branch_at: int | None = None,
) -> tuple[BranchPin, ...]:
    """Build a tuple of :class:`BranchPin` from a shadow-recorded
    trace's branch events (SCHEMA.md §14.3, §14.6).

    ``flip_branch_at``: when provided, the pin for the branch event
    at that step has its ``taken`` direction inverted. Raises
    :class:`ValueError` if no branch event is recorded at that step.

    Pins are returned in the order their events were recorded
    (i.e. by step).
    """
    shadow = (trace.final_state or {}).get("shadow") if trace.final_state else None
    if not shadow:
        return ()
    events = shadow.get("branch_events", ())

    if flip_branch_at is not None and not any(
        e["step"] == flip_branch_at for e in events
    ):
        raise ValueError(
            f"no branch event at step {flip_branch_at}; "
            f"available: {sorted(e['step'] for e in events)}"
        )

    pins: list[BranchPin] = []
    for ev in events:
        taken = bool(ev["taken"])
        if ev["step"] == flip_branch_at:
            taken = not taken
        pins.append(BranchPin(step=int(ev["step"]), taken=taken, pc=int(ev["pc"])))
    return tuple(pins)


__all__ = ["trace_to_branch_pins"]
