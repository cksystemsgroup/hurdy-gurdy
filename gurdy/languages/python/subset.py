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
        ``<body>`` is a body of in-scope statements (assignments and nested
        ``if`` — but no nested loop and no ``assert``). The loop variable ``i`` is
        readable **inside** the body (it is the iteration index) but **not** after
        the loop; a body-only-assigned name is likewise not readable after (the
        loop may run zero times), so an accumulator read after the loop must be
        initialised *before* it (the ``if`` one-arm rule);
      - ``while <cond>: <body>`` — a **BMC-bounded loop** (slice 4), where
        ``<cond>`` is one integer comparison and ``<body>`` is a body of in-scope
        statements (assignments and nested ``if`` — but no nested loop and no
        ``assert``). ``T`` unrolls the body to a fixed bound ``K`` (BMC) and
        asserts termination within ``K`` (SPEC.md §"BMC-bounded loop"). As with
        ``for``, no body-assigned name is readable after the loop (it may run zero
        times, or not terminate within ``K``), so an accumulator must be
        initialised *before* it;
      - a single trailing ``assert <cond>`` whose ``<cond>`` is one integer
        comparison ``<linear> <op> <linear>`` with ``op`` in
        ``== != < <= > >=``.

Everything else hard-aborts ``unsupported: python:<construct>``: a nested loop
or a non-constant / non-``range`` ``for``, ``//`` / ``%`` (floored division —
see the div/mod note in ``SPEC.md``), ``/`` (float), ``**`` (non-linear),
boolean / bitwise operators, function calls (other than the loop's ``range``
header), ``return`` with a value, ``break`` / ``continue``, ``list`` / ``dict``
/ ``set`` / ``str`` literals, attribute access, subscripting, ``import``,
``lambda``, comprehensions, multiple / tuple assignment targets, augmented
assignment, and any second ``assert``.

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


def _check_linear(expr: ast.expr, known: set[str]) -> None:
    """Validate an integer **linear** arithmetic expression. Hard-aborts any
    out-of-subset node. ``known`` is the set of names readable here (parameters
    plus already-assigned locals); a load of an unknown name aborts as
    ``python:undefined-name`` rather than deferring to a CPython ``NameError``.
    """
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
        return
    if isinstance(expr, ast.UnaryOp):
        if not isinstance(expr.op, (ast.UAdd, ast.USub)):
            raise _unsupported(expr.op, "only unary +/- are in scope")
        _check_linear(expr.operand, known)
        return
    if isinstance(expr, ast.BinOp):
        if isinstance(expr.op, (ast.Add, ast.Sub)):
            _check_linear(expr.left, known)
            _check_linear(expr.right, known)
            return
        if isinstance(expr.op, ast.Mult):
            _check_linear(expr.left, known)
            _check_linear(expr.right, known)
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
    raise _unsupported(expr, "expression out of the integer subset")


def _check_assign(stmt: ast.Assign, known: set[str]) -> str:
    """Validate ``name = <linear>`` (single ``Name`` target). Returns the
    assigned name; the RHS is validated against the names known *before* this
    statement (so ``x = x + 1`` reads the old ``x``)."""
    if len(stmt.targets) != 1:
        raise Unsupported("python", "multiple-targets", "chained assignment is out of scope")
    target = stmt.targets[0]
    if not isinstance(target, ast.Name):
        # Tuple/list unpacking, attribute, or subscript target.
        raise _unsupported(target, "only a single Name assignment target is in scope")
    _check_linear(stmt.value, known)
    return target.id


def _check_compare(test: ast.expr, known: set[str], what: str) -> None:
    """Validate that ``test`` is one in-scope integer comparison
    ``<linear> <cmp> <linear>`` with ``cmp`` in ``== != < <= > >=`` and both
    operands readable in ``known``. Shared by ``assert`` and ``if`` conditions —
    one definition, so the assert's property and a branch's guard are the same
    construct (``what`` only names the abort detail)."""
    if not isinstance(test, ast.Compare):
        raise _unsupported(test, f"{what} must be a single integer comparison")
    if len(test.ops) != 1 or len(test.comparators) != 1:
        raise Unsupported("python", "chained-compare", "only a single comparison is in scope")
    op = test.ops[0]
    if type(op) not in _CMP_OPS:
        raise _unsupported(op, "comparison operator out of scope")
    _check_linear(test.left, known)
    _check_linear(test.comparators[0], known)


def _check_assert(stmt: ast.Assert, known: set[str]) -> None:
    """Validate ``assert <linear> <cmp> <linear>`` (one comparison, no message
    expression beyond a constant)."""
    if stmt.msg is not None and not isinstance(stmt.msg, ast.Constant):
        raise _unsupported(stmt.msg, "assert message must be a constant or absent")
    _check_compare(stmt.test, known, "assert condition")


def _check_if(stmt: ast.If, known: set[str], *, in_loop: bool) -> set[str]:
    """Validate ``if <cond>: <arm> [else: <arm>]`` (slice 2). The condition is one
    in-scope integer comparison over names already in ``known``; each arm is a
    body of in-scope statements (assignments / nested ``if`` / a bounded ``for`` —
    no ``assert``) validated against a *copy* of ``known`` (each arm sees the same
    incoming scope). Returns the names assigned on **both** arms — the only ones
    that are guaranteed-defined, hence readable, after the join; a name first
    assigned on only one arm is *not* propagated (it may be undefined on the
    other path). ``in_loop`` is threaded down so a loop nested in an arm of a loop
    body is still rejected (nested loops are out of scope)."""
    _check_compare(stmt.test, known, "if condition")
    then_assigned = _check_body(stmt.body, set(known), in_branch=True, in_loop=in_loop)
    else_assigned = _check_body(stmt.orelse, set(known), in_branch=True, in_loop=in_loop)
    # Only the intersection is definitely-assigned regardless of which arm runs.
    return then_assigned & else_assigned


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


def _check_for(stmt: ast.For, known: set[str], *, in_loop: bool) -> None:
    """Validate ``for <i> in range(<const>): <body>`` (slice 3 — the bounded
    loop). Nested loops are out of scope, so a ``for`` reached while already
    ``in_loop`` hard-aborts (``python:For``). The loop variable ``i`` is in scope
    **inside** the body (bound to the concrete iteration index when ``T`` unrolls)
    but is **not** readable after the loop. The loop contributes **no** new
    readable name to the outer scope: because ``range(n)`` may have ``n == 0`` (the
    body never runs), no body-assigned name is guaranteed-defined after the loop —
    an accumulator must be initialised *before* the loop to be read after it
    (exactly the ``if`` one-arm rule)."""
    if in_loop:
        raise _unsupported(stmt, "nested loops are out of scope")
    range_bound(stmt)  # validate the header; T re-derives the trip count from it
    body_scope = set(known)
    body_scope.add(stmt.target.id)  # the loop variable is readable in the body
    _check_body(stmt.body, body_scope, in_branch=True, in_loop=True)


def _check_while(stmt: ast.While, known: set[str], *, in_loop: bool) -> None:
    """Validate ``while <cond>: <body>`` (slice 4 — the BMC-bounded loop). Like the
    bounded ``for`` it does not nest: a ``while`` (or any loop) reached while already
    ``in_loop`` hard-aborts (``python:While`` / ``python:For``). The condition is one
    in-scope integer comparison over names already in ``known`` (the same comparison
    construct as an ``if`` guard / the assert property); ``T`` lowers it once per
    unrolled iteration over the advancing SSA. A ``while … else`` is out of scope.
    The body is a body of in-scope statements (assignment / nested ``if`` — **no**
    nested loop, no ``assert``, no ``break`` / ``continue``) validated with
    ``in_loop=True``. The loop contributes **no** new readable name to the outer
    scope: the loop may run zero times (the condition false at entry) and is
    unrolled only to a finite bound (it may also not have entered its terminating
    iteration within the bound), so no body-assigned name is guaranteed-defined
    after the loop — an accumulator must be initialised *before* the loop to be read
    after it (exactly the ``if`` one-arm / ``for`` rule)."""
    if in_loop:
        raise _unsupported(stmt, "nested loops are out of scope")
    if stmt.orelse:
        raise Unsupported("python", "while-else", "while…else is out of scope")
    _check_compare(stmt.test, known, "while condition")
    _check_body(stmt.body, set(known), in_branch=True, in_loop=True)


def _check_body(
    body: list[ast.stmt], known: set[str], *, in_branch: bool, in_loop: bool = False
) -> set[str]:
    """Validate a statement list (the function body, an ``if`` arm, a ``for`` body,
    or a ``while`` body), mutating ``known`` with each assignment so later statements
    see earlier locals. Returns the set of names this body assigns (used by
    ``_check_if`` for the SSA join). ``in_branch`` forbids the trailing-``assert``
    property inside an ``if`` arm or a loop body — the property is the single
    top-level assert; a branch / loop body carries only assignments, nested ``if``,
    and (outside a loop) one bounded ``for`` / ``while``. ``in_loop`` forbids a
    *nested* loop (loops do not nest in this slice)."""
    assigned: set[str] = set()
    for stmt in body:
        if isinstance(stmt, ast.Assign):
            name = _check_assign(stmt, known)
            known.add(name)
            assigned.add(name)
        elif isinstance(stmt, ast.If):
            joined = _check_if(stmt, known, in_loop=in_loop)
            known |= joined
            assigned |= joined
        elif isinstance(stmt, ast.For):
            _check_for(stmt, known, in_loop=in_loop)
            # A bounded loop contributes no guaranteed-defined name (n may be 0).
        elif isinstance(stmt, ast.While):
            _check_while(stmt, known, in_loop=in_loop)
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
    if not func.body or not isinstance(func.body[-1], ast.Assert):
        # Either an empty body or a body not ending in the property. A bare
        # trailing non-assert statement means no property to decide.
        if any(isinstance(s, ast.Assert) for s in func.body):
            raise Unsupported("python", "post-assert-statement",
                              "no statement may follow the single assert")
        raise Unsupported("python", "no-assert",
                          "the slice requires exactly one trailing assert as the property")
    # Validate every statement up to (not including) the trailing assert.
    _check_body(list(func.body[:-1]), known, in_branch=False)
    _check_assert(func.body[-1], known)

    return Program(name=func.name, params=tuple(params), body=tuple(func.body), source=source)
