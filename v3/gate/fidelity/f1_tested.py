"""F1 — Tested. Round-trip agrees with the Sail reference on a generated
instance suite (held-out partition for differential_only). STUB."""

from __future__ import annotations

from gurdy.core.manifest import Manifest
from gurdy.core.report import CheckResult, CheckStatus, Fidelity


def check(manifest: Manifest) -> CheckResult:
    # TODO(gate): generate instances; run the pair round-trip and the Sail
    # oracle on the held-out partition; compare on the pinned projection.
    return CheckResult(
        Fidelity.F1_tested,
        CheckStatus.NOT_IMPLEMENTED,
        "differential vs Sail held-out partition [TODO(gate)]",
    )
