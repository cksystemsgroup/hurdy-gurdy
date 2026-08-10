#!/usr/bin/env python3
"""Broken: uses pigeons >= holes instead of the strict pigeons > holes
the counting argument actually needs, so it wrongly claims a
contradiction when pigeons == holes (a case that is satisfiable)."""
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


class UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def pigeon_partition(n_vars, clauses):
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
    return pos


def neg_pair_set(clauses):
    return {frozenset((-c[0], -c[1]))
            for c in clauses if len(c) == 2 and c[0] < 0 and c[1] < 0}


def hole_partition(n_vars, neg):
    uf = UnionFind(range(1, n_vars + 1))
    for pair in neg:
        a, b = tuple(pair)
        uf.union(a, b)
    groups = {}
    for v in range(1, n_vars + 1):
        groups.setdefault(uf.find(v), []).append(v)
    for g in groups.values():
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                if frozenset((g[i], g[j])) not in neg:
                    return None
    return list(groups.values())


def main(argv):
    program, _mode, observable, _bound, _wall_s = argv[:5]
    if observable != "sat":
        print(json.dumps({"kind": "partial", "progress": {}}, sort_keys=True))
        return 0
    n_vars, clauses = parse_cnf(program)
    pigeons = pigeon_partition(n_vars, clauses)
    if pigeons is None:
        print(json.dumps({"kind": "partial", "progress": {}}, sort_keys=True))
        return 0
    holes = hole_partition(n_vars, neg_pair_set(clauses))
    if holes is None:
        print(json.dumps({"kind": "partial", "progress": {}}, sort_keys=True))
        return 0
    p, h = len(pigeons), len(holes)
    if p < h:  # should be `p <= h`
        print(json.dumps({"kind": "partial", "progress": {}}, sort_keys=True))
        return 0
    cert = {"holes": [sorted(g) for g in holes]}
    print(json.dumps({"kind": "all", "bound": "inf", "cert": cert},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
