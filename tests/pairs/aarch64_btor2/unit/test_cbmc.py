"""Tests for bench/aarch64-btor2/baselines/cbmc.py — P14b CBMC adapter.

Covers (offline, no cbmc binary required unless marked @pytest.mark.integration):
- _parse_cbmc_output: FAILED, SUCCESSFUL, unwinding-assertion edge case,
  PARSING ERROR, no-verdict, **** ERROR.
- run_one: skip when no C source; error when cbmc not on PATH.
- run_one: schema fields present.
- main: exits 2 on missing corpus.
- Integration: seed 0001-c-loopsum-o0 — CBMC should agree (unreachable).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[4]
_BASELINES = _REPO / "bench" / "aarch64-btor2" / "baselines"
_SEED_DIR = _REPO / "bench" / "aarch64-btor2" / "corpus" / "seed"

sys.path.insert(0, str(_BASELINES))

from cbmc import _parse_cbmc_output, _expected_verdict, run_one, main  # noqa: E402


# ---------------------------------------------------------------------------
# _parse_cbmc_output
# ---------------------------------------------------------------------------


def test_parse_verification_failed_returns_reachable():
    verdict, notes = _parse_cbmc_output("VERIFICATION FAILED\n", "")
    assert verdict == "reachable"
    assert "FAILED" in notes


def test_parse_verification_successful_returns_unreachable():
    verdict, notes = _parse_cbmc_output("VERIFICATION SUCCESSFUL\n", "")
    assert verdict == "unreachable"


def test_parse_failed_takes_priority_over_successful():
    out = "VERIFICATION SUCCESSFUL\nVERIFICATION FAILED\n"
    verdict, _ = _parse_cbmc_output(out, "")
    assert verdict == "reachable"


def test_parse_successful_with_unwinding_assertion_returns_unknown():
    out = "VERIFICATION SUCCESSFUL\n**** WARNING: unwinding assertion\n"
    verdict, notes = _parse_cbmc_output(out, "")
    assert verdict == "unknown"
    assert "unwinding" in notes


def test_parse_parsing_error_returns_error():
    verdict, notes = _parse_cbmc_output("", "PARSING ERROR: foo.c:1")
    assert verdict == "error"
    assert "PARSING ERROR" in notes


def test_parse_cprover_error_returns_error():
    verdict, notes = _parse_cbmc_output("**** ERROR: something bad\n", "")
    assert verdict == "error"
    assert "ERROR" in notes


def test_parse_no_verdict_returns_error():
    verdict, notes = _parse_cbmc_output("some random output\n", "")
    assert verdict == "error"
    assert "no verdict" in notes


# ---------------------------------------------------------------------------
# run_one — offline paths (no cbmc binary needed)
# ---------------------------------------------------------------------------


def test_run_one_no_c_source_returns_skip(tmp_path: pathlib.Path):
    task_dir = tmp_path / "0099-fake-task"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "0099-fake-task"\n[expected]\nverdict = "unreachable"\n'
    )
    row = run_one(task_dir)
    assert row["verdict"] == "skip"
    assert row["tool"] == "cbmc"
    assert row["task"] == "0099-fake-task"
    assert "no task.c" in row["notes"]


def test_run_one_cbmc_not_on_path_returns_error(
    tmp_path: pathlib.Path, monkeypatch
):
    task_dir = tmp_path / "0099-fake-task"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "0099-fake-task"\n[expected]\nverdict = "unreachable"\n'
    )
    (task_dir / "task.c").write_text("void _start(void) {}\n")
    monkeypatch.setattr(shutil, "which", lambda _: None)
    row = run_one(task_dir)
    assert row["verdict"] == "error"
    assert "not on PATH" in row["notes"]


def test_run_one_schema_fields_present(tmp_path: pathlib.Path):
    task_dir = tmp_path / "0099-fake-task"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "0099-fake-task"\n[expected]\nverdict = "unreachable"\n'
    )
    row = run_one(task_dir)
    for field in (
        "tool", "task", "verdict", "wall_s", "rss_mb",
        "expected", "correct", "cmd", "raw_excerpt", "notes",
    ):
        assert field in row, f"missing field: {field}"


# ---------------------------------------------------------------------------
# main — offline paths
# ---------------------------------------------------------------------------


def test_main_missing_corpus_returns_2():
    rc = main(["--corpus", "/nonexistent_corpus_dir_xyz"])
    assert rc == 2


def test_main_real_seeds_with_cbmc_not_on_path(capsys, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    rc = main(["--corpus", str(_SEED_DIR), "--max-tasks", "3"])
    assert rc == 0
    out, _ = capsys.readouterr()
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert len(rows) <= 3
    for row in rows:
        assert row["tool"] == "cbmc"
        assert row["verdict"] in ("error", "skip")


# ---------------------------------------------------------------------------
# Integration — requires cbmc on PATH
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("cbmc") is None, reason="cbmc not on PATH")
def test_cbmc_seed_0001_loopsum_unreachable():
    """CBMC agrees with harness on 0001: sum loop, trap unreachable."""
    task_dir = _SEED_DIR / "0001-c-loopsum-o0"
    if not task_dir.exists():
        pytest.skip("seed 0001-c-loopsum-o0 not present")
    row = run_one(task_dir, timeout_s=60, unwind=20)
    assert row["verdict"] == "unreachable", (
        f"expected unreachable, got {row['verdict']!r}: {row['notes']}"
    )
    assert row["correct"] is True
