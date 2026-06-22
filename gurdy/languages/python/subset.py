"""The Python-subset **loader** — bytes/str/AST -> a validated in-memory model
(languages/python brief; ARCHITECTURE.md §5).

The source of truth for the subset is **the AST node set the loader accepts**:
walking the parsed program, any node outside the allow-list hard-aborts with a
typed ``unsupported: python:<construct>`` (never a silent drop, BENCHMARKS.md
§3). The accepted program is then a *straight-line integer function* the
translator and the CPython executor both consume.

**Minimal vertical slice (PAIRING.md §1 "start thin").** Exactly one construct
class is in scope end-to-end:

  * a single top-level ``def`` whose parameters are all plain (positional)
    integer inputs (no defaults, ``*args``, ``**kwargs``, keyword-only, or
    annotations that aren't ``int``);
  * a **straight-line** body (no control flow) of:
      - integer **assignment** ``name = <expr>`` to a single ``Name`` target;
      - **linear integer arithmetic** in ``<expr>``: integer literals, parameter
        / local ``Name`` loads, unary ``+`` / ``-``, binary ``+`` / ``-``, and
        ``*`` **with at least one constant operand** (so the term stays linear —
        a variable-by-variable product is non-linear and hard-aborts);
      - a single trailing ``assert <cond>`` whose ``<cond>`` is one integer
        comparison ``<linear> <op> <linear>`` with ``op`` in
        ``== != < <= > >=``.

Everything else hard-aborts ``unsupported: python:<construct>``: ``if`` / ``else``,
``while`` / ``for`` (loops), ``//`` / ``%`` (floored division — see the div/mod
note in ``SPEC.md``), ``/`` (float), ``**`` (non-linear), boolean / bitwise
operators, function calls, ``return`` with a value, ``list`` / ``dict`` / ``set``
/ ``str`` literals, attribute access, subscripting, ``import``, ``lambda``,
comprehensions, multiple / tuple assignment targets, augmented assignment, and
any second ``assert``.

The model is **deterministic**: parameters in declaration order, statements in
source order; nothing hashed, ordered by dict iteration, or timestamped.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ...core.errors import Unsupported

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
    """A validated straight-line integer function.

    ``name`` — the function name; ``params`` — its integer parameters in
    declaration order; ``body`` — the original ``ast.FunctionDef`` body
    (statements in source order); ``source`` — the exact source text (the
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


def _check_assert(stmt: ast.Assert) -> None:
    """Validate ``assert <linear> <cmp> <linear>`` (one comparison, no message
    expression beyond a constant)."""
    if stmt.msg is not None and not isinstance(stmt.msg, ast.Constant):
        raise _unsupported(stmt.msg, "assert message must be a constant or absent")
    test = stmt.test
    if not isinstance(test, ast.Compare):
        raise _unsupported(test, "assert condition must be a single integer comparison")
    if len(test.ops) != 1 or len(test.comparators) != 1:
        raise Unsupported("python", "chained-compare", "only a single comparison is in scope")
    op = test.ops[0]
    if type(op) not in _CMP_OPS:
        raise _unsupported(op, "comparison operator out of scope")


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

    # Walk the body: a run of assignments, then exactly one trailing assert.
    known: set[str] = set(params)
    seen_assert = False
    for stmt in func.body:
        if seen_assert:
            raise Unsupported("python", "post-assert-statement",
                              "no statement may follow the single assert")
        if isinstance(stmt, ast.Assign):
            name = _check_assign(stmt, known)
            known.add(name)
        elif isinstance(stmt, ast.Assert):
            _check_assert(stmt)
            seen_assert = True
        elif isinstance(stmt, ast.Pass):
            continue
        else:
            # if/for/while/return/expr-call/with/try/... all hard-abort here.
            raise _unsupported(stmt, "statement out of the straight-line integer subset")
    if not seen_assert:
        raise Unsupported("python", "no-assert",
                          "the slice requires exactly one trailing assert as the property")

    return Program(name=func.name, params=tuple(params), body=tuple(func.body), source=source)
