#!/usr/bin/env python3
"""Universal certification for dimacs-cadical: the certificate is an
LRAT unsatisfiability proof, checked by cake_lpr — a checker built
from a different codebase than the cadical solver that produced the
proof. <program> <cert> -> {"ok": bool, "obligations": {...}}."""
import json
import os
import subprocess
import sys
import tempfile


def fail():
    print(json.dumps({"ok": False, "obligations": {}}))


def main():
    program, cert_path = sys.argv[1], sys.argv[2]
    try:
        with open(cert_path, encoding="utf-8") as fh:
            cert = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return fail()
    if not isinstance(cert, dict) or cert.get("format") != "lrat":
        return fail()
    proof_text = cert.get("proof")
    if not isinstance(proof_text, str):
        return fail()

    with tempfile.TemporaryDirectory() as scratch:
        proof_path = os.path.join(scratch, "proof.lrat")
        with open(proof_path, "w", encoding="utf-8") as fh:
            fh.write(proof_text)
        try:
            p = subprocess.run(["cake_lpr", program, proof_path],
                               capture_output=True, timeout=60, text=True)
        except subprocess.TimeoutExpired:
            return fail()
        if "s VERIFIED UNSAT" not in p.stdout:
            return fail()
    print(json.dumps({"ok": True,
                      "obligations": {"checked_by": "cake_lpr",
                                       "format": "lrat"}}))


if __name__ == "__main__":
    main()
