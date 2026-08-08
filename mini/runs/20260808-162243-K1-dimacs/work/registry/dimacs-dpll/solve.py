#!/usr/bin/env python3
"""dimacs solver: from-scratch chronological DPLL (no external SAT
engine at all). SAT -> witness(assignment). UNSAT -> all(bound="inf",
cert=<RUP proof>) discharged by this entry's own RUP checker — a
decision procedure and a certificate format independent of both
cadical and z3.

<program> <mode> <observable> <bound> <wall_s> -> result JSON on stdout.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dpll_core  # noqa: E402


def partial(note, **kw):
    print(json.dumps({"kind": "partial",
                      "progress": {"note": note, **kw}}, sort_keys=True))


def main():
    program, mode, observable, bound, wall_s = sys.argv[1:6]
    if observable != "sat":
        return partial(f"observable {observable!r} not decided")

    budget = max(1.0, float(wall_s) - 2.0)
    t0 = time.monotonic()
    nvars, nclauses, clauses = dpll_core.parse_cnf(program)
    try:
        model, proof, nodes = dpll_core.solve(
            nvars, clauses, t0 + budget, time.monotonic)
    except dpll_core.Budget as exc:
        return partial("dpll node budget exhausted before a verdict",
                       nodes_explored=exc.args[0], wall_s=wall_s)

    if model is not None:
        assignment = sorted((v if val else -v for v, val in model.items()),
                            key=abs)
        print(json.dumps({"kind": "witness",
                          "payload": {"assignment": assignment}},
                         sort_keys=True))
    else:
        print(json.dumps({"kind": "all", "bound": "inf",
                          "cert": {"format": "rup", "clauses": proof}},
                         sort_keys=True))


if __name__ == "__main__":
    main()
