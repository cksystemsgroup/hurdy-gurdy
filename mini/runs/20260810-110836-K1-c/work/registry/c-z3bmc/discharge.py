#!/usr/bin/env python3
"""Independent re-verification of a {"strategy":"unroll","bound":k,
"complete":bool} claim: re-run the symbolic executor fresh at exactly
that bound and check UNSAT of both the violation and (if complete is
claimed) the residual formula, directly on the source program."""
import json
import sys

import czlib
import z3


def main():
    program, cert_path = sys.argv[1], sys.argv[2]
    try:
        with open(cert_path, encoding='utf-8') as fh:
            cert = json.load(fh)
        if cert.get('strategy') != 'unroll':
            raise ValueError('unknown strategy')
        bound = int(cert['bound'])
        complete = bool(cert['complete'])
        if bound < 0:
            raise ValueError('negative bound')
    except Exception:
        print(json.dumps({"ok": False, "obligations": {}}))
        return
    with open(program, encoding='utf-8') as fh:
        src = fh.read()
    try:
        stmts = czlib.parse_program(src)
        _, viol, resid = czlib.run_bounded(stmts, bound)
    except Exception:
        print(json.dumps({"ok": False, "obligations": {}}))
        return
    s = z3.Solver()
    s.add(viol)
    r1 = s.check()
    violated = (r1 == z3.sat)
    residual_ok = True
    if complete:
        s2 = z3.Solver()
        s2.add(resid)
        r2 = s2.check()
        residual_ok = (r2 == z3.unsat)
    ok = (r1 == z3.unsat) and (residual_ok if complete else True)
    obligations = {"bound": bound, "complete": complete,
                   "violated": violated, "residual_ok": residual_ok}
    print(json.dumps({"ok": ok, "obligations": obligations}, sort_keys=True))


if __name__ == '__main__':
    main()
