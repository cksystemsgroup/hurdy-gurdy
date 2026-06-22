"""Construct-coverage inventory for python-smtlib (BENCHMARKS.md §2, §5).

The denominator is the Python-language construct set the brief fixes (the
inventory the agent does **not** choose — languages/python brief). A construct is
*covered* iff a minimal program exercising it translates to ``QF_LIA`` without an
``Unsupported`` abort.

This is the widening vertical slice (PAIRING.md §1 "start thin, then widen").
Covered end-to-end: a straight-line integer function (assignment + linear
arithmetic + trailing ``assert``) **and** ``if`` / ``else`` (slice 2, lowered by
the SSA branch merge — SPEC.md). Every other Python construct hard-aborts
``unsupported: python:<construct>`` and is itemized in the histogram. The honest
result is ``partial`` (k/N), not a false ``built``; the coverage ratchet
(BENCHMARKS.md §5) only grows it.

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
    # OUT OF SCOPE — each hard-aborts a distinct typed unsupported construct.
    "while-loop": _probe("while x > 0:", "    x = x - 1", "assert x == 0"),
    "for-loop": _probe("for i in range(x):", "    pass", "assert x == x"),
    "floordiv": _probe("y = x // 2", "assert y == y"),       # floored division
    "modulo": _probe("y = x % 3", "assert y == y"),          # floored remainder
    "truediv": _probe("y = x / 2", "assert y == y"),         # float result
    "power": _probe("y = x ** 2", "assert y == y"),          # non-linear
    "nonlinear-mul": _probe("y = x * x", "assert y == y"),   # var * var
    "boolop": _probe("assert x > 0 and x < 10"),             # boolean operator
    "call": _probe("y = abs(x)", "assert y == y"),           # function call
    "list-literal": _probe("y = [x]", "assert x == x"),      # container
    "return-value": _probe("return x", "assert x == x"),     # value return
    "import": "import os\ndef f(x):\n    assert x == x\n",    # module-level import
    "no-assert": _probe("y = x + 1"),                        # missing property
}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
