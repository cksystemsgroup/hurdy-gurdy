"""Tests for bench/aarch64-btor2/oracle_cross.py — P10 cross-engine oracle."""

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

import oracle_cross as _oc  # noqa: E402
from oracle_cross import (  # noqa: E402
    BMC_PROFILES,
    INDUCTIVE_PINNED,
    INDUCTIVE_PROFILES,
    Profile,
    profiles_for,
    render_text,
    summarize,
    verdict_satisfies,
    verdicts_agree,
)

_SEED_DIR = _BENCH_DIR / "corpus" / "seed"
_TASK_0001 = _SEED_DIR / "0001-c-loopsum-o0"
_TASK_0002 = _SEED_DIR / "0002-c-loopsum-o1"

_Z3_AVAILABLE = pytest.mark.skipif(
    importlib.util.find_spec("z3") is None,
    reason="z3 not installed",
)


# ---------------------------------------------------------------------------
# profiles_for
# ---------------------------------------------------------------------------


def test_profiles_for_bmc_engine_returns_bmc_profiles():
    result = profiles_for("z3-bmc")
    assert result is BMC_PROFILES
    assert {p.label for p in result} == {"z3-bmc", "bitwuzla", "cvc5", "pono"}


def test_profiles_for_bitwuzla_returns_bmc_profiles():
    assert profiles_for("bitwuzla") is BMC_PROFILES


def test_profiles_for_z3_spacer_returns_inductive_profiles():
    result = profiles_for("z3-spacer")
    assert result is INDUCTIVE_PROFILES
    assert {p.label for p in result} == {"z3-spacer", "pono-ind"}


def test_inductive_profiles_pono_ind_has_engine_extra():
    pono_ind = next(p for p in INDUCTIVE_PROFILES if p.label == "pono-ind")
    assert pono_ind.extras.get("engine") == "ind"
    assert pono_ind.bound_fallback == 10


def test_no_pono_docker_profiles():
    all_labels = {p.label for p in BMC_PROFILES} | {p.label for p in INDUCTIVE_PROFILES}
    assert "pono-docker" not in all_labels
    assert "pono-ind-docker" not in all_labels


# ---------------------------------------------------------------------------
# verdict_satisfies
# ---------------------------------------------------------------------------


def test_verdict_satisfies_reachable_match():
    assert verdict_satisfies("reachable", "reachable") is True


def test_verdict_satisfies_unreachable_match():
    assert verdict_satisfies("unreachable", "unreachable") is True


def test_verdict_satisfies_unreachable_accepts_proved():
    assert verdict_satisfies("unreachable", "proved") is True


def test_verdict_satisfies_unknown_never_satisfies():
    assert verdict_satisfies("reachable", "unknown") is False
    assert verdict_satisfies("unreachable", "unknown") is False


def test_verdict_satisfies_error_never_satisfies():
    assert verdict_satisfies("unreachable", "error") is False


def test_verdict_satisfies_cross_mismatch():
    assert verdict_satisfies("reachable", "unreachable") is False
    assert verdict_satisfies("unreachable", "reachable") is False


# ---------------------------------------------------------------------------
# verdicts_agree
# ---------------------------------------------------------------------------


def test_verdicts_agree_both_reachable():
    assert verdicts_agree("reachable", "reachable") is True


def test_verdicts_agree_both_unreachable():
    assert verdicts_agree("unreachable", "unreachable") is True


def test_verdicts_agree_unreachable_and_proved():
    assert verdicts_agree("unreachable", "proved") is True


def test_verdicts_disagree_reachable_vs_unreachable():
    assert verdicts_agree("reachable", "unreachable") is False


def test_verdicts_agree_unknown_always_agrees():
    assert verdicts_agree("unknown", "reachable") is True
    assert verdicts_agree("unknown", "unreachable") is True
    assert verdicts_agree("error", "reachable") is True


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------


def _make_row(verdict: str, label: str = "z3-bmc") -> dict[str, Any]:
    return {"label": label, "engine": label, "verdict": verdict, "elapsed": 0.1, "reason": None}


def test_summarize_cross_pass_single_confirm():
    rows = [_make_row("unreachable")]
    result = summarize("unreachable", rows)
    assert result["status"] == "CROSS-PASS"
    assert result["n_confirm"] == 1
    assert result["n_disagree"] == 0
    assert result["n_skipped"] == 0


def test_summarize_cross_pass_with_skips():
    rows = [_make_row("unreachable", "z3-bmc"), _make_row("unknown", "bitwuzla")]
    result = summarize("unreachable", rows)
    assert result["status"] == "CROSS-PASS"
    assert result["n_confirm"] == 1
    assert result["n_skipped"] == 1


def test_summarize_cross_fail_disagreement_with_expected():
    rows = [_make_row("reachable")]
    result = summarize("unreachable", rows)
    assert result["status"] == "CROSS-FAIL"
    assert result["n_disagree"] == 1


def test_summarize_cross_mismatch_engine_conflict():
    rows = [_make_row("reachable", "z3-bmc"), _make_row("unreachable", "bitwuzla")]
    result = summarize("reachable", rows)
    assert result["status"] == "CROSS-MISMATCH"


def test_summarize_cross_skipped_all_unknown():
    rows = [_make_row("unknown", "z3-bmc"), _make_row("error", "bitwuzla")]
    result = summarize("unreachable", rows)
    assert result["status"] == "CROSS-SKIPPED"
    assert result["n_skipped"] == 2
    assert result["n_confirm"] == 0
    assert result["n_disagree"] == 0


def test_summarize_preserves_engine_rows():
    rows = [_make_row("unreachable")]
    result = summarize("unreachable", rows)
    assert result["engines"] == rows


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------


def test_render_text_pass_row():
    summary = summarize("unreachable", [_make_row("unreachable")])
    text = render_text("0001-c-loopsum-o0", "unreachable", summary)
    assert "TASK 0001-c-loopsum-o0" in text
    assert "PASS" in text
    assert "CROSS-PASS" in text


def test_render_text_skip_row():
    summary = summarize("unreachable", [_make_row("unknown")])
    text = render_text("0001-x", "unreachable", summary)
    assert "SKIP" in text
    assert "CROSS-SKIPPED" in text


def test_render_text_fail_row():
    summary = summarize("unreachable", [_make_row("reachable")])
    text = render_text("0001-x", "unreachable", summary)
    assert "FAIL" in text
    assert "CROSS-FAIL" in text


def test_render_text_counts_in_summary_line():
    rows = [_make_row("unreachable", "z3-bmc"), _make_row("unknown", "bitwuzla")]
    summary = summarize("unreachable", rows)
    text = render_text("x", "unreachable", summary)
    assert "1 confirm" in text
    assert "0 disagree" in text
    assert "1 skipped" in text


# ---------------------------------------------------------------------------
# CLI — SKIP path (tasks without source.elf)
# ---------------------------------------------------------------------------


def test_main_skips_tasks_without_elf(tmp_path):
    """Tasks with task.toml but no source.elf produce SKIP rows, exit 0."""
    seed = tmp_path / "seed"
    t = seed / "0002-c-loopsum-o1"
    t.mkdir(parents=True)
    (t / "task.toml").write_text(
        '[task]\nid = "0002-c-loopsum-o1"\n\n[expected]\nverdict = "unreachable"\n'
    )
    # No spec.json, no source.elf

    ret = _oc.main(["--corpus", str(seed)])
    assert ret == 0


def test_main_json_emits_skip_for_no_elf(tmp_path, capsys):
    seed = tmp_path / "seed"
    t = seed / "0002-no-elf"
    t.mkdir(parents=True)
    (t / "task.toml").write_text(
        '[task]\nid = "0002-no-elf"\n\n[expected]\nverdict = "unreachable"\n'
    )

    ret = _oc.main(["--corpus", str(seed), "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["failures"] == 0
    assert data["mismatches"] == 0
    assert len(data["rows"]) == 1
    assert data["rows"][0]["status"] == "SKIP"
    assert data["rows"][0]["task"] == "0002-no-elf"


def test_main_no_task_match_returns_2(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    ret = _oc.main(["--corpus", str(seed), "--task", "nonexistent"])
    assert ret == 2


# ---------------------------------------------------------------------------
# CLI — seed 0001 scaffold path (z3 required)
# ---------------------------------------------------------------------------


@_Z3_AVAILABLE
def test_main_seed_0001_z3bmc_cross_pass(capsys):
    """Seed 0001 with only z3-bmc selected should CROSS-PASS or CROSS-SKIPPED."""
    ret = _oc.main([
        "--corpus", str(_SEED_DIR),
        "--task", "0001-c-loopsum-o0",
        "--engines", "z3-bmc",
        "--per-profile-timeout", "60",
    ])
    captured = capsys.readouterr()
    # Must not CROSS-FAIL or CROSS-MISMATCH
    assert ret == 0
    assert "CROSS-PASS" in captured.out or "CROSS-SKIPPED" in captured.out


@_Z3_AVAILABLE
def test_main_seed_0001_json_output(capsys):
    """--json flag emits valid JSON with summary key for seed 0001."""
    ret = _oc.main([
        "--corpus", str(_SEED_DIR),
        "--task", "0001-c-loopsum-o0",
        "--engines", "z3-bmc",
        "--per-profile-timeout", "60",
        "--json",
    ])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "rows" in data
    assert "failures" in data
    assert data["failures"] == 0
    task_row = next(r for r in data["rows"] if r.get("task") == "0001-c-loopsum-o0")
    assert "summary" in task_row
    assert task_row["summary"]["status"] in ("CROSS-PASS", "CROSS-SKIPPED")


@_Z3_AVAILABLE
def test_main_full_corpus_skips_seeds_without_elf(capsys):
    """Running with --engines z3-bmc: 0002-0011 SKIP (no ELF); 0001 runs z3-bmc;
    0012/0013 (spacer tasks) have ELFs but their profiles don't include z3-bmc,
    so they appear as CROSS-SKIPPED task rows."""
    ret = _oc.main([
        "--corpus", str(_SEED_DIR),
        "--engines", "z3-bmc",
        "--per-profile-timeout", "60",
        "--json",
    ])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    skip_rows = [r for r in data["rows"] if r.get("status") == "SKIP"]
    task_rows = [r for r in data["rows"] if "summary" in r]
    assert len(skip_rows) == 10   # 0002-0011 have no ELF
    assert len(task_rows) == 3    # 0001 (bmc pass), 0012+0013 (spacer — z3-bmc filtered out)
    bmc_row = next(r for r in task_rows if r.get("task") == "0001-c-loopsum-o0")
    assert bmc_row["summary"]["status"] in ("CROSS-PASS", "CROSS-SKIPPED")
    for spacer_id in ("0012-aarch64-monotonic-x5-spacer", "0013-aarch64-bounded-counter-spacer"):
        spacer_row = next(r for r in task_rows if r.get("task") == spacer_id)
        assert spacer_row["summary"]["status"] == "CROSS-SKIPPED"
