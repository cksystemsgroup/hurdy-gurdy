#!/usr/bin/env python3
"""Mutant: runs the real search but fabricates an 'inf' certificate that
drops the search's own last layer — an unsound closure claim the
discharge check must catch."""
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
    ok = all(eval_node(P, c, state_vals, input_vals, memo)
             for c in P["constraints"])
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


def search(P, wall):
    t0 = time.monotonic()
    combos = input_combos(P)
    init = initial_state(P)
    start = state_key(P, init)
    visited = {start: init}
    layers = [[start]]
    frontier = [start]
    depth = 0
    while True:
        if time.monotonic() - t0 > wall * 0.8:
            return {"outcome": "budget", "layers": layers, "visited": visited}
        new_frontier = []
        for skey in frontier:
            sval = visited[skey]
            for inp in combos:
                b, ok, nxt = step(P, sval, inp)
                if not ok or b:
                    continue
                nkey = state_key(P, nxt)
                if nkey not in visited:
                    visited[nkey] = nxt
                    new_frontier.append(nkey)
        if not new_frontier:
            return {"outcome": "fixpoint", "layers": layers,
                    "visited": visited}
        if len(visited) > MAX_STATES:
            return {"outcome": "budget", "layers": layers,
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
    P = parse(text)
    if observable != "bad":
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"cannot decide {observable!r}"}}))
        return
    result = search(P, wall)
    layers = cert_layers(P, result["visited"], result["layers"])
    # MUTATION: drop the last layer from the certificate while still
    # claiming the full ('inf') closure — an unsound shrink the honest
    # solver never performs.
    layers = layers[:-1] if len(layers) > 1 else layers
    print(json.dumps({"kind": "all", "bound": "inf",
                      "cert": {"bound": "inf", "layers": layers}}))


if __name__ == "__main__":
    main()
