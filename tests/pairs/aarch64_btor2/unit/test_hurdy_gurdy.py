"""Tests for bench/aarch64-btor2/baselines/hurdy_gurdy.py — P15.

Covers (offline, no solver required unless marked @pytest.mark.integration):
- _lifted_to_schema: reachable, unreachable, proved, unknown, lift-error, unrecognized.
- run_one: skip when no spec.json (ELF not yet compiled).
- run_one: error row on pipeline exception.
- run_one: schema fields present on all output rows.
- main: exits 2 on missing corpus.
- main: runs all tasks up to --max-tasks.
- Integration: seed 0001-c-loopsum-o0 should yield correct=true, verdict=unreachable.
"""

from __future__ import annotations

import json
import pathlib
import sys
from unittest import mock

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[4]
_BASELINES = _REPO / "bench" / "aarch64-btor2" / "baselines"
_SEED_DIR = _REPO / "bench" / "aarch64-btor2" / "corpus" / "seed"

sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_BASELINES))

from hurdy_gurdy import _lifted_to_schema, run_one, main  # noqa: E402


# ---------------------------------------------------------------------------
# _lifted_to_schema
# ---------------------------------------------------------------------------


def test_lifted_to_schema_reachable():
    v, n = _lifted_to_schema("reachable")
    assert v == "reachable"
    assert "reachable" in n


def test_lifted_to_schema_unreachable():
    v, n = _lifted_to_schema("unreachable")
    assert v == "unreachable"
    assert "unreachable" in n


def test_lifted_to_schema_proved():
    v, n = _lifted_to_schema("proved")
    assert v == "proved"
    assert "proved" in n


def test_lifted_to_schema_unknown():
    v, n = _lifted_to_schema("unknown")
    assert v == "unknown"


def test_lifted_to_schema_lift_error_returns_error():
    v, n = _lifted_to_schema("lift-error: translation failed")
    assert v == "error"
    assert "lift-error" in n


def test_lifted_to_schema_unrecognized_returns_error():
    v, n = _lifted_to_schema("bogus-verdict")
    assert v == "error"
    assert "unrecognized" in n
    assert "bogus-verdict" in n


# ---------------------------------------------------------------------------
# run_one — offline paths (no solver needed)
# ---------------------------------------------------------------------------


def test_run_one_no_spec_json_returns_skip(tmp_path: pathlib.Path):
    """Tasks without spec.json (ELF not compiled) emit a single skip row."""
    task_dir = tmp_path / "0099-fake-task"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "0099-fake-task"\n[expected]\nverdict = "unreachable"\n'
    )
    rows = run_one(task_dir)
    assert len(rows) == 1
    row = rows[0]
    assert row["verdict"] == "skip"
    assert row["tool"] == "hurdy-gurdy"
    assert row["task"] == "0099-fake-task"
    assert "spec.json" in row["notes"]


def test_run_one_pipeline_error_returns_error_row(tmp_path: pathlib.Path):
    """When the pipeline raises, run_one returns an error row (not an exception)."""
    task_dir = tmp_path / "0099-fake-task"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "0099-fake-task"\n[expected]\nverdict = "unreachable"\n'
    )
    # Write a malformed spec.json to trigger a pipeline error.
    (task_dir / "spec.json").write_text('{"pair":"aarch64-btor2","fields":{}}')
    rows = run_one(task_dir)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "error"
    assert rows[0]["tool"] == "hurdy-gurdy"


def test_run_one_schema_fields_present(tmp_path: pathlib.Path):
    """Every row must have the 10 Pareto-schema fields."""
    task_dir = tmp_path / "0099-schema-check"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "0099-schema-check"\n[expected]\nverdict = "unreachable"\n'
    )
    rows = run_one(task_dir)
    assert rows, "run_one must return at least one row"
    required = {"tool", "task", "verdict", "wall_s", "rss_mb",
                "expected", "correct", "cmd", "raw_excerpt", "notes"}
    for row in rows:
        missing = required - set(row)
        assert not missing, f"row missing fields: {missing}"


# ---------------------------------------------------------------------------
# main — offline paths
# ---------------------------------------------------------------------------


def test_main_missing_corpus_returns_2():
    rc = main(["--corpus", "/nonexistent_corpus_dir_xyz"])
    assert rc == 2


def test_main_max_tasks_limits_output(capsys):
    """main --max-tasks 2 emits at most 2 JSONL lines."""
    rc = main(["--corpus", str(_SEED_DIR), "--max-tasks", "2"])
    assert rc == 0
    out, _ = capsys.readouterr()
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert len(rows) <= 2


def test_main_task_filter_selects_matching(capsys):
    """--task substring filter restricts output to matching task dirs."""
    rc = main(["--corpus", str(_SEED_DIR), "--task", "0001", "--max-tasks", "5"])
    assert rc == 0
    out, _ = capsys.readouterr()
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]
    for row in rows:
        assert "0001" in row["task"]


def test_main_all_rows_have_tool_hurdy_gurdy(capsys):
    """Every row emitted by main must carry tool=hurdy-gurdy."""
    rc = main(["--corpus", str(_SEED_DIR), "--max-tasks", "5"])
    assert rc == 0
    out, _ = capsys.readouterr()
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert rows
    for row in rows:
        assert row["tool"] == "hurdy-gurdy"


# ---------------------------------------------------------------------------
# Integration — requires z3 on PATH (z3-bmc engine used by seed 0001)
# ---------------------------------------------------------------------------


def _z3_importable() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _z3_importable(), reason="z3 not installed in this Python environment")
def test_seed_0001_loopsum_unreachable():
    """Full pipeline on seed 0001 should yield correct=True, verdict=unreachable."""
    task_dir = _SEED_DIR / "0001-c-loopsum-o0"
    if not task_dir.exists() or not (task_dir / "spec.json").exists():
        pytest.skip("seed 0001-c-loopsum-o0 not present or not compiled")
    rows = run_one(task_dir, timeout_s=60)
    assert len(rows) == 1
    row = rows[0]
    assert row["verdict"] == "unreachable", (
        f"expected unreachable, got {row['verdict']!r}: {row['notes']}"
    )
    assert row["correct"] is True
    assert row["tool"] == "hurdy-gurdy"
