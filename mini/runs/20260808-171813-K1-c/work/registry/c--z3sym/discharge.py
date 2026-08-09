#!/usr/bin/env python3
"""discharge.py <program> <cert> -> {"ok": bool, "obligations": {...}}

Independently re-derives the formula at the certified unroll bound and
re-checks both obligations from scratch: the violation formula is
UNSAT (no input violates the assertion within the bound) and the
unwinding-deficit formula is UNSAT (the bound was enough -- no state
after k iterations still wants another one). Fail-safe: any malformed
cert or unmet obligation is ok=False, never ok=True.
"""
import json
import sys

import z3

from csubset import build


def main(argv):
    program_path, cert_path = argv[0], argv[1]
    with open(program_path, encoding="utf-8") as fh:
        src = fh.read()
    with open(cert_path, encoding="utf-8") as fh:
        cert = json.load(fh)
    k = cert.get("unroll_k") if isinstance(cert, dict) else None
    if not isinstance(k, int) or isinstance(k, bool) or k < 0:
        print(json.dumps({"ok": False, "obligations": {}}))
        return 0
    violation, deficit, _ = build(src, k)
    s = z3.Solver()
    s.add(violation)
    if s.check() != z3.unsat:
        print(json.dumps({"ok": False, "obligations": {}}))
        return 0
    s2 = z3.Solver()
    s2.add(deficit)
    if s2.check() != z3.unsat:
        print(json.dumps({"ok": False, "obligations": {}}))
        return 0
    print(json.dumps({"ok": True, "obligations": {"unroll_k": k,
                                                   "violation_unsat": True,
                                                   "unwinding_sufficient": True}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
