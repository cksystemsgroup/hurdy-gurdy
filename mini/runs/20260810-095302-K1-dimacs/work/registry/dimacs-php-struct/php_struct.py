#!/usr/bin/env python3
"""Shared core for the structural pigeonhole decision procedure: no
SAT search anywhere. It recognizes when a CNF *is* (up to the
standard variable numbering) the canonical pigeonhole encoding
PHP(pigeons, holes) with pigeons > holes, and if so the formula is
UNSAT by the counting argument alone -- polynomial-time to check,
completely independent of CDCL search on the same formula.
"""


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
    """Standard 1-indexed encoding: pigeon p (1..pigeons) in hole h
    (1..holes) is the boolean variable (p-1)*holes + h."""
    return (p - 1) * holes + h


def canonical_php(pigeons, holes):
    """The textbook encoding: one at-least-one-hole clause per
    pigeon, one at-most-one-pigeon clause per hole per pigeon pair."""
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


def detect(nvars, nclauses, clauses):
    """Try to recognize (nvars, nclauses, clauses) as canonical
    PHP(pigeons, holes) with pigeons > holes. Returns (pigeons, holes)
    or None -- abstaining is always safe, a false positive is not."""
    given = sorted(clauses)
    for pigeons, holes in factor_pairs(nvars):
        if pigeons <= holes or holes == 0:
            continue
        expect_n = pigeons + holes * pigeons * (pigeons - 1) // 2
        if expect_n != nclauses:
            continue
        if sorted(canonical_php(pigeons, holes)) == given:
            return pigeons, holes
    return None
