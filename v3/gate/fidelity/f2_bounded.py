"""F2 — Bounded. Per program, T(p) == Sail for all inputs up to bound k
(symbolic, SMT). STUB."""

from __future__ import annotations

from gurdy.core.manifest import Manifest
from gurdy.core.report import CheckResult, CheckStatus, Fidelity


def check(manifest: Manifest) -> CheckResult:
    # TODO(gate): SMT-prove bounded equivalence of T(p) to the Sail-derived
    # transition relation, per corpus program.
    return CheckResult(
        Fidelity.F2_bounded,
        CheckStatus.NOT_IMPLEMENTED,
        "bounded all-input equivalence [TODO(gate)]",
    )
