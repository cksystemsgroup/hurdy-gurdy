#!/usr/bin/env python3
"""One iteration of the frontier loop (FRONTIER.md §5's protocol;
plan C7).

    python tools/frontier_loop.py BENCH.json WORKDIR [--k 20]
                                  [--engine auto|native|bridge]

Per invocation, exactly one iteration — the human valve is structural,
not a prompt: the loop pauses *between* invocations, where
registration (a human act, AGENTS.md §1) grows the registry, and the
next invocation measures the growth. Stages:

1. **Pin.** Every instance fetched streamed-with-pin through
   ``core/benchmark.py`` (sha256 verified; offline is honest, not
   fatal).
2. **Play.** The Phase-3 player is mechanical and hub-native: BTOR2
   questions decided by the native checker (btormc) or the bridge
   (z3), one instance at a time, released before the next (the RAM
   discipline). The *general* player plugs in at ``decide=`` — the
   same seam the tests inject verdicts through. A spent verdict
   (``unknown``/``resource-out``) is booked as a **cost demand**
   (suite-tagged, ``origin=campaign``), and blocked instances get an
   **ascending probe** (a few smaller bounds) so the report's
   failure-mode reading has a curve to fit. An unavailable engine is
   ``skipped`` — never a spent budget.
3. **Book + fixpoint.** ``core/frontier.py::saturate`` re-diagnoses
   the suite against the iteration's books and derives the terminal
   board.
4. **Deposit.** One self-contained record appended to
   ``WORKDIR/iterations.jsonl``; the report regenerated
   (``tools/saturation_report.py`` — pure, byte-identical on the same
   input); the board printed. Exit 0 iff saturated.

The driver never registers, never writes under ``pairs/``, never
touches a protected field: it plays, books, and reports.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import gurdy.cli  # noqa: F401,E402  (the import is the registration)

from gurdy.core import ledger  # noqa: E402
from gurdy.core.benchmark import Benchmark, fetch  # noqa: E402
from gurdy.core.frontier import saturate  # noqa: E402
from gurdy.core.solver import Verdict  # noqa: E402
from gurdy.core.whynot import why_not  # noqa: E402

#: Ascending probe bounds for blocked instances (the O2 curve; capped).
PROBE_KS = (2, 4, 8)

DecideFn = Callable[[str, int], tuple[Verdict, dict[str, Any]]]


def pick_decide(engine: str = "auto") -> tuple[str, DecideFn] | None:
    """The mechanical hub-native player: native checker first, bridge
    second. Returns (name, fn) or None when nothing is available."""
    if engine in ("auto", "native"):
        from gurdy.solvers.native_btor2 import NativeBtor2Checker, find_btormc

        if find_btormc():
            checker = NativeBtor2Checker()

            def native(text: str, k: int) -> tuple[Verdict, dict[str, Any]]:
                v, _wit = checker.decide_witness(text, k)
                if v is not Verdict.REACHABLE:
                    v = checker.decide_bounded(text, k)
                return v, {"engine": "btormc"}

            return "native", native
        if engine == "native":
            return None
    if engine in ("auto", "bridge"):
        try:
            import z3  # noqa: F401
        except Exception:
            return None
        from gurdy.pairs.btor2_smtlib import reach

        def bridge(text: str, k: int) -> tuple[Verdict, dict[str, Any]]:
            info = reach(text, k)
            return info["verdict"], {"engine": "z3-bridge"}

        return "bridge", bridge
    return None


def _count_lines(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def run_iteration(bench: Benchmark, workdir: str, *, k: int = 20,
                  decide: DecideFn | None = None, engine: str = "auto",
                  probe: bool = True,
                  cache_dir: str | None = None) -> dict[str, Any]:
    os.makedirs(workdir, exist_ok=True)
    books = os.path.join(workdir, "books.jsonl")
    iterations = os.path.join(workdir, "iterations.jsonl")
    iteration = _count_lines(iterations)

    engine_name = "injected"
    if decide is None:
        picked = pick_decide(engine)
        if picked is not None:
            engine_name, decide = picked
        else:
            engine_name = "none"

    verdicts: dict[str, dict[str, Any]] = {}
    books_before = _count_lines(books)
    ledger.configure(books)
    try:
        for inst in bench.instances:
            if decide is None:
                verdicts[inst.name] = {"verdict": "skipped (no engine)"}
                continue
            data = fetch(bench, inst.name, cache_dir=cache_dir)
            if data is None:
                verdicts[inst.name] = {"verdict": "skipped (offline)"}
                continue
            text = data.decode("utf-8")
            t0 = time.perf_counter()
            v, meta = decide(text, k)
            wall = round(time.perf_counter() - t0, 4)
            row: dict[str, Any] = {"verdict": v.value, "wall_s": wall,
                                   "k": k, "bounded": True, **meta}
            if inst.expected:
                row["expected"] = inst.expected
                row["agree"] = v.value == inst.expected
            verdicts[inst.name] = row
            if v.value in ("unknown", "resource-out"):
                # The spent verdict becomes a cost demand on the books…
                q = inst.question
                why_not(q.source,
                        list(q.observables) if q.observables else None,
                        q.shape, floor=q.floor,
                        program=q.program or inst.name,
                        verdict=v.value, origin="campaign",
                        suite=bench.suite)
                # …and the blocked instance gets its curve measured.
                if probe:
                    for pk in PROBE_KS:
                        if pk < k:
                            decide(text, pk)
            del text, data  # one instance fully, then release
        saturation = saturate(bench, ledger_path=books)
    finally:
        ledger.configure(None)

    decide_records = [
        r for r in ledger._records(books)[books_before:]
        if r.get("kind") == "decide"]
    record = {
        "iteration": iteration,
        "suite": bench.suite,
        "caps": {"k": k, "engine": engine_name,
                 "probe_ks": list(PROBE_KS) if probe else []},
        "verdicts": verdicts,
        "decide_records": decide_records,
        "saturation": saturation,
    }
    with open(iterations, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("benchmark")
    ap.add_argument("workdir")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--engine", choices=["auto", "native", "bridge"],
                    default="auto")
    ap.add_argument("--no-probe", action="store_true")
    args = ap.parse_args()

    with open(args.benchmark, encoding="utf-8") as f:
        bench = Benchmark.from_json(f.read())
    record = run_iteration(bench, args.workdir, k=args.k,
                           engine=args.engine, probe=not args.no_probe)

    from saturation_report import build_report, render_markdown

    iterations_path = os.path.join(args.workdir, "iterations.jsonl")
    with open(iterations_path, encoding="utf-8") as f:
        iterations = [json.loads(line) for line in f if line.strip()]
    report = build_report(iterations)
    prefix = os.path.join(args.workdir, "report")
    with open(prefix + ".json", "w", encoding="utf-8") as f:
        f.write(json.dumps(report, indent=2, sort_keys=True, default=str)
                + "\n")
    with open(prefix + ".md", "w", encoding="utf-8") as f:
        f.write(render_markdown(report))

    sat = record["saturation"]
    print(f"iteration {record['iteration']} — suite {bench.suite}: "
          f"solved {len(sat['solved'])}, open {len(sat['open'])}, "
          f"saturated {sat['saturated']}")
    for name, v in record["verdicts"].items():
        agree = ("" if "agree" not in v
                 else " ✓" if v["agree"] else f" (expected {v['expected']})")
        print(f"  {name}: {v['verdict']}"
              + (f" {v['wall_s']}s" if v.get("wall_s") is not None else "")
              + agree)
    if sat["board"]:
        print("terminal board (promote with `gurdy frontier-promote "
              f"<id> --ledger {os.path.join(args.workdir, 'books.jsonl')}`):")
        for o in sat["board"]:
            where = ("in-set" if o["in_known_set"]
                     else "frontier" if o["in_known_set"] is False
                     else "no honest target")
            print(f"  {o['id']} [{where}] {o['kind']} "
                  f"questions={o['evidence']['distinct_questions']}")
    print(f"report: {prefix}.md — registration is a human act; the loop "
          "resumes when the registry grows")
    return 0 if sat["saturated"] else 1


if __name__ == "__main__":
    sys.exit(main())
