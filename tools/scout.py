#!/usr/bin/env python3
"""tools/scout.py — scouting runs: measure an encoding before anyone
designs around it (FRONTIER-PLAN.md §1.5/O3).

Whether a demanded fragment wants a *native procedure* or a *reduction
into an existing fragment* is measurable in advance: run a prototype
encoding of sample instances across a parameter sweep and record the
blowup. Polynomial growth on samples → the reduction is honest, demand
the pair; explosive growth → demand the native procedure, with the
measured explosion as the justification. This is the strings/FP debate
in SMT run as an experiment instead of a taste argument.

Discipline:

* **Evidence, never verdicts.** A scout records ``kind="scout"`` cost
  rows to the books (opt-in, like every ledger record) and returns a
  growth reading; it answers no question, records no demand, and its
  ``scout`` origin exists precisely so probing is displayed apart and
  cannot launder into organic evidence.
* **Failures are evidence too.** An encoding that explodes has
  measured exactly what a brief needs to justify the native-procedure
  demand instead.

The growth fit reuses the report's failure-mode machinery
(tools/saturation_report.py) — one curve reader, not two.
"""

from __future__ import annotations

import math
import pathlib
import sys
import time
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from saturation_report import _fit  # noqa: E402  (one curve reader)


def scout(name: str, encode: Callable[[Any, int], bytes],
          samples: dict[str, Any], params: list[int]) -> dict[str, Any]:
    """Run one scouting campaign: ``encode(sample, param)`` across the
    sweep, sizes and times measured, growth fitted per sample. Rows go
    to the books when a ledger is configured."""
    from gurdy.core import ledger

    rows: list[dict[str, Any]] = []
    readings: dict[str, Any] = {}
    for sname, sample in sorted(samples.items()):
        pts = []
        for p in params:
            t0 = time.perf_counter()
            out = encode(sample, p)
            wall = time.perf_counter() - t0
            rows.append({"sample": sname, "param": p,
                         "out_bytes": len(out),
                         "wall_s": round(wall, 6)})
            ledger.record("scout", f"{name}/{sname}", wall_s=wall,
                          origin="scout", param=p, size=len(out))
            pts.append((float(p), float(max(len(out), 1))))
        lin_slope, lin_r2 = _fit(pts)
        log_slope, log_r2 = _fit([(x, math.log(y)) for x, y in pts])
        if log_slope > 0.05 and log_r2 > max(lin_r2, 0.9):
            growth = "explosive"
        elif lin_slope >= 0 and lin_r2 > 0.9:
            growth = "polynomial-ish"
        else:
            growth = "flat-or-unclear"
        readings[sname] = {"growth": growth,
                           "sizes": [int(y) for _x, y in pts]}
    explosive = [s for s, r in readings.items() if r["growth"] == "explosive"]
    recommendation = (
        "every sampled embedding explodes — the honest demand is the "
        "native procedure, and these measurements are its brief's "
        "justification" if explosive and len(explosive) == len(readings)
        else "the encoding is affordable on the samples — the honest "
             "demand is the reduction pair"
        if not explosive
        else "mixed — split the cluster before demanding anything")
    return {"name": name, "params": list(params), "rows": rows,
            "readings": readings, "recommendation": recommendation}


def demo() -> dict[str, Any]:
    """The worked example on the one prototype encoding the platform
    already ships: the bridge's unrolling (BTOR2 → SMT-LIB at bound
    k). Expected reading: polynomial-ish — which is exactly why the
    bridge is a pair and not a demand."""
    import gurdy.cli  # noqa: F401
    from gurdy.languages.btor2.build import Builder
    from gurdy.pairs.btor2_smtlib import translate

    def counter(bad_at: int) -> str:
        b = Builder()
        c = b.state(8, "c")
        b.init(c, b.zero(8))
        b.next(c, b.op2("add", 8, c, b.one(8)))
        b.bad(b.op2("eq", 1, c, b.constd(8, bad_at)))
        return b.to_text()

    return scout("btor2-smtlib-unroll",
                 lambda text, k: translate({"system": text, "k": k}),
                 {"counter-small": counter(50), "counter-large": counter(200)},
                 params=[4, 8, 16, 32])


def main() -> int:
    report = demo()
    for sname, r in report["readings"].items():
        print(f"{sname}: {r['growth']}  sizes={r['sizes']}")
    print(f"recommendation: {report['recommendation']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
