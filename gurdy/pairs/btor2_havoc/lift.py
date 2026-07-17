"""The ``btor2-havoc`` target-to-source interpreter ``Λ``.

The abstraction keeps every state node and every ``bad`` of the source system
(only ``next`` functions are rewritten and a fresh input added), so a target
behavior already speaks the source system's observable vocabulary: the
carry-back is the identity on rows. The fresh ``havoc_*`` inputs are not
state observables and never appear in a trace row, so nothing needs dropping.
"""

from __future__ import annotations

from ...core.types import Trace

__all__ = ["lift"]


def lift(btrace: Trace) -> list[dict]:
    return [dict(row) for row in btrace]
