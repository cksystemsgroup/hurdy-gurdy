#!/usr/bin/env python3
"""Bad solver: relaxes pigeons > holes to pigeons >= holes. Must be
caught claiming UNSAT on a pigeons == holes instance, which is
satisfiable (identity mapping).
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
            if lits and lits[-1] == 0:
                lits = lits[:-1]
            clauses.append(tuple(sorted(lits)))
    return nvars, nclauses, clauses


def var_of(p, h, holes):
    return (p - 1) * holes + h


def canonical_php(pigeons, holes):
    clauses = []
    for p in range(1, pigeons + 1):
        clauses.append(tuple(sorted(var_of(p, h, holes)
                                     for h in range(1, holes + 1))))
    for h in range(1, holes + 1):
        for p in range(1, pigeons + 1):
            for q in range(p + 1, pigeons + 1):
                clauses.append(tuple(sorted((-var_of(p, h, holes),
                                              -var_of(q, h, holes)))))
    return clauses


def factor_pairs(nvars):
    return [(m, nvars // m) for m in range(1, nvars + 1) if nvars % m == 0]


def partial(note, **kw):
    print(json.dumps({"kind": "partial",
                      "progress": {"note": note, **kw}}, sort_keys=True))


def detect_off_by_one(nvars, nclauses, clauses):
    given = sorted(clauses)
    for pigeons, holes in factor_pairs(nvars):
        if pigeons < holes or holes == 0:  # bug: should be <=
            continue
        expect_n = pigeons + holes * pigeons * (pigeons - 1) // 2
        if expect_n != nclauses:
            continue
        if sorted(canonical_php(pigeons, holes)) == given:
            return pigeons, holes
    return None


def main():
    program, mode, observable, bound, wall_s = sys.argv[1:6]
    if observable != "sat":
        return partial(f"observable {observable!r} not decided")
    nvars, nclauses, clauses = parse_cnf(program)
    found = detect_off_by_one(nvars, nclauses, clauses)
    if found is None:
        return partial("not a recognized pigeonhole encoding")
    pigeons, holes = found
    print(json.dumps({"kind": "all", "bound": "inf",
                      "cert": {"format": "php-struct",
                               "pigeons": pigeons, "holes": holes}},
                     sort_keys=True))


if __name__ == "__main__":
    main()
