#!/usr/bin/env python3
"""discharge.py <program> <cert> -> {"ok": bool, "obligations": {...}}

Independently re-runs cbmc at the certified unwind bound and confirms,
fresh, that the user assertion holds and the unwinding was sufficient
(no `main.unwind.*` FAILUREs). Fail-safe: a malformed cert or an
unwind bound that turns out to be insufficient is ok=False.
"""
import json
import sys
import tempfile

from cbmc_run import classify, run_cbmc, with_c_extension


def main(argv):
    program_path, cert_path = argv[0], argv[1]
    with open(cert_path, encoding="utf-8") as fh:
        cert = json.load(fh)
    k = cert.get("unwind") if isinstance(cert, dict) else None
    if not isinstance(k, int) or isinstance(k, bool) or k < 0:
        print(json.dumps({"ok": False, "obligations": {}}))
        return 0
    with tempfile.TemporaryDirectory() as d:
        c_path = with_c_extension(program_path, d)
        data = run_cbmc(c_path, k, 60.0)
    if data is None:
        print(json.dumps({"ok": False, "obligations": {}}))
        return 0
    witness_vals, unwind_insufficient, error = classify(data)
    if error is not None or witness_vals is not None or unwind_insufficient:
        print(json.dumps({"ok": False, "obligations": {}}))
        return 0
    print(json.dumps({"ok": True, "obligations": {"unwind": k,
                                                   "assertion_holds": True,
                                                   "unwinding_sufficient": True}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
