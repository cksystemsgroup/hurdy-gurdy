"""F3 — Lowering. Per-instruction machine-checked QF_BV lemma vs Sail =>
programs faithful by composition (the paste lemma). STUB.

For a reasoning hop whose source group ships a verified btor2-machine, F3 may
be discharged by reusing the machine model's per-instruction lemmas rather
than re-proving them — but only for the *machine* path; the *own* path's
independent lowering must be proven on its own to retain validator status.
"""

from __future__ import annotations

from gurdy.core.manifest import Manifest
from gurdy.core.report import CheckResult, CheckStatus, Fidelity


def check(manifest: Manifest) -> CheckResult:
    # TODO(gate): discharge per-instruction QF_BV equivalence of the pair's
    # own lowering vs the Sail per-instruction relation.
    return CheckResult(
        Fidelity.F3_lowering,
        CheckStatus.NOT_IMPLEMENTED,
        "per-instruction lowering lemmas vs Sail [TODO(gate)]",
    )
