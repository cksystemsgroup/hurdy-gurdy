"""Smoke test for the bench/riscv-btor2/calibration.py script.

Builds a tiny synthetic transcripts directory pointing at the real
corpus, runs the calibration script, and asserts that the §5
metrics (verdict accuracy, hallucination rate, Brier score, ECE)
come out as expected for hand-constructed cells.

The synthetic cells deliberately mix correct, wrong-confident, and
unknown verdicts to exercise every branch of the metric code.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "bench" / "riscv-btor2" / "calibration.py"
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"


def _make_transcript(path: Path, observed: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "prompt": "(test stub)",
        "tools": None,
        "response_text": "(test stub)",
        "tool_call_log": [],
        "observed": observed,
        "seed": int(path.stem.split("-", 1)[1]),
    }))


@pytest.mark.skipif(not SCRIPT.exists(), reason="calibration script missing")
@pytest.mark.skipif(not CORPUS.exists(), reason="corpus dir missing")
def test_calibration_reports_expected_metrics(tmp_path: Path):
    tx = tmp_path / "_transcripts"

    # Cell 1: 0001-x0-write-dropped  expected=unreachable
    #         observed correct, very confident. Counts: correct=1.
    _make_transcript(
        tx / "0001-x0-write-dropped" / "A" / "slot_test" / "seed-0.json",
        {"verdict": "unreachable", "confidence": 0.95,
         "reason": "synthetic", "witness": None, "lift": None},
    )
    # Cell 2: 0001-x0-write-dropped same task, wrong-with-high-confidence.
    #         Counts as a hallucination.
    _make_transcript(
        tx / "0001-x0-write-dropped" / "A" / "slot_test" / "seed-1.json",
        {"verdict": "reachable", "confidence": 0.9,
         "reason": "synthetic-wrong",
         "witness": {"bad_pc": 0, "anchor_step": 0,
                     "final_regs": {}, "executed_pcs": []},
         "lift": None},
    )
    # Cell 3: an unknown -- excluded from accuracy, counted as refusal.
    _make_transcript(
        tx / "0001-x0-write-dropped" / "A" / "slot_test" / "seed-2.json",
        {"verdict": "unknown", "confidence": 0.3,
         "reason": "synthetic-unknown", "witness": None, "lift": None},
    )

    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--transcripts-dir", str(tx),
         "--corpus", str(CORPUS),
         "--json"],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, res.stderr

    payload = json.loads(res.stdout)
    assert len(payload["summaries"]) == 1
    s = payload["summaries"][0]

    assert s["condition"] == "A"
    assert s["model_slot"] == "slot_test"
    assert s["n_total"] == 3
    assert s["n_unknown"] == 1
    assert s["n_correct"] == 1
    assert s["n_wrong"] == 1
    assert s["accuracy"] == pytest.approx(0.5, abs=1e-9)  # 1/2 scored correct
    # 1 hallucination (cell 2: wrong + conf >= 0.8) out of 3 total cells
    assert s["hallucination_rate"] == pytest.approx(1 / 3, abs=1e-9)
    # Brier over the 2 scored cells: (0.95-1)^2 + (0.9-0)^2 = 0.0025 + 0.81 = 0.8125
    # mean = 0.40625
    assert s["brier"] == pytest.approx(0.40625, abs=1e-9)
    # ECE: bucket [0.9, 1.0) holds both scored cells (mean_conf=0.925, frac_correct=0.5)
    # gap = |0.5 - 0.925| = 0.425; ECE = (2/2)*0.425 = 0.425
    assert s["ece"] == pytest.approx(0.425, abs=1e-9)
