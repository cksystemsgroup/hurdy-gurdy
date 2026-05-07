"""Calibration analysis for a sweep transcripts directory.

BENCHMARKING.md §5 calls for verdict accuracy, hallucination rate,
and Brier score / ECE. This script reads the per-cell transcripts a
sweep wrote (under ``--transcripts-dir``), regrades each cell with
the deterministic matcher, and emits the §5 metrics. No LLM calls.

Design notes:

- The transcript on disk is the source of truth for ``confidence``;
  the matcher.match call recomputes ``verdict_correct`` from the same
  ``observed`` blob, so this script is robust to the matcher being
  tightened (e.g. the proved/unreachable equivalence) after the
  sweep ran.
- ``unknown`` cells are tracked separately per §5: they don't count
  toward verdict accuracy in either direction, and they're excluded
  from calibration buckets (a well-calibrated unknown is just a
  refusal).
- ECE uses 10 equal-width buckets over [0, 1]; reliability-diagram
  detail is reported per bucket so the reader can spot an
  overconfident region without needing a plot.

Output layout: one summary line per (condition, model_slot) cell-group
followed by per-bucket reliability rows. JSON output is also offered
for machine consumption.

Usage:

    python bench/riscv-btor2/calibration.py --transcripts-dir /tmp/bench-sweep-XYZ/_transcripts
    python bench/riscv-btor2/calibration.py --transcripts-dir ./_transcripts --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


HIGH_CONFIDENCE_THRESHOLD = 0.8  # §5 hallucination rate cutoff
N_BUCKETS = 10


@dataclass
class Cell:
    task_id: str
    condition: str
    model_slot: str
    seed: int
    verdict: str
    confidence: float
    verdict_correct: bool
    expected_verdict: str


@dataclass
class GroupSummary:
    condition: str
    model_slot: str
    n_total: int
    n_unknown: int
    n_correct: int
    n_wrong: int
    accuracy: float                 # n_correct / (n_total - n_unknown)
    hallucination_rate: float       # wrong-with-confidence-≥-threshold / n_total
    mean_confidence_correct: float  # confidence | verdict_correct
    mean_confidence_wrong: float    # confidence | not verdict_correct (excludes unknown)
    brier: float                    # mean (y - p)^2 over scored cells
    ece: float                      # expected calibration error
    buckets: list[dict] = field(default_factory=list)


def discover_cells(transcripts_dir: Path, corpus_dir: Path) -> list[Cell]:
    """Walk transcripts_dir/<task>/<condition>/<slot>/seed-*.json and
    re-grade each cell against task.toml in corpus_dir."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / "rubric"))
    import matcher  # type: ignore

    cells: list[Cell] = []
    for task_dir in sorted(transcripts_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        corpus_task = corpus_dir / task_dir.name
        if not (corpus_task / "task.toml").exists():
            continue  # spurious directory or stale name
        for cond_dir in sorted(task_dir.iterdir()):
            if not cond_dir.is_dir():
                continue
            for slot_dir in sorted(cond_dir.iterdir()):
                if not slot_dir.is_dir():
                    continue
                for seed_file in sorted(slot_dir.glob("seed-*.json")):
                    try:
                        d = json.loads(seed_file.read_text())
                    except Exception:
                        continue
                    seed = int(seed_file.stem.split("-", 1)[1])
                    observed = d.get("observed") or {}
                    verdict = observed.get("verdict", "unknown")
                    conf = observed.get("confidence")
                    try:
                        conf = float(conf) if conf is not None else 0.0
                    except (TypeError, ValueError):
                        conf = 0.0
                    rep = matcher.match(corpus_task, observed)
                    cells.append(Cell(
                        task_id=task_dir.name,
                        condition=cond_dir.name,
                        model_slot=slot_dir.name,
                        seed=seed,
                        verdict=verdict,
                        confidence=max(0.0, min(1.0, conf)),
                        verdict_correct=rep.verdict_correct,
                        expected_verdict=rep.expected_verdict,
                    ))
    return cells


def _bucket_index(p: float) -> int:
    if p >= 1.0:
        return N_BUCKETS - 1
    return int(p * N_BUCKETS)


def summarize_group(condition: str, model_slot: str, cells: list[Cell]) -> GroupSummary:
    n_total = len(cells)
    scored = [c for c in cells if c.verdict != "unknown"]
    n_unknown = n_total - len(scored)
    correct = [c for c in scored if c.verdict_correct]
    wrong = [c for c in scored if not c.verdict_correct]
    n_correct = len(correct)
    n_wrong = len(wrong)
    accuracy = n_correct / max(1, len(scored))
    hallucination = sum(
        1 for c in wrong if c.confidence >= HIGH_CONFIDENCE_THRESHOLD
    ) / max(1, n_total)
    mean_cf_correct = (
        sum(c.confidence for c in correct) / max(1, n_correct)
        if correct else 0.0
    )
    mean_cf_wrong = (
        sum(c.confidence for c in wrong) / max(1, n_wrong)
        if wrong else 0.0
    )
    if scored:
        brier = sum(
            (c.confidence - (1.0 if c.verdict_correct else 0.0)) ** 2
            for c in scored
        ) / len(scored)
    else:
        brier = 0.0

    # Bucket reliability + ECE.
    buckets: dict[int, list[Cell]] = defaultdict(list)
    for c in scored:
        buckets[_bucket_index(c.confidence)].append(c)
    bucket_rows: list[dict] = []
    ece = 0.0
    n_scored = max(1, len(scored))
    for b in range(N_BUCKETS):
        bcells = buckets[b]
        if not bcells:
            bucket_rows.append({
                "lo": b / N_BUCKETS,
                "hi": (b + 1) / N_BUCKETS,
                "n": 0,
                "mean_confidence": None,
                "fraction_correct": None,
                "gap": None,
            })
            continue
        mc = sum(c.confidence for c in bcells) / len(bcells)
        fc = sum(1 for c in bcells if c.verdict_correct) / len(bcells)
        gap = abs(fc - mc)
        ece += (len(bcells) / n_scored) * gap
        bucket_rows.append({
            "lo": b / N_BUCKETS,
            "hi": (b + 1) / N_BUCKETS,
            "n": len(bcells),
            "mean_confidence": mc,
            "fraction_correct": fc,
            "gap": gap,
        })

    return GroupSummary(
        condition=condition,
        model_slot=model_slot,
        n_total=n_total,
        n_unknown=n_unknown,
        n_correct=n_correct,
        n_wrong=n_wrong,
        accuracy=accuracy,
        hallucination_rate=hallucination,
        mean_confidence_correct=mean_cf_correct,
        mean_confidence_wrong=mean_cf_wrong,
        brier=brier,
        ece=ece,
        buckets=bucket_rows,
    )


def render_text(summaries: list[GroupSummary], cells: list[Cell]) -> str:
    out: list[str] = []
    for s in summaries:
        out.append("")
        out.append(f"=== condition={s.condition}  model_slot={s.model_slot}  n={s.n_total} ===")
        out.append(f"  Verdict accuracy:     {s.n_correct}/{s.n_total - s.n_unknown}  ({s.accuracy:.1%})")
        out.append(f"  Unknown / refused:    {s.n_unknown}  ({s.n_unknown / max(1, s.n_total):.1%})")
        out.append(f"  Hallucination rate:   {s.hallucination_rate:.1%}  (wrong with confidence ≥ {HIGH_CONFIDENCE_THRESHOLD})")
        out.append(f"  Mean conf | correct:  {s.mean_confidence_correct:.3f}")
        out.append(f"  Mean conf | wrong:    {s.mean_confidence_wrong:.3f}  (lower = better calibrated)")
        out.append(f"  Brier score:          {s.brier:.4f}  (lower is better; perfect = 0)")
        out.append(f"  ECE (10 buckets):     {s.ece:.4f}  (lower is better; perfect = 0)")
        out.append("")
        out.append("  Reliability diagram (buckets with n=0 omitted):")
        out.append(f"  {'range':<14} {'n':>4}  {'mean_conf':>10}  {'frac_correct':>12}  {'gap':>6}")
        for b in s.buckets:
            if b["n"] == 0:
                continue
            out.append(
                f"  [{b['lo']:.1f}, {b['hi']:.1f})    {b['n']:>4}  "
                f"{b['mean_confidence']:>10.3f}  {b['fraction_correct']:>12.3f}  {b['gap']:>6.3f}"
            )
    # Hallucinated cells, listed individually so they're easy to inspect.
    halluc = [
        c for c in cells
        if c.verdict != "unknown"
        and not c.verdict_correct
        and c.confidence >= HIGH_CONFIDENCE_THRESHOLD
    ]
    if halluc:
        out.append("")
        out.append("Hallucinated cells (wrong + confidence ≥ {:.2f}):".format(HIGH_CONFIDENCE_THRESHOLD))
        for c in halluc:
            out.append(
                f"  {c.task_id:38s} cond={c.condition} slot={c.model_slot} seed={c.seed}  "
                f"verdict={c.verdict:11s} expected={c.expected_verdict:11s} conf={c.confidence:.3f}"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--transcripts-dir",
        type=Path,
        default=Path("./_transcripts"),
        help="Directory laid out as <task>/<condition>/<slot>/seed-*.json",
    )
    p.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).resolve().parent / "corpus",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if not args.transcripts_dir.is_dir():
        print(f"transcripts dir not found: {args.transcripts_dir}", file=sys.stderr)
        return 2

    cells = discover_cells(args.transcripts_dir, args.corpus)
    if not cells:
        print(f"no transcripts found in {args.transcripts_dir}", file=sys.stderr)
        return 2

    grouped: dict[tuple[str, str], list[Cell]] = defaultdict(list)
    for c in cells:
        grouped[(c.condition, c.model_slot)].append(c)
    summaries = [summarize_group(cond, slot, gcells)
                 for (cond, slot), gcells in sorted(grouped.items())]

    if args.json:
        payload = {
            "summaries": [
                {**{k: getattr(s, k) for k in (
                    "condition", "model_slot", "n_total", "n_unknown",
                    "n_correct", "n_wrong", "accuracy", "hallucination_rate",
                    "mean_confidence_correct", "mean_confidence_wrong",
                    "brier", "ece",
                )}, "buckets": s.buckets}
                for s in summaries
            ],
            "cells": [
                {**c.__dict__} for c in cells
            ],
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(render_text(summaries, cells))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
