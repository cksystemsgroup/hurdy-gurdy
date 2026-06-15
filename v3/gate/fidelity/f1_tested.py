"""F1 — Tested. The reasoning realization agrees with the Sail reference on a
generated instance suite, validated on the **held-out** partition for
``differential_only`` pairs.

WHAT THIS CHECKS (and what it does not)
=======================================
The candidate under test is the ``sail-riscv@btor2-machine`` realization's
instruction semantics (the proven execute datapaths the pair's alt path relies
on). We generate single-instruction instances over random + corner operands,
split them into train / held-out with a gate-owned key the agent cannot
compute (``oracle_service.Partitioner``), and assert the candidate's predicted
result equals the Sail emulator's on every **held-out** instance.

This is the concrete (tested) companion to the symbolic F3 lemmas: F3 proves
execute == reference for all inputs; the Step-4a cross-check pins reference to
Sail; F1 here exercises the realization against Sail end-to-end on held-out
samples through the gate's oracle discipline. It covers execute-level
behavior; the fetch/decode/pc harness is the next slice (see F2/F3 notes and
``verify.py``), so F1 deliberately stays at the instruction granularity.

If Sail (or the RISC-V toolchain) is unavailable in the environment, F1 SKIPs
with a reason rather than claiming a pass.
"""

from __future__ import annotations

from gurdy.core.manifest import Manifest
from gurdy.core.report import CheckResult, CheckStatus, Fidelity
from gate.oracle_service import Partitioner

# Gate-owned partition key. In a live gate this is secret/per-run; pinned here
# for a reproducible skeleton. The agent never sees it, so it cannot tell an
# instance's partition and cannot selectively avoid the validation set.
_GATE_KEY = b"hurdy-gurdy/v3 gate held-out key :: sail-riscv"

# How many divergences to surface in the detail string before truncating.
_MAX_SHOWN = 5


def check(manifest: Manifest) -> CheckResult:
    # F1 here is defined for reasoning pairs over the sail-riscv group that
    # rely on the btor2-machine realization as their candidate model.
    applicable = (
        manifest.kind in ("reasoning", "bridge")
        and manifest.source_group == "sail-riscv"
        and manifest.machine_tool is not None
    )
    if not applicable:
        return CheckResult(Fidelity.F1_tested, CheckStatus.SKIP,
                           "F1 differential not applicable to this hop")

    from tools.sail_btor2_machine import sail_cross

    oracle = sail_cross._load_oracle()
    try:
        records = sail_cross.collect_records(n_random=4)
    except (oracle.SailUnavailable, oracle.ToolchainUnavailable) as e:
        return CheckResult(Fidelity.F1_tested, CheckStatus.SKIP,
                           f"Sail/toolchain unavailable: {e}")

    part = Partitioner(_GATE_KEY)
    heldout = [r for r in records if part.is_heldout(r.instance_id)]
    if not heldout:
        return CheckResult(Fidelity.F1_tested, CheckStatus.SKIP,
                           "no held-out instances generated")

    mismatches = [r for r in heldout if not r.agree]
    if mismatches:
        shown = "; ".join(r.describe() for r in mismatches[:_MAX_SHOWN])
        more = "" if len(mismatches) <= _MAX_SHOWN else f" (+{len(mismatches) - _MAX_SHOWN} more)"
        return CheckResult(
            Fidelity.F1_tested, CheckStatus.FAIL,
            f"{len(mismatches)}/{len(heldout)} held-out instances diverge from Sail: {shown}{more}",
        )

    return CheckResult(
        Fidelity.F1_tested, CheckStatus.PASS,
        f"{len(heldout)} held-out instances agree with Sail v0.12 "
        f"(of {len(records)} generated; differential_only held-out discipline)",
    )
