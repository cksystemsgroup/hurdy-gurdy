#!/usr/bin/env python3
"""Independent re-verification of a loop-summarization certificate: re-parse
the source, re-run the SAME structural pattern match (not trusting the
cert's own numbers), require every field to match what's actually in the
program, then independently rebuild the closed form and re-check UNSAT of
the violation formula."""
import json
import sys

import czlib
import pattern


def main():
    program, cert_path = sys.argv[1], sys.argv[2]
    try:
        with open(cert_path, encoding='utf-8') as fh:
            cert = json.load(fh)
        if cert.get('strategy') != 'loop-summarization':
            raise ValueError('unknown strategy')
    except Exception:
        print(json.dumps({"ok": False, "obligations": {}}))
        return
    with open(program, encoding='utf-8') as fh:
        src = fh.read()
    try:
        stmts = czlib.parse_program(src)
        pat, reason = pattern.analyze(stmts)
    except Exception:
        pat, reason = None, "parse/analyze error"
    if pat is None:
        print(json.dumps({"ok": False, "obligations": {"reason": reason}}))
        return
    fields = ("ivar", "ival", "bound_var", "bound_lit", "deltas", "inits")
    mismatches = [f for f in fields if cert.get(f) != pat[f]]
    if mismatches:
        print(json.dumps({"ok": False,
                          "obligations": {"mismatched": mismatches}}))
        return
    ex = czlib.Executor()
    top = pattern._flatten(stmts)
    before = []
    for s in top:
        if s[0] == 'if' and s[1] is pat["guard"]:
            break
        before.append(s)
    env, pc = ex.exec_stmts(before, {}, czlib.z3.BoolVal(True), 0)
    cond = czlib.truthy(ex.eval_expr(pat["guard"], dict(env), pc))
    pc_in = czlib.z3.And(pc, cond)
    env, pc_in = ex.exec_stmts(pat["prefix"], env, pc_in, 0)
    env = pattern.build_closed_form(pat, env)
    ex.exec_stmts(pat["suffix"], env, pc_in, 0)
    viol = czlib.z3.Or(*ex.violations) if ex.violations else czlib.z3.BoolVal(False)
    s = czlib.z3.Solver()
    s.add(viol)
    res = s.check()
    ok = (res == czlib.z3.unsat)
    print(json.dumps({"ok": ok, "obligations": {"violated": res == czlib.z3.sat}},
                     sort_keys=True))


if __name__ == '__main__':
    main()
