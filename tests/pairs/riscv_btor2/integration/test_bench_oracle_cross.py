"""Smoke test for the bench/riscv-btor2/oracle_cross.py oracle.

The cross oracle dispatches each corpus task under every compatible
engine in the pair's solver inventory and asserts that no engine
returns a definitive verdict that disagrees with ``expected_verdict``
or with another engine. CROSS-SKIPPED is permitted (engines that
aren't present in the local environment, e.g., cvc5/pono outside the
bench Docker image, return error and are excluded from agreement).

Skipped when corpus binaries aren't built (the RV64 toolchain isn't
guaranteed in CI).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
ORACLE = REPO / "bench" / "riscv-btor2" / "oracle_cross.py"
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"


def _corpus_has_built_binaries() -> bool:
    if not CORPUS.exists():
        return False
    return any(CORPUS.glob("*/source.elf"))


@pytest.mark.skipif(not ORACLE.exists(), reason="oracle_cross script missing")
@pytest.mark.skipif(
    not _corpus_has_built_binaries(),
    reason="corpus source.elf binaries not built (run `make` in bench/riscv-btor2/corpus)",
)
def test_bench_oracle_cross_reports_no_failures_or_mismatches():
    # Full-corpus oracle_cross at the default --per-profile-timeout=10s
    # has a worst-case ~89 tasks × ~4 engines × 10s ≈ 3500s, but in
    # practice runs in ~30 min because most BMC dispatches finish
    # sub-second and only z3-spacer / pono-ind hit the cap. The 1800s
    # subprocess timeout here is the honest accommodation; the prior
    # 600s was an artefact of a smaller corpus and inductive engine
    # set.  See V2_PROGRESS.md (iter 44) for the speedup history.
    res = subprocess.run(
        [sys.executable, str(ORACLE), "--json"],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    assert res.returncode == 0, (
        f"oracle_cross exited {res.returncode}\n"
        f"stdout (tail):\n{res.stdout[-2000:]}\nstderr:\n{res.stderr}"
    )
    payload = json.loads(res.stdout)
    assert payload["failures"] == 0, payload
    assert payload["mismatches"] == 0, payload
    # At least one row should report CROSS-PASS — i.e., the cross
    # oracle is doing real work (not silently CROSS-SKIPPED across
    # the board).
    statuses = {row["summary"]["status"] for row in payload["rows"] if "summary" in row}
    assert "CROSS-PASS" in statuses, statuses
