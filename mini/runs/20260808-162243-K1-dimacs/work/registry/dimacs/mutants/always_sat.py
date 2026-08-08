#!/usr/bin/env python3
"""Bad interpreter: claims every clause is satisfied. Must fail the
vectors that expect sat=false."""
import json
import sys


def parse_cnf(path):
    nvars = nclauses = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line[0] == "c":
                continue
            if line[0] == "p":
                _, _, nv, nc = line.split()
                nvars, nclauses = int(nv), int(nc)
    return nvars, nclauses


def main():
    program, input_path = sys.argv[1], sys.argv[2]
    nvars, nclauses = parse_cnf(program)
    with open(input_path, encoding="utf-8") as fh:
        data = json.load(fh)
    assign = {abs(lit): lit > 0 for lit in data.get("assignment", [])}
    complete = all(v in assign for v in range(1, nvars + 1))
    print(json.dumps({
        "sat": True,
        "complete": complete,
        "depth": len(assign),
        "num_vars": nvars,
        "num_clauses": nclauses,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
