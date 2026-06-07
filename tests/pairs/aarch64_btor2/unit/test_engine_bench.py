"""Tests for bench/aarch64-btor2/engine_bench.py — P11 wall-clock bench."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from io import StringIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[4]
_BENCH_DIR = _REPO / "bench" / "aarch64-btor2"
sys.path.insert(0, str(_BENCH_DIR))

import engine_bench as _eb  # noqa: E402
from engine_bench import (  # noqa: E402
    _measure,
    _profiles,
    _row_text,
    main,
)
from oracle_cross import (  # noqa: E402
    BMC_PROFILES,
    INDUCTIVE_PROFILES,
    Profile,
)

_SEED_DIR = _BENCH_DIR / "corpus" / "seed"
_TASK_0001 = _SEED_DIR / "0001-c-loopsum-o0"
_TASK_0002 = _SEED_DIR / "0002-c-loopsum-o1"

_Z3_AVAILABLE = pytest.mark.skipif(
    importlib.util.find_spec("z3") is None,
    reason="z3 not installed",
)


# ---------------------------------------------------------------------------
# _profiles
# ---------------------------------------------------------------------------


def test_profiles_bmc_engine_returns_bmc_profiles():
    result = _profiles("z3-bmc", inductive_only=False, bmc_only=False)
    assert result is BMC_PROFILES


def test_profiles_bmc_engine_inductive_only_returns_empty():
    result = _profiles("z3-bmc", inductive_only=True, bmc_only=False)
    assert result == ()


def test_profiles_inductive_engine_returns_inductive_profiles():
    result = _profiles("z3-spacer", inductive_only=False, bmc_only=False)
    assert result is INDUCTIVE_PROFILES


def test_profiles_inductive_engine_bmc_only_returns_empty():
    result = _profiles("z3-spacer", inductive_only=False, bmc_only=True)
    assert result == ()


def test_profiles_inductive_engine_inductive_only_returns_inductive():
    result = _profiles("z3-spacer", inductive_only=True, bmc_only=False)
    assert result is INDUCTIVE_PROFILES


# ---------------------------------------------------------------------------
# _row_text
# ---------------------------------------------------------------------------


def test_row_text_measured_engine_shows_ms():
    results = {
        "z3-bmc": {
            "engine": "z3-bmc",
            "verdict": "unreachable",
            "reason": None,
            "samples": [0.123],
            "median": 0.123,
            "min": 0.123,
        }
    }
    text = _row_text("my-task", results)
    assert "z3-bmc=" in text
    assert "ms" in text
    assert "SKIP" not in text


def test_row_text_unknown_verdict_shows_skip():
    results = {
        "bitwuzla": {
            "engine": "bitwuzla",
            "verdict": "unknown",
            "reason": "bitwuzla not on PATH",
            "samples": [0.001],
            "median": 0.001,
            "min": 0.001,
        }
    }
    text = _row_text("my-task", results)
    assert "bitwuzla=SKIP" in text


def test_row_text_fixed_column_order():
    results = {
        "cvc5": {"engine": "cvc5", "verdict": "unreachable", "reason": None,
                 "samples": [0.2], "median": 0.2, "min": 0.2},
        "z3-bmc": {"engine": "z3-bmc", "verdict": "unreachable", "reason": None,
                   "samples": [0.1], "median": 0.1, "min": 0.1},
    }
    text = _row_text("task", results)
    assert text.index("z3-bmc") < text.index("cvc5")


# ---------------------------------------------------------------------------
# main — SKIP paths (no ELF)
# ---------------------------------------------------------------------------


def test_main_skips_task_without_elf(capsys):
    rc = main(["--task", "0002-c-loopsum-o1"])
    out, _ = capsys.readouterr()
    assert rc == 0
    assert "SKIP" in out
    assert "0002-c-loopsum-o1" in out


def test_main_json_skip_for_no_elf():
    rc = main(["--task", "0002-c-loopsum-o1", "--json"])
    # should succeed (SKIP ≠ error)
    assert rc == 0


def test_main_json_skip_row_structure(capsys):
    rc = main(["--task", "0002-c-loopsum-o1", "--json"])
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert data["rows"][0]["status"] == "SKIP"
    assert rc == 0


def test_main_no_task_match_returns_2(capsys):
    rc = main(["--task", "does-not-exist-xyz"])
    _, err = capsys.readouterr()
    assert rc == 2


# ---------------------------------------------------------------------------
# main — live seed 0001 (z3 required)
# ---------------------------------------------------------------------------


@_Z3_AVAILABLE
def test_main_seed_0001_z3bmc_text(capsys):
    rc = main(["--task", "0001-c-loopsum-o0", "--repeat", "1",
               "--corpus", str(_SEED_DIR)])
    out, _ = capsys.readouterr()
    assert rc == 0
    assert "0001-c-loopsum-o0" in out
    assert "z3-bmc=" in out


@_Z3_AVAILABLE
def test_main_seed_0001_json_output(capsys):
    rc = main(["--task", "0001-c-loopsum-o0", "--repeat", "1", "--json",
               "--corpus", str(_SEED_DIR)])
    out, _ = capsys.readouterr()
    assert rc == 0
    data = json.loads(out)
    rows = [r for r in data["rows"] if r.get("task") == "0001-c-loopsum-o0"]
    assert rows, "0001-c-loopsum-o0 missing from JSON output"
    assert "engines" in rows[0]


@_Z3_AVAILABLE
def test_main_full_corpus_skips_seeds_without_elf(capsys):
    rc = main(["--repeat", "1", "--corpus", str(_SEED_DIR)])
    out, _ = capsys.readouterr()
    assert rc == 0
    skip_lines = [l for l in out.splitlines() if l.startswith("SKIP")]
    assert len(skip_lines) >= 10, f"expected ≥10 SKIP rows, got {len(skip_lines)}"
