#!/usr/bin/env python3
"""The cost-calibration benchmark: the ledger's measured cost axis,
exercised end to end (ROUTES.md §6-7; BENCHMARKS.md §7; the second
post-snapshot benchmark family named by the paper's evaluation
exhibits).

Runs the capped route-grader (``tools/route_grader.py``, the CI
entrypoint, verbatim) ``--reps`` times over the RISC-V head — each
repetition a fresh subprocess with its own ledger file, so the
content-addressed translation cache never swallows a translate record —
then, on the pooled records:

* **per-hop cost profiles** — translate and square-oracle medians/p90
  per pair, decide medians per engine (host-tagged; a profile is what
  this costs when it runs, on this machine);
* **stability across repetitions** — the per-repetition route translate
  totals and their spread, the calibration claim in numbers;
* **the dominance mark, calibrated** — ``route_report("riscv",
  "smtlib")`` on the pooled ledger must list both RISC-V routes at
  equal assurance and direction with measured totals, and any
  dominance mark must be *coherent* (it points from the cheaper
  measured total to the costlier — never against the measurement).
  Whether the mark is *stable* is itself a measurement: the report is
  recomputed per repetition and the mark's direction counted --- at
  totals that tie within the repetition spread, the mark flips, which
  is the calibration finding (the report enforces no noise margin);
* **the honesty invariants, executable** — on an *empty* ledger every
  route reads unmeasured (``None`` totals, never zero) and no dominance
  is computed; on a *partially* measured ledger (the direct route's
  pairs only) dominance is still not computed --- it needs complete
  measurement on both sides.

RAM discipline: repetitions are strictly sequential subprocesses; the
corpus is the grader's own capped probe slice.
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gurdy.core import ledger, registry  # noqa: E402
from gurdy.core.route import route_report  # noqa: E402

# Register the graph (the import is the registration).
import gurdy.cli  # noqa: F401,E402

DIRECT = ["riscv-btor2", "btor2-smtlib"]
SAIL = ["riscv-sail", "sail-btor2", "btor2-smtlib"]
PAIRS = sorted(set(DIRECT) | set(SAIL))


def _grader_pass(ledger_file: str, max_probes: int, k: int) -> None:
    """One capped route-grader run in a fresh subprocess (fresh process =
    fresh translation cache = translate records actually written)."""
    env = dict(os.environ, GURDY_LEDGER=ledger_file)
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "route_grader.py"),
         "--sources", "riscv", "--max-probes", str(max_probes),
         "--k", str(k)],
        check=True, env=env, cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def _pool(files: list[str], into: str) -> str:
    with open(into, "w", encoding="utf-8") as out:
        for f in files:
            with open(f, encoding="utf-8") as src:
                out.write(src.read())
    return into


def _route_total(path: str, pairs: list[str]) -> float | None:
    """A route's translate total (sum of per-pair medians) from one
    ledger file — None unless every hop is measured (the report's own
    reading, recomputed here per repetition)."""
    medians = []
    for pid in pairs:
        prof = ledger.profile("translate", pair=pid, path=path)
        if prof is None:
            return None
        medians.append(prof["wall_median_s"])
    return round(sum(medians), 6)


def _report_for(path: str | None) -> list[dict[str, Any]]:
    """route_report against a specific ledger file (or no ledger)."""
    ledger.configure(path)
    try:
        return route_report("riscv", "smtlib")
    finally:
        ledger.configure(None)


def _entry(report: list[dict[str, Any]], route: list[str]) -> dict[str, Any]:
    for e in report:
        if e["route"] == route:
            return e
    raise AssertionError(f"route {route} not in report")


def run_experiment(reps: int = 5, max_probes: int = 24, k: int = 2,
                   workdir: str | None = None) -> dict[str, Any]:
    """The full calibration run. Requires z3 (the grader's decide corpus
    and the bridged squares); btormc is not needed."""
    td = workdir or tempfile.mkdtemp(prefix="cost-calibration-")
    rep_files = []
    for i in range(reps):
        f = os.path.join(td, f"ledger-rep{i}.jsonl")
        _grader_pass(f, max_probes, k)
        rep_files.append(f)
    pooled = _pool(rep_files, os.path.join(td, "ledger-pooled.jsonl"))

    # Per-hop profiles from the pooled books.
    profiles = {
        "translate": {pid: ledger.profile("translate", pair=pid, path=pooled)
                      for pid in PAIRS},
        "cross_check": {pid: ledger.profile("cross_check", pair=pid, path=pooled)
                        for pid in PAIRS},
        "decide": ledger.profiles_by("engine", "decide", path=pooled),
    }

    # Stability: the per-repetition route totals and their spread.
    totals = {
        "direct": [_route_total(f, DIRECT) for f in rep_files],
        "sail": [_route_total(f, SAIL) for f in rep_files],
    }

    def _spread(vals: list[float | None]) -> dict[str, Any] | None:
        got = [v for v in vals if v is not None]
        if len(got) != len(vals) or not got:
            return None
        med = statistics.median(got)
        return {
            "median_s": round(med, 6),
            "min_s": min(got), "max_s": max(got),
            "rel_spread": round((max(got) - min(got)) / med, 3) if med else None,
        }

    stability = {name: _spread(vals) for name, vals in totals.items()}

    # The dominance mark on the pooled, fully measured books: coherence
    # (a mark never points against the measured totals), then stability
    # (the mark's direction, recounted per repetition).
    def _marks(report: list[dict[str, Any]]) -> dict[str, Any]:
        d, s = _entry(report, DIRECT), _entry(report, SAIL)
        dt = d["cost"]["translate_total_median_s"]
        st = s["cost"]["translate_total_median_s"]
        sail_marked = " -> ".join(DIRECT) in s["dominated_by"]
        direct_marked = " -> ".join(SAIL) in d["dominated_by"]
        coherent = True
        if sail_marked and (dt is None or st is None or dt > st):
            coherent = False
        if direct_marked and (dt is None or st is None or st > dt):
            coherent = False
        return {"direct_total_s": dt, "sail_total_s": st,
                "sail_marked": sail_marked, "direct_marked": direct_marked,
                "coherent": coherent}

    full = _report_for(pooled)
    direct_e, sail_e = _entry(full, DIRECT), _entry(full, SAIL)
    pooled_marks = _marks(full)
    per_rep_marks = [_marks(_report_for(f)) for f in rep_files]
    sail_marked_reps = sum(m["sail_marked"] for m in per_rep_marks)
    direct_marked_reps = sum(m["direct_marked"] for m in per_rep_marks)

    def _ranges_overlap() -> bool | None:
        d, s = stability["direct"], stability["sail"]
        if d is None or s is None:
            return None
        return d["min_s"] <= s["max_s"] and s["min_s"] <= d["max_s"]

    dominance = {
        "both_listed": len(full) == 2,
        "equal_assurance": direct_e["assurance"] == sail_e["assurance"],
        "equal_direction": direct_e["direction"] == sail_e["direction"],
        **pooled_marks,
        "sail_marked_reps": sail_marked_reps,
        "direct_marked_reps": direct_marked_reps,
        "mark_stable": (sail_marked_reps in (0, reps)
                        and direct_marked_reps in (0, reps)),
        "tie_within_spread": _ranges_overlap(),
        "coherent_all": (pooled_marks["coherent"]
                         and all(m["coherent"] for m in per_rep_marks)),
    }

    # Invariant 1: an empty ledger reads unmeasured — None totals, never
    # zero — and computes no dominance.
    empty = _report_for(os.path.join(td, "ledger-empty.jsonl"))
    unmeasured = {
        "totals_none": all(
            e["cost"]["translate_total_median_s"] is None for e in empty),
        "not_measured": all(not e["cost"]["measured"] for e in empty),
        "no_dominance": all(e["dominated_by"] == [] for e in empty),
    }

    # Invariant 2: partial measurement (direct-route pairs only) still
    # computes no dominance — it needs both sides fully measured.
    partial_file = os.path.join(td, "ledger-partial.jsonl")
    with open(pooled, encoding="utf-8") as src, \
            open(partial_file, "w", encoding="utf-8") as out:
        for line in src:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("kind") == "translate" and rec.get("pair") in DIRECT:
                out.write(line)
    partial = _report_for(partial_file)
    partial_inv = {
        "direct_measured": _entry(partial, DIRECT)["cost"]["measured"],
        "sail_unmeasured": not _entry(partial, SAIL)["cost"]["measured"],
        "no_dominance": all(e["dominated_by"] == [] for e in partial),
    }

    ok = (dominance["both_listed"] and dominance["equal_assurance"]
          and dominance["equal_direction"] and dominance["coherent_all"]
          and all(unmeasured.values()) and all(partial_inv.values())
          and all(s is not None for s in stability.values()))
    return {
        "reps": reps, "max_probes": max_probes, "k": k,
        "host": ledger.host_id(),
        "profiles": profiles,
        "per_rep_totals": totals,
        "stability": stability,
        "dominance": dominance,
        "unmeasured_invariant": unmeasured,
        "partial_invariant": partial_inv,
        "ok": ok,
    }


def main() -> int:
    try:
        import z3  # noqa: F401
    except Exception:
        print("cost calibration: z3 unavailable — cannot run")
        return 1
    report = run_experiment()
    print(json.dumps(
        {kk: report[kk] for kk in ("stability", "dominance",
                                   "unmeasured_invariant",
                                   "partial_invariant", "ok")},
        indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
