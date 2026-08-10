#!/usr/bin/env python3
"""Broken: treats every literal as if it were positive (drops negation)."""
import json
import sys


def parse_cnf(path):
    n_vars = 0
    clauses = []
    cur = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line[0] == "c":
                continue
            if line[0] == "p":
                n_vars = int(line.split()[2])
                continue
            for tok in line.split():
                v = int(tok)
                if v == 0:
                    clauses.append(cur)
                    cur = []
                else:
                    cur.append(v)
    if cur:
        clauses.append(cur)
    return n_vars, clauses


def main(argv):
    program, input_path = argv[0], argv[1]
    n_vars, clauses = parse_cnf(program)
    with open(input_path, encoding="utf-8") as fh:
        assignment = json.load(fh)
    val = {abs(int(x)) for x in assignment}  # sign dropped on purpose

    def lit_true(lit):
        return abs(lit) in val

    sat = all(any(lit_true(lit) for lit in clause) for clause in clauses)
    print(json.dumps({"sat": sat, "depth": n_vars}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
