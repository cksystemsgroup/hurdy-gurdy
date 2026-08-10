#!/usr/bin/env python3
"""Structural pigeonhole solver: recognizes the canonical PHP(m, n)
encoding (m > n) and certifies UNSAT by the counting argument, in
time polynomial in the formula size -- no branching, no proof search,
nothing a CDCL engine would recognize as "solving". Abstains on
anything it cannot recognize; a false positive is never risked.

<program> <mode> <observable> <bound> <wall_s> -> result JSON on stdout.
"""
import json
import sys

from php_struct import parse_cnf, detect


def partial(note, **kw):
    print(json.dumps({"kind": "partial",
                      "progress": {"note": note, **kw}}, sort_keys=True))


def main():
    program, mode, observable, bound, wall_s = sys.argv[1:6]
    if observable != "sat":
        return partial(f"observable {observable!r} not decided")
    nvars, nclauses, clauses = parse_cnf(program)
    found = detect(nvars, nclauses, clauses)
    if found is None:
        return partial("not a recognized pigeonhole encoding")
    pigeons, holes = found
    print(json.dumps({"kind": "all", "bound": "inf",
                      "cert": {"format": "php-struct",
                               "pigeons": pigeons, "holes": holes}},
                     sort_keys=True))


if __name__ == "__main__":
    main()
