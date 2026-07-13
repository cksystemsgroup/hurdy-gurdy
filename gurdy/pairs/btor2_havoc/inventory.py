"""Construct inventory for ``btor2-havoc`` (BENCHMARKS.md §2).

The yardstick is the rewrite's spec-enumerable construct set: what shapes of
state/next/init structure the abstraction must handle. Each probe is a
translator input ``{"system", "havoc", "binding"}``; the binding drives the
square (source run + witness embedding). ``havoc.array-state`` is declared
and out of scope (typed ``Unsupported``) — the honest gap, not a hidden one.
"""

from __future__ import annotations

# Two independent 4-bit counters; havoc one, the other must still track.
_COUNTERS = """1 sort bitvec 4
2 state 1 a
3 state 1 b
4 one 1
5 add 1 2 4
6 add 1 3 4
7 next 1 2 5
8 next 1 3 6
"""

# A three-state system; havoc two of the three.
_TRIPLE = """1 sort bitvec 4
2 state 1 x
3 state 1 y
4 state 1 z
5 one 1
6 add 1 2 5
7 add 1 3 6
8 add 1 4 7
9 next 1 2 6
10 next 1 3 7
11 next 1 4 8
"""

# The havocked state carries an ``init`` — it must be preserved (the
# abstraction havocs the update, not the start).
_WITH_INIT = """1 sort bitvec 4
2 state 1 c
3 constd 1 5
4 init 1 2 3
5 one 1
6 add 1 2 5
7 next 1 2 6
"""

# A state with no ``next`` at all: the rewrite is append-only.
_NEXTLESS = """1 sort bitvec 4
2 state 1 f
"""

# The system already has an input feeding the logic; the original input's
# binding must pass through beside the fresh havoc input.
_WITH_INPUT = """1 sort bitvec 4
2 input 1 u
3 state 1 s
4 state 1 t
5 add 1 3 2
6 next 1 3 5
7 one 1
8 add 1 4 7
9 next 1 4 8
"""

# A ``bad`` observable rides through the rewrite untouched.
_WITH_BAD = """1 sort bitvec 4
2 state 1 c
3 one 1
4 add 1 2 3
5 next 1 2 4
6 constd 1 3
7 eq 1 2 6
8 bad 7
"""

# An array-sorted state: out of scope (no array-valued inputs in the shared
# interpreter) — the typed ``Unsupported`` construct.
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
    "havoc.state": {"system": _COUNTERS, "havoc": ("a",), "binding": _STEPS},
    "havoc.multiple-states": {"system": _TRIPLE, "havoc": ("x", "z"), "binding": _STEPS},
    "havoc.init-preserved": {"system": _WITH_INIT, "havoc": ("c",), "binding": _STEPS},
    "havoc.next-less-state": {"system": _NEXTLESS, "havoc": ("f",), "binding": _STEPS},
    "havoc.none": {"system": _COUNTERS, "havoc": (), "binding": _STEPS},
    "passthrough.input": {
        "system": _WITH_INPUT, "havoc": ("t",),
        "binding": {"steps": 4, "inputs": {0: {2: 3}, 1: {2: 7}, 2: {2: 1}, 3: {2: 2}}},
    },
    "passthrough.bad": {"system": _WITH_BAD, "havoc": ("c",), "binding": _STEPS},
    "havoc.array-state": {"system": _ARRAY, "havoc": ("mem",), "binding": _STEPS},
}
