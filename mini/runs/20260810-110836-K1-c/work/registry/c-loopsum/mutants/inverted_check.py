#!/usr/bin/env python3
"""Solver pair c -> result via loop summarization (pattern.py): closes a
single affine-accumulator loop in O(1) instead of unrolling it, so a loop
whose *trip count* is large (bigloop.c: up to 60000) is exactly as cheap
to prove as one whose *body* is large. Declines (partial) whenever the
program doesn't match the supported shape, or the closed form isn't
provably overflow-free — the fallback is whatever unrolling solver is
also registered for the language."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import czlib
import pattern


def run_pattern(stmts, pat):
    ex = czlib.Executor()
    env, pc = ex.exec_stmts(stmts_before_if(stmts, pat), {}, czlib.z3.BoolVal(True), 0)
    cond = czlib.truthy(ex.eval_expr(pat["guard"], dict(env), pc))
    pc_in = czlib.z3.And(pc, cond)
    env, pc_in = ex.exec_stmts(pat["prefix"], env, pc_in, 0)
    env = pattern.build_closed_form(pat, env)
    ex.exec_stmts(pat["suffix"], env, pc_in, 0)
    viol = czlib.z3.Or(*ex.violations) if ex.violations else czlib.z3.BoolVal(False)
    return ex.nondet_calls, viol


def stmts_before_if(stmts, pat):
    flat = pattern._flatten(stmts)
    out = []
    for s in flat:
        if s[0] == 'if' and s[1] is pat["guard"]:
            break
        out.append(s)
    return out


def main():
    program = sys.argv[1]
    wall_s = float(sys.argv[5])
    with open(program, encoding='utf-8') as fh:
        src = fh.read()
    stmts = czlib.parse_program(src)
    pat, reason = pattern.analyze(stmts)
    if pat is None:
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"loop-summarization does not apply: {reason}"}},
            sort_keys=True))
        return
    nondet_calls, viol = run_pattern(stmts, pat)
    s = czlib.z3.Solver()
    s.set('timeout', int(min(wall_s, 10.0) * 1000))
    s.add(viol)
    res = s.check()
    if res == czlib.z3.unsat:
        payload = czlib.extract_witness(nondet_calls, s.model())
        print(json.dumps({"kind": "witness",
                          "payload": {"nondet": payload}}, sort_keys=True))
        return
    if res != czlib.z3.unsat:
        print(json.dumps({"kind": "partial", "progress": {
            "note": "closed form built but z3 could not settle it"}},
            sort_keys=True))
        return
    cert = {"strategy": "loop-summarization", "ivar": pat["ivar"],
            "ival": pat["ival"], "bound_var": pat["bound_var"],
            "bound_lit": pat["bound_lit"], "deltas": pat["deltas"],
            "inits": pat["inits"]}
    print(json.dumps({"kind": "all", "bound": "inf", "cert": cert},
                     sort_keys=True))


if __name__ == '__main__':
    main()
