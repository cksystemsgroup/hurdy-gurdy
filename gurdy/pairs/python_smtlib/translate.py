"""Python -> SMT-LIB translator ``T``: a schema-determined lowering of the
straight-line integer subset to ``QF_LIA`` (pairs/python-smtlib brief;
PAIRING.md §2). **Direct to SMT-LIB, not via BTOR2** — Python's unbounded
``int`` maps faithfully to SMT ``Int``, a fit only the direct-to-LIA route
affords (the brief's central design decision).

**Vertical slice (PAIRING.md §1 "start thin, then widen").** In scope, widened
construct by construct under the coverage ratchet: a integer function of
assignment + linear arithmetic (``+`` / ``-`` / ``*``-by-constant), ``if`` /
``else`` (slice 2, lowered by the SSA branch merge below), a **bounded loop**
``for i in range(<const>)`` (slice 3, **fully unrolled** ``<const>`` times over
the advancing SSA — see ``emit_for`` below), a **BMC-bounded loop**
``while <cond>: <body>`` (slice 4, **unrolled to the fixed bound ``K`` =
``WHILE_BOUND``** with per-iteration ``ite`` carry-through plus a
terminated-within-``K`` assertion — see ``emit_while`` below), nested loops
(slice 5), and **fixed-length integer lists** (slice 6, a list of static length
``L`` modeled as a **tuple of ``L`` ``Int`` SSA vars** — *not* an SMT ``Array``,
so the encoding stays in ``QF_LIA``: list literal, constant / dynamic index read &
write (a dynamic index lowers to an ``ite`` chain with a ``0 <= i < L`` range
constraint), and ``len(xs)`` — see ``emit_assign`` / ``_read_index`` below),
terminated by a single ``assert`` comparison. Every other Python construct
hard-aborts ``unsupported: python:<construct>`` in the loader (``subset.load``),
never a silent drop (BENCHMARKS.md §3).

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
from ...languages.python.subset import WHILE_BOUND, _CMP_OPS, Program, load, range_bound

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


def _is_const_index(idx: ast.expr) -> bool:
    """Is a subscript index a literal integer (possibly under a unary sign)? — the
    loader has already validated and bounds-checked it (slice 6)."""
    if isinstance(idx, ast.UnaryOp) and isinstance(idx.op, (ast.UAdd, ast.USub)):
        return _is_const_index(idx.operand)
    return isinstance(idx, ast.Constant) and isinstance(idx.value, int) and not isinstance(idx.value, bool)


def _const_index_value(idx: ast.expr) -> int:
    """The integer value of a constant subscript index (caller proved it const)."""
    if isinstance(idx, ast.UnaryOp):
        v = _const_index_value(idx.operand)
        return -v if isinstance(idx.op, ast.USub) else +v
    return int(idx.value)


def _ite_chain(iterm: str, elems: list[str]) -> str:
    """The right-folded ``ite`` chain selecting ``elems[i]`` for a dynamic index
    ``iterm`` (slice 6): ``(ite (= i 0) e0 (ite (= i 1) e1 … e{L-1}))``. The last
    position is the catch-all ``else`` (the caller asserts ``0 <= i < L``, so the
    index is guaranteed to hit one of the ``L`` positions). For ``L == 1`` the chain
    is just ``e0``."""
    term = elems[-1]
    for k in range(len(elems) - 2, -1, -1):
        term = f"(ite (= {iterm} {k}) {elems[k]} {term})"
    return term


class _Emitter:
    """Carries the mutable SSA state while lowering a statement list in source
    order: the emitted ``lines``, the ``current`` SSA version per live **scalar**
    name, the ``lists`` map (a list name -> the list of its ``L`` element terms — a
    *tuple of Ints*, slice 6), an ``order`` list of names in declaration /
    first-assignment order (the deterministic key for branch-join emission), and the
    shared SSA ``counter``. A single object threads through nested ``if`` arms so the
    counter is global and the bytes are reproducible."""

    def __init__(
        self, lines: list[str], current: dict[str, str], order: list[str],
        lists: dict[str, list[str]] | None = None,
    ) -> None:
        self.lines = lines
        self.current = current
        self.order = order
        # slice 6: a list-typed name maps to the list of its element SSA terms
        # (length L). A name is either a scalar (in ``current``) or a list (in
        # ``lists``), never both — the loader enforces the static typing.
        self.lists: dict[str, list[str]] = lists if lists is not None else {}
        self.counter = 0

    # --- expression lowering (slice 6: list element reads emit range constraints) -

    def _lower(self, expr: ast.expr) -> str:
        """Lower a validated linear-integer expression to an SMT-LIB term, reading
        each scalar name at its current SSA version. A list **element read**
        ``xs[i]`` (slice 6) lowers to the element term directly for a constant index,
        or to an ``ite`` chain over the ``L`` positions for a dynamic index (with the
        index's ``0 <= i < L`` range asserted as a side constraint — see
        ``_read_index``). ``len(xs)`` lowers to the constant ``L``."""
        if isinstance(expr, ast.Constant):
            return _lower_int_literal(int(expr.value))
        if isinstance(expr, ast.Name):
            return self.current[expr.id]
        if isinstance(expr, ast.Subscript):
            return self._read_index(expr)
        if isinstance(expr, ast.Call):  # the only in-scope call is len(xs)
            arg = expr.args[0]
            return str(len(self.lists[arg.id]))  # the static list length L
        if isinstance(expr, ast.UnaryOp):
            inner = self._lower(expr.operand)
            return inner if isinstance(expr.op, ast.UAdd) else f"(- {inner})"
        if isinstance(expr, ast.BinOp):
            a = self._lower(expr.left)
            b = self._lower(expr.right)
            head = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}[type(expr.op)]
            return f"({head} {a} {b})"
        raise AssertionError(f"loader admitted an out-of-subset expr: {ast.dump(expr)}")

    def _read_index(self, sub: ast.Subscript) -> str:
        """Lower an element read ``xs[i]`` (slice 6). For a **constant** index the
        element term is read straight from the tuple of Ints (no new symbol, no
        constraint — the loader already bounds-checked the literal). For a **dynamic**
        index ``i`` (an in-scope scalar int), assert ``0 <= i < L`` as a side
        constraint and return the right-fold ``ite`` chain
        ``(ite (= i 0) e0 (ite (= i 1) e1 … e{L-1}))`` over the ``L`` positions — the
        range constraint makes the final ``else`` (position ``L-1``) the catch-all,
        so an out-of-range index is **excluded** by the solver (a defined
        under-approximation, never a silent wrong read)."""
        name = sub.value.id
        elems = self.lists[name]
        idx = sub.slice
        if _is_const_index(idx):
            return elems[_const_index_value(idx)]
        iterm = self._lower(idx)
        self._assert_in_range(iterm, len(elems))
        return _ite_chain(iterm, elems)

    def _assert_in_range(self, iterm: str, length: int) -> None:
        """Emit the path constraint ``0 <= i < L`` for a dynamic list index ``i``
        (slice 6). Like the ``while`` termination assertion, it **restricts** the
        decided question to runs whose every dynamic index is in range — an
        out-of-range access is excluded (carried back as UNREACHABLE), never a silent
        wrong answer. ``L`` is the static list length (a constant numeral)."""
        self.lines.append(f"(assert (and (<= 0 {iterm}) (< {iterm} {length})))")

    def _lower_cond(self, test: ast.Compare) -> str:
        """Lower a single integer comparison (an ``assert`` property or an ``if`` /
        ``while`` guard) to an SMT-LIB predicate, reading operands via ``_lower`` (so
        a guard may compare ``xs[i]`` / ``len(xs)``, slice 6)."""
        _py, smt_head = _CMP_OPS[type(test.ops[0])]
        left = self._lower(test.left)
        right = self._lower(test.comparators[0])
        return f"({smt_head} {left} {right})"

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

    def _fresh_bool(self, label: str, term: str) -> str:
        """Declare a fresh ``Bool`` SSA symbol ``<label>__<n>`` constrained
        ``= term`` and bump the **shared** counter (so its numbering is globally
        unique against the ``Int`` SSA variables and reproducible). Used for the
        ``while`` per-iteration *active* flag — the conjunction of the loop
        condition holding at every iteration so far. It is never added to
        ``order`` (it is not a program variable, so it never participates in a
        join); the shared counter alone makes the bytes predictable."""
        sym = f"{label}__{self.counter}"
        self.lines.append(f"(declare-fun {sym} () Bool)")
        self.lines.append(f"(assert (= {sym} {term}))")
        self.counter += 1
        return sym

    def emit_body(self, body: list[ast.stmt]) -> None:
        """Lower a statement list (function body, an ``if`` arm, a ``for`` body, or
        a ``while`` body), updating ``current`` / ``lists`` in place. The trailing
        ``assert`` is handled by the caller."""
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                self.emit_assign(stmt)
            elif isinstance(stmt, ast.If):
                self.emit_if(stmt)
            elif isinstance(stmt, ast.For):
                self.emit_for(stmt)
            elif isinstance(stmt, ast.While):
                self.emit_while(stmt)
            # ast.Pass / trailing assert: nothing here.

    def emit_assign(self, stmt: ast.Assign) -> None:
        """Lower one assignment (slice 6 adds the two list-producing shapes):

          * **scalar** ``name = <expr>`` -> a fresh ``name__<n>`` = the lowered
            integer expression; the name becomes a scalar (any prior list binding is
            dropped);
          * **list literal** ``xs = [e0, …, e{L-1}]`` -> ``L`` fresh ``xs__<n>``, one
            per lowered element, recorded as the tuple of Ints ``lists[xs]``;
          * **index write** ``xs[i] = v`` -> an SSA update of the tuple: for a
            constant ``i`` only position ``i`` becomes a fresh ``xs__<n>`` = the
            lowered ``v``; for a dynamic ``i`` (range-asserted ``0 <= i < L``) *every*
            position ``j`` becomes a fresh ``xs__<n>`` = ``(ite (= i j) v old_j)``.
        """
        target = stmt.targets[0]
        if isinstance(target, ast.Name):
            name = target.id
            if isinstance(stmt.value, ast.List):
                # A list literal: L fresh element SSA vars (a tuple of Ints).
                elems = [self._fresh(name, self._lower(e)) for e in stmt.value.elts]
                self.current.pop(name, None)
                self.lists[name] = elems
            else:
                rhs = self._lower(stmt.value)
                self.lists.pop(name, None)  # (re)bound to a scalar int
                self.current[name] = self._fresh(name, rhs)
        else:  # ast.Subscript: an index write xs[i] = v
            name = target.value.id
            elems = self.lists[name]
            vterm = self._lower(stmt.value)
            idx = target.slice
            if _is_const_index(idx):
                k = _const_index_value(idx)
                new = list(elems)
                new[k] = self._fresh(name, vterm)
                self.lists[name] = new
            else:
                iterm = self._lower(idx)
                self._assert_in_range(iterm, len(elems))
                # Each position j becomes ite(i == j, v, old_j) — SSA update of the
                # whole tuple (only the matched position changes value).
                self.lists[name] = [
                    self._fresh(name, f"(ite (= {iterm} {j}) {vterm} {old})")
                    for j, old in enumerate(elems)
                ]

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
        numbering — and the emitted bytes — are reproducible. A **list** in scope
        before the loop (slice 6) is index-written over the advancing tuple of Ints
        exactly as a scalar accumulator advances; a body-only list literal is dropped
        after the loop like any body-only name."""
        var = stmt.target.id
        n = range_bound(stmt)  # the single source of truth for the trip count
        before = set(self.current) | set(self.lists)  # names readable before the loop
        for k in range(n):
            # Bind the loop variable to this iteration's index. k >= 0, so the
            # numeral is plain (never the (- m) negative form).
            self.current[var] = str(k)
            self.emit_body(stmt.body)
        # Drop the loop variable and any body-only-new name (scalar or list): not
        # readable after the loop (the loader rejects reading them later), so they
        # never feed a later lowering. Keep only names that were in scope before the
        # loop (their current SSA version is the last iteration's — the accumulator).
        for name in list(self.current):
            if name == var or name not in before:
                del self.current[name]
        for name in list(self.lists):
            if name == var or name not in before:
                del self.lists[name]

    def emit_while(self, stmt: ast.While) -> None:
        """Lower ``while cond: body`` by **bounded unrolling** (BMC, SPEC.md
        §"BMC-bounded loop"). The bound is the fixed module constant
        ``WHILE_BOUND`` (= ``K``), part of the predictable spec (PAIRING.md §2): not
        a heuristic, not adaptive.

        Unroll ``K`` body copies over the **advancing** SSA map. For iteration ``j``
        (``0 ≤ j < K``), with ``incoming`` the SSA map at its start:

          * lower ``cond`` over ``incoming`` -> a predicate ``cond_j``;
          * declare an *active* flag ``active_j`` = ``cond_0 ∧ … ∧ cond_j`` (the
            loop condition held at every iteration up to and including ``j`` — so
            iteration ``j`` actually runs);
          * lower ``body`` **unconditionally** from a copy of ``incoming`` (advancing
            the shared counter), giving the would-be post-body SSA versions;
          * **join** every live variable ``v`` whose body-version ``b`` differs from
            its carried (incoming) version ``c`` with
            ``(ite active_j b c)`` — when the loop is no longer active the value is
            carried through unchanged (a no-op iteration). A variable the body did
            not reassign keeps its version with no emission (exactly the ``if``
            merge, with ``active_j`` as the guard and the carried value as the
            else-arm).

        After ``K`` iterations, **assert termination within the bound**: the loop
        condition lowered over the post-loop SSA map must be **false**
        ``(assert (not cond_final))``. A run that terminated early carries a false
        ``cond`` through to ``cond_final`` (so the assert holds); a run that would
        need a (K+1)-th iteration has ``cond_final`` still true, so this constraint
        **excludes** it — the property is then decided only over runs that terminate
        within ``K`` (a non-terminating-within-``K`` model is unsatisfiable, carried
        back as UNREACHABLE, never a silent wrong answer). Finally, any name first
        assigned in the body is dropped from ``current`` (not readable after the
        loop — it may run zero times or hit the bound), exactly the ``for`` rule.
        The shared counter threads through every iteration so the unrolled bytes are
        reproducible. A **list** in scope before the loop (slice 6) is joined
        element-wise — each position carried through ``(ite active_j body_elem
        carried_elem)`` — exactly as a scalar accumulator is."""
        before = set(self.current) | set(self.lists)  # names readable before the loop
        prev_active: str | None = None
        for _j in range(WHILE_BOUND):
            incoming = dict(self.current)
            incoming_lists = {k: list(v) for k, v in self.lists.items()}
            cond_j = self._lower_cond(stmt.test)  # over the current (incoming) SSA
            # active_j = cond_0 ∧ … ∧ cond_j (the loop ran every iteration so far).
            if prev_active is None:
                active = self._fresh_bool("while__active", cond_j)
            else:
                active = self._fresh_bool("while__active", f"(and {prev_active} {cond_j})")
            # Lower the body unconditionally over a copy of the incoming SSA map.
            body_emit = _Emitter(self.lines, dict(incoming), self.order,
                                 {k: list(v) for k, v in incoming_lists.items()})
            body_emit.counter = self.counter
            body_emit.emit_body(stmt.body)
            self.counter = body_emit.counter
            body_current = body_emit.current
            body_lists = body_emit.lists
            # Join: value_after_j = ite(active_j, body_value, carried_value), in the
            # deterministic declaration / first-assignment order (the same key as the
            # if-merge). A body-only-new name (not in scope before) is dropped here
            # (carried value is None), matching the loader rejecting a read of it.
            for name in self.order:
                if name in incoming_lists:
                    self._join_list(name, active, body_lists.get(name),
                                    incoming_lists.get(name))
                    continue
                body_v = body_current.get(name, incoming.get(name))
                carry_v = incoming.get(name)
                if body_v is None or carry_v is None:
                    continue
                if body_v == carry_v:
                    self.current[name] = body_v  # untouched by the body
                else:
                    self.current[name] = self._fresh(
                        name, f"(ite {active} {body_v} {carry_v})"
                    )
            prev_active = active
        # Termination within K: the loop condition must now be false. A model that
        # would need a (K+1)-th iteration is excluded.
        cond_final = self._lower_cond(stmt.test)
        self.lines.append(f"(assert (not {cond_final}))")
        # Drop body-only-new names (scalar or list): not readable after the loop.
        for name in list(self.current):
            if name not in before:
                del self.current[name]
        for name in list(self.lists):
            if name not in before:
                del self.lists[name]

    def _join_list(
        self, name: str, guard: str, then_elems: list[str] | None, else_elems: list[str] | None
    ) -> None:
        """Join a list-typed name at an ``if`` / ``while`` merge element-wise (slice
        6): each position ``j`` becomes ``(ite guard then_j else_j)`` when its two
        sides differ, or keeps the shared term when they agree (no emission). The two
        sides have the same length (the loader's ``list-join-mismatch`` /
        ``list-len-changed-in-loop`` checks guarantee it). A side that is ``None`` (the
        list is not live there) means the name is not readable after the merge, so it
        is left untouched."""
        if then_elems is None or else_elems is None:
            return
        joined: list[str] = []
        for t, e in zip(then_elems, else_elems):
            joined.append(t if t == e else self._fresh(name, f"(ite {guard} {t} {e})"))
        self.lists[name] = joined

    def emit_if(self, stmt: ast.If) -> None:
        """Lower ``if cond: then [else: else]`` by the SSA branch merge: the
        guard once, each arm from a copy of the incoming SSA map, then an ``ite``
        join for every variable whose then/else versions differ. A **list** joined at
        the if (slice 6) is merged element-wise (``_join_list``)."""
        cond = self._lower_cond(stmt.test)
        incoming = dict(self.current)
        incoming_lists = {k: list(v) for k, v in self.lists.items()}

        then_emit = _Emitter(self.lines, dict(incoming), self.order,
                             {k: list(v) for k, v in incoming_lists.items()})
        then_emit.counter = self.counter
        then_emit.emit_body(stmt.body)
        then_current = then_emit.current
        then_lists = then_emit.lists
        self.counter = then_emit.counter

        else_emit = _Emitter(self.lines, dict(incoming), self.order,
                             {k: list(v) for k, v in incoming_lists.items()})
        else_emit.counter = self.counter
        else_emit.emit_body(stmt.orelse)
        else_current = else_emit.current
        else_lists = else_emit.lists
        self.counter = else_emit.counter

        # Merge in deterministic order: every name now live on either arm, keyed
        # by declaration / first-assignment order. A name keeps its incoming
        # version on a side that did not reassign it (arm-skipped ⇒ old value).
        for name in self.order:
            if name in incoming_lists or name in then_lists or name in else_lists:
                # A list joined at the if: each arm leaves it a list (the loader's
                # list-join-mismatch check rules out a list-vs-int disagreement on a
                # name readable after the join).
                then_l = then_lists.get(name, incoming_lists.get(name))
                else_l = else_lists.get(name, incoming_lists.get(name))
                self._join_list(name, cond, then_l, else_l)
                continue
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

    # SSA over the body (assignments + ``if`` branch merges + list updates), in
    # source order. The trailing assert is the property; everything before it is
    # lowered by the emitter, then the assert's condition is lowered against the
    # joined SSA map (a dynamic index in the assert emits its range constraint as a
    # side assert *before* the negated property — slice 6).
    emitter = _Emitter(lines, current, order)
    emitter.emit_body(list(prog.body[:-1]))
    trailing = prog.body[-1]
    if not isinstance(trailing, ast.Assert):  # loader guarantees this; defensive.
        raise Unsupported("python", "no-assert", "no property to decide")
    cond_term = emitter._lower_cond(trailing.test)

    # Property: the assert is *violable* iff (not cond) is satisfiable.
    lines.append(f"(assert (not {cond_term}))")
    lines.append("(check-sat)")
    return ("\n".join(lines) + "\n").encode("utf-8")
