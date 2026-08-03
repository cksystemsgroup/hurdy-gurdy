"""The ``btor2-interval`` target-to-source interpreter ``Λ``.

The abstraction keeps every state node and every ``bad`` of the source
system (only ``next`` functions are rewritten; the fresh ``iv_*`` input and
const/arith nodes introduce no observables), so a target behavior already
speaks the source system's observable vocabulary: the carry-back is the
identity on rows.
"""

from __future__ import annotations

from ...core.types import Trace

__all__ = ["lift"]


def lift(btrace: Trace) -> list[dict]:
    return [dict(row) for row in btrace]
