"""Tests for bench/aarch64-btor2/baselines/pareto.py — P11 Pareto aggregator."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[4]
_BASELINES_DIR = _REPO / "bench" / "aarch64-btor2" / "baselines"
sys.path.insert(0, str(_BASELINES_DIR))

from pareto import (  # noqa: E402
    PairwiseStats,
    Row,
    ToolAggregate,
    aggregate,
    load_runs,
    main,
    pareto_pair,
    render_text,
)


# ---------------------------------------------------------------------------
# Row.from_dict
# ---------------------------------------------------------------------------


def test_row_from_dict_basic():
    r = Row.from_dict({
        "tool": "hurdy-gurdy",
        "task": "0001-c-loopsum-o0",
        "verdict": "unreachable",
        "wall_s": 1.5,
        "rss_mb": 100.0,
        "expected": "unreachable",
        "correct": True,
    })
    assert r.tool == "hurdy-gurdy"
    assert r.verdict == "unreachable"
    assert r.wall_s == 1.5
    assert r.correct is True


def test_row_from_dict_missing_fields_use_defaults():
    r = Row.from_dict({})
    assert r.tool == ""
    assert r.verdict == ""
    assert r.wall_s == 0.0
    assert r.correct is None


def test_row_from_dict_null_wall_s_becomes_zero():
    r = Row.from_dict({"wall_s": None, "tool": "t", "task": "x",
                       "verdict": "skip", "rss_mb": 0.0, "expected": "?"})
    assert r.wall_s == 0.0


# ---------------------------------------------------------------------------
# load_runs
# ---------------------------------------------------------------------------


def test_load_runs_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        result = load_runs(pathlib.Path(d))
    assert result == {}


def test_load_runs_missing_dir():
    result = load_runs(pathlib.Path("/nonexistent_dir_xyz"))
    assert result == {}


def test_load_runs_reads_jsonl_file():
    rows_data = [
        {"tool": "cbmc", "task": "t1", "verdict": "unreachable",
         "wall_s": 2.0, "rss_mb": 50.0, "expected": "unreachable", "correct": True},
        {"tool": "cbmc", "task": "t2", "verdict": "reachable",
         "wall_s": 1.0, "rss_mb": 40.0, "expected": "reachable", "correct": True},
    ]
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "cbmc.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in rows_data) + "\n")
        result = load_runs(pathlib.Path(d))
    assert "cbmc" in result
    assert len(result["cbmc"]) == 2


def test_load_runs_skips_blank_lines():
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "tool.jsonl"
        p.write_text('\n\n{"tool":"t","task":"x","verdict":"unknown","wall_s":0,"rss_mb":0,"expected":"?","correct":null}\n\n')
        result = load_runs(pathlib.Path(d))
    assert "t" in result
    assert len(result["t"]) == 1


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


def _make_row(verdict: str, expected: str, correct: bool | None, wall_s: float = 1.0) -> Row:
    return Row(tool="t", task="x", verdict=verdict, wall_s=wall_s, rss_mb=0.0,
               expected=expected, correct=correct)


def test_aggregate_solved_correct():
    rows = [_make_row("unreachable", "unreachable", True, 2.0)]
    agg = aggregate(rows)
    assert agg.solved == 1
    assert agg.correct == 1
    assert agg.false_pos == 0
    assert agg.false_neg == 0
    assert agg.total_wall_s == 2.0


def test_aggregate_false_positive():
    rows = [_make_row("reachable", "unreachable", False)]
    agg = aggregate(rows)
    assert agg.false_pos == 1
    assert agg.false_neg == 0


def test_aggregate_false_negative():
    rows = [_make_row("unreachable", "reachable", False)]
    agg = aggregate(rows)
    assert agg.false_neg == 1
    assert agg.false_pos == 0


def test_aggregate_timeout_and_unknown():
    rows = [
        _make_row("timeout", "unreachable", None),
        _make_row("unknown", "reachable", None),
    ]
    agg = aggregate(rows)
    assert agg.timeout == 1
    assert agg.unknown == 1
    assert agg.solved == 0


def test_aggregate_median_wall_s():
    rows = [
        _make_row("unreachable", "unreachable", True, 1.0),
        _make_row("unreachable", "unreachable", True, 3.0),
        _make_row("unreachable", "unreachable", True, 2.0),
    ]
    agg = aggregate(rows)
    assert agg.median_wall_s() == 2.0


# ---------------------------------------------------------------------------
# pareto_pair
# ---------------------------------------------------------------------------


def _make_rows(tool: str, entries: list[tuple[str, str, bool | None, float]]) -> list[Row]:
    return [
        Row(tool=tool, task=task, verdict=verdict, wall_s=wall_s,
            rss_mb=0.0, expected="?", correct=correct)
        for task, verdict, correct, wall_s in entries
    ]


def test_pareto_pair_a_dominates_by_correctness():
    a = _make_rows("a", [("t1", "unreachable", True, 5.0)])
    b = _make_rows("b", [("t1", "unreachable", False, 1.0)])
    s = pareto_pair(a, b)
    assert s.a_dominates == 1
    assert s.b_dominates == 0


def test_pareto_pair_b_dominates_by_correctness():
    a = _make_rows("a", [("t1", "unreachable", False, 1.0)])
    b = _make_rows("b", [("t1", "unreachable", True, 5.0)])
    s = pareto_pair(a, b)
    assert s.b_dominates == 1
    assert s.a_dominates == 0


def test_pareto_pair_both_correct_faster_dominates():
    a = _make_rows("a", [("t1", "unreachable", True, 1.0)])
    b = _make_rows("b", [("t1", "unreachable", True, 2.0)])
    s = pareto_pair(a, b)
    assert s.a_dominates == 1
    assert s.b_dominates == 0


def test_pareto_pair_tie_same_time():
    a = _make_rows("a", [("t1", "unreachable", True, 1.0)])
    b = _make_rows("b", [("t1", "unreachable", True, 1.0)])
    s = pareto_pair(a, b)
    assert s.ties == 1
    assert s.a_dominates == 0


def test_pareto_pair_no_common_tasks():
    a = _make_rows("a", [("t1", "unreachable", True, 1.0)])
    b = _make_rows("b", [("t2", "unreachable", True, 1.0)])
    s = pareto_pair(a, b)
    assert s.n_common == 0


def test_pareto_pair_empty_rows():
    s = pareto_pair([], [])
    assert s.n_common == 0
    assert s.a_dominates == 0


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------


def test_render_text_no_data_shows_message():
    out = render_text({})
    assert "no runs found" in out


def test_render_text_shows_tool_name():
    rows = _make_rows("hurdy-gurdy", [("t1", "unreachable", True, 1.0)])
    out = render_text({"hurdy-gurdy": rows})
    assert "hurdy-gurdy" in out


def test_render_text_no_hurdy_gurdy_shows_placeholder():
    rows = _make_rows("cbmc", [("t1", "unreachable", True, 1.0)])
    out = render_text({"cbmc": rows})
    assert "no hurdy-gurdy row yet" in out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_empty_runs_dir_returns_0(capsys):
    with tempfile.TemporaryDirectory() as d:
        rc = main(["--runs", d])
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "no runs found" in out


def test_main_json_empty_runs_returns_0(capsys):
    with tempfile.TemporaryDirectory() as d:
        rc = main(["--runs", d, "--json"])
    assert rc == 0
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert "tools" in data
