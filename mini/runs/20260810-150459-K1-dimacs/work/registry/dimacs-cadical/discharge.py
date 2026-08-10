#!/usr/bin/env python3
"""Independently verify an LRAT unsatisfiability certificate with cake_lpr,
a formally-verified (CakeML) checker — a different codebase than the
cadical/drat-trim pair that produced the certificate.

discharge.py <program> <cert> -> {"ok": bool, "obligations": {...}}
"""
import json
import subprocess
import sys


def main(argv):
    program, cert_path = argv[0], argv[1]
    try:
        with open(cert_path, encoding="utf-8") as fh:
            cert = json.load(fh)
        if cert.get("format") != "lrat":
            print(json.dumps({"ok": False, "obligations": {}}, sort_keys=True))
            return 0
        with open("proof.lrat", "w", encoding="utf-8") as fh:
            fh.write(cert["text"])
        p = subprocess.run(["cake_lpr", program, "proof.lrat"],
                           capture_output=True, timeout=120, text=True)
        ok = "VERIFIED UNSAT" in p.stdout
        print(json.dumps({"ok": ok,
                          "obligations": {"checker": "cake_lpr"} if ok else {}},
                         sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"ok": False, "obligations": {}}, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
