#!/usr/bin/env python3
"""dimacs solver via z3's own DIMACS front end — a wholly independent
codebase from cadical/drat-trim/cake_lpr, used for corroboration.

solve.py <program> <mode> <observable> <bound> <wall_s>

SAT   -> witness(payload=<full signed assignment>)
UNSAT -> all(bound="inf")            (no certificate: z3 -dimacs emits none)
else  -> partial(progress)
"""
import json
import subprocess
import sys


def main(argv):
    program, _mode, observable, _bound, wall_s = argv[:5]
    wall = float(wall_s)
    if observable != "sat":
        print(json.dumps({"kind": "partial",
                          "progress": {"note": "unsupported observable",
                                       "observable": observable}},
                         sort_keys=True))
        return 0

    z3_wall = max(1, int(wall))
    try:
        p = subprocess.run(["z3", "-dimacs", f"-T:{z3_wall}", program],
                           capture_output=True, timeout=wall + 5, text=True)
        lines = p.stdout.splitlines()
    except subprocess.TimeoutExpired:
        lines = []

    if lines and lines[0] == "s SATISFIABLE":
        payload = []
        for line in lines[1:]:
            if line.startswith("v "):
                payload += [int(t) for t in line[2:].split()]
        if payload and payload[-1] == 0:
            payload = payload[:-1]
        out = {"kind": "witness", "payload": payload}
    elif lines and lines[0] == "s UNSATISFIABLE":
        out = {"kind": "all", "bound": "inf", "cert": None}
    else:
        out = {"kind": "partial",
               "progress": {"note": "z3 exhausted its budget without a "
                            "verdict", "wall_s": wall,
                            "raw": lines[0] if lines else ""}}

    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
