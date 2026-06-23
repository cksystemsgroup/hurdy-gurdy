"""The Python-subset **loader** — bytes/str/AST -> a validated in-memory model
(languages/python brief; ARCHITECTURE.md §5).

The source of truth for the subset is **the AST node set the loader accepts**:
walking the parsed program, any node outside the allow-list hard-aborts with a
typed ``unsupported: python:<construct>`` (never a silent drop, BENCHMARKS.md
§3). The accepted program is then an *integer function* (assignment + linear
arithmetic + ``if`` / ``else``, terminated by one assert) the translator and the
CPython executor both consume.

**Vertical slice (PAIRING.md §1 "start thin, then widen").** In scope
end-to-end, widened construct by construct under the coverage ratchet:

  * a single top-level ``def`` whose parameters are all plain (positional)
    integer inputs (no defaults, ``*args``, ``**kwargs``, keyword-only, or
    annotations that aren't ``int``);
  * a body of:
      - integer **assignment** ``name = <expr>`` to a single ``Name`` target;
      - **linear integer arithmetic** in ``<expr>``: integer literals, parameter
        / local ``Name`` loads, unary ``+`` / ``-``, binary ``+`` / ``-``, and
        ``*`` **with at least one constant operand** (so the term stays linear —
        a variable-by-variable product is non-linear and hard-aborts);
      - ``if <cond>: <arm>`` with an optional ``else: <arm>`` (slice 2), where
        ``<cond>`` is one integer comparison and each ``<arm>`` is itself a body
        of in-scope statements (assignments, nested ``if``, a bounded ``for`` —
        but **no** ``assert`` inside an arm: the property stays the single
        trailing assert). A variable that is assigned on *both* arms (or already
        in scope before the ``if``) is readable after the join; a variable first
        assigned on only one arm is **not** in scope after the ``if`` (it may be
        undefined on the other path) and reading it later hard-aborts
        ``undefined-name``;
      - ``for <i> in range(<const>): <body>`` — a **bounded loop** (slice 3),
        where ``<const>`` is a **non-negative integer literal** trip count and
        ``<body>`` is a body of in-scope statements (assignments, nested ``if``,
        and — slice 5 — a **nested ``for`` / ``while``** within the nesting caps —
        but no ``assert``). The loop variable ``i`` is readable **inside** the body
        (it is the iteration index) but **not** after the loop; a body-only-assigned
        name is likewise not readable after (the loop may run zero times), so an
        accumulator read after the loop must be initialised *before* it (the ``if``
        one-arm rule);
      - ``while <cond>: <body>`` — a **BMC-bounded loop** (slice 4), where
        ``<cond>`` is one integer comparison and ``<body>`` is a body of in-scope
        statements (assignments, nested ``if``, and — slice 5 — a **nested ``for`` /
        ``while``** within the nesting caps — but no ``assert``). ``T`` unrolls the
        body to a fixed bound ``K`` (BMC) and asserts termination within ``K``
        (SPEC.md §"BMC-bounded loop"). As with ``for``, no body-assigned name is
        readable after the loop (it may run zero times, or not terminate within
        ``K``), so an accumulator must be initialised *before* it;
      - a single trailing ``assert <cond>`` whose ``<cond>`` is one integer
        comparison ``<linear> <op> <linear>`` with ``op`` in
        ``== != < <= > >=``.

**Nested loops (slice 5).** A ``for`` / ``while`` may now appear inside another
loop's body (and inside an ``if`` arm inside a loop): the inner loop is unrolled
at *each* outer iteration, the sizes multiplying. Two fixed caps bound the
unrolled SMT size (``MAX_LOOP_DEPTH`` / ``MAX_UNROLL_PRODUCT`` above): a loop
nested deeper than ``MAX_LOOP_DEPTH``, or whose running product of unroll bounds
would exceed ``MAX_UNROLL_PRODUCT``, hard-aborts ``python:nesting-too-deep`` at
load time (never an enormous emitted script).

**Fixed-length integer lists (slice 6).** A Python list of statically-known length
``L`` is admitted as a **tuple of ``L`` ``Int`` values** (``T`` models it as ``L``
separate ``Int`` SSA variables — *not* an SMT ``Array``, so the encoding stays in
``QF_LIA``). In scope: a **list literal** ``xs = [e0, …, e{L-1}]`` (each element an
in-scope int expression; ``L`` bounded by ``MAX_LIST_LEN`` above), a constant /
dynamic-index element **read** ``xs[i]`` and **write** ``xs[i] = v``, and
``len(xs)`` -> the constant ``L``. A constant index is bounds-checked at load time
(an out-of-range literal aborts ``list-index-out-of-range``); a dynamic (in-scope
int) index is range-asserted ``0 <= i < L`` in the SMT by ``T``. A list in scope
before a loop may be index-written in the body (it persists) but must keep its
static length; an ``if`` joining a list requires both arms to leave it the same
length. Out of scope (hard-abort): ``append`` / ``pop`` / ``insert`` (length
change), a non-constant-length / nested list, slicing, a list of non-int, a list
used as an int, ``dict`` / ``set`` / ``str``, list comprehensions, and iterating a
list with ``for x in xs`` (only ``for i in range(...)`` stays in scope).

Everything else hard-aborts ``unsupported: python:<construct>``: a loop nested
beyond the caps (``nesting-too-deep``), a non-constant / non-``range`` ``for``,
``//`` / ``%`` (floored division — see the div/mod note in ``SPEC.md``), ``/``
(float), ``**`` (non-linear), boolean / bitwise operators, function calls (other
than the loop's ``range`` header and ``len(xs)``), ``return`` with a value,
``break`` / ``continue``, ``dict`` / ``set`` / ``str`` literals / a nested or
over-cap list, attribute access, slicing, ``import``, ``lambda``, comprehensions,
multiple / tuple assignment targets, augmented assignment, and any second
``assert``.

The model is **deterministic**: parameters in declaration order, statements in
source order; nothing hashed, ordered by dict iteration, or timestamped.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ...core.errors import Unsupported

# The fixed BMC unrolling bound ``K`` for a ``while`` loop (slice 4), the single
# source of truth for both the executor (which caps its replay at ``K`` body
# iterations so an unbounded loop can never hang ``I_s``) and the translator
# (which unrolls the body ``K`` times and asserts termination within ``K``). It is
# part of the *predictable* spec (PAIRING.md §2): the bound is this fixed module
# constant — not a heuristic, not adaptive. Kept small (≤ 8) to bound SMT size
# (BENCHMARKS.md §6, the unrolling-bound cap). Shared exactly as ``range_bound`` is
# shared, so the two sides unroll the same depth.
WHILE_BOUND = 8

# The **nested-loop caps** (slice 5 — loops may nest). Both are fixed module
# constants (the predictability test, PAIRING.md §2) and bound the unrolled SMT
# size (BENCHMARKS.md §6, the unrolling-bound cap) when loops compose
# multiplicatively (the inner loop is re-unrolled at *every* outer iteration).
#
#  * ``MAX_LOOP_DEPTH`` — the maximum loop **nesting depth**: a loop at depth 1 is
#    outermost, a loop inside it is depth 2. A loop reached at depth > this cap
#    (a loop inside a loop inside a loop) hard-aborts ``nesting-too-deep``.
#  * ``MAX_UNROLL_PRODUCT`` — the maximum **product of unroll bounds** along a
#    nesting path (a ``for i in range(n)`` contributes its constant trip count
#    ``n``; a ``while`` contributes ``WHILE_BOUND``). The running product is the
#    number of times the innermost body is unrolled; if entering a loop would push
#    it over this cap, the loop hard-aborts ``nesting-too-deep`` rather than emit an
#    enormous script. The cap ``WHILE_BOUND * WHILE_BOUND`` is the natural ceiling
#    of a ``while`` inside a ``while`` (8 × 8 = 64).
#
# Shared by the loader (the static boundary check + the typed abort) and the
# translator (which re-derives the same product as it recurses), so the bound is
# predictable from the source and this spec.
MAX_LOOP_DEPTH = 2
MAX_UNROLL_PRODUCT = WHILE_BOUND * WHILE_BOUND  # 64

# The **fixed-length integer list cap** (slice 6 — lists). A Python list of
# statically-known length ``L`` is modeled as ``L`` separate ``Int`` SSA variables
# (a *tuple of Ints*), **not** an SMT ``Array`` — so the encoding stays in the
# existing ``QF_LIA`` fragment (Int + linear arith + ``ite``, no ``Array`` sort).
# A dynamic-index read / write fans out into an ``ite`` chain over the ``L``
# positions, so the emitted SMT grows linearly with ``L``; this fixed module
# constant (the predictability test, PAIRING.md §2) caps the per-list element count
# to bound SMT size (BENCHMARKS.md §6). A list literal whose length exceeds the cap
# hard-aborts ``python:list-too-long`` at load time — never an enormous emitted
# script. Shared by the loader (the boundary check) and the translator (which
# re-derives each list's length as it lowers), so the bound is predictable from the
# source and this spec.
MAX_LIST_LEN = 16

# Comparison AST node -> the (Python operator string, SMT-LIB head). ``==`` /
# ``!=`` lower through ``=`` / ``distinct``; the orderings map straight across.
_CMP_OPS: dict[type, tuple[str, str]] = {
    ast.Eq: ("==", "="),
    ast.NotEq: ("!=", "distinct"),
    ast.Lt: ("<", "<"),
    ast.LtE: ("<=", "<="),
    ast.Gt: (">", ">"),
    ast.GtE: (">=", ">="),
}


def _unsupported(node: ast.AST, detail: str = "") -> Unsupported:
    """A typed abort naming the offending AST node class (the histogram key)."""
    return Unsupported("python", type(node).__name__, detail)


@dataclass(frozen=True)
class Program:
    """A validated integer function (assignment + linear arithmetic + ``if`` /
    ``else``, terminated by one trailing assert).

    ``name`` — the function name; ``params`` — its integer parameters in
    declaration order; ``body`` — the original ``ast.FunctionDef`` body
    (statements in source order, ``if`` nodes carrying their arms); ``source`` —
    the exact source text (the
    executor re-runs this byte-for-byte, so the CPython oracle sees the program
    the player wrote, not a re-serialization).
    """

    name: str
    params: tuple[str, ...]
    body: tuple[ast.stmt, ...]
    source: str


def _is_int_const(expr: ast.expr) -> bool:
    """Is ``expr`` a literal integer constant, possibly under a unary +/-?
    (Used only for the linearity guard; ``True``/``False`` are excluded.)"""
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, (ast.UAdd, ast.USub)):
        return _is_int_const(expr.operand)
    return (
        isinstance(expr, ast.Constant)
        and isinstance(expr.value, int)
        and not isinstance(expr.value, bool)
    )


def _check_index(idx: ast.expr, known: set[str], lists: dict[str, int]) -> None:
    """Validate a list **index** expression (the ``i`` of ``xs[i]``): it must be a
    plain integer expression — an integer literal (possibly negative under a unary
    sign) or an in-scope **scalar** int (linear arithmetic over names). The index
    is never itself a list; a list-typed name used as an index aborts ``list-as-int``
    via ``_check_linear``. A *constant* index is additionally bounds-checked by the
    caller against the list length (so an out-of-range literal aborts at load time);
    a non-constant index is range-asserted in the SMT by ``T`` (slice 6 — see
    ``SPEC.md`` §"Integer lists")."""
    _check_linear(idx, known, lists)


def _check_linear(expr: ast.expr, known: set[str], lists: dict[str, int]) -> None:
    """Validate an integer **linear** arithmetic expression. Hard-aborts any
    out-of-subset node. ``known`` is the set of names readable here (parameters
    plus already-assigned locals); a load of an unknown name aborts as
    ``python:undefined-name`` rather than deferring to a CPython ``NameError``.
    ``lists`` maps a list-typed name to its (static) length; a bare list name read
    as an integer aborts ``python:list-as-int`` (a whole list is not an int term),
    while ``xs[i]`` (an ``ast.Subscript`` index read) *is* an integer term and is
    validated here (slice 6 — integer lists)."""
    if isinstance(expr, ast.Constant):
        if isinstance(expr.value, bool) or not isinstance(expr.value, int):
            # ``bool`` is an ``int`` subclass in Python; exclude it (and floats,
            # strings, ``None``) — the slice is integers only.
            raise _unsupported(expr, f"non-int constant {expr.value!r}")
        return
    if isinstance(expr, ast.Name):
        if not isinstance(expr.ctx, ast.Load):
            raise _unsupported(expr, "name used in non-load context")
        if expr.id not in known:
            raise Unsupported("python", "undefined-name", f"read of unassigned {expr.id!r}")
        if expr.id in lists:
            # A whole list used where an int is expected (e.g. ``y = xs`` /
            # ``xs + 1``). The slice has no list-valued int expression — only
            # ``xs[i]`` reads an element. (List-to-list copy / aliasing is out of
            # scope; only a list literal or an index write produces a list.)
            raise Unsupported("python", "list-as-int",
                              f"list {expr.id!r} used where an integer is expected")
        return
    if isinstance(expr, ast.Subscript):
        # An element read ``xs[i]`` — an integer term (slice 6 — integer lists).
        if not (isinstance(expr.value, ast.Name) and isinstance(expr.value.ctx, ast.Load)):
            # Subscripting anything but a plain list name (a slice target, a nested
            # subscript ``xs[i][j]``, a call result) is out of scope.
            raise _unsupported(expr.value, "only a plain list name may be subscripted")
        name = expr.value.id
        if name not in known:
            raise Unsupported("python", "undefined-name", f"read of unassigned {name!r}")
        if name not in lists:
            # Subscripting an int scalar (``a[i]`` where ``a`` is an int) is out of
            # scope — only a list is indexable.
            raise Unsupported("python", "index-non-list",
                              f"{name!r} is an int, not an indexable list")
        if isinstance(expr.slice, ast.Slice):
            raise Unsupported("python", "list-slice", "list slicing is out of scope")
        idx = expr.slice
        _check_index(idx, known, lists)
        if _is_int_const(idx):
            # A constant index is bounds-checked statically (an out-of-range literal
            # is a definite error, not a solver-excluded path).
            k = _eval_const_int(idx)
            length = lists[name]
            if not (0 <= k < length):
                raise Unsupported("python", "list-index-out-of-range",
                                  f"constant index {k} out of range for len {length}")
        return
    if isinstance(expr, ast.UnaryOp):
        if not isinstance(expr.op, (ast.UAdd, ast.USub)):
            raise _unsupported(expr.op, "only unary +/- are in scope")
        _check_linear(expr.operand, known, lists)
        return
    if isinstance(expr, ast.BinOp):
        if isinstance(expr.op, (ast.Add, ast.Sub)):
            _check_linear(expr.left, known, lists)
            _check_linear(expr.right, known, lists)
            return
        if isinstance(expr.op, ast.Mult):
            _check_linear(expr.left, known, lists)
            _check_linear(expr.right, known, lists)
            # Linearity guard: at least one factor must be a *literal* integer
            # constant (after folding a unary sign), else the product is a
            # variable-by-variable term and out of QF_LIA.
            if not (_is_int_const(expr.left) or _is_int_const(expr.right)):
                raise Unsupported(
                    "python", "nonlinear-mul",
                    "* needs a constant operand to stay linear (QF_LIA)",
                )
            return
        # FloorDiv / Mod / Div / Pow / bit-ops all land here.
        raise _unsupported(expr.op, "operator out of the linear-integer subset")
    if isinstance(expr, ast.Call):
        # The single in-scope call is ``len(xs)`` over an in-scope list — a
        # compile-time-constant int (the list's static length L). Every other call
        # is out of scope (slice 6 — integer lists).
        if (isinstance(expr.func, ast.Name) and expr.func.id == "len"
                and len(expr.args) == 1 and not expr.keywords):
            arg = expr.args[0]
            if not (isinstance(arg, ast.Name) and isinstance(arg.ctx, ast.Load)):
                raise Unsupported("python", "len-arg", "len() takes a plain list name")
            if arg.id not in known:
                raise Unsupported("python", "undefined-name", f"read of unassigned {arg.id!r}")
            if arg.id not in lists:
                raise Unsupported("python", "len-non-list",
                                  f"len({arg.id!r}) — only a list has a static length here")
            return
        raise _unsupported(expr, "function call out of the integer subset")
    raise _unsupported(expr, "expression out of the integer subset")


def _check_list_literal(expr: ast.List, known: set[str], lists: dict[str, int]) -> int:
    """Validate a list literal ``[e0, e1, …, e{L-1}]`` (slice 6 — integer lists):
    each element is an in-scope **integer** expression (a list of non-int / nested
    list is out of scope), and the literal length ``L`` is a compile-time constant
    bounded by ``MAX_LIST_LEN`` (a longer literal hard-aborts ``list-too-long`` to
    bound SMT size). Returns ``L``. The list is modeled by ``T`` as ``L`` separate
    ``Int`` SSA variables — a *tuple of Ints*, staying in ``QF_LIA``."""
    length = len(expr.elts)
    if length > MAX_LIST_LEN:
        raise Unsupported("python", "list-too-long",
                          f"list length {length} exceeds the cap {MAX_LIST_LEN}")
    for elt in expr.elts:
        if isinstance(elt, (ast.List, ast.Tuple, ast.Dict, ast.Set)):
            raise Unsupported("python", "nested-list",
                              "a nested list / non-int element is out of scope")
        _check_linear(elt, known, lists)  # each element is an in-scope int expr
    return length


def _check_assign(
    stmt: ast.Assign, known: set[str], lists: dict[str, int]
) -> tuple[str, int | None]:
    """Validate one assignment and return ``(name, length)`` — the assigned name and
    its post-assignment list length (an ``int``) or ``None`` if it is a scalar int.
    Three shapes are in scope (the RHS is validated against the scope *before* this
    statement, so ``x = x + 1`` reads the old ``x``):

      * **list literal** ``xs = [e0, …, e{L-1}]`` — a single ``Name`` target bound to
        an in-scope-int list literal of static length ``L`` (slice 6); returns
        ``(xs, L)``;
      * **index write** ``xs[i] = <linear>`` — an ``ast.Subscript`` target over an
        in-scope **list** ``xs``, with an in-scope index ``i`` (constant or scalar
        int) and an in-scope-int RHS (slice 6); returns ``(xs, len(xs))`` — the list
        keeps its length, SSA-updated at position ``i`` by ``T``;
      * **scalar** ``name = <linear>`` — a single ``Name`` target bound to an in-scope
        integer expression (including an element read ``ys[k]``); returns
        ``(name, None)``. Rebinding an existing list name to an int (or vice versa)
        re-types it, which the caller records.
    """
    if len(stmt.targets) != 1:
        raise Unsupported("python", "multiple-targets", "chained assignment is out of scope")
    target = stmt.targets[0]
    if isinstance(target, ast.Name):
        if isinstance(stmt.value, ast.List):
            length = _check_list_literal(stmt.value, known, lists)
            return target.id, length
        _check_linear(stmt.value, known, lists)
        return target.id, None
    if isinstance(target, ast.Subscript):
        # An index write ``xs[i] = v`` (an SSA list update — slice 6). The list name
        # inside a subscript-store carries ``Load`` ctx (only the Subscript is the
        # Store target), so we check it is a plain Name, not its ctx.
        if not isinstance(target.value, ast.Name):
            raise _unsupported(target.value, "only a plain list name may be index-assigned")
        name = target.value.id
        if name not in known:
            raise Unsupported("python", "undefined-name", f"write to unassigned {name!r}")
        if name not in lists:
            raise Unsupported("python", "index-non-list",
                              f"{name!r} is an int, not an indexable list")
        if isinstance(target.slice, ast.Slice):
            raise Unsupported("python", "list-slice", "list slice assignment is out of scope")
        idx = target.slice
        _check_index(idx, known, lists)
        length = lists[name]
        if _is_int_const(idx):
            k = _eval_const_int(idx)
            if not (0 <= k < length):
                raise Unsupported("python", "list-index-out-of-range",
                                  f"constant index {k} out of range for len {length}")
        # The RHS is an in-scope integer (a list literal cannot be stored into an
        # element — that would nest).
        if isinstance(stmt.value, ast.List):
            raise Unsupported("python", "nested-list",
                              "storing a list into an element is out of scope")
        _check_linear(stmt.value, known, lists)
        return name, length
    # Tuple/list unpacking, attribute target.
    raise _unsupported(target, "only a single Name or list-index assignment target is in scope")


def _check_compare(test: ast.expr, known: set[str], lists: dict[str, int], what: str) -> None:
    """Validate that ``test`` is one in-scope integer comparison
    ``<linear> <cmp> <linear>`` with ``cmp`` in ``== != < <= > >=`` and both
    operands readable in ``known``. Shared by ``assert`` and ``if`` conditions —
    one definition, so the assert's property and a branch's guard are the same
    construct (``what`` only names the abort detail). Each operand is an integer
    expression (an element read ``xs[i]`` or ``len(xs)`` is allowed; a whole list
    aborts ``list-as-int`` — slice 6)."""
    if not isinstance(test, ast.Compare):
        raise _unsupported(test, f"{what} must be a single integer comparison")
    if len(test.ops) != 1 or len(test.comparators) != 1:
        raise Unsupported("python", "chained-compare", "only a single comparison is in scope")
    op = test.ops[0]
    if type(op) not in _CMP_OPS:
        raise _unsupported(op, "comparison operator out of scope")
    _check_linear(test.left, known, lists)
    _check_linear(test.comparators[0], known, lists)


def _check_assert(stmt: ast.Assert, known: set[str], lists: dict[str, int]) -> None:
    """Validate ``assert <linear> <cmp> <linear>`` (one comparison, no message
    expression beyond a constant)."""
    if stmt.msg is not None and not isinstance(stmt.msg, ast.Constant):
        raise _unsupported(stmt.msg, "assert message must be a constant or absent")
    _check_compare(stmt.test, known, lists, "assert condition")


def _check_if(
    stmt: ast.If, known: set[str], lists: dict[str, int], *, loop_depth: int, unroll_product: int
) -> set[str]:
    """Validate ``if <cond>: <arm> [else: <arm>]`` (slice 2). The condition is one
    in-scope integer comparison over names already in ``known``; each arm is a
    body of in-scope statements (assignments / nested ``if`` / a bounded ``for`` /
    ``while`` — no ``assert``) validated against a *copy* of ``known`` (each arm
    sees the same incoming scope). Returns the names assigned on **both** arms —
    the only ones that are guaranteed-defined, hence readable, after the join; a
    name first assigned on only one arm is *not* propagated (it may be undefined on
    the other path). ``loop_depth`` / ``unroll_product`` are threaded down
    unchanged (an ``if`` is not a loop, so it does not deepen the nesting or
    multiply the unroll count) so a loop nested in an arm inside a loop is checked
    against the nesting caps at the right depth (a loop inside an ``if`` inside a
    loop is *one* level of nesting, not two).

    For a **list** joined at the if (slice 6), the two arms must agree on its
    static type: both arms must leave it a list of the **same length** (a length
    that differs between arms, or a list-vs-int disagreement, hard-aborts
    ``list-join-mismatch`` — the post-join tuple-of-Ints width would be ambiguous).
    The reconciled list lengths are written back into the parent ``lists`` map for
    every joined list name."""
    _check_compare(stmt.test, known, lists, "if condition")
    then_lists = dict(lists)
    else_lists = dict(lists)
    then_assigned = _check_body(
        stmt.body, set(known), then_lists, in_branch=True,
        loop_depth=loop_depth, unroll_product=unroll_product,
    )
    else_assigned = _check_body(
        stmt.orelse, set(known), else_lists, in_branch=True,
        loop_depth=loop_depth, unroll_product=unroll_product,
    )
    # Only the intersection is definitely-assigned regardless of which arm runs.
    joined = then_assigned & else_assigned
    # Reconcile the type of every joined name: a name that is a list on one arm and
    # an int (or a list of a different length) on the other has an ambiguous static
    # shape after the join — hard-abort. Names whose type is unchanged across both
    # arms keep their entry; a joined int name drops out of ``lists``.
    for name in joined:
        then_len = then_lists.get(name)
        else_len = else_lists.get(name)
        if then_len != else_len:
            raise Unsupported("python", "list-join-mismatch",
                              f"{name!r} has different list shapes on the two arms")
        if then_len is None:
            lists.pop(name, None)  # a joined int — no longer a list
        else:
            lists[name] = then_len
    return joined


def _eval_const_int(expr: ast.expr) -> int:
    """The integer value of a literal (possibly under unary +/-). The caller has
    already proven ``_is_int_const(expr)``."""
    if isinstance(expr, ast.UnaryOp):
        v = _eval_const_int(expr.operand)
        return -v if isinstance(expr.op, ast.USub) else +v
    return int(expr.value)  # ast.Constant carrying an int


def range_bound(stmt: ast.For) -> int:
    """Validate a ``for <name> in range(<const>):`` header and return the
    compile-time-constant trip count ``n``. The bounded loop is **fully unrolled**
    by ``T`` exactly ``n`` times (SPEC.md §"Bounded loop"), so the iterable must be
    a ``range`` over a single **non-negative integer literal** — the only shape
    with a statically-known, predictable trip count (the predictability test,
    PAIRING.md §2). Anything else hard-aborts a typed construct: a non-``Name``
    target, a ``for…else``, an iterable that is not ``range``, a ``range`` with a
    start/step (more than one argument), or a bound that is not a non-negative
    integer constant. Shared by the loader (boundary check) and ``T`` (the trip
    count) — one definition, so the unrolled count is predictable from this spec.
    """
    if not (isinstance(stmt.target, ast.Name) and isinstance(stmt.target.ctx, ast.Store)):
        raise _unsupported(stmt.target, "the loop variable must be a single Name")
    if stmt.orelse:
        raise Unsupported("python", "for-else", "for…else is out of scope")
    it = stmt.iter
    if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range"):
        raise Unsupported("python", "nonrange-loop",
                          "only `for i in range(n)` (a bounded loop) is in scope")
    if it.keywords or len(it.args) != 1:
        raise Unsupported("python", "range-shape",
                          "only single-argument `range(n)` (no start/step) is in scope")
    bound = it.args[0]
    if not _is_int_const(bound):
        # A non-constant range bound has no statically-known trip count, so the
        # unrolling would not be predictable — out of scope.
        raise Unsupported("python", "nonconst-range",
                          "the range bound must be a compile-time integer constant")
    n = _eval_const_int(bound)
    if n < 0:
        raise Unsupported("python", "negative-range", "the range bound must be non-negative")
    return n


def _enter_loop(stmt: ast.stmt, loop_depth: int, unroll_product: int, bound: int) -> tuple[int, int]:
    """Enter a loop at nesting ``loop_depth`` with running ``unroll_product``, the
    new loop contributing ``bound`` unrolled iterations. Returns the
    ``(loop_depth, unroll_product)`` *inside* the new loop's body, after enforcing
    the nesting caps (slice 5 — nested loops). Both caps are static (a ``for``'s
    trip count is a source constant; a ``while``'s is ``WHILE_BOUND``), so the abort
    fires at load time (BENCHMARKS.md §3) — never an enormous emitted script.

    The depth cap bounds *how deep* loops nest; the product cap bounds the *total*
    unrolled size (the inner body is re-unrolled at every outer iteration, so the
    sizes multiply). Either being exceeded hard-aborts ``nesting-too-deep`` with the
    cap in the detail."""
    new_depth = loop_depth + 1
    if new_depth > MAX_LOOP_DEPTH:
        raise Unsupported(
            "python", "nesting-too-deep",
            f"loop nesting depth {new_depth} exceeds the cap {MAX_LOOP_DEPTH}",
        )
    new_product = unroll_product * bound
    if new_product > MAX_UNROLL_PRODUCT:
        raise Unsupported(
            "python", "nesting-too-deep",
            f"unrolled size {new_product} exceeds the cap {MAX_UNROLL_PRODUCT}",
        )
    return new_depth, new_product


def _check_loop_list_lengths_stable(
    before: dict[str, int], body_lists: dict[str, int]
) -> None:
    """A list in scope **before** a loop must keep its static length across the body
    (slice 6). The translator re-unrolls the body over the advancing SSA, so a
    pre-loop list's *tuple-of-Ints width* must be invariant — index writes are fine
    (they keep the length), but reassigning the name to a literal of a **different**
    length would make the post-loop width ambiguous and hard-aborts
    ``list-len-changed-in-loop``. (A body-only list literal is dropped after the loop,
    so it imposes no constraint.)"""
    for name, length in before.items():
        new_len = body_lists.get(name)
        if new_len is not None and new_len != length:
            raise Unsupported("python", "list-len-changed-in-loop",
                              f"list {name!r} changes length ({length}->{new_len}) in the loop")


def _check_for(
    stmt: ast.For, known: set[str], lists: dict[str, int], *, loop_depth: int, unroll_product: int
) -> None:
    """Validate ``for <i> in range(<const>): <body>`` (slice 3 — the bounded loop;
    slice 5 — it may now nest). The header fixes a compile-time-constant trip count
    ``n``; entering the loop deepens the nesting and multiplies the unrolled size by
    ``n``, both checked against the nesting caps (``_enter_loop`` — a loop too deep
    or whose unrolled product would exceed the cap hard-aborts ``nesting-too-deep``).
    The loop variable ``i`` is in scope **inside** the body (bound to the concrete
    iteration index when ``T`` unrolls) but is **not** readable after the loop. The
    loop contributes **no** new readable name to the outer scope: because
    ``range(n)`` may have ``n == 0`` (the body never runs), no body-assigned name is
    guaranteed-defined after the loop — an accumulator must be initialised *before*
    the loop to be read after it (exactly the ``if`` one-arm rule). The body may
    itself contain a nested ``for`` / ``while`` (slice 5), validated one level
    deeper. A **list** in scope before the loop (slice 6) may be index-written in the
    body (the index write persists — that is "a list updated in a loop") but must
    keep its static length (``_check_loop_list_lengths_stable``)."""
    n = range_bound(stmt)  # validate the header; T re-derives the trip count from it
    body_depth, body_product = _enter_loop(stmt, loop_depth, unroll_product, n)
    body_scope = set(known)
    body_scope.add(stmt.target.id)  # the loop variable is readable in the body
    body_lists = dict(lists)
    _check_body(stmt.body, body_scope, body_lists, in_branch=True,
                loop_depth=body_depth, unroll_product=body_product)
    _check_loop_list_lengths_stable(lists, body_lists)


def _check_while(
    stmt: ast.While, known: set[str], lists: dict[str, int], *, loop_depth: int, unroll_product: int
) -> None:
    """Validate ``while <cond>: <body>`` (slice 4 — the BMC-bounded loop; slice 5 —
    it may now nest). Entering the loop deepens the nesting and multiplies the
    unrolled size by ``WHILE_BOUND`` (its fixed bound), both checked against the
    nesting caps (``_enter_loop`` — a loop too deep or whose unrolled product would
    exceed the cap hard-aborts ``nesting-too-deep``). The condition is one in-scope
    integer comparison over names already in ``known`` (the same comparison
    construct as an ``if`` guard / the assert property); ``T`` lowers it once per
    unrolled iteration over the advancing SSA. A ``while … else`` is out of scope.
    The body is a body of in-scope statements (assignment / nested ``if`` / a nested
    ``for`` / ``while`` within the caps — **no** ``assert``, no ``break`` /
    ``continue``) validated one level deeper. The loop contributes **no** new
    readable name to the outer scope: the loop may run zero times (the condition
    false at entry) and is unrolled only to a finite bound (it may also not have
    entered its terminating iteration within the bound), so no body-assigned name is
    guaranteed-defined after the loop — an accumulator must be initialised *before*
    the loop to be read after it (exactly the ``if`` one-arm / ``for`` rule). A
    **list** in scope before the loop (slice 6) may be index-written in the body but
    must keep its static length (``_check_loop_list_lengths_stable``)."""
    if stmt.orelse:
        raise Unsupported("python", "while-else", "while…else is out of scope")
    _check_compare(stmt.test, known, lists, "while condition")
    body_depth, body_product = _enter_loop(stmt, loop_depth, unroll_product, WHILE_BOUND)
    body_lists = dict(lists)
    _check_body(stmt.body, set(known), body_lists, in_branch=True,
                loop_depth=body_depth, unroll_product=body_product)
    _check_loop_list_lengths_stable(lists, body_lists)


def _check_body(
    body: list[ast.stmt], known: set[str], lists: dict[str, int], *, in_branch: bool,
    loop_depth: int = 0, unroll_product: int = 1,
) -> set[str]:
    """Validate a statement list (the function body, an ``if`` arm, a ``for`` body,
    or a ``while`` body), mutating ``known`` with each assignment so later statements
    see earlier locals. Returns the set of names this body assigns (used by
    ``_check_if`` for the SSA join). ``in_branch`` forbids the trailing-``assert``
    property inside an ``if`` arm or a loop body — the property is the single
    top-level assert; a branch / loop body carries only assignments, nested ``if``,
    and a bounded ``for`` / ``while`` (which, slice 5, may itself be nested within
    the nesting caps). ``loop_depth`` is the current loop nesting depth and
    ``unroll_product`` the running product of unroll bounds; both are threaded into
    each loop (``_check_for`` / ``_check_while`` → ``_enter_loop``) to enforce the
    ``MAX_LOOP_DEPTH`` / ``MAX_UNROLL_PRODUCT`` caps (a loop nested too deep or whose
    unrolled size would exceed the cap hard-aborts ``nesting-too-deep``).

    ``lists`` (slice 6) maps each in-scope **list** name to its static length; it is
    mutated alongside ``known`` (a list literal adds / re-lengths an entry; an index
    write keeps it; rebinding a list name to an int drops it). It is the loader's
    static type map, so a list used where an int is expected — or vice versa —
    hard-aborts with a typed construct."""
    assigned: set[str] = set()
    for stmt in body:
        if isinstance(stmt, ast.Assign):
            name, length = _check_assign(stmt, known, lists)
            known.add(name)
            assigned.add(name)
            if length is None:
                lists.pop(name, None)  # (re)bound to a scalar int
            else:
                lists[name] = length   # a list literal / index-updated list
        elif isinstance(stmt, ast.If):
            joined = _check_if(stmt, known, lists, loop_depth=loop_depth, unroll_product=unroll_product)
            known |= joined
            assigned |= joined
        elif isinstance(stmt, ast.For):
            _check_for(stmt, known, lists, loop_depth=loop_depth, unroll_product=unroll_product)
            # A bounded loop contributes no guaranteed-defined name (n may be 0).
        elif isinstance(stmt, ast.While):
            _check_while(stmt, known, lists, loop_depth=loop_depth, unroll_product=unroll_product)
            # A BMC-bounded loop contributes no guaranteed-defined name (it may run
            # zero times, or not reach termination within the bound).
        elif isinstance(stmt, ast.Pass):
            continue
        elif isinstance(stmt, ast.Assert):
            if in_branch:
                raise Unsupported("python", "branch-assert",
                                  "assert is the trailing property, not an if-arm/loop statement")
            # The top-level trailing assert is handled by the caller (load); a
            # bare assert reached here would be mid-body — out of scope.
            raise Unsupported("python", "non-trailing-assert",
                              "the single assert must be the function's last statement")
        else:
            # while/return/expr-call/with/try/... all hard-abort here.
            raise _unsupported(stmt, "statement out of the integer subset")
    return assigned


def load(program: object) -> Program:
    """Parse and validate a Python-subset program (bytes / str / ``Program``).

    Hard-aborts ``unsupported: python:<construct>`` on any out-of-subset node;
    on success returns the validated :class:`Program`. Deterministic: the same
    source yields the same model on any host (no hashing / dict-order surface).
    """
    if isinstance(program, Program):
        return program
    if isinstance(program, bytes):
        source = program.decode("utf-8")
    elif isinstance(program, str):
        source = program
    else:
        raise TypeError(f"unsupported program type {type(program).__name__}")

    module = ast.parse(source)
    funcs = [s for s in module.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
    others = [s for s in module.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if others:
        # Anything at module level other than the single def (imports, top-level
        # statements) is out of scope.
        raise _unsupported(others[0], "module body must be exactly one function def")
    if len(funcs) != 1:
        raise Unsupported("python", "module-shape", f"expected exactly one def, found {len(funcs)}")
    func = funcs[0]
    if isinstance(func, ast.AsyncFunctionDef):
        raise _unsupported(func, "async functions are out of scope")
    if func.decorator_list:
        raise _unsupported(func.decorator_list[0], "decorators are out of scope")

    args = func.args
    if (args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs
            or args.defaults or args.kw_defaults):
        raise Unsupported("python", "param-shape",
                          "only plain positional integer parameters are in scope")
    params: list[str] = []
    for a in args.args:
        if a.annotation is not None and not (
            isinstance(a.annotation, ast.Name) and a.annotation.id == "int"
        ):
            raise _unsupported(a.annotation, f"parameter {a.arg!r} annotation must be int or absent")
        params.append(a.arg)
    if len(set(params)) != len(params):
        raise Unsupported("python", "duplicate-param", "parameter names must be distinct")

    # Walk the body: a run of assignments / ``if`` blocks, then exactly one
    # trailing ``assert`` (the property). The assert must be the *last*
    # statement; anything after it, or a missing assert, hard-aborts.
    known: set[str] = set(params)
    lists: dict[str, int] = {}  # slice 6: list name -> static length (params are all int)
    if not func.body or not isinstance(func.body[-1], ast.Assert):
        # Either an empty body or a body not ending in the property. A bare
        # trailing non-assert statement means no property to decide.
        if any(isinstance(s, ast.Assert) for s in func.body):
            raise Unsupported("python", "post-assert-statement",
                              "no statement may follow the single assert")
        raise Unsupported("python", "no-assert",
                          "the slice requires exactly one trailing assert as the property")
    # Validate every statement up to (not including) the trailing assert.
    _check_body(list(func.body[:-1]), known, lists, in_branch=False)
    _check_assert(func.body[-1], known, lists)

    return Program(name=func.name, params=tuple(params), body=tuple(func.body), source=source)
