#!/usr/bin/env python3
"""Bad interpreter: never checks the last clause of the formula. Must
fail vectors where the last clause is the one that's violated."""
import json
import sys


def parse_cnf(path):
    nvars = nclauses = 0
    clauses = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line[0] == "c":
                continue
            if line[0] == "p":
                _, _, nv, nc = line.split()
                nvars, nclauses = int(nv), int(nc)
                continue
            lits = [int(x) for x in line.split()]
            clauses.append(lits[:-1])
    return nvars, nclauses, clauses


def main():
    program, input_path = sys.argv[1], sys.argv[2]
    nvars, nclauses, clauses = parse_cnf(program)
    clauses = clauses[:-1]  # the bug: drop the last clause entirely
    with open(input_path, encoding="utf-8") as fh:
        data = json.load(fh)
    assign = {abs(lit): lit > 0 for lit in data.get("assignment", [])}

    sat = True
    for clause in clauses:
        satisfied = False
        for lit in clause:
            v = abs(lit)
            val = assign.get(v, False)
            if (lit > 0 and val) or (lit < 0 and not val):
                satisfied = True
                break
        if not satisfied:
            sat = False
            break

    complete = all(v in assign for v in range(1, nvars + 1))
    print(json.dumps({
        "sat": sat,
        "complete": complete,
        "depth": len(assign),
        "num_vars": nvars,
        "num_clauses": nclauses,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
