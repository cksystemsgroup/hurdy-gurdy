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

    # Most tasks use RegisterAt as the observable. Two classes of
    # exceptions:
    #
    # 1. spacer-based global-invariant tasks (0020, 0021, 0045–0047)
    #    that leave observables empty — the property itself is the
    #    invariant.
    # 2. v0.4+ C-source tasks (0100+) whose auto-generated spec.json
    #    expresses the property as `eq(pc, const(trap_pc))` and ships
    #    no separate observable. (Adding a redundant Executed/RegisterAt
    #    observable wouldn't tell the LLM anything the property doesn't
    #    already say.)
    #
    # Compute the cap dynamically so this test doesn't drift each time
    # the corpus grows in either direction.
    expected_no_observables = sum(
        1 for d in CORPUS.iterdir()
        if d.is_dir() and (d/"spec.json").exists()
        and not json.loads((d/"spec.json").read_text())
            .get("fields", {}).get("observables", [])
    )
    assert payload["observable_use"]["RegisterAt"] >= expected_n - expected_no_observables

    # Overall utilization is a fraction in [0, 1].
    assert 0.0 <= payload["overall_utilization"] <= 1.0
