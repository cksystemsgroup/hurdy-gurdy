#!/usr/bin/env python3
"""Bad solver: decides correctly via the real DPLL search, but on
unsat fabricates a trivial one-line proof instead of shipping the
real one derived from the search. Must fail because the fabricated
proof is not RUP for formulas that need real case-splitting."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import dpll_core  # noqa: E402


def main():
    program, mode, observable, bound, wall_s = sys.argv[1:6]
    nvars, nclauses, clauses = dpll_core.parse_cnf(program)
    model, proof, nodes = dpll_core.solve(
        nvars, clauses, time.monotonic() + max(1.0, float(wall_s) - 2.0),
        time.monotonic)
    if model is not None:
        assignment = sorted((v if val else -v for v, val in model.items()),
                            key=abs)
        print(json.dumps({"kind": "witness",
                          "payload": {"assignment": assignment}}))
    else:
        print(json.dumps({"kind": "all", "bound": "inf",
                          "cert": {"format": "rup", "clauses": [[]]}}))


if __name__ == "__main__":
    main()
