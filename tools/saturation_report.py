#!/usr/bin/env python3
"""The saturation report — the map, rendered (FRONTIER.md §5's
deliverable; plan C6, with O2 folded in as the cost reading).

A pure function of the loop's ``iterations.jsonl``
(``tools/frontier_loop.py`` appends one self-contained record per
iteration): the **curve** (answered fraction per iteration, monotone
by the ratchet), **cost per answer** per iteration, the last
iteration's **way-census** and **terminal board** (frontier objects,
conditional plans included), the declared **caps and pins**, and the
**failure-mode reading** of the decide records — the O2 classifier,
deliberately folded in here rather than shipped as its own tool: it
is one more way of reading the books, not a new instrument. No clock,
no host lookups: regenerating from the same input is byte-identical.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from typing import Any


# --- O2: the failure-mode reading of decide records ------------------------

def _fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Least-squares slope and r² for y over x."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return 0.0, 0.0
    slope, _ = statistics.linear_regression(xs, ys)
    r = statistics.correlation(xs, ys)
    return slope, r * r


def failure_modes(decide_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Per system (record ``key``): which parameter binds, judged from
    the measured curve of successful decides over the unrolling bound
    ``k`` — the binding-parameter fit of FRONTIER-PLAN.md §1.5. Wants
    ≥ 3 distinct bounds (the loop's ascending probe supplies them for
    blocked instances); fewer reads ``unmeasured``, never a guess."""
    by_key: dict[str, list[dict[str, Any]]] = {}
    for r in decide_records:
        if r.get("wall_s") is not None and r.get("k") is not None:
            by_key.setdefault(r["key"], []).append(r)
    out: dict[str, Any] = {}
    for key, recs in sorted(by_key.items()):
        pts = sorted({(float(r["k"]), max(float(r["wall_s"]), 1e-6))
                      for r in recs})
        if len({k for k, _ in pts}) < 3:
            out[key] = {"points": len(pts), "fit": "unmeasured",
                        "remedy": "no curve yet — probe more bounds "
                                  "before designing anything"}
            continue
        lin_slope, lin_r2 = _fit(list(pts))
        log_slope, log_r2 = _fit([(k, math.log(w)) for k, w in pts])
        if log_slope > 0.05 and log_r2 > max(lin_r2, 0.9):
            fit, remedy = "exponential-in-k", (
                "deeper BMC will not close this: an unbounded engine "
                "(k-induction / interpolation) or a property "
                "transformation — or an abstraction pair if the cone "
                "is small")
        elif lin_slope > 0 and lin_r2 > 0.9:
            fit, remedy = "linear-in-k", (
                "depth is affordable — raise k within budget before "
                "demanding a new instrument")
        else:
            fit, remedy = "flat", (
                "cost is not k-bound at these scales — if blocked, "
                "look at instance size or engine choice, not depth")
        out[key] = {"points": len(pts), "fit": fit, "remedy": remedy,
                    "engines": sorted({r.get("engine", "?") for r in recs}),
                    "size": max((r.get("size", 0) for r in recs),
                                default=None)}
    return out


# --- the report -------------------------------------------------------------

def build_report(iterations: list[dict[str, Any]]) -> dict[str, Any]:
    """The map, as data. Pure: everything comes from the iteration
    records; nothing from the clock or the host."""
    if not iterations:
        raise ValueError("no iterations — run tools/frontier_loop.py first")
    curve = []
    costs = []
    all_decides: list[dict[str, Any]] = []
    for it in iterations:
        sat = it["saturation"]
        total = len(sat["solved"]) + len(sat["open"])
        curve.append({
            "iteration": it["iteration"],
            "solved": len(sat["solved"]),
            "open": len(sat["open"]),
            "answered_fraction": (round(len(sat["solved"]) / total, 4)
                                  if total else None),
            "saturated": sat["saturated"],
        })
        decides = it.get("decide_records", [])
        all_decides.extend(decides)
        wall = sum(r.get("wall_s", 0.0) for r in decides)
        answered = sum(1 for v in it.get("verdicts", {}).values()
                       if v.get("verdict") in ("reachable", "unreachable"))
        costs.append({
            "iteration": it["iteration"],
            "decide_wall_s": round(wall, 6),
            "answered": answered,
            "cost_per_answer_s": (round(wall / answered, 6)
                                  if answered else None),
        })
    last = iterations[-1]
    return {
        "suite": last["saturation"]["suite"],
        "provenance": last["saturation"]["provenance"],
        "caps": last.get("caps", {}),
        "curve": curve,
        "cost_per_answer": costs,
        "verdicts": last.get("verdicts", {}),
        "census": {e["name"]: e.get("census")
                   for e in last["saturation"]["questions"]
                   if e.get("census") is not None},
        "board": last["saturation"]["board"],
        "saturated": last["saturation"]["saturated"],
        "failure_modes": failure_modes(all_decides),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Saturation report — `{report['suite']}`",
        "",
        f"Source: `{report['provenance']['source']}` "
        f"({report['provenance']['instances']} questions, sha256-pinned). "
        f"Caps: `{json.dumps(report['caps'], sort_keys=True)}` — capped "
        "results are capped, never full-suite.",
        "",
        f"**Saturated: {report['saturated']}** (no in-set target standing)"
        if report["saturated"] else
        f"**Saturated: {report['saturated']}**",
        "",
        "## The curve",
        "",
        "| iteration | solved | open | answered | saturated |",
        "|---|---|---|---|---|",
    ]
    for c in report["curve"]:
        lines.append(f"| {c['iteration']} | {c['solved']} | {c['open']} | "
                     f"{c['answered_fraction']} | {c['saturated']} |")
    lines += ["", "## Cost per answer", "",
              "| iteration | decide wall (s) | answered | s/answer |",
              "|---|---|---|---|"]
    for c in report["cost_per_answer"]:
        lines.append(f"| {c['iteration']} | {c['decide_wall_s']} | "
                     f"{c['answered']} | {c['cost_per_answer_s']} |")
    lines += ["", "## Way-census (last iteration)", ""]
    for name, census in sorted(report["census"].items()):
        v = report["verdicts"].get(name, {})
        routes = ", ".join(
            (" -> ".join(r["route"]) or "(native)")
            + f" [{r.get('assurance')}/{r.get('direction')}]"
            for r in census)
        lines.append(f"- **{name}** — verdict: "
                     f"{v.get('verdict', '(statics only)')}"
                     + (f" ({v.get('wall_s')}s, {v.get('engine')})"
                        if v.get("wall_s") is not None else "")
                     + f"; ways: {routes}")
    lines += ["", "## Terminal board", ""]
    if not report["board"]:
        lines.append("(empty — every question is solved)")
    for o in report["board"]:
        where = ("in-set" if o["in_known_set"]
                 else "frontier" if o["in_known_set"] is False
                 else "no honest target")
        lines.append(
            f"- `{o['id']}` [{where}] **{o['kind'] or '(none)'}** — "
            f"{o['evidence']['distinct_questions']} distinct question(s), "
            f"origins {o['evidence']['origins']}"
            + (f", registered in flight: "
               f"{', '.join(o['registered_matches'])}"
               if o["registered_matches"] else "")
            + (f"; required keep ⊇ {o['required']['keep']}"
               if o["required"]["keep"] else ""))
    fm = report["failure_modes"]
    if fm:
        lines += ["", "## Failure modes (the cost reading)", ""]
        for key, m in fm.items():
            lines.append(f"- `{key[:12]}` — {m['fit']} "
                         f"({m['points']} point(s)): {m['remedy']}")
    lines += ["", "---", "",
              "Generated by `tools/saturation_report.py` from "
              "`iterations.jsonl` — regenerating from the same input is "
              "byte-identical; `unknown`/`resource-out` are counted, "
              "never hidden."]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: saturation_report.py <iterations.jsonl> [out-prefix]")
        return 2
    with open(argv[1], encoding="utf-8") as f:
        iterations = [json.loads(line) for line in f if line.strip()]
    report = build_report(iterations)
    prefix = argv[2] if len(argv) > 2 else argv[1].rsplit("/", 1)[0] + "/report"
    with open(prefix + ".json", "w", encoding="utf-8") as f:
        f.write(json.dumps(report, indent=2, sort_keys=True, default=str)
                + "\n")
    with open(prefix + ".md", "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    print(f"wrote {prefix}.json and {prefix}.md "
          f"(saturated={report['saturated']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
