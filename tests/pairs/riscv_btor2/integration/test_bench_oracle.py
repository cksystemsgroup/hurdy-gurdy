"""Smoke test for the bench/riscv-btor2/oracle.py oracle.

The oracle runs the framework's ``check`` tool against every corpus
task and reports agreement with the task's pre-registered
``expected.verdict``. This test invokes the script, captures its
stdout, and asserts that no FAIL row was emitted (SKIP rows are
permitted — they indicate inconclusive evidence on a default-input
binding, not a soundness bug).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
ORACLE = REPO / "bench" / "riscv-btor2" / "oracle.py"


@pytest.mark.skipif(not ORACLE.exists(), reason="oracle script missing")
def test_bench_oracle_reports_no_failures():
    res = subprocess.run(
        [sys.executable, str(ORACLE), "--json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert res.returncode == 0, (
        f"oracle exited {res.returncode}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
    payload = json.loads(res.stdout)
    assert payload["failures"] == 0, payload
    # We expect at least one PASS row from the corpus.
    statuses = {row["status"] for row in payload["rows"]}
    assert "PASS" in statuses
