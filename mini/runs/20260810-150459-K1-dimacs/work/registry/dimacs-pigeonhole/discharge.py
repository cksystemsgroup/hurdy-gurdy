#!/usr/bin/env python3
"""Independently re-verify a pigeonhole counting certificate straight from
the raw CNF — recomputes the pigeon side itself (a direct scan, no
search to trust) and checks the supplied hole side against the actual
NAND clauses, rather than trusting solve.py's union-find derivation.

discharge.py <program> <cert> -> {"ok": bool, "obligations": {...}}
"""
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


def pigeon_count(n_vars, clauses):
    all_vars = set(range(1, n_vars + 1))
    pos = [c for c in clauses if c and all(l > 0 for l in c)]
    seen = {}
    for idx, c in enumerate(pos):
        for v in c:
            if v in seen:
                return None
            seen[v] = idx
    if set(seen.keys()) != all_vars:
        return None
    return len(pos)


def main(argv):
    program, cert_path = argv[0], argv[1]
    try:
        with open(cert_path, encoding="utf-8") as fh:
            cert = json.load(fh)
        holes = cert["holes"]
        n_vars, clauses = parse_cnf(program)

        p = pigeon_count(n_vars, clauses)
        if p is None:
            raise ValueError("no pigeon partition in the raw formula")

        neg = {frozenset((-c[0], -c[1]))
               for c in clauses if len(c) == 2 and c[0] < 0 and c[1] < 0}

        all_vars = set(range(1, n_vars + 1))
        covered = set()
        for g in holes:
            g = [int(v) for v in g]
            if not set(g).isdisjoint(covered):
                raise ValueError("hole groups overlap")
            covered.update(g)
            for i in range(len(g)):
                for j in range(i + 1, len(g)):
                    if frozenset((g[i], g[j])) not in neg:
                        raise ValueError("claimed hole is not a clique "
                                         "in the actual formula")
        if covered != all_vars:
            raise ValueError("hole groups do not partition all variables")

        h = len(holes)
        if not (p > h):
            raise ValueError(f"pigeons ({p}) do not exceed holes ({h})")

        print(json.dumps({"ok": True, "obligations": {"pigeons": p,
                          "holes": h}}, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"ok": False, "obligations": {}}, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
