#!/usr/bin/env python3
"""Broken: only checks the first clause, ignores the rest."""
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
    val = {}
    for lit in assignment:
        lit = int(lit)
        val[abs(lit)] = lit > 0

    def lit_true(lit):
        v = val.get(abs(lit))
        if v is None:
            return False
        return v if lit > 0 else not v

    first = clauses[0] if clauses else []
    sat = any(lit_true(lit) for lit in first)
    print(json.dumps({"sat": sat, "depth": n_vars}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
