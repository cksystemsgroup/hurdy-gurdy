"""Construct-coverage inventory for python-smtlib (BENCHMARKS.md §2, §5).

The denominator is the Python-language construct set the brief fixes (the
inventory the agent does **not** choose — languages/python brief). A construct is
*covered* iff a minimal program exercising it translates to ``QF_LIA`` without an
``Unsupported`` abort.

This is the widening vertical slice (PAIRING.md §1 "start thin, then widen").
Covered end-to-end: a straight-line integer function (assignment + linear
arithmetic + trailing ``assert``), ``if`` / ``else`` (slice 2, lowered by the SSA
branch merge — SPEC.md), a **bounded loop** ``for i in range(<const>)`` (slice 3,
fully unrolled by ``T`` — SPEC.md §"Bounded loop"), a **BMC-bounded loop**
``while <cond>: <body>`` (slice 4, unrolled to the fixed bound ``K`` with a
terminated-within-``K`` assertion — SPEC.md §"BMC-bounded loop"), **nested
loops** (slice 5, a loop inside another loop's body / inside an ``if`` arm inside a
loop, the inner loop re-unrolled at each outer iteration within the
``MAX_LOOP_DEPTH`` / ``MAX_UNROLL_PRODUCT`` caps — SPEC.md §"Nested loops"), **and
fixed-length integer lists** (slice 6, a list of static length ``L`` modeled as a
tuple of ``L`` ``Int`` SSA vars — staying in ``QF_LIA``, no ``Array`` sort: list
literal, constant / dynamic index read & write, ``len(xs)`` — SPEC.md §"Integer
lists"). Every other Python construct hard-aborts ``unsupported: python:<construct>``
and is itemized in the histogram — including the loop *boundary* cases the slices
deliberately keep out (a loop nested past the depth/size cap aborts
``nesting-too-deep``, a non-constant / unbounded range, a loop ``break`` /
``continue``) and the list *boundary* (an over-cap or nested list, a length-changing
``append``). The honest result is ``partial`` (k/N), not a false ``built``; the
coverage ratchet (BENCHMARKS.md §5) only grows it.

Note (the div/mod wrinkle — SPEC.md): ``//`` and ``%`` are deliberately *out of
scope* in this slice. SMT-LIB ``div``/``mod`` are Euclidean while Python
``//``/``%`` are floored; they differ for negative operands, so widening to them
requires the explicit floor↔Euclidean correction. The probe ``floordiv`` records
the gap honestly rather than papering over it.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from .translate import translate


def _probe(*body: str, params: str = "x") -> str:
    """A minimal one-function program with the given body lines and a trailing
    assert (added if the body does not already end in one)."""
    indented = "\n".join("    " + line for line in body)
    return f"def f({params}):\n{indented}\n"


ALL_PROBES: dict[str, str] = {
    # IN SCOPE — covered constructs.
    # (1) a straight-line integer function: assignment + linear arithmetic + a
    #     trailing assert.
    "straightline-int": _probe("y = 2 * x + 1", "z = y - x", "assert z == x + 1"),
    # (2) if/else, lowered by the SSA branch merge (slice 2). A variable assigned
    #     on both arms is joined by an ite at the join; the trailing assert reads
    #     the merged value.
    "if-else": _probe(
        "if x > 0:", "    y = 1", "else:", "    y = -1", "assert y == y",
    ),
    # (3) bare if (no else) — the empty-else case of the same merge: the
    #     else-version of a touched variable is its incoming value.
    "bare-if": _probe("y = 0", "if x > 0:", "    y = x", "assert y == y"),
    # (4) a bounded loop: for i in range(<const>), fully unrolled (slice 3). The
    #     accumulator s is initialised before the loop (readable after); the loop
    #     variable i is the iteration index, read in the body only.
    "for-loop": _probe(
        "s = x", "for i in range(3):", "    s = s + i", "assert s == x + 3",
    ),
    # (5) a BMC-bounded loop: while <cond>: <body>, unrolled to the fixed bound K
    #     with a terminated-within-K assertion (slice 4). The countdown terminates
    #     within K for the inputs the solver considers; the property is decided over
    #     terminating-within-K runs.
    "while-loop": _probe("while x > 0:", "    x = x - 1", "assert x == 0"),
    # (6) a NESTED loop: a bounded for inside another bounded for (slice 5). The
    #     inner loop is re-unrolled at each outer iteration over the advancing SSA
    #     (2 x 2 = 4 body copies); within the MAX_LOOP_DEPTH / MAX_UNROLL_PRODUCT
    #     caps, so it lowers without an Unsupported abort.
    "nested-loop": _probe(
        "for i in range(2):", "    for j in range(2):", "        x = x + 1",
        "assert x == x",
    ),
    # (7) a fixed-length integer LIST literal (slice 6) — modeled as a tuple of
    #     Ints (L separate Int SSA vars), staying in QF_LIA (no Array sort).
    "list-literal": _probe("xs = [x, x + 1, 2]", "assert xs[0] == x"),
    # (8) a constant-index element READ xs[k] — reads element k of the tuple.
    "list-index-read": _probe("xs = [x, x + 1]", "y = xs[1]", "assert y == x + 1"),
    # (9) a constant-index element WRITE xs[k] = v — SSA-updates that position.
    "list-index-write": _probe("xs = [0, 0, 0]", "xs[1] = x", "assert xs[1] == x"),
    # (10) a DYNAMIC index (read + write) over an in-scope int — an ite chain over
    #      the L positions, with 0 <= i < L asserted (an out-of-range index excluded).
    "list-dynamic-index": _probe(
        "xs = [10, 20, 30]", "j = xs[i]", "xs[i] = j", "assert xs[i] == j",
        params="x, i",
    ),
    # (11) len(xs) -> the constant L (the static list length).
    "list-len": _probe("xs = [x, x, x]", "n = len(xs)", "assert n == 3"),
    # OUT OF SCOPE — each hard-aborts a distinct typed unsupported construct.
    # The loop boundary, kept out of scope and itemized honestly: a loop nested
    # deeper than MAX_LOOP_DEPTH (a loop inside a loop inside a loop) exceeds the
    # nesting cap (aborts nesting-too-deep), a non-constant range has no
    # statically-known trip count at all (nonconst-range), and break/continue
    # (non-structured control flow) is out of the unrolling (aborts as Break).
    "nesting-too-deep": _probe(
        "for i in range(2):", "    for j in range(2):", "        for k in range(2):",
        "            x = x + 1", "assert x == x",
    ),
    "nonconst-range": _probe("for i in range(x):", "    pass", "assert x == x"),
    "loop-break": _probe(
        "while x > 0:", "    break", "assert x == x",
    ),  # break/continue — non-structured control flow, out of the unrolling
    "floordiv": _probe("y = x // 2", "assert y == y"),       # floored division
    "modulo": _probe("y = x % 3", "assert y == y"),          # floored remainder
    "truediv": _probe("y = x / 2", "assert y == y"),         # float result
    "power": _probe("y = x ** 2", "assert y == y"),          # non-linear
    "nonlinear-mul": _probe("y = x * x", "assert y == y"),   # var * var
    "boolop": _probe("assert x > 0 and x < 10"),             # boolean operator
    "call": _probe("y = abs(x)", "assert y == y"),           # function call (non-len)
    # The list BOUNDARY, kept out of scope and itemized honestly (slice 6): a list
    # longer than MAX_LIST_LEN (bounds SMT size), a nested list (no flat tuple of
    # Ints), and a length-changing op append (the length must be static).
    "list-too-long": _probe(
        "xs = [" + ", ".join(["0"] * 17) + "]", "assert x == x",
    ),  # 17 > MAX_LIST_LEN = 16
    "nested-list": _probe("xs = [[1], [2]]", "assert x == x"),    # list of lists
    "list-append": _probe("xs = [x]", "xs.append(1)", "assert x == x"),  # length change
    "return-value": _probe("return x", "assert x == x"),     # value return
    "import": "import os\ndef f(x):\n    assert x == x\n",    # module-level import
    "no-assert": _probe("y = x + 1"),                        # missing property
}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
