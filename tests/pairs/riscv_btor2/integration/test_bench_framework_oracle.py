"""Smoke test for the bench/riscv-btor2/framework_oracle.py oracle.

The framework oracle is the no-LLM "condition B0" of the benchmark:
for every corpus task it loads the pre-registered ``spec.json``,
compiles, dispatches to the spec's solver, lifts, and compares the
verdict to ``expected.verdict`` from ``task.toml``. This test
invokes the script in JSON mode and asserts that no FAIL row was
emitted (SKIP rows are permitted -- they indicate the solver
returned ``unknown`` / ``error``, not a label/framework
disagreement).

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
ORACLE = REPO / "bench" / "riscv-btor2" / "framework_oracle.py"
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"


def _corpus_has_built_binaries() -> bool:
    if not CORPUS.exists():
        return False
    return any(CORPUS.glob("*/source.elf"))


@pytest.mark.skipif(not ORACLE.exists(), reason="framework_oracle script missing")
@pytest.mark.skipif(
    not _corpus_has_built_binaries(),
    reason="corpus source.elf binaries not built (run `make` in bench/riscv-btor2/corpus)",
)
def test_bench_framework_oracle_reports_no_failures():
    res = subprocess.run(
        [sys.executable, str(ORACLE), "--json"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert res.returncode == 0, (
        f"framework oracle exited {res.returncode}\n"
        f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
    payload = json.loads(res.stdout)
    assert payload["failures"] == 0, payload
    statuses = {row["status"] for row in payload["rows"]}
    assert "PASS" in statuses
