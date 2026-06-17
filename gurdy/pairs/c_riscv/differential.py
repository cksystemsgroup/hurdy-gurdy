"""Differential of the ``c-riscv`` long path against an independent C verifier.

The ``c-riscv`` translator is an opaque, pinned C compiler: its honest fidelity
is ``reproducible``, and meaning-preservation is established *downstream*
(PATHS.md §3, the c-riscv brief). This module is one of those downstream
re-establishers -- the analogue, for the C head, of the ``sail_riscv_sim``
harness for the RISC-V interpreter.

It decides a property about a C program two ways and cross-checks them:

* on the **lowered RISC-V program**, through the long path
  ``c -> riscv -> btor2 -> smtlib`` (the existing route machinery); and
* on the **C source itself**, with CBMC (``gurdy.solvers.cbmc_c``), an
  independent C bounded model checker.

Agreement re-establishes the opaque head to ``checked`` for that run. A
disagreement is then *classified*: if CBMC's UB checks fire on the expression,
it is a documented **C-undefined-but-RISC-V-defined** behavior (signed
overflow, shift masking, INT_MIN/-1 and div/rem by zero -- the languages/riscv
brief's central reason C is paired *through* RISC-V), not a translator fault;
only a value disagreement with no UB is a fault localized to the compile hop
(SOLVERS.md §7).

The property mirrors the long path's ``reg_eq [10, value]`` (is the program's
``a0`` equal to ``value``?). CBMC and the compiler are gated on the pinned dev
image (DOCKER.md); the harness builders and the classifier are pure, and both
the CBMC checker and the long-path reference are injectable.
"""

from __future__ import annotations

from typing import Any, Callable

from ...core.solver import Verdict
from ...solvers.cbmc_c import DOCUMENTED_UB, UB_CHECK_ARGS, CbmcChecker


def c_source(expr: str) -> str:
    """The freestanding program the long path compiles: compute ``expr`` into a
    ``long`` and surface it in ``a0`` before halting (the head the c-riscv test
    decides over)."""
    return ("void _start(void){ long r=(" + expr + "); "
            '__asm__ volatile("mv a0,%0\\n\\tecall\\n"::"r"(r):"a0"); for(;;){} }\n')


def _c_long_literal(value: int) -> str:
    v = value - (1 << 64) if value >= (1 << 63) else value
    if v == -(1 << 63):                       # INT64_MIN has no direct C literal
        return "(-9223372036854775807L - 1)"
    return f"{v}L"


def cbmc_reg_eq_harness(expr: str, value: int) -> str:
    """A CBMC harness deciding ``a0 == value``: assert the negation, so a
    reachable assertion failure (``VERIFICATION FAILED``) means ``r`` *can*
    equal ``value`` -> REACHABLE, matching the long path's ``reg_eq``."""
    return ("int main(void){ long r = (long)(" + expr + "); "
            f"__CPROVER_assert(r != {_c_long_literal(value)}, \"reg_eq\"); "
            "return 0; }\n")


def ub_probe_harness(expr: str) -> str:
    """A harness that merely evaluates ``expr`` (no assertion), so CBMC's UB
    checks report which undefined behaviors the expression itself triggers."""
    return ("int main(void){ volatile long sink = (long)(" + expr + "); "
            "(void)sink; return 0; }\n")


def cbmc_reg_eq(expr: str, value: int, checker: CbmcChecker | None = None) -> Verdict:
    """CBMC's verdict for ``a0 == value`` on the C source (no UB checks)."""
    return (checker or CbmcChecker()).decide(cbmc_reg_eq_harness(expr, value))


def ub_classes(expr: str, checker: CbmcChecker | None = None) -> set[str]:
    """The documented C-undefined-but-RISC-V-defined behavior classes ``expr``
    triggers, per CBMC's UB checks (subset of ``DOCUMENTED_UB``)."""
    from ...solvers.cbmc_c import failed_property_classes

    out = (checker or CbmcChecker()).run(ub_probe_harness(expr), UB_CHECK_ARGS)
    return failed_property_classes(out) & DOCUMENTED_UB


def long_path_reg_eq(expr: str, value: int, k: int = 6) -> Verdict:
    """Decide ``reg_eq [10, value]`` for ``c_source(expr)`` through the long
    path, over *both* backend routes (direct and Sail-mediated). Returns the
    shared verdict; ``UNKNOWN`` if the two routes disagree (a branch defect the
    differential will surface as a non-agreement)."""
    from ...core import grade, route
    from ...solvers.z3_smt import Z3SmtBackend

    # ensure the whole route graph is registered
    from .. import btor2_smtlib, c_riscv, riscv_btor2, riscv_sail, sail_btor2  # noqa: F401

    routes = route.routes("c", "smtlib")
    params = {"riscv-btor2": {"property": {"reg_eq": [10, value]}},
              "riscv-sail": {"property": {"reg_eq": [10, value]}},
              "btor2-smtlib": {"k": k}}
    ba = grade.branch_agreement(
        routes, {"source": c_source(expr)},
        lambda artifact: Z3SmtBackend().decide(artifact).verdict, params)
    return next(iter(ba.verdicts.values())) if ba.agree else Verdict.UNKNOWN


def differential(
    expr: str,
    value: int,
    *,
    k: int = 6,
    reference: Verdict | None = None,
    reference_fn: Callable[[str, int, int], Verdict] | None = None,
    checker: CbmcChecker | None = None,
) -> dict[str, Any]:
    """Cross-check CBMC (on the C source) against the long-path/RISC-V verdict
    for ``a0 == value``, and classify any disagreement.

    ``reference`` pins the RISC-V-side verdict directly; otherwise ``reference_fn``
    (default: the real long path) computes it. Returns the two verdicts, whether
    they agree, the documented-UB classes the expression triggers, and a
    ``status``:

    * ``agree`` -- clean corroboration (no UB);
    * ``agree-under-riscv-definition`` -- they agree, but the value rests on a
      behavior C leaves undefined and RISC-V defines (flagged, not a fault);
    * ``c-undefined-divergence`` -- they differ *and* the expression is C-UB:
      a documented C-undefined-but-RISC-V-defined case, not a fault;
    * ``localized-fault`` -- they differ with no UB: a real fault localized to
      the compile hop.
    """
    checker = checker or CbmcChecker()
    cbmc_v = cbmc_reg_eq(expr, value, checker)
    if reference is None:
        reference = (reference_fn or long_path_reg_eq)(expr, value, k)
    ub = ub_classes(expr, checker)
    agree = cbmc_v == reference
    if agree:
        status = "agree-under-riscv-definition" if ub else "agree"
    else:
        status = "c-undefined-divergence" if ub else "localized-fault"
    return {
        "expr": expr, "value": value,
        "cbmc": cbmc_v, "reference": reference, "agree": agree,
        "ub_classes": sorted(ub), "status": status,
        "fault": status == "localized-fault",
    }
