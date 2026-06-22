"""Python -> SMT-LIB translator ``T``: a schema-determined lowering of the
straight-line integer subset to ``QF_LIA`` (pairs/python-smtlib brief;
PAIRING.md §2). **Direct to SMT-LIB, not via BTOR2** — Python's unbounded
``int`` maps faithfully to SMT ``Int``, a fit only the direct-to-LIA route
affords (the brief's central design decision).

**Vertical slice (PAIRING.md §1 "start thin, then widen").** In scope, widened
construct by construct under the coverage ratchet: a integer function of
assignment + linear arithmetic (``+`` / ``-`` / ``*``-by-constant), ``if`` /
``else`` (slice 2, lowered by the SSA branch merge below), and a **bounded loop**
``for i in range(<const>)`` (slice 3, **fully unrolled** ``<const>`` times over
the advancing SSA — see ``emit_for`` below), terminated by a single ``assert``
comparison. Every other Python construct hard-aborts
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

*SSA.* A counter ``n`` (starting 0) numbers assignment **and branch-join**
results. The ``i``-th assignment ``name = e`` (source order) declares a fresh
``(declare-fun <name>__<n> () Int)``, asserts ``(= <name>__<n> <lower(e)>)``
where ``e`` is lowered using the *current* SSA version of every read name (so
``x = x + 1`` reads the previous version), then makes ``<name>__<n>`` the
current version of ``name`` and increments ``n``.

*Branch merge (``if cond: then [else: else]``).* The guard is lowered once to a
predicate ``C`` over the *incoming* SSA versions. Each arm is then lowered
**independently** from a copy of the incoming SSA map (the arm's assignments,
including nested ``if``, do not see the other arm), yielding two post-arm SSA
maps. At the join, for every variable ``v`` readable after the ``if`` (assigned
on both arms, or already in scope) whose then- and else-versions differ, a fresh
join variable ``<v>__<n>`` is declared and constrained
``(= <v>__<n> (ite C <then_v> <else_v>))`` — where a side that did not reassign
``v`` contributes its *incoming* version (so an arm-skipped variable keeps its
old value). ``<v>__<n>`` becomes ``v``'s current version. Variables touched
identically in both arms (or in neither) keep their shared version with no
emission. The join variables are processed in a deterministic order (program
declaration / first-assignment order) so the counter — and the bytes — are
reproducible. A bare ``if`` with no ``else`` is the empty-else case: the
else-version of every variable is its incoming version.

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
from ...languages.python.subset import _CMP_OPS, Program, load, range_bound

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
    """Lower a single integer comparison (an ``assert`` property or an ``if``
    guard) to an SMT-LIB predicate."""
    _py, smt_head = _CMP_OPS[type(test.ops[0])]
    left = _lower(test.left, current)
    right = _lower(test.comparators[0], current)
    return f"({smt_head} {left} {right})"


class _Emitter:
    """Carries the mutable SSA state while lowering a statement list in source
    order: the emitted ``lines``, the ``current`` SSA version per live name, an
    ``order`` list of names in declaration / first-assignment order (the
    deterministic key for branch-join emission), and the shared SSA ``counter``.
    A single object threads through nested ``if`` arms so the counter is global
    and the bytes are reproducible."""

    def __init__(self, lines: list[str], current: dict[str, str], order: list[str]) -> None:
        self.lines = lines
        self.current = current
        self.order = order
        self.counter = 0

    def _fresh(self, name: str, term: str) -> str:
        """Declare a fresh SSA variable ``<name>__<n>`` constrained ``= term``,
        bump the counter, and record first-seen order."""
        ssa = f"{name}__{self.counter}"
        self.lines.append(f"(declare-fun {ssa} () Int)")
        self.lines.append(f"(assert (= {ssa} {term}))")
        self.counter += 1
        if name not in self.order:
            self.order.append(name)
        return ssa

    def emit_body(self, body: list[ast.stmt]) -> None:
        """Lower a statement list (function body, an ``if`` arm, or a ``for``
        body), updating ``current`` in place. The trailing ``assert`` is handled
        by the caller."""
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                name = stmt.targets[0].id
                rhs = _lower(stmt.value, self.current)
                self.current[name] = self._fresh(name, rhs)
            elif isinstance(stmt, ast.If):
                self.emit_if(stmt)
            elif isinstance(stmt, ast.For):
                self.emit_for(stmt)
            # ast.Pass / trailing assert: nothing here.

    def emit_for(self, stmt: ast.For) -> None:
        """Lower ``for i in range(n): <body>`` by **full unrolling** (BMC with a
        compile-time-constant bound, SPEC.md §"Bounded loop"): the body is lowered
        ``n`` times over the **advancing** SSA map, with the loop variable ``i``
        bound to the concrete iteration index ``0, 1, …, n-1`` (a literal numeral)
        on each pass. Because the trip count is a constant, there is no
        per-iteration path condition — every iteration is unconditional, so no
        ``ite`` join is needed (unlike ``if``). After the loop the loop variable
        ``i`` and any name first assigned in the body are removed from ``current``:
        they are not readable after the loop (``n`` may be 0), exactly the loader's
        rule. The counter threads through ``self`` so the unrolled body's SSA
        numbering — and the emitted bytes — are reproducible."""
        var = stmt.target.id
        n = range_bound(stmt)  # the single source of truth for the trip count
        before = set(self.current)  # names readable before the loop
        for k in range(n):
            # Bind the loop variable to this iteration's index. k >= 0, so the
            # numeral is plain (never the (- m) negative form).
            self.current[var] = str(k)
            self.emit_body(stmt.body)
        # Drop the loop variable and any body-only-new name: not readable after
        # the loop (the loader rejects reading them later), so they never feed a
        # later lowering. Keep only names that were in scope before the loop
        # (their current SSA version is the last iteration's — the accumulator).
        for name in list(self.current):
            if name == var or name not in before:
                del self.current[name]

    def emit_if(self, stmt: ast.If) -> None:
        """Lower ``if cond: then [else: else]`` by the SSA branch merge: the
        guard once, each arm from a copy of the incoming SSA map, then an ``ite``
        join for every variable whose then/else versions differ."""
        cond = _lower_cond(stmt.test, self.current)
        incoming = dict(self.current)

        then_emit = _Emitter(self.lines, dict(incoming), self.order)
        then_emit.counter = self.counter
        then_emit.emit_body(stmt.body)
        then_current = then_emit.current
        self.counter = then_emit.counter

        else_emit = _Emitter(self.lines, dict(incoming), self.order)
        else_emit.counter = self.counter
        else_emit.emit_body(stmt.orelse)
        else_current = else_emit.current
        self.counter = else_emit.counter

        # Merge in deterministic order: every name now live on either arm, keyed
        # by declaration / first-assignment order. A name keeps its incoming
        # version on a side that did not reassign it (arm-skipped ⇒ old value).
        for name in self.order:
            then_v = then_current.get(name, incoming.get(name))
            else_v = else_current.get(name, incoming.get(name))
            if then_v is None or else_v is None:
                # Assigned on only one arm and not in scope before — not readable
                # after the join (the loader excludes it), so no merge needed.
                continue
            if then_v == else_v:
                self.current[name] = then_v  # touched identically / not at all
            else:
                self.current[name] = self._fresh(name, f"(ite {cond} {then_v} {else_v})")


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
    order: list[str] = list(prog.params)
    for p in prog.params:
        sym = f"{p}{_INPUT_SUFFIX}"
        lines.append(f"(declare-fun {sym} () Int)")
        current[p] = sym

    # SSA over the body (assignments + ``if`` branch merges), in source order.
    # The trailing assert is the property; everything before it is lowered by the
    # emitter, then the assert's condition is lowered against the joined SSA map.
    emitter = _Emitter(lines, current, order)
    emitter.emit_body(list(prog.body[:-1]))
    trailing = prog.body[-1]
    if not isinstance(trailing, ast.Assert):  # loader guarantees this; defensive.
        raise Unsupported("python", "no-assert", "no property to decide")
    cond_term = _lower_cond(trailing.test, current)

    # Property: the assert is *violable* iff (not cond) is satisfiable.
    lines.append(f"(assert (not {cond_term}))")
    lines.append("(check-sat)")
    return ("\n".join(lines) + "\n").encode("utf-8")
