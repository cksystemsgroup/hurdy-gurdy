#!/usr/bin/env python3
"""dimacs language interpreter: checks a candidate total assignment
against a DIMACS CNF program. Observable "sat" is the ground truth
against which every witness gets replayed.

<program> is a .cnf file in DIMACS format.
<input> is a JSON file: {"assignment": [lit, lit, ...]} where each
lit is a nonzero int; its sign gives the variable's truth value.
A variable not mentioned in the assignment defaults to false.
"""
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
            if lits[-1] != 0:
                raise ValueError(f"clause not zero-terminated: {line!r}")
            clauses.append(lits[:-1])
    return nvars, nclauses, clauses


def main():
    program, input_path = sys.argv[1], sys.argv[2]
    nvars, nclauses, clauses = parse_cnf(program)
    with open(input_path, encoding="utf-8") as fh:
        data = json.load(fh)
    assign = {}
    for lit in data.get("assignment", []):
        assign[abs(lit)] = lit > 0

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
