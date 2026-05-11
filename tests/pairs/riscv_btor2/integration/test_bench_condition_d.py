"""Smoke test for the bench/riscv-btor2/condition_d_reference.py oracle.

Condition D (BENCHMARKING.md §3.D) is the source-level-verifier
baseline. For the v0.4 C-derived corpus the bench ships a CBMC
adapter; this test runs the reference oracle and asserts:

1. The oracle exits successfully (no infrastructure error).
2. At least one row reports CBMC PASS (sanity: CBMC is invoked
   and produces a comparable verdict).
3. The lowering-sensitive UB-vs-RV64 cases (0115, 0116, 0117,
   0118, 0121) appear as FAIL — that's the v0.4 condition-D
   headline and the strongest single argument the bench has
   for the pair's distinctive value over a source-level
   verifier.

Skipped when CBMC isn't installed locally (the bench Docker
image installs it; developer machines may not).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
ORACLE = REPO / "bench" / "riscv-btor2" / "condition_d_reference.py"
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"


def _corpus_has_built_binaries() -> bool:
    if not CORPUS.exists():
        return False
    return any(CORPUS.glob("*/source.elf"))


@pytest.mark.skipif(shutil.which("cbmc") is None, reason="cbmc binary not on PATH")
@pytest.mark.skipif(not ORACLE.exists(), reason="condition_d_reference script missing")
@pytest.mark.skipif(
    not _corpus_has_built_binaries(),
    reason="corpus source.elf binaries not built (run `make` in bench/riscv-btor2/corpus)",
)
def test_bench_condition_d_smoke():
    res = subprocess.run(
        [sys.executable, str(ORACLE), "--json"],
        capture_output=True, text=True, timeout=600,
    )
    # Exit code 1 is expected (the v0.4 lowering-sensitive tasks
    # FAIL CBMC by design — that's the headline finding). The
    # script itself must not crash.
    assert res.returncode in (0, 1), (
        f"oracle crashed with rc={res.returncode}\nstderr:\n{res.stderr}"
    )
    payload = json.loads(res.stdout)
    rows = payload["rows"]
    assert rows, "no C tasks discovered — corpus may be empty"

    # At least one CBMC PASS — sanity check that CBMC actually runs.
    assert any(r.get("passes") for r in rows), \
        "no CBMC PASS rows — CBMC is misconfigured or rewriter broken"

    # The lowering-sensitive UB tasks must FAIL CBMC. This is the
    # v0.4 condition-D headline finding documented in SCOPE.md §6;
    # if CBMC starts passing them, either CBMC's behaviour changed
    # (worth investigating) or the rewriter is no longer surfacing
    # the UB checks.
    expected_ub_fails = {
        "0115-c-int-overflow",
        "0116-c-divu-sentinel",
        "0117-c-int-min-div-neg-one",
        "0118-c-shift-amount-mask",
        "0121-c-mulw-truncation",
    }
    by_task = {r["task"]: r for r in rows}
    for tid in expected_ub_fails:
        if tid not in by_task:
            continue  # task not in the corpus; benign
        r = by_task[tid]
        assert not r.get("passes", True), (
            f"{tid} is expected to FAIL CBMC (UB-vs-RV64 case) but PASSed; "
            f"either CBMC behaviour changed or the rewriter regressed. Row: {r}"
        )
