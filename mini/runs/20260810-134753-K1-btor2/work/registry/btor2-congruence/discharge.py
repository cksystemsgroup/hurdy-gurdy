#!/usr/bin/env python3
"""Discharge: independently verify a congruence-invariant certificate.

<program> <cert> -> {"ok": bool, "obligations": {...}}

A cert is {"modulus": g, "residue": r} (g a power of two). This script
re-parses the program from scratch (it never trusts solve.py) and
re-derives the same three SMT obligations solve.py's search used to
find the pair, checking them independently:

  1. base: the program's real initial value satisfies state mod g == r.
  2. inductive: no legal step (satisfying every 'constraint') out of an
     invariant-satisfying state can leave the invariant — checked as
     the unsat of an existential SMT query, sound for the full (up to
     2^W-sized) state space regardless of g.
  3. safe: no invariant-satisfying, constraint-legal state satisfies
     any 'bad' node — same style of query.

Together, 1+2 make "state mod g == r" a true closed superset of the
reachable set (by induction from the initial state); 3 makes it
bad-free. A wrong (g, r) can only fail one of these and never
discharge.
"""
import json
import sys

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


def verify(P, cert):
    if len(P["states"]) != 1:
        return False, {}
    sid = P["states"][0]
    W = width_of(P, sid)

    try:
        g = int(cert["modulus"])
        r = int(cert["residue"])
    except (KeyError, TypeError, ValueError):
        return False, {}
    if g < 2 or (g & (g - 1)) != 0 or g > (1 << W):
        return False, {}
    r &= mask(W)

    init_val = (eval_concrete(P, P["inits"][sid], {})
                if sid in P["inits"] else 0)
    if (init_val & (g - 1)) != (r & (g - 1)):
        return False, {}

    state_var = z3.BitVec("state", W)
    input_vars = {i: z3.BitVec(P["nodes"][i]["name"], width_of(P, i))
                  for i in P["inputs"]}
    memo = {}
    try:
        next_expr = (sym_eval(P, P["nexts"][sid], state_var, input_vars, memo)
                    if sid in P["nexts"] else state_var)
        bad_exprs = [sym_eval(P, b, state_var, input_vars, memo)
                    for b in P["bads"]]
        con_exprs = [sym_eval(P, c, state_var, input_vars, memo)
                    for c in P["constraints"]]
    except Exception:
        return False, {}
    bad_bool = (z3.Or([e == z3.BitVecVal(1, 1) for e in bad_exprs])
               if bad_exprs else z3.BoolVal(False))
    ok_bool = (z3.And([e == z3.BitVecVal(1, 1) for e in con_exprs])
              if con_exprs else z3.BoolVal(True))
    mask_bv = z3.BitVecVal(g - 1, W)
    r_bv = z3.BitVecVal(r, W)
    inv = (state_var & mask_bv) == r_bv

    ind = z3.Solver()
    ind.add(ok_bool, inv, z3.Not((next_expr & mask_bv) == r_bv))
    if ind.check() != z3.unsat:
        return False, {}

    safe = z3.Solver()
    safe.add(inv, ok_bool, bad_bool)
    if safe.check() != z3.unsat:
        return False, {}

    return True, {"modulus": g, "residue": r, "width": W}


def main():
    program_path, cert_path = sys.argv[1], sys.argv[2]
    with open(program_path, encoding="utf-8") as fh:
        P = parse(fh.read())
    with open(cert_path, encoding="utf-8") as fh:
        cert = json.load(fh)
    try:
        ok, obligations = (False, {}) if z3 is None else verify(P, cert)
    except Exception:
        ok, obligations = False, {}
    print(json.dumps({"ok": ok, "obligations": obligations}, sort_keys=True))


if __name__ == "__main__":
    main()
