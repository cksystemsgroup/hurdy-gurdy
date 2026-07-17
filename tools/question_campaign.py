#!/usr/bin/env python3
"""The question-campaign benchmark: the demand books, measured end to
end (AGENTS.md §1; POTENTIAL.md §1–3; the books of core/ledger.py; the
third post-snapshot benchmark family named by the paper's evaluation
exhibits).

A corpus of 25 authored questions whose **first failing obstacle is
known by construction** — the five obstacles of the demand taxonomy
(connectivity, loss, shape, cost, trust), plus answerable controls that
exercise every way a question can *pass* (feasible routes; a floor met
by declared grade; a floor met by branch corroboration). The campaign
measures the whole diagnosis-to-recommendation path:

* **diagnosis accuracy** — ``why_not`` must name the constructed
  obstacle, first, for every failing question;
* **zero false demand** — every answerable control must return
  answerable *and append no demand record* (the books never record an
  answered question);
* **board aggregation** — ``ledger.demand_summary`` groups records per
  generation target; re-asking a question verbatim must not grow its
  target's distinct-question count (dedup by question identity);
* **origin separation** — the same question asked from an ``organic``
  session and a synthetic ``campaign`` shows both origins, displayed
  apart, on its board row;
* **stubs where promised** — every connectivity demand carries a draft
  brief stub that itself states registration is a human act.

Read-only against the registry (the diagnosis never registers); the
ledger is a temp file per run. Sequential, no solver calls — seconds.
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Register the full graph (the import is the registration).
import gurdy.cli  # noqa: F401,E402

from gurdy.core import ledger, registry  # noqa: E402
from gurdy.core.whynot import why_not  # noqa: E402


def build_corpus() -> list[dict[str, Any]]:
    """25 questions; ``expected`` is the constructed first-failing
    obstacle, or None for an answerable control. ``why`` documents the
    construction (and the control's expected pass mechanism)."""
    q: list[dict[str, Any]] = []

    def add(qid, expected, why, **kwargs):
        q.append({"qid": qid, "expected": expected, "why": why,
                  "kwargs": kwargs})

    # connectivity — sources whose routes reach no reasoning language
    add("con-smiles-formula", "connectivity",
        "smiles reaches only molecular-formula, not a hub",
        source="smiles", observables=["formula"])
    add("con-smiles-rings", "connectivity",
        "distinct question, same missing edge",
        source="smiles", observables=["ring_count"])
    add("con-formula-mass", "connectivity",
        "molecular-formula has no outgoing pair at all",
        source="molecular-formula", observables=["mass"])
    add("con-formula-reach", "connectivity",
        "distinct question, same missing edge",
        source="molecular-formula", shape="reachability")

    # loss — routes exist but every head drops the asked observable
    for obs in ("csr_mstatus", "fflags", "cycle_counter", "mem_dirty_bit"):
        add(f"loss-riscv-{obs}", "loss",
            f"no RISC-V head projection keeps `{obs}`",
            source="riscv", observables=["pc", obs])

    # shape — no registered hub declares the question shape
    add("shape-riscv-liveness", "shape",
        "no hub declares liveness",
        source="riscv", observables=["pc"], shape="liveness")
    add("shape-riscv-termination", "shape",
        "no hub declares termination",
        source="riscv", observables=["pc"], shape="termination")
    add("shape-ebpf-ctl", "shape",
        "no hub declares ctl",
        source="ebpf", shape="ctl")
    add("shape-evm-probabilistic", "shape",
        "no hub declares probabilistic-reachability",
        source="evm", shape="probabilistic-reachability")

    # cost — statics pass; the player hands in a spent verdict
    add("cost-riscv-resource-out", "cost",
        "resource-out on a feasible route",
        source="riscv", observables=["pc"], shape="reachability",
        verdict="resource-out")
    add("cost-evm-unknown", "cost",
        "unknown on a feasible route",
        source="evm", shape="reachability", verdict="unknown")
    add("cost-ebpf-resource-out", "cost",
        "resource-out, bounded-unreachability shape",
        source="ebpf", shape="bounded-unreachability",
        verdict="resource-out")

    # trust — floor unmet by grade, no independent branch
    for src in ("wasm", "ebpf", "evm"):
        add(f"trust-{src}-universal", "trust",
            f"{src} is single-route at per-run class; floor universal",
            source=src, floor="universal")

    # answerable controls — every pass mechanism, no demand recorded
    add("ok-riscv-reach", None, "feasible routes, kept observable",
        source="riscv", observables=["pc"], shape="reachability")
    add("ok-riscv-floor", None, "floor met by ISA branch corroboration",
        source="riscv", floor="universal")
    add("ok-aarch64-floor", None, "floor met by ISA branch corroboration",
        source="aarch64", floor="universal")
    add("ok-c-floor", None, "floor met by the diverse segment below the C head",
        source="c", floor="universal")
    add("ok-python-floor", None, "floor met by declared grade (predicted)",
        source="python", floor="universal")
    add("ok-ebpf-reach", None, "feasible route to the bit-level hub",
        source="ebpf", shape="reachability")
    add("ok-evm-bounded", None, "declared shape, feasible route",
        source="evm", shape="bounded-unreachability")
    return q


# Re-asked verbatim in the dedup round (must add 0 distinct questions)
DEDUP_QIDS = ("con-smiles-formula", "loss-riscv-csr_mstatus",
              "shape-riscv-liveness", "cost-riscv-resource-out",
              "trust-wasm-universal", "con-formula-mass")
# Re-asked as organic sessions (their board rows must show both origins)
ORGANIC_QIDS = ("shape-riscv-liveness", "trust-wasm-universal",
                "cost-riscv-resource-out")


def _ledger_lines(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def run_experiment(workdir: str | None = None) -> dict[str, Any]:
    td = workdir or tempfile.mkdtemp(prefix="question-campaign-")
    books = os.path.join(td, "books.jsonl")
    ledger.configure(books)
    corpus = build_corpus()
    pairs_before = set(registry.list_pairs())
    try:
        rows = []
        for entry in corpus:
            before = _ledger_lines(books)
            rec = why_not(origin="campaign", **entry["kwargs"])
            recorded = _ledger_lines(books) - before
            diagnosed = None if rec["answerable"] else rec["obstacle"]
            ok = (diagnosed == entry["expected"]
                  and recorded == (0 if entry["expected"] is None else 1)
                  and (entry["expected"] != "connectivity"
                       or "registration is a human act"
                       in rec.get("brief_stub", "")))
            rows.append({
                "qid": entry["qid"], "expected": entry["expected"],
                "diagnosed": diagnosed, "recorded": recorded,
                "why": entry["why"],
                "target_kind": (rec.get("generation_target") or {}).get("kind")
                               if not rec["answerable"] else None,
                "ok": ok,
            })

        by_qid = {e["qid"]: e for e in corpus}
        distinct_before = sum(
            r["distinct_questions"] for r in ledger.demand_summary(books))
        for qid in DEDUP_QIDS:  # verbatim re-asks: distinct must not grow
            why_not(origin="campaign", **by_qid[qid]["kwargs"])
        distinct_after = sum(
            r["distinct_questions"] for r in ledger.demand_summary(books))
        for qid in ORGANIC_QIDS:  # same questions, organic origin
            why_not(origin="organic", **by_qid[qid]["kwargs"])

        board = ledger.demand_summary(books)
    finally:
        ledger.configure(None)

    organic_rows = [r for r in board if "organic" in r["origins"]]
    checks = {
        "accuracy": {
            "failing_total": sum(1 for r in rows if r["expected"]),
            "failing_correct": sum(1 for r in rows
                                   if r["expected"] and r["ok"]),
            "controls_total": sum(1 for r in rows if r["expected"] is None),
            "controls_correct": sum(1 for r in rows
                                    if r["expected"] is None and r["ok"]),
        },
        "dedup": {
            "reasked": len(DEDUP_QIDS),
            "distinct_before": distinct_before,
            "distinct_after": distinct_after,
            "ok": distinct_after == distinct_before,
        },
        "origins": {
            "organic_reasks": len(ORGANIC_QIDS),
            "rows_showing_both": sum(
                1 for r in organic_rows if "campaign" in r["origins"]),
            "ok": (len(organic_rows) > 0
                   and all("campaign" in r["origins"] for r in organic_rows)),
        },
        "read_only": set(registry.list_pairs()) == pairs_before,
    }
    acc = checks["accuracy"]
    ok = (acc["failing_correct"] == acc["failing_total"]
          and acc["controls_correct"] == acc["controls_total"]
          and checks["dedup"]["ok"] and checks["origins"]["ok"]
          and checks["read_only"])
    return {"rows": rows, "board": board, "checks": checks, "ok": ok}


def main() -> int:
    report = run_experiment()
    for r in report["rows"]:
        print(f"{'ok ' if r['ok'] else 'FAIL'} {r['qid']:28s} "
              f"expected={str(r['expected']):13s} "
              f"diagnosed={str(r['diagnosed']):13s} recorded={r['recorded']}")
    print(f"\nboard: {len(report['board'])} generation targets")
    for row in report["board"]:
        kind = (row["target"] or {}).get("kind", "(none)")
        print(f"  {kind:20s} distinct={row['distinct_questions']} "
              f"obstacles={','.join(row['obstacles'])} "
              f"origins={row['origins']}")
    print("checks:", report["checks"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
