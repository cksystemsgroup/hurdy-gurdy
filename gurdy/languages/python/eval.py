"""The Python-subset **executor** — the shared source interpreter ``I_s``
(languages/python brief; ARCHITECTURE.md §5).

The soundness story (pairs/python-smtlib brief; PAIRING.md §6, §9) resolves the
"large real interpreter" open question toward the **real interpreter as the
oracle**: ``I_s`` is *pinned real CPython restricted to the subset*, not a
hand-written mirror. The loader (``subset.load``) enforces the subset by
rejecting any out-of-subset AST node; the accepted statements are then executed
**by CPython itself** over the input binding, in a *restricted namespace* with
``__builtins__`` emptied — so no import, no I/O, no name resolves outside the
program's own variables. The subset has no nondeterministic surface (no
wall-clock / RNG / hashing), so a fixed CPython tag makes the trace
byte-reproducible (ARCHITECTURE.md §4).

The pinned interpreter version is the host CPython this runs under, recorded as
``PYTHON_PIN`` and surfaced in the trace's provenance so a divergence can name
the oracle.

Trace shape (ARCHITECTURE.md §5: post-step state). One :class:`dict` per
*executed* statement, recorded *after* the statement executes:

  * for an assignment ``name = e`` — the full named-variable environment after
    the update (every parameter + local in scope), under their names, plus
    ``"__stmt__": "assign"`` and ``"__assigned__": name``. A **list** assignment /
    index write (slice 6) is one such row whose ``name`` is the list, the list value
    snapshotted *by copy* so a later in-place ``xs[i] = v`` does not retroactively
    alter an earlier row;
  * an ``if cond: ... else: ...`` records **no row of its own**; its guard is
    evaluated through CPython and only the taken arm's statements run (and record
    their rows), so the trace is exactly the sequence of statements the input
    actually executes;
  * a ``for i in range(n): ...`` records **no row of its own**; its body runs once
    per ``i = 0..n-1`` (each body statement records its row, with the live loop
    variable ``i`` in the environment) — the bounded unrolling, exactly the count
    ``T`` lowers. After the loop ``i`` is dropped (not readable post-loop);
  * a ``while cond: ...`` records **no row of its own**; the guard is evaluated
    through CPython before each iteration and the body runs (recording its rows)
    while the guard holds, **capped at the BMC bound ``WHILE_BOUND`` (= K) body
    iterations** so an unbounded loop can never hang ``I_s`` — the same depth ``T``
    unrolls, so the executor's behavior matches the bounded model. (The pair only
    ever replays inputs the solver returns, which terminate within ``K``, so the
    cap is a safety floor that does not fire on a witnessed counterexample.) No
    body-assigned name is in scope after the loop (it may run zero times, or hit
    the cap);
  * for the trailing ``assert cond`` — the same environment plus
    ``"__stmt__": "assert"``, ``"__cond__": <bool>`` (did the condition hold?),
    and ``"__violated__": not <bool>`` (did the assert fire?). The executor does
    **not** raise on a false condition; it records the verdict, so the carry-back
    can exhibit the firing assert as an observation rather than an exception.

The projection ``π`` (pairs/python-smtlib) selects the named program variables
at the observation point plus the property verdict from these states.
"""

from __future__ import annotations

import ast
import platform
from typing import Any

from ...core.types import Trace
from .subset import WHILE_BOUND, Program, _CMP_OPS, load, range_bound

# The pinned CPython tag (the source oracle's version — DOCKER.md / AGENTS.md
# §4). Recorded so any commuting-square divergence can name the interpreter it
# was checked against, exactly as RISC-V names ``sail_riscv_sim``.
PYTHON_PIN = f"CPython {platform.python_version()}"


def _eval_expr(expr: ast.expr, env: dict[str, int]) -> int:
    """Evaluate a validated linear-integer expression under ``env``. The loader
    has already proven every node is in subset, so this is total."""
    if isinstance(expr, ast.Constant):
        return int(expr.value)
    if isinstance(expr, ast.Name):
        return env[expr.id]
    if isinstance(expr, ast.UnaryOp):
        v = _eval_expr(expr.operand, env)
        return +v if isinstance(expr.op, ast.UAdd) else -v
    if isinstance(expr, ast.BinOp):
        a = _eval_expr(expr.left, env)
        b = _eval_expr(expr.right, env)
        if isinstance(expr.op, ast.Add):
            return a + b
        if isinstance(expr.op, ast.Sub):
            return a - b
        return a * b  # Mult (the loader guaranteed a constant operand)
    raise AssertionError(f"loader admitted an out-of-subset expr: {ast.dump(expr)}")


def _compare(op: ast.cmpop, a: int, b: int) -> bool:
    """The single in-subset integer comparison, evaluated by CPython's own
    operators (so the oracle is real Python semantics, not a re-derivation)."""
    py_op, _smt = _CMP_OPS[type(op)]
    return {
        "==": a == b, "!=": a != b,
        "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b,
    }[py_op]


def _restricted_globals() -> dict[str, Any]:
    """A namespace with builtins emptied: no import, no I/O, no name outside the
    program's own variables (the subset's allow-list, enforced at runtime as
    well as by the loader). The **only** builtin exposed is ``len`` (slice 6 —
    ``len(xs)`` over an in-scope list), the single call the loader admits; every
    other call is rejected at load time, so no other builtin can leak."""
    return {"__builtins__": {"len": len}}


def _snapshot(env: dict[str, Any]) -> dict[str, Any]:
    """A post-step row of the named-variable environment. A **list** value is
    copied (slice 6) so a later index write — which mutates the list in place —
    cannot retroactively change an earlier recorded row; an int is immutable and
    stored directly."""
    return {k: (list(v) if isinstance(v, list) else v) for k, v in env.items()}


def run(program: object, binding: dict[str, int] | None = None) -> Trace:
    """Execute the validated subset program over an input ``binding`` (a
    ``{param: int}`` map; missing parameters default to 0) and return the
    post-step trace.

    Statements run **through CPython**: each assignment RHS is compiled and
    ``eval``'d in the restricted namespace (so the arithmetic is real CPython's,
    not this module's), and the assert condition likewise. The deterministic
    post-step states are what the commuting-square oracle aligns.

    A list **index out of range** (slice 6) is caught and recorded as a *defined
    error* — a terminal row ``{"__stmt__": "error", "__error__": "index-out-of-range",
    "__violated__": False}`` — so ``I_s`` stays total rather than raising. The pair
    only ever replays solver-returned inputs, whose dynamic indices are
    range-constrained in the SMT (``0 <= i < L``), so this floor never fires on a
    witnessed counterexample; it is the list analogue of the ``while`` replay cap.
    """
    prog: Program = load(program)
    binding = binding or {}

    # The named-variable environment seeded with the integer inputs (declaration
    # order; an unbound parameter defaults to 0 so the run is total).
    env: dict[str, Any] = {}
    g = _restricted_globals()
    for p in prog.params:
        env[p] = int(binding.get(p, 0))

    trace: list[dict[str, Any]] = []
    try:
        _exec_body(prog.body, env, g, trace)
    except IndexError:
        trace.append({"__stmt__": "error", "__error__": "index-out-of-range",
                      "__cond__": False, "__violated__": False})
    return trace


def _exec_body(
    body: tuple[ast.stmt, ...] | list[ast.stmt],
    env: dict[str, Any],
    g: dict[str, Any],
    trace: list[dict[str, Any]],
) -> None:
    """Execute a validated statement list (function body, an ``if`` arm, or a
    ``for`` body) through CPython, appending one post-step row per assignment and
    the trailing assert. An ``if`` evaluates its guard through CPython and recurses
    into the taken arm only; a ``for i in range(n)`` runs its body once per
    ``i = 0..n-1`` (the same finite unrolling ``T`` performs), so the replayed run
    takes exactly the path the input selects — the behavior the commuting-square
    and carry-back checks observe. A **list** assignment / index write (slice 6)
    runs natively through CPython (a list literal builds the real list, ``xs[i] = v``
    mutates it); the row snapshots list values by copy."""
    for stmt in body:
        if isinstance(stmt, ast.Assign):
            target = stmt.targets[0]
            if isinstance(target, ast.Name):
                name = target.id
                # Run the RHS through CPython in the restricted namespace.
                code = compile(ast.Expression(stmt.value), "<subset>", "eval")
                val = eval(code, g, env)  # noqa: S307 - sandboxed (no builtins)
                # A list literal yields a Python list; a scalar expr an int.
                env[name] = val if isinstance(val, list) else int(val)
            else:
                # An index write ``xs[i] = v`` — mutate the real list in place
                # (validated by the loader: a list target, an in-scope int index).
                name = target.value.id  # the list name
                stmt_code = compile(ast.Module([stmt], type_ignores=[]), "<subset>", "exec")
                exec(stmt_code, g, env)  # noqa: S102 - sandboxed (no builtins)
            row: dict[str, Any] = _snapshot(env)
            row["__stmt__"] = "assign"
            row["__assigned__"] = name
            trace.append(row)
        elif isinstance(stmt, ast.If):
            code = compile(ast.Expression(stmt.test), "<subset>", "eval")
            taken = bool(eval(code, g, env))  # noqa: S307 - sandboxed (no builtins)
            _exec_body(stmt.body if taken else stmt.orelse, env, g, trace)
        elif isinstance(stmt, ast.For):
            # Bounded loop: run the body for i = 0..n-1 (n the constant trip count
            # the loader validated — `range_bound` is the single source of truth,
            # so the executor and T unroll exactly the same number of times). The
            # loop variable is live in the body's rows but is removed after the
            # loop: it is not readable post-loop (matching the SSA translator,
            # which drops i from its current map at the join).
            var = stmt.target.id
            n = range_bound(stmt)
            had_var = var in env  # almost never (the loader keeps i loop-local)
            saved = env.get(var)
            for i in range(n):
                env[var] = i
                _exec_body(stmt.body, env, g, trace)
            if had_var:
                env[var] = saved  # type: ignore[assignment]
            else:
                env.pop(var, None)
        elif isinstance(stmt, ast.While):
            # BMC-bounded loop: evaluate the guard through CPython before each
            # iteration and run the body while it holds, **capped at WHILE_BOUND
            # body iterations** — the same depth T unrolls (so the executor matches
            # the bounded model), and a hard ceiling that keeps I_s total even if a
            # non-terminating input is ever run directly (the solver never returns
            # one, so the cap does not fire on a witnessed counterexample). Any name
            # first assigned in the body is dropped after the loop: the loop may run
            # zero times, so it is not readable post-loop (matching the translator,
            # which drops body-only names at the join — exactly the for-loop rule).
            test = compile(ast.Expression(stmt.test), "<subset>", "eval")
            before = set(env)
            steps = 0
            while steps < WHILE_BOUND and bool(eval(test, g, env)):  # noqa: S307 - sandboxed
                _exec_body(stmt.body, env, g, trace)
                steps += 1
            for name in list(env):
                if name not in before:
                    del env[name]
        elif isinstance(stmt, ast.Assert):
            code = compile(ast.Expression(stmt.test), "<subset>", "eval")
            cond = bool(eval(code, g, env))  # noqa: S307 - sandboxed (no builtins)
            row = _snapshot(env)
            row["__stmt__"] = "assert"
            row["__cond__"] = cond
            row["__violated__"] = not cond
            trace.append(row)
        # ast.Pass: nothing to record.


def interpret(program: object, binding: dict[str, int] | None = None, **_kw: Any) -> Trace:
    """Parse + validate + execute. The callable registered as the language's
    source interpreter ``I_s``."""
    return run(program, binding)
