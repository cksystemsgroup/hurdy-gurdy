#!/usr/bin/env python3
"""Mutant: skips the 'no invariant-state satisfies bad' obligation —
accepts the first inductive congruence class even if it doesn't exclude
bad. On corpus item 002 (mod-4 needed, mod-2 insufficient) this claims
safety via the merely-inductive-but-unsafe g=2, which the real
discharge.py must reject."""
import json
import sys
import time

try:
    import z3
except ImportError:
    z3 = None


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
    return {"nodes": nodes, "sorts": sorts, "inits": inits, "nexts": nexts,
            "bads": bads, "constraints": constraints, "states": states,
            "inputs": inputs}


def width_of(P, nid):
    return P["sorts"][P["nodes"][nid]["sid"]]


def eval_concrete(P, nid, memo):
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
    elif op == "not":
        v = ~eval_concrete(P, n["a"], memo)
    elif op in ("add", "sub", "mul", "and", "eq", "ult"):
        a = eval_concrete(P, n["a"], memo)
        b = eval_concrete(P, n["b"], memo)
        v = {"add": a + b, "sub": a - b, "mul": a * b, "and": a & b,
             "eq": int(a == b), "ult": int(a < b)}[op]
    elif op == "ite":
        c = eval_concrete(P, n["cond"], memo)
        v = (eval_concrete(P, n["a"], memo) if c else
             eval_concrete(P, n["b"], memo))
    else:
        raise ValueError(f"init expression is not constant (hits {op!r})")
    v &= mask(width_of(P, nid))
    memo[nid] = v
    return v


def sym_eval(P, nid, state_var, input_vars, memo):
    if nid in memo:
        return memo[nid]
    n = P["nodes"][nid]
    op = n["op"]
    w = width_of(P, nid)
    if op == "zero":
        v = z3.BitVecVal(0, w)
    elif op == "one":
        v = z3.BitVecVal(1, w)
    elif op == "constd":
        v = z3.BitVecVal(n["value"], w)
    elif op == "input":
        v = input_vars[nid]
    elif op == "state":
        v = state_var
    elif op == "not":
        v = ~sym_eval(P, n["a"], state_var, input_vars, memo)
    elif op in ("add", "sub", "mul", "and", "eq", "ult"):
        a = sym_eval(P, n["a"], state_var, input_vars, memo)
        b = sym_eval(P, n["b"], state_var, input_vars, memo)
        if op == "add":
            v = a + b
        elif op == "sub":
            v = a - b
        elif op == "mul":
            v = a * b
        elif op == "and":
            v = a & b
        elif op == "eq":
            v = z3.If(a == b, z3.BitVecVal(1, 1), z3.BitVecVal(0, 1))
        else:
            v = z3.If(z3.ULT(a, b), z3.BitVecVal(1, 1), z3.BitVecVal(0, 1))
    elif op == "ite":
        c = sym_eval(P, n["cond"], state_var, input_vars, memo)
        a = sym_eval(P, n["a"], state_var, input_vars, memo)
        b = sym_eval(P, n["b"], state_var, input_vars, memo)
        v = z3.If(c == z3.BitVecVal(1, 1), a, b)
    else:
        raise ValueError(f"cannot symbolically evaluate op {op!r}")
    memo[nid] = v
    return v


def search(P, wall):
    if len(P["states"]) != 1:
        raise ValueError("congruence procedure handles exactly one state")
    sid = P["states"][0]
    W = width_of(P, sid)
    init_val = (eval_concrete(P, P["inits"][sid], {})
               if sid in P["inits"] else 0)
    state_var = z3.BitVec("state", W)
    input_vars = {i: z3.BitVec(P["nodes"][i]["name"], width_of(P, i))
                  for i in P["inputs"]}
    memo = {}
    next_expr = (sym_eval(P, P["nexts"][sid], state_var, input_vars, memo)
                if sid in P["nexts"] else state_var)
    con_exprs = [sym_eval(P, c, state_var, input_vars, memo)
                for c in P["constraints"]]
    ok_bool = (z3.And([e == z3.BitVecVal(1, 1) for e in con_exprs])
              if con_exprs else z3.BoolVal(True))

    t0 = time.monotonic()
    for k in range(1, W + 1):
        if time.monotonic() - t0 > wall * 0.8:
            break
        g = 1 << k
        r = init_val & (g - 1)
        mask_bv = z3.BitVecVal(g - 1, W)
        r_bv = z3.BitVecVal(r, W)
        inv = (state_var & mask_bv) == r_bv

        ind = z3.Solver()
        ind.add(ok_bool, inv, z3.Not((next_expr & mask_bv) == r_bv))
        if ind.check() != z3.unsat:
            continue
        # MUTATION: no safety check at all — accept the first inductive g.
        return g, r
    return None


def main():
    program_path, mode, observable, bound_s, wall_s = sys.argv[1:6]
    wall = float(wall_s)
    if z3 is None:
        print(json.dumps({"kind": "partial", "progress": {"note": "no z3"}}))
        return
    z3.set_param("sat.random_seed", 0)
    z3.set_param("smt.random_seed", 0)
    try:
        with open(program_path, encoding="utf-8") as fh:
            P = parse(fh.read())
        if observable != "bad":
            print(json.dumps({"kind": "partial", "progress": {
                "note": f"cannot decide {observable!r}"}}))
            return
        found = search(P, wall)
    except Exception as exc:
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"inapplicable: {exc}", "bound_reached": -1}}))
        return
    if found is None:
        print(json.dumps({"kind": "partial", "progress": {
            "note": "no inductive congruence class found",
            "bound_reached": -1}}))
        return
    g, r = found
    print(json.dumps({"kind": "all", "bound": "inf",
                      "cert": {"modulus": g, "residue": r}}))


if __name__ == "__main__":
    main()
