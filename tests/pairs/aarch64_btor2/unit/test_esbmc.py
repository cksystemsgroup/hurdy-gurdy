"""Tests for bench/aarch64-btor2/baselines/esbmc.py — P14 ESBMC adapter.

Covers (offline, no esbmc binary required unless marked):
- Importability of the module.
- _parse_esbmc_output: FAILED, SUCCESSFUL, no-verdict, PARSING ERROR.
- run_one: skip when task.c absent; error when esbmc not on PATH.
- main: exits 2 on missing corpus; produces skip rows from real seeds.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[4]
_BASELINES = _REPO / "bench" / "aarch64-btor2" / "baselines"
_SEED_DIR = _REPO / "bench" / "aarch64-btor2" / "corpus" / "seed"

sys.path.insert(0, str(_BASELINES))

from esbmc import _parse_esbmc_output, _expected_verdict, run_one, main  # noqa: E402


# ---------------------------------------------------------------------------
# _parse_esbmc_output
# ---------------------------------------------------------------------------


def test_parse_verification_failed_returns_reachable():
    verdict, notes = _parse_esbmc_output("VERIFICATION FAILED\n", "")
    assert verdict == "reachable"
    assert "FAILED" in notes


def test_parse_verification_successful_returns_unreachable():
    verdict, notes = _parse_esbmc_output("VERIFICATION SUCCESSFUL\n", "")
    assert verdict == "unreachable"
    assert "SUCCESSFUL" in notes


def test_parse_failed_takes_priority_over_successful():
    out = "VERIFICATION SUCCESSFUL\nVERIFICATION FAILED\n"
    verdict, _ = _parse_esbmc_output(out, "")
    assert verdict == "reachable"


def test_parse_no_verdict_returns_error():
    verdict, notes = _parse_esbmc_output("some random output\n", "")
    assert verdict == "error"
    assert "no verdict" in notes


def test_parse_parsing_error_in_stderr():
    verdict, notes = _parse_esbmc_output("", "PARSING ERROR: foo.c:1")
    assert verdict == "error"
    assert "PARSING ERROR" in notes


# ---------------------------------------------------------------------------
# run_one — offline paths (no esbmc binary needed)
# ---------------------------------------------------------------------------


def test_run_one_no_task_c_returns_skip(tmp_path: pathlib.Path):
    task_dir = tmp_path / "0099-fake-task"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "0099-fake-task"\n[expected]\nverdict = "unreachable"\n'
    )
    row = run_one(task_dir)
    assert row["verdict"] == "skip"
    assert row["tool"] == "esbmc"
    assert row["task"] == "0099-fake-task"
    assert "no task.c" in row["notes"]


def test_run_one_esbmc_not_on_path_returns_error(tmp_path: pathlib.Path, monkeypatch):
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
    for field in ("tool", "task", "verdict", "wall_s", "rss_mb",
                  "expected", "correct", "cmd", "raw_excerpt", "notes"):
        assert field in row, f"missing field: {field}"


# ---------------------------------------------------------------------------
# main — offline paths
# ---------------------------------------------------------------------------


def test_main_missing_corpus_returns_2():
    rc = main(["--corpus", "/nonexistent_corpus_dir_xyz"])
    assert rc == 2


def test_main_real_seeds_with_esbmc_not_on_path(capsys, monkeypatch):
    """When esbmc not on PATH, main produces one error row per C-source seed."""
    monkeypatch.setattr(shutil, "which", lambda _: None)
    rc = main([
        "--corpus", str(_SEED_DIR),
        "--max-tasks", "3",
    ])
    assert rc == 0
    out, _ = capsys.readouterr()
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert len(rows) <= 3
    for row in rows:
        assert row["tool"] == "esbmc"
        assert row["verdict"] in ("error", "skip")
