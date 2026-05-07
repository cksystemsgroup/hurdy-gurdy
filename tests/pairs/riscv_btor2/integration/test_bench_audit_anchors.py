"""Smoke test for the bench/riscv-btor2/audit_anchors.py audit.

Runs the corpus-wide BMC-anchor audit and asserts no FAIL row was
emitted. SKIP rows (proved/unreachable tasks; reachable tasks
without a trace step at bad_pc) are permitted.

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
AUDIT = REPO / "bench" / "riscv-btor2" / "audit_anchors.py"
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"


def _corpus_has_built_binaries() -> bool:
    if not CORPUS.exists():
        return False
    return any(CORPUS.glob("*/source.elf"))


@pytest.mark.skipif(not AUDIT.exists(), reason="audit script missing")
@pytest.mark.skipif(
    not _corpus_has_built_binaries(),
    reason="corpus source.elf binaries not built",
)
def test_bench_audit_anchors_reports_no_failures():
    res = subprocess.run(
        [sys.executable, str(AUDIT), "--json"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert res.returncode == 0, (
        f"audit exited {res.returncode}\n"
        f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
    payload = json.loads(res.stdout)
    assert payload["failures"] == 0, payload
    statuses = {row["status"] for row in payload["rows"]}
    assert "PASS" in statuses
