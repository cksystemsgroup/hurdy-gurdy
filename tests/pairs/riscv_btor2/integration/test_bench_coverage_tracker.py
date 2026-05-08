"""Smoke test for bench/riscv-btor2/coverage_tracker.py.

Runs the tracker against the live corpus and asserts that every
existing task is counted, plus a few invariants the corpus
satisfies as of the v0.1.2 baseline. Skipped when the corpus
isn't built (the script reads task.toml + spec.json, not source.elf,
but we keep the skip in case the bench dir is absent in CI
environments).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "bench" / "riscv-btor2" / "coverage_tracker.py"
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"


@pytest.mark.skipif(not SCRIPT.exists(), reason="coverage_tracker missing")
@pytest.mark.skipif(not CORPUS.exists(), reason="corpus dir missing")
def test_coverage_tracker_counts_corpus_tasks(tmp_path):
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)

    # Every directory with a task.toml + spec.json should be counted.
    expected_n = sum(
        1 for d in CORPUS.iterdir()
        if d.is_dir() and (d/"task.toml").exists() and (d/"spec.json").exists()
    )
    assert payload["n_tasks"] == expected_n

    # Most tasks use RegisterAt; the spacer-based global-invariant
    # tasks (0020, 0021, 0045, 0046, 0047) leave observables empty.
    # Sanity-check the tracker spots RegisterAt as the dominant
    # observable type.
    assert payload["observable_use"]["RegisterAt"] >= expected_n - 6

    # Overall utilization is a fraction in [0, 1].
    assert 0.0 <= payload["overall_utilization"] <= 1.0
