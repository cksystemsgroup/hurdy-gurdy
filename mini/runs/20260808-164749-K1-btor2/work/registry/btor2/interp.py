#!/usr/bin/env python3
"""btor2 language interpreter.

Parses a subset of BTOR2 (sort bitvec, zero/one/state/input/constd,
add/sub/mul/and/not/ite/ult/eq, init/next/bad/constraint) and replays a
concrete step trace against it.

<program> <input> -> observables JSON on stdout.

<input> is a JSON list of per-step dicts (input-symbol -> integer
value). Step i's dict supplies the input values used to evaluate
bad/constraint at state i AND to compute the transition to state i+1.
Determinism: pure function of program text + input list, no I/O, no
randomness.
"""
import json
import sys


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


def main():
    program_path, input_path = sys.argv[1], sys.argv[2]
    with open(program_path, encoding="utf-8") as fh:
        P = parse(fh.read())
    with open(input_path, encoding="utf-8") as fh:
        steps = json.load(fh)
    if not isinstance(steps, list):
        steps = []
    state_vals = initial_state(P)
    bad_found, depth, valid_steps = False, -1, 0
    for i, inp in enumerate(steps):
        input_vals = inp if isinstance(inp, dict) else {}
        b, ok, nxt = step(P, state_vals, input_vals)
        if not ok:
            break
        valid_steps = i + 1
        if b:
            bad_found, depth = True, i
            break
        state_vals = nxt
    print(json.dumps({"bad": bad_found, "depth": depth, "steps": valid_steps},
                     sort_keys=True))


if __name__ == "__main__":
    main()
