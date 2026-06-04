"""Pareto aggregator for the SOTA baselines.

Consumes per-tool JSONL streams (one row per task per
``baselines/README.md`` §2) and produces:

1. **Per-tool aggregate table**: solved, correct, false_positive,
   false_negative, unknown, error, timeout, skip, total_wall_s,
   median_wall_s.
2. **Per-task wide table**: one row per task, one column per tool,
   each cell = (verdict, correct, wall_s).
3. **Pareto-dominance summary** (`V2_BOOTSTRAP.md` §5): for each
   (hurdy-gurdy, SOTA-tool) pair, the set of tasks where
   hurdy-gurdy strictly dominates on (correct, wall_s) and vice
   versa, plus tasks where they tie.

Input: a directory of JSONL files named ``<tool>.jsonl`` (default
``baselines/_runs/``). Each line one JSON object matching the
schema. Hurdy-gurdy participates as one of the tools with ``tool ==
"hurdy-gurdy"`` (rows produced by ``framework_oracle.py --jsonl``
or by an explicit adapter; the exact source is left to a future
iteration).

Usage::

    python bench/riscv-btor2/baselines/pareto.py
    python bench/riscv-btor2/baselines/pareto.py --runs _runs/
    python bench/riscv-btor2/baselines/pareto.py --md > pareto.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RUNS = Path(__file__).resolve().parent / "_runs"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """One JSONL row, schema-conformant."""

    tool: str
    task: str
    verdict: str
    wall_s: float
    rss_mb: float
    expected: str
    correct: bool | None
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Row":
        return cls(
            tool=d.get("tool", ""),
            task=d.get("task", ""),
            verdict=d.get("verdict", ""),
            wall_s=float(d.get("wall_s", 0.0) or 0.0),
            rss_mb=float(d.get("rss_mb", 0.0) or 0.0),
            expected=d.get("expected", "?"),
            correct=d.get("correct"),
            notes=d.get("notes", "") or "",
        )


def load_runs(runs_dir: Path) -> dict[str, list[Row]]:
    """Read every ``*.jsonl`` in the runs dir; return {tool: [Row]}."""
    by_tool: dict[str, list[Row]] = {}
    if not runs_dir.is_dir():
        return by_tool
    for fp in sorted(runs_dir.glob("*.jsonl")):
        rows: list[Row] = []
        for line in fp.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(Row.from_dict(d))
        if rows:
            by_tool.setdefault(rows[0].tool, []).extend(rows)
    return by_tool


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


@dataclass
class ToolAggregate:
    tool: str
    n_tasks: int = 0
    solved: int = 0           # verdict ∈ {reachable, unreachable, proved}
    correct: int = 0          # correct == True
    false_pos: int = 0        # verdict=reachable but expected != reachable
    false_neg: int = 0        # verdict ∈ {unreachable,proved} but expected != unreachable
    unknown: int = 0
    error: int = 0
    timeout: int = 0
    skip: int = 0
    total_wall_s: float = 0.0
    walls: list[float] = field(default_factory=list)

    def median_wall_s(self) -> float:
        return statistics.median(self.walls) if self.walls else 0.0


def aggregate(rows: list[Row]) -> ToolAggregate:
    tool = rows[0].tool if rows else "?"
    agg = ToolAggregate(tool=tool, n_tasks=len(rows))
    for r in rows:
        agg.total_wall_s += r.wall_s
        if r.verdict in ("reachable", "unreachable", "proved"):
            agg.solved += 1
            agg.walls.append(r.wall_s)
            if r.correct is True:
                agg.correct += 1
            if r.verdict == "reachable" and r.expected != "reachable":
                agg.false_pos += 1
            if r.verdict in ("unreachable", "proved") and r.expected == "reachable":
                agg.false_neg += 1
        elif r.verdict == "unknown":
            agg.unknown += 1
        elif r.verdict == "timeout":
            agg.timeout += 1
        elif r.verdict == "skip":
            agg.skip += 1
        else:
            agg.error += 1
    return agg


# ---------------------------------------------------------------------------
# Pareto dominance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairwiseStats:
    """Pairwise Pareto counts between (tool_a, tool_b) on tasks where both
    produced a verdict."""

    tool_a: str
    tool_b: str
    n_common: int  # tasks where both solved
    a_dominates: int  # a strictly better: (a.correct and !b.correct) or
                     # (both correct and a.wall_s < b.wall_s)
    b_dominates: int
    ties: int


def pareto_pair(rows_a: list[Row], rows_b: list[Row]) -> PairwiseStats:
    """Strict dominance on (correct, wall_s) over tasks where both
    have a non-skip non-error verdict. A dominates B if A is correct
    and B is not, OR both correct and A is strictly faster."""
    if not rows_a or not rows_b:
        return PairwiseStats(
            tool_a=rows_a[0].tool if rows_a else "?",
            tool_b=rows_b[0].tool if rows_b else "?",
            n_common=0, a_dominates=0, b_dominates=0, ties=0,
        )
    by_task_a = {r.task: r for r in rows_a}
    by_task_b = {r.task: r for r in rows_b}
    SOLVED = {"reachable", "unreachable", "proved"}
    n_common = ad = bd = ties = 0
    for task, a in by_task_a.items():
        if a.verdict not in SOLVED:
            continue
        b = by_task_b.get(task)
        if b is None or b.verdict not in SOLVED:
            continue
        n_common += 1
        a_ok = a.correct is True
        b_ok = b.correct is True
        if a_ok and not b_ok:
            ad += 1
        elif b_ok and not a_ok:
            bd += 1
        elif a_ok and b_ok:
            if a.wall_s < b.wall_s:
                ad += 1
            elif b.wall_s < a.wall_s:
                bd += 1
            else:
                ties += 1
        else:
            ties += 1
    return PairwiseStats(
        tool_a=rows_a[0].tool,
        tool_b=rows_b[0].tool,
        n_common=n_common, a_dominates=ad, b_dominates=bd, ties=ties,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_text(by_tool: dict[str, list[Row]]) -> str:
    if not by_tool:
        return "no runs found.\n"
    aggs = {t: aggregate(rows) for t, rows in by_tool.items()}
    lines: list[str] = []
    lines.append("## Per-tool aggregates")
    lines.append("")
    lines.append(
        f"{'tool':16s} {'tasks':>6s} {'solved':>6s} {'correct':>7s}"
        f" {'FP':>4s} {'FN':>4s} {'unk':>4s} {'err':>4s} {'tmo':>4s}"
        f" {'skip':>5s} {'total_s':>9s} {'med_s':>7s}"
    )
    for t, agg in sorted(aggs.items()):
        lines.append(
            f"{agg.tool:16s} {agg.n_tasks:6d} {agg.solved:6d}"
            f" {agg.correct:7d} {agg.false_pos:4d} {agg.false_neg:4d}"
            f" {agg.unknown:4d} {agg.error:4d} {agg.timeout:4d}"
            f" {agg.skip:5d} {agg.total_wall_s:9.3f}"
            f" {agg.median_wall_s():7.3f}"
        )
    lines.append("")
    lines.append("## Pareto dominance (strict, on commonly-solved)")
    lines.append("")
    tools = sorted(by_tool.keys())
    if "hurdy-gurdy" in tools:
        # Highlight hurdy-gurdy as the anchor.
        anchor = "hurdy-gurdy"
        others = [t for t in tools if t != anchor]
        lines.append(f"{'opponent':16s} {'common':>6s} {'hg dom':>7s} {'opp dom':>8s} {'ties':>5s}")
        for opp in others:
            s = pareto_pair(by_tool[anchor], by_tool[opp])
            lines.append(
                f"{opp:16s} {s.n_common:6d} {s.a_dominates:7d}"
                f" {s.b_dominates:8d} {s.ties:5d}"
            )
    else:
        lines.append("(no hurdy-gurdy row yet; rerun once framework_oracle.py JSONL is in _runs/)")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SOTA baselines Pareto aggregator")
    p.add_argument("--runs", default=str(RUNS), help="dir containing *.jsonl")
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = p.parse_args(argv)

    runs = Path(args.runs)
    by_tool = load_runs(runs)
    if args.json:
        aggs = {t: aggregate(rows).__dict__ for t, rows in by_tool.items()}
        # Drop the walls list (large, redundant with median).
        for v in aggs.values():
            v.pop("walls", None)
        json.dump({"runs_dir": str(runs), "tools": aggs}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(by_tool))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
