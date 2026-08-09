#!/usr/bin/env python3
"""Mutant: constraint nodes are never enforced during the search."""
import itertools
import json
import sys
import time

MAX_STATES = 200_000
MAX_COMBOS = 4096


def mask(w):
    return (1 << w) - 1


def parse(text):
    nodes, sorts = {}, {}
    inits, nexts = {}, {}
    bads, constraints = [], []
    states, inputs = [], []
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        tok = line.split()
        nid, op, rest = int(tok[0]), tok[1], tok[2:]
        if op == "sort":
            if rest[0] != "bitvec":
                raise ValueError(f"unsupported sort {rest[0]!r}")
            sorts[nid] = int(rest[1])
            nodes[nid] = {"op": "sort"}
        elif op in ("zero", "one"):
            nodes[nid] = {"op": op, "sid": int(rest[0])}
        elif op == "constd":
            nodes[nid] = {"op": op, "sid": int(rest[0]), "value": int(rest[1])}
        elif op == "input":
            name = rest[1] if len(rest) > 1 else f"n{nid}"
            nodes[nid] = {"op": op, "sid": int(rest[0]), "name": name}
            inputs.append(nid)
        elif op == "state":
            name = rest[1] if len(rest) > 1 else f"n{nid}"
            nodes[nid] = {"op": op, "sid": int(rest[0]), "name": name}
            states.append(nid)
        elif op in ("not",):
            nodes[nid] = {"op": op, "sid": int(rest[0]), "a": int(rest[1])}
        elif op in ("add", "sub", "mul", "and", "eq", "ult"):
            nodes[nid] = {"op": op, "sid": int(rest[0]), "a": int(rest[1]),
                          "b": int(rest[2])}
        elif op == "ite":
            nodes[nid] = {"op": op, "sid": int(rest[0]), "cond": int(rest[1]),
                          "a": int(rest[2]), "b": int(rest[3])}
        elif op == "init":
            inits[int(rest[1])] = int(rest[2])
        elif op == "next":
            nexts[int(rest[1])] = int(rest[2])
        elif op == "bad":
            bads.append(int(rest[0]))
        elif op == "constraint":
            constraints.append(int(rest[0]))
        else:
            raise ValueError(f"unsupported op {op!r}")
    return {"nodes": nodes, "sorts": sorts, "inits": inits, "nexts": nexts,
            "bads": bads, "constraints": constraints, "states": states,
            "inputs": inputs}


def width_of(P, nid):
    return P["sorts"][P["nodes"][nid]["sid"]]


def eval_node(P, nid, state_vals, input_vals, memo):
    if nid in memo:
        return memo[nid]
    n = P["nodes"][nid]
    op = n["op"]
    if op == "zero":
        v = 0
    elif op == "one":
        v = 1
    elif op == "constd":
        v = n["value"]
    elif op == "input":
        v = input_vals.get(n["name"], 0)
    elif op == "state":
        v = state_vals.get(nid, 0)
    elif op == "not":
        v = ~eval_node(P, n["a"], state_vals, input_vals, memo)
    elif op in ("add", "sub", "mul", "and", "eq", "ult"):
        a = eval_node(P, n["a"], state_vals, input_vals, memo)
        b = eval_node(P, n["b"], state_vals, input_vals, memo)
        v = {"add": a + b, "sub": a - b, "mul": a * b, "and": a & b,
             "eq": int(a == b), "ult": int(a < b)}[op]
    elif op == "ite":
        c = eval_node(P, n["cond"], state_vals, input_vals, memo)
        v = (eval_node(P, n["a"], state_vals, input_vals, memo) if c else
             eval_node(P, n["b"], state_vals, input_vals, memo))
    else:
        raise ValueError(f"cannot evaluate op {op!r}")
    v &= mask(width_of(P, nid))
    memo[nid] = v
    return v


def initial_state(P):
    vals = {}
    for s in P["states"]:
        vals[s] = (eval_node(P, P["inits"][s], {}, {}, {})
                   if s in P["inits"] else 0)
    return vals


def step(P, state_vals, input_vals):
    memo = {}
    bad = any(eval_node(P, b, state_vals, input_vals, memo)
              for b in P["bads"])
    ok = True  # MUTATION: constraints never enforced.
    nxt = {}
    for s in P["states"]:
        nxt[s] = (eval_node(P, P["nexts"][s], state_vals, input_vals, memo)
                  if s in P["nexts"] else state_vals.get(s, 0))
    return bad, ok, nxt


def input_combos(P, cap=MAX_COMBOS):
    names = [P["nodes"][i]["name"] for i in P["inputs"]]
    widths = [width_of(P, i) for i in P["inputs"]]
    total = 1
    for w in widths:
        total *= (1 << w)
        if total > cap:
            raise OverflowError("input space too large for exhaustive search")
    return [dict(zip(names, vals))
            for vals in itertools.product(*[range(1 << w) for w in widths])]


def state_key(P, vals):
    return tuple(vals[s] for s in P["states"])


def state_dict(P, vals):
    return {P["nodes"][s]["name"]: vals[s] for s in P["states"]}


def reconstruct(edge, leaf_key, leaf_input):
    trail = []
    k = leaf_key
    while k in edge:
        pk, inp = edge[k]
        trail.append(inp)
        k = pk
    trail.reverse()
    trail.append(leaf_input)
    return trail


def search(P, wall):
    t0 = time.monotonic()
    try:
        combos = input_combos(P)
    except OverflowError as exc:
        return {"outcome": "budget", "depth": -1, "layers": [], "visited": {},
                "note": str(exc)}

    init = initial_state(P)
    start = state_key(P, init)
    visited = {start: init}
    edge = {}
    layers = [[start]]
    frontier = [start]
    depth = 0

    while True:
        if time.monotonic() - t0 > wall * 0.8:
            return {"outcome": "budget", "depth": depth - 1,
                    "layers": layers[:depth], "visited": visited}
        new_frontier = []
        found = None
        for skey in frontier:
            sval = visited[skey]
            for inp in combos:
                b, ok, nxt = step(P, sval, inp)
                if not ok:
                    continue
                if b:
                    found = reconstruct(edge, skey, inp)
                    break
                nkey = state_key(P, nxt)
                if nkey not in visited:
                    visited[nkey] = nxt
                    edge[nkey] = (skey, inp)
                    new_frontier.append(nkey)
            if found is not None:
                break
        if found is not None:
            return {"outcome": "bad", "depth": depth, "trail": found,
                    "layers": layers, "visited": visited}
        if not new_frontier:
            return {"outcome": "fixpoint", "depth": depth, "layers": layers,
                    "visited": visited}
        if len(visited) > MAX_STATES:
            return {"outcome": "budget", "depth": depth, "layers": layers,
                    "visited": visited}
        layers.append(new_frontier)
        frontier = new_frontier
        depth += 1


def cert_layers(P, visited, layers):
    return [[state_dict(P, visited[k]) for k in layer] for layer in layers]


def main():
    program_path, mode, observable, bound_s, wall_s = sys.argv[1:6]
    wall = float(wall_s)
    with open(program_path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        P = parse(text)
    except Exception as exc:
        print(json.dumps({"kind": "partial",
                          "progress": {"note": f"parse error: {exc}"}}))
        return
    if observable != "bad":
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"cannot decide {observable!r}"}}))
        return
    bound_i = None if bound_s == "inf" else int(bound_s)

    result = search(P, wall)
    outcome, depth = result["outcome"], result["depth"]

    if outcome == "bad":
        if bound_i is not None and depth > bound_i:
            safe_bound = depth - 1
            layers = cert_layers(P, result["visited"], result["layers"][:depth])
            print(json.dumps({"kind": "all", "bound": safe_bound,
                              "cert": {"bound": safe_bound, "layers": layers}}))
            return
        print(json.dumps({"kind": "witness", "payload": result["trail"]}))
        return

    if outcome == "fixpoint":
        layers = cert_layers(P, result["visited"], result["layers"])
        print(json.dumps({"kind": "all", "bound": "inf",
                          "cert": {"bound": "inf", "layers": layers}}))
        return

    if depth < 0:
        print(json.dumps({"kind": "partial", "progress": {
            "note": result.get("note", "budget exhausted before any depth "
                                        "was fully verified"),
            "bound_reached": -1}}))
        return
    layers = cert_layers(P, result["visited"], result["layers"])
    print(json.dumps({"kind": "all", "bound": depth,
                      "cert": {"bound": depth, "layers": layers}}))


if __name__ == "__main__":
    main()
