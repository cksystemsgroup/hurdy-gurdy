"""Construct inventory for ``btor2-interval`` (BENCHMARKS.md §2).

The yardstick is the brief's spec-enumerable construct set
(pairs/btor2-interval/README.md "Coverage target"): the four range shapes
required for ``built`` — proper subrange, singleton, full range
(havoc-degenerate), multi-state — plus the two constructs typed
``unsupported`` at registration scope: the wrapped range ``hi < lo`` and
the array-sorted state (the shared interpreter has no array-valued
inputs — havoc's same gap). Each probe is a translator input ``{"system",
"intervals", "binding"}``; the binding drives the square (source run +
witness embedding), so every declared range must actually be invariant for
the source run — the square along ``W`` *is* the interval claim.
"""

from __future__ import annotations

# Two independent 4-bit counters; confine one, the other must still track.
# Four steps drive ``a`` through 1..4 — inside the declared [0, 6].
_COUNTERS = """1 sort bitvec 4
2 state 1 a
3 state 1 b
4 one 1
5 add 1 2 4
6 add 1 3 4
7 next 1 2 5
8 next 1 3 6
"""

# A state pinned by its own update: init 5, next = itself. The singleton
# [5, 5] is the constant-pinning rung of the CEGAR ladder; the emission
# keeps the uniform shape (urem(iv, 1) = 0, so next := 5).
_PINNED = """1 sort bitvec 4
2 state 1 c
3 constd 1 5
4 init 1 2 3
5 next 1 2 2
6 constd 1 9
7 eq 1 2 6
8 bad 7
"""

# Full range [0, 15] on a 4-bit counter: the havoc-degenerate rewrite,
# next := iv directly (no urem-by-zero edge).
_COUNTER = """1 sort bitvec 4
2 state 1 s
3 one 1
4 add 1 2 3
5 next 1 2 4
"""

# Two mapped states with different ranges: x steps by 1 (range [0, 6]),
# y steps by 2 (range [0, 9]); z stays exact and must still track.
_TRIPLE = """1 sort bitvec 4
2 state 1 x
3 state 1 y
4 state 1 z
5 one 1
6 constd 1 2
7 add 1 2 5
8 add 1 3 6
9 add 1 4 5
10 next 1 2 7
11 next 1 3 8
12 next 1 4 9
"""

# An array-sorted state: out of scope (no array-valued inputs in the
# shared interpreter) — the typed ``Unsupported`` construct.
_ARRAY = """1 sort bitvec 2
2 sort bitvec 4
3 sort array 1 2
4 state 3 mem
5 state 2 w
6 one 2
7 add 2 5 6
8 next 2 5 7
"""

_STEPS = {"steps": 4}

ALL_PROBES: dict[str, dict] = {
    "interval.subrange": {
        "system": _COUNTERS, "intervals": {"a": (0, 6)}, "binding": _STEPS},
    "interval.singleton": {
        "system": _PINNED, "intervals": {"c": (5, 5)}, "binding": _STEPS},
    "interval.full-range": {
        "system": _COUNTER, "intervals": {"s": (0, 15)}, "binding": _STEPS},
    "interval.multi-state": {
        "system": _TRIPLE, "intervals": {"x": (0, 6), "y": (0, 9)},
        "binding": _STEPS},
    "interval.wraparound": {
        "system": _COUNTER, "intervals": {"s": (14, 2)}, "binding": _STEPS},
    "interval.array-state": {
        "system": _ARRAY, "intervals": {"mem": (0, 3)}, "binding": _STEPS},
}
