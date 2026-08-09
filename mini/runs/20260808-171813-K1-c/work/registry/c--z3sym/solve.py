#!/usr/bin/env python3
"""c--z3sym: bounded symbolic execution (own compile-head, csubset.py)
discharged by z3. decides ["violation"]. Escalates the loop-unroll
bound K until either a violation is found (witness, sound at any K)
or the unwinding-deficit formula is proved UNSAT (a complete proof --
bound "inf"). If wall runs out first, reports the best bound reached
as a k-bounded 'all' rather than a bare partial.
"""
import json
import sys
import time

import z3

from csubset import build, signed


def decide(program_path, wall_s):
    with open(program_path, encoding="utf-8") as fh:
        src = fh.read()
    t0 = time.monotonic()
    k = 4
    best_k = None
    while True:
        remaining = wall_s - (time.monotonic() - t0)
        if remaining < 1.0:
            if best_k is not None:
                return {"kind": "all", "bound": best_k, "cert": None}
            return {"kind": "partial",
                    "progress": {"note": "wall budget exhausted",
                                "bound_reached": 0}}
        violation, deficit, nondet_vars = build(src, k)
        # Search only among assignments where every loop actually
        # terminates within k iterations (not deficit): the merged
        # post-loop state for a still-looping assignment is a k-step
        # artifact, not the program's real behavior, so a "witness"
        # found there would not reliably replay.
        s = z3.Solver()
        s.set("timeout", int(max(1, remaining) * 1000))
        s.add(violation)
        s.add(z3.Not(deficit))
        res = s.check()
        if res == z3.sat:
            model = s.model()
            vals = [signed(model.eval(v, model_completion=True))
                   for v in nondet_vars]
            return {"kind": "witness", "payload": {"nondet": vals}}
        if res == z3.unknown:
            if best_k is not None:
                return {"kind": "all", "bound": best_k, "cert": None}
            return {"kind": "partial",
                    "progress": {"note": "z3 unknown deciding violation",
                                "bound_reached": 0}}
        # UNSAT: no violation among assignments settled within k unrollings
        best_k = k
        remaining = wall_s - (time.monotonic() - t0)
        if remaining < 1.0:
            return {"kind": "all", "bound": best_k, "cert": None}
        s2 = z3.Solver()
        s2.set("timeout", int(max(1, remaining) * 1000))
        s2.add(deficit)
        res2 = s2.check()
        if res2 == z3.unsat:
            return {"kind": "all", "bound": "inf", "cert": {"unroll_k": k}}
        if res2 == z3.unknown or k >= 4096:
            return {"kind": "all", "bound": best_k, "cert": None}
        k *= 2


def main(argv):
    program, mode, observable, bound, wall_s = argv[:5]
    if observable != "violation":
        print(json.dumps({"kind": "partial",
                          "progress": {"note": f"cannot decide {observable!r}"}}))
        return 0
    print(json.dumps(decide(program, float(wall_s))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
