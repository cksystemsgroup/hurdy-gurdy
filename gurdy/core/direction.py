"""Square direction — exact vs. over-approximating pairs (ARCHITECTURE.md §3;
POTENTIAL.md §6).

A pair's square is either **exact** (``I_s(p) ≡_π Λ(I_t(T(p)))`` — every pair
before the directional extension) or **over-approximating** (``I_s(p) ⊑_π
Λ(I_t(T(p)))`` — the target admits every source behavior on the kept
observables, and possibly more). An ``over`` pair is an *abstraction*: it is
checked as an exact square **along its witness embedding** (the pair-supplied
map from a source binding to the target binding that simulates it), so the
oracle, coverage, determinism, and negative-control machinery apply unchanged.

Direction governs **verdict transfer** — what an answer obtained at the target
means at the source:

- ``unreachable`` (universal) transfers along ``exact`` and ``over`` alike: a
  superset of behaviors avoiding ``bad`` implies the source avoids it.
- ``reachable`` (existential) transfers along ``exact`` only — and is *never*
  taken on transfer alone: it is carried back and replayed at the source
  (SOLVERS.md §4), which either certifies it or exposes it as **spurious**, a
  refinement demand on the abstraction.

Direction composes as a meet on the chain ``exact > over``: a route is exact
iff every hop is. It is a third declared axis beside fidelity and coverage —
and like ``π`` it is a protected field (SCALING.md §9): a builder must not
flip it.
"""

from __future__ import annotations

from typing import Any

EXACT = "exact"
OVER = "over"

_ORDER = (EXACT, OVER)  # meet-chain, strongest first


def compose(*directions: str) -> str:
    """The direction of a composition: the weakest hop's (``exact`` iff all
    hops are exact). Unknown values are a contract violation, not a default."""
    worst = EXACT
    for d in directions:
        if d not in _ORDER:
            raise ValueError(f"unknown square direction: {d!r}")
        if _ORDER.index(d) > _ORDER.index(worst):
            worst = d
    return worst


def transfers(verdict: Any, direction: str) -> bool:
    """Does ``verdict``, obtained at the target end, hold at the source on the
    strength of the (route-composed) ``direction`` alone?

    ``unreachable`` transfers along ``exact`` and ``over``; ``reachable``
    transfers along ``exact`` only — and by SOLVERS.md §4 is replayed at the
    source regardless, so this function is about *meaning*, not about skipping
    the replay. ``unknown`` / ``resource-out`` never transfer: they assert
    nothing.
    """
    if direction not in _ORDER:
        raise ValueError(f"unknown square direction: {direction!r}")
    v = getattr(verdict, "value", verdict)
    if v == "unreachable":
        return True
    if v == "reachable":
        return direction == EXACT
    return False
