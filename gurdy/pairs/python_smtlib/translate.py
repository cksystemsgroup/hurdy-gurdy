"""Python -> SMT-LIB translator ``T``: a schema-determined lowering of the
straight-line integer subset to ``QF_LIA`` (pairs/python-smtlib brief;
PAIRING.md §2). **Direct to SMT-LIB, not via BTOR2** — Python's unbounded
``int`` maps faithfully to SMT ``Int``, a fit only the direct-to-LIA route
affords (the brief's central design decision).

**Minimal vertical slice (PAIRING.md §1 "start thin").** Exactly one construct
class is translated end-to-end: a straight-line integer function (assignment +
linear arithmetic ``+`` / ``-`` / ``*``-by-constant) terminated by a single
``assert`` comparison. Every other Python construct hard-aborts
``unsupported: python:<construct>`` in the loader (``subset.load``), never a
silent drop (BENCHMARKS.md §3).

The emitted ``QF_LIA`` script is determined **byte-for-byte** by the source
text and this fixed schema (``predicted`` fidelity): SSA renaming in source
order, the per-construct lowering below, nothing adaptive / hashed / timestamped.

Schema
------
*Inputs.* Each parameter ``p`` (declaration order) is one input variable,
declared ``(declare-fun p__in () Int)``. The SSA "current version" of ``p``
starts at ``p__in``.

*SSA.* A counter ``n`` (starting 0) numbers assignment results. The ``i``-th
assignment ``name = e`` (source order) declares a fresh ``(declare-fun
<name>__<n> () Int)``, asserts ``(= <name>__<n> <lower(e)>)`` where ``e`` is
lowered using the *current* SSA version of every read name (so ``x = x + 1``
reads the previous version), then makes ``<name>__<n>`` the current version of
``name`` and increments ``n``.

*Expression lowering* (``lower``): an integer literal ``c`` -> ``c`` (a negative
``c`` -> ``(- |c|)``); a name load -> its current SSA version; unary ``-x`` ->
``(- <x>)``, unary ``+x`` -> ``<x>``; binary ``a+b`` / ``a-b`` / ``a*b`` ->
``(+ <a> <b>)`` / ``(- <a> <b>)`` / ``(* <a> <b>)`` (``*`` has a constant
operand, kept linear by the loader).

*Property.* The trailing ``assert cond`` lowers ``cond`` (one integer
comparison ``l <op> r``) to an SMT-LIB predicate: ``==`` -> ``(= l r)``,
``!=`` -> ``(distinct l r)``, the orderings ``< <= > >=`` straight across. The
script then asserts the **negation** ``(assert (not <cond>))`` (for ``==`` the
negation is the more direct ``(distinct l r)``, but ``(not (= …))`` is emitted
uniformly). The script is ``sat`` iff some input assignment **violates** the
assert — i.e. ``not cond`` is reachable, the property the pair decides.

``(check-sat)`` terminates. A ``sat`` model binds each ``p__in`` to a concrete
violating input; the carry-back ``L`` replays it through CPython.
"""

from __future__ import annotations

import ast
from typing import Any

from ...core.errors import Unsupported
from ...languages.python.subset import _CMP_OPS, Program, load

# Suffixes chosen so they never collide with a legal Python identifier (``__in``
# for an input, ``__<n>`` for an SSA result). Python identifiers can contain
# double underscores, but ``name__in`` / ``name__0`` are emitted only for SSA
# results, and a source name equal to a generated symbol is still distinct
# because the source name is only ever read via its *current SSA version*, never
# emitted raw.
_INPUT_SUFFIX = "__in"


def _lower_int_literal(value: int) -> str:
    """An SMT-LIB ``Int`` numeral. Negatives are written ``(- n)`` (SMT-LIB has
    no negative literal token), matching the evaluator's reader."""
    return str(value) if value >= 0 else f"(- {-value})"


def _lower(expr: ast.expr, current: dict[str, str]) -> str:
    """Lower a validated linear-integer expression to an SMT-LIB term, reading
    each name at its current SSA version (``current``)."""
    if isinstance(expr, ast.Constant):
        return _lower_int_literal(int(expr.value))
    if isinstance(expr, ast.Name):
        return current[expr.id]
    if isinstance(expr, ast.UnaryOp):
        inner = _lower(expr.operand, current)
        return inner if isinstance(expr.op, ast.UAdd) else f"(- {inner})"
    if isinstance(expr, ast.BinOp):
        a = _lower(expr.left, current)
        b = _lower(expr.right, current)
        head = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}[type(expr.op)]
        return f"({head} {a} {b})"
    raise AssertionError(f"loader admitted an out-of-subset expr: {ast.dump(expr)}")


def _lower_cond(test: ast.Compare, current: dict[str, str]) -> str:
    """Lower the assert's single integer comparison to an SMT-LIB predicate."""
    _py, smt_head = _CMP_OPS[type(test.ops[0])]
    left = _lower(test.left, current)
    right = _lower(test.comparators[0], current)
    return f"({smt_head} {left} {right})"


def translate(program: dict[str, Any] | str | bytes) -> bytes:
    """Lower a Python-subset reachability question to ``QF_LIA``.

    Accepts either the raw program (str / bytes / ``Program``) or a dict with a
    ``"python"`` key (the path-runner / ``compose_input`` shape). The decided
    question is fixed by the schema: **can the trailing assert be violated for
    some integer input?** (no extra parameters needed — the assert *is* the
    property).
    """
    src: Any = program["python"] if isinstance(program, dict) else program
    prog: Program = load(src)

    lines = ["(set-logic QF_LIA)"]

    # Inputs: one Int per parameter, declaration order.
    current: dict[str, str] = {}
    for p in prog.params:
        sym = f"{p}{_INPUT_SUFFIX}"
        lines.append(f"(declare-fun {sym} () Int)")
        current[p] = sym

    # SSA assignments + the property, in source order.
    counter = 0
    cond_term: str | None = None
    for stmt in prog.body:
        if isinstance(stmt, ast.Assign):
            name = stmt.targets[0].id
            rhs = _lower(stmt.value, current)
            ssa = f"{name}__{counter}"
            lines.append(f"(declare-fun {ssa} () Int)")
            lines.append(f"(assert (= {ssa} {rhs}))")
            current[name] = ssa
            counter += 1
        elif isinstance(stmt, ast.Assert):
            cond_term = _lower_cond(stmt.test, current)
        # ast.Pass: nothing emitted.

    if cond_term is None:  # the loader guarantees a trailing assert; defensive.
        raise Unsupported("python", "no-assert", "no property to decide")

    # Property: the assert is *violable* iff (not cond) is satisfiable.
    lines.append(f"(assert (not {cond_term}))")
    lines.append("(check-sat)")
    return ("\n".join(lines) + "\n").encode("utf-8")
