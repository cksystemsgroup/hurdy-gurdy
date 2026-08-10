#!/usr/bin/env python3
"""Solver pair c -> result via an independent Z3 bitvector symbolic
executor (czlib.py, no code shared with the cbmc-based solver or with the
language's own interp.py). Bound schedule is a fixed function of the wall
budget, never of measured elapsed time, so repeated runs are deterministic."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import czlib


def main():
    program = sys.argv[1]
    wall_s = float(sys.argv[5])
    with open(program, encoding='utf-8') as fh:
        src = fh.read()
    stmts = czlib.parse_program(src)
    schedule = czlib.bound_schedule(wall_s)
    per_call_ms = int(min(wall_s, 10.0) * 1000)
    last_ok = None
    tried = []
    for n in schedule:
        nondet_calls, viol, resid = czlib.run_bounded(stmts, n)
        s = czlib.z3.Solver()
        s.set('timeout', per_call_ms)
        s.add(viol)
        res = s.check()
        if res == czlib.z3.unsat:
            payload = czlib.extract_witness(nondet_calls, s.model())
            print(json.dumps({"kind": "witness",
                              "payload": {"nondet": payload}}, sort_keys=True))
            return
        tried.append(n)
        if res != czlib.z3.unsat:
            break
        s2 = czlib.z3.Solver()
        s2.set('timeout', per_call_ms)
        s2.add(resid)
        res2 = s2.check()
        if res2 == czlib.z3.unsat:
            last_ok = (n, True)
            break
        if res2 != czlib.z3.sat:
            break
        last_ok = (n, False)
    if last_ok is None:
        print(json.dumps({"kind": "partial", "progress": {
            "note": "z3 gave no usable verdict", "tried": tried}},
            sort_keys=True))
        return
    n, complete = last_ok
    print(json.dumps({"kind": "all", "bound": "inf" if complete else n,
                      "cert": {"strategy": "unroll", "bound": n,
                               "complete": complete}}, sort_keys=True))


if __name__ == '__main__':
    main()
