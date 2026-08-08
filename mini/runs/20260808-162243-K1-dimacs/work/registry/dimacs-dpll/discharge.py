#!/usr/bin/env python3
"""Universal certification for dimacs-dpll: the certificate is a RUP
refutation, checked by this entry's own from-scratch checker (no
cadical, no cake_lpr, no drat-trim anywhere in this path).
<program> <cert> -> {"ok": bool, "obligations": {...}}."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dpll_core  # noqa: E402


def fail():
    print(json.dumps({"ok": False, "obligations": {}}))


def main():
    program, cert_path = sys.argv[1], sys.argv[2]
    try:
        with open(cert_path, encoding="utf-8") as fh:
            cert = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return fail()
    if not isinstance(cert, dict) or cert.get("format") != "rup":
        return fail()
    proof = cert.get("clauses")
    if not isinstance(proof, list) or not all(isinstance(c, list) for c in proof):
        return fail()

    try:
        nvars, nclauses, clauses = dpll_core.parse_cnf(program)
    except (OSError, ValueError):
        return fail()

    ok, msg = dpll_core.verify(clauses, proof)
    if not ok:
        return fail()
    print(json.dumps({"ok": True,
                      "obligations": {"checked_by": "dimacs-dpll-scratch/rup",
                                       "proof_len": len(proof)}}))


if __name__ == "__main__":
    main()
