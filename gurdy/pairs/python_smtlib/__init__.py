"""The ``python-smtlib`` pair — a high-level language compiled **directly to the
SMT-LIB hub** (not via BTOR2): the ``crn-smtlib`` pattern (schema-determined
unrolling into ``QF_LIA``, witness replayed through the source interpreter)
scaled up from chemistry to a high-level language (pairs/python-smtlib brief).
Python's unbounded ``int`` maps faithfully to SMT ``Int`` — the fit only the
direct-to-LIA route affords (ARCHITECTURE.md §9; the brief's central decision).

**Status: partial — widening vertical slice (PAIRING.md §1 "start thin, then
widen").** In scope end-to-end through the commuting square: a integer function
of assignment + linear arithmetic (``+`` / ``-`` / ``*``-by-constant),
``if`` / ``else`` (slice 2 — the SSA branch merge / ``ite`` join), a
**bounded loop** ``for i in range(<const>)`` (slice 3 — full unrolling of a
compile-time-constant trip count), a **BMC-bounded loop**
``while <cond>: <body>`` (slice 4 — unrolling to the fixed bound ``K`` =
``WHILE_BOUND`` with a terminated-within-``K`` assertion), and **nested loops**
(slice 5 — a ``for`` / ``while`` inside another loop's body, or inside an ``if``
arm inside a loop, the inner loop re-unrolled at each outer iteration over the
advancing SSA, within the ``MAX_LOOP_DEPTH`` / ``MAX_UNROLL_PRODUCT`` caps),
terminated by a single ``assert``; every other Python construct hard-aborts
``unsupported: python:<construct>`` (BENCHMARKS.md §3).

Registers the pair (reusing the shared **Python** interpreter as source ``I_s``
— pinned real CPython restricted to the subset — and the shared **SMT-LIB**
``QF_LIA`` evaluator as target ``I_t``) and provides ``reach()``: translate to
``QF_LIA``, decide with z3, and on ``sat`` decode the satisfying **input
assignment** and replay it through CPython to confirm the assert actually fires
within the program (SOLVERS.md §4-5).

Soundness story (pairs/python-smtlib brief; PAIRING.md §6, §9). ``I_s``
**re-executes against pinned real CPython** restricted to the subset (the
"large real interpreter" open question resolved toward the real interpreter as
the oracle). The commuting square is ``I_s(p)`` (CPython, the oracle) vs
``L(I_t(T(p)))`` (SMT model replayed through CPython), under ``π``. Fidelity:
``predicted`` on the encoding (byte-reproducible from SPEC.md) + ``checked``
overall (the square validated every run via the CPython differential) — **not**
``proved`` (LIA proof certificates have weaker tooling — do not inflate).
"""

from __future__ import annotations

from typing import Any

from ...core import registry
from ...core.oracle import align
from ...core.registry import Pair, Status
from ...core.solver import Verdict
from ...core.types import AlignResult, Projection

# Importing the languages registers what the pair reuses.
from ...languages import python as _python  # noqa: F401
from ...languages import smtlib as _smtlib  # noqa: F401
from ...languages.python.eval import run as py_run
from ...languages.python.subset import Program, load
from .inventory import ALL_PROBES
from .lift import decode_inputs, lift
from .translate import translate

registry.register_pair(
    Pair(
        id="python-smtlib",
        source="python",
        target="smtlib",
        translator=translate,
        target_to_source=lift,
        # Per-program variables are the observables; the cross-check builds the
        # concrete projection from the program (see ``projection_for``). The
        # registered projection is the property verdict (program-independent);
        # like crn-smtlib the soundness story is byte-prediction + witness replay.
        projection=Projection(("__stmt__", "__cond__", "__violated__")),
        fidelity="predicted",
        # 0.1 → 0.2: additive widening to if/else (the SSA branch merge);
        # 0.2 → 0.3: additive widening to the bounded for-loop (full unrolling);
        # 0.3 → 0.4: additive widening to the BMC-bounded while-loop (unroll to K +
        # terminated-within-K assertion);
        # 0.4 → 0.5: additive widening to **nested loops** (a loop inside another
        # loop / inside an if inside a loop, within the MAX_LOOP_DEPTH /
        # MAX_UNROLL_PRODUCT caps — the inner loop re-unrolled at each outer
        # iteration over the advancing SSA). The version keys the content-addressed
        # cache, so a schema change bumps it. Additive: every 0.4 program lowers to
        # byte-identical output (the existing single-loop bytes are unchanged — the
        # recursion only newly admits a loop inside a loop body).
        translator_version="0.5",
        status=Status.PARTIAL,
        # Path-runner glue: wrap a predecessor's Python output into our input.
        compose_input=lambda prev, params: {"python": prev},
        # Construct-coverage inventory: Python's construct set.
        probes=ALL_PROBES,
    )
)

__all__ = [
    "translate",
    "lift",
    "decode_inputs",
    "reach",
    "projection_for",
    "cross_check",
]


def projection_for(program: Any) -> Projection:
    """The projection ``π`` for a given program: its named program variables
    (parameters + locals, in declaration / first-assignment order — including
    locals assigned inside ``if`` arms) plus the statement kind and the property
    verdict (``__cond__`` / ``__violated__``).
    """
    prog: Program = load(program)
    names: list[str] = list(prog.params)
    import ast

    def collect(body: Any) -> None:
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                name = stmt.targets[0].id
                if name not in names:
                    names.append(name)
            elif isinstance(stmt, ast.If):
                collect(stmt.body)
                collect(stmt.orelse)

    collect(prog.body)
    return Projection(tuple(names) + ("__stmt__", "__cond__", "__violated__"))


def reach(program: Any) -> dict[str, Any]:
    """Decide "can the trailing assert be violated for some integer input?".

    Returns a dict with the ``verdict``; on ``reachable`` also the decoded
    violating ``inputs``, the carried-back ``behavior`` (the per-step states from
    the CPython replay), ``smt_model_ok`` (the shared ``QF_LIA`` evaluator
    re-checks the solver's model against the script — the authoritative SMT-level
    witness check, SOLVERS.md §4), and ``witness_ok`` (does the CPython replay
    actually fire the assert — ``__violated__`` true at the observation point?).

    A ``reachable`` verdict means the assert is *violable*; ``unreachable`` means
    it holds for every integer input (the property is proved over all inputs by
    the solver, carried back as UNREACHABLE).
    """
    from ...languages.smtlib.eval import evaluate as smt_evaluate
    from ...solvers.z3_smt import Z3SmtBackend

    prog: Program = load(program)
    artifact = translate(prog)
    result = Z3SmtBackend().decide(artifact)
    info: dict[str, Any] = {"verdict": result.verdict, "model": result.model}
    if result.verdict is Verdict.REACHABLE:
        # Authoritative SMT-level witness check (SOLVERS.md §4): re-evaluate the
        # QF_LIA script under the solver's model with the shared evaluator. For a
        # REACHABLE verdict this must hold and must agree with the CPython replay.
        info["smt_model_ok"] = smt_evaluate(artifact, result.model)
        info["inputs"] = decode_inputs(prog, result.model or {})
        behavior = lift({"python": prog, "model": result.model})
        info["behavior"] = behavior
        # The replay fires the assert iff its final (assert) state is violated.
        info["witness_ok"] = bool(behavior and behavior[-1].get("__violated__"))
    return info


def cross_check(program: Any) -> tuple[Verdict, AlignResult]:
    """The commuting-square check (PAIRING.md §7): run the source interpreter
    directly and compare it, under ``π``, with translate -> decide -> carry-back.

    Returns ``(verdict, AlignResult)``. On ``reachable`` the right-hand side
    ``L(I_t(T(p)))`` is the CPython replay of the solver's violating input; the
    left-hand side ``I_s(p)`` re-runs the **same input** through CPython (the
    inputs held in correspondence — ARCHITECTURE.md §3), so a faithful pair makes
    the two traces identical under ``π`` (the program variables + the verdict),
    and the witnessed state is genuinely ``__violated__``. On ``unreachable``
    there is no model to align, so the alignment is the trivially-true empty-trace
    agreement.
    """
    prog: Program = load(program)
    info = reach(prog)
    pi = projection_for(prog)
    if info["verdict"] is not Verdict.REACHABLE:
        return info["verdict"], align([], [], pi)
    # I_s(p): the source interpreter on the witness's input.
    left = py_run(prog, info["inputs"])
    right = info["behavior"]
    return info["verdict"], align(left, right, pi)
