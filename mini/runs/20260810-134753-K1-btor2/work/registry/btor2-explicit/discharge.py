#!/usr/bin/env python3
"""Discharge: independently verify a bounded-safety certificate.

<program> <cert> -> {"ok": bool, "obligations": {...}}

A cert is {"bound": k|"inf", "layers": [[state_dict,...], ...]}. This
script re-parses the program from scratch (it never trusts solve.py)
and checks, purely from the cert's own claimed layers:

  1. layers[0] is exactly the program's real initial state.
  2. no state in any layer satisfies 'bad' under any input combination
     that survives the program's constraints.
  3. every valid transition out of every layer (all of them, for an
     'inf' claim; all but the last, for a finite bound k, since a
     finite claim says nothing about what happens after depth k) lands
     on a state that is itself listed somewhere in the cert.
  4. for a finite bound k, the cert supplies exactly k+1 layers
     (depths 0..k) — a certificate can't claim more than it enumerates.

This is a genuine over-approximate reachable-set / bounded-invariant
check: it does not require every listed state to be truly reachable,
only that the listed set is closed (within its claimed scope), bad-free,
and contains the initial state. A wrong cert can only fail to discharge.
"""
import itertools
import json
import sys

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
            raise OverflowError("input space too large for exhaustive check")
    return [dict(zip(names, vals))
            for vals in itertools.product(*[range(1 << w) for w in widths])]


def state_key(P, vals):
    return tuple(vals[s] for s in P["states"])


def state_from_dict(P, d):
    return {s: d[P["nodes"][s]["name"]] for s in P["states"]}


def verify(P, cert):
    bound = cert["bound"]
    layers_raw = cert["layers"]
    if not isinstance(layers_raw, list) or not layers_raw:
        return False, {}
    try:
        combos = input_combos(P)
    except OverflowError:
        return False, {}
    try:
        layers = [[state_from_dict(P, sd) for sd in layer]
                  for layer in layers_raw]
    except (KeyError, TypeError):
        return False, {}
    if any(not layer for layer in layers):
        return False, {}

    init = initial_state(P)
    if [state_key(P, s) for s in layers[0]] != [state_key(P, init)]:
        return False, {}

    if bound != "inf":
        try:
            bound_i = int(bound)
        except (TypeError, ValueError):
            return False, {}
        if bound_i < 0 or len(layers) != bound_i + 1:
            return False, {}

    visited = set()
    for layer in layers:
        for s in layer:
            visited.add(state_key(P, s))

    checked = 0
    for layer in layers:
        for s in layer:
            for inp in combos:
                b, ok, _ = step(P, s, inp)
                if not ok:
                    continue
                if b:
                    return False, {}
                checked += 1

    last_index = len(layers) - 1
    for i, layer in enumerate(layers):
        if bound != "inf" and i == last_index:
            continue
        for s in layer:
            for inp in combos:
                b, ok, nxt = step(P, s, inp)
                if not ok:
                    continue
                if state_key(P, nxt) not in visited:
                    return False, {}

    return True, {"layers": len(layers), "states_checked": checked,
                  "bound": bound}


def main():
    program_path, cert_path = sys.argv[1], sys.argv[2]
    with open(program_path, encoding="utf-8") as fh:
        P = parse(fh.read())
    with open(cert_path, encoding="utf-8") as fh:
        cert = json.load(fh)
    try:
        ok, obligations = verify(P, cert)
    except Exception:
        ok, obligations = False, {}
    print(json.dumps({"ok": ok, "obligations": obligations}, sort_keys=True))


if __name__ == "__main__":
    main()
