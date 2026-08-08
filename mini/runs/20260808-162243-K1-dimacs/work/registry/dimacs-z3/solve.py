#!/usr/bin/env python3
"""dimacs solver backed by z3's DIMACS front end — a codebase wholly
independent of cadical/cake_lpr, giving disjoint-lineage corroboration.
SAT -> witness(assignment). UNSAT -> all(bound="inf", cert=None):
z3's CLI does not hand us a checkable proof here, so this stays a
claimed universal rather than a certified one.

<program> <mode> <observable> <bound> <wall_s> -> result JSON on stdout.
"""
import json
import subprocess
import sys


def partial(note, **kw):
    print(json.dumps({"kind": "partial",
                      "progress": {"note": note, **kw}}, sort_keys=True))


def main():
    program, mode, observable, bound, wall_s = sys.argv[1:6]
    if observable != "sat":
        return partial(f"observable {observable!r} not decided")

    limit = max(1, int(float(wall_s)))
    try:
        p = subprocess.run(
            ["z3", "-dimacs", f"-T:{limit}", program],
            capture_output=True, timeout=limit + 10, text=True)
    except subprocess.TimeoutExpired:
        return partial("z3 timed out", wall_s=wall_s)

    out = p.stdout
    if "s SATISFIABLE" in out:
        assignment = []
        for line in out.splitlines():
            if line.startswith("v "):
                assignment += [int(x) for x in line[2:].split()]
        assignment = [x for x in assignment if x != 0]
        print(json.dumps({"kind": "witness",
                          "payload": {"assignment": assignment}},
                         sort_keys=True))
    elif "s UNSATISFIABLE" in out:
        print(json.dumps({"kind": "all", "bound": "inf", "cert": None},
                         sort_keys=True))
    else:
        return partial("z3 returned neither sat nor unsat",
                       returncode=p.returncode)


if __name__ == "__main__":
    main()
