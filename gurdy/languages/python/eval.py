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
statement, recorded *after* the statement executes:

  * for an assignment ``name = e`` — the full named-variable environment after
    the update (every parameter + local in scope), under their names, plus
    ``"__stmt__": "assign"`` and ``"__assigned__": name``;
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
from .subset import Program, _CMP_OPS, load

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
    well as by the loader)."""
    return {"__builtins__": {}}


def run(program: object, binding: dict[str, int] | None = None) -> Trace:
    """Execute the validated subset program over an input ``binding`` (a
    ``{param: int}`` map; missing parameters default to 0) and return the
    post-step trace.

    Statements run **through CPython**: each assignment RHS is compiled and
    ``eval``'d in the restricted namespace (so the arithmetic is real CPython's,
    not this module's), and the assert condition likewise. The deterministic
    post-step states are what the commuting-square oracle aligns.
    """
    prog: Program = load(program)
    binding = binding or {}

    # The named-variable environment seeded with the integer inputs (declaration
    # order; an unbound parameter defaults to 0 so the run is total).
    env: dict[str, int] = {}
    g = _restricted_globals()
    for p in prog.params:
        env[p] = int(binding.get(p, 0))

    trace: list[dict[str, Any]] = []
    for stmt in prog.body:
        if isinstance(stmt, ast.Assign):
            name = stmt.targets[0].id  # validated single Name target
            # Run the RHS through CPython in the restricted namespace.
            code = compile(ast.Expression(stmt.value), "<subset>", "eval")
            env[name] = int(eval(code, g, env))  # noqa: S307 - sandboxed (no builtins)
            row: dict[str, Any] = {k: env[k] for k in env}
            row["__stmt__"] = "assign"
            row["__assigned__"] = name
            trace.append(row)
        elif isinstance(stmt, ast.Assert):
            code = compile(ast.Expression(stmt.test), "<subset>", "eval")
            cond = bool(eval(code, g, env))  # noqa: S307 - sandboxed (no builtins)
            row = {k: env[k] for k in env}
            row["__stmt__"] = "assert"
            row["__cond__"] = cond
            row["__violated__"] = not cond
            trace.append(row)
        # ast.Pass: nothing to record.
    return trace


def interpret(program: object, binding: dict[str, int] | None = None, **_kw: Any) -> Trace:
    """Parse + validate + execute. The callable registered as the language's
    source interpreter ``I_s``."""
    return run(program, binding)
