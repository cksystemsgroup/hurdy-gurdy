#!/usr/bin/env python3
"""Independent re-derivation: rebuilds the canonical PHP(pigeons,
holes) clause set from the certificate's own numbers and checks it
against the program's actual clauses from scratch. It does not trust
solve.py's detection -- it repeats the counting argument itself.

<program> <cert> -> {"ok": bool, "obligations": {...}}.
"""
import json
import sys

from php_struct import parse_cnf, canonical_php


def fail():
    print(json.dumps({"ok": False, "obligations": {}}))


def main():
    program, cert_path = sys.argv[1], sys.argv[2]
    try:
        with open(cert_path, encoding="utf-8") as fh:
            cert = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return fail()
    if not isinstance(cert, dict) or cert.get("format") != "php-struct":
        return fail()
    pigeons, holes = cert.get("pigeons"), cert.get("holes")
    if not isinstance(pigeons, int) or not isinstance(holes, int):
        return fail()
    if pigeons <= holes or holes < 1:
        return fail()
    nvars, nclauses, clauses = parse_cnf(program)
    if nvars != pigeons * holes:
        return fail()
    if sorted(canonical_php(pigeons, holes)) != sorted(clauses):
        return fail()
    print(json.dumps({"ok": True,
                      "obligations": {"checked_by": "php-struct-recount",
                                       "pigeons": pigeons, "holes": holes}}))


if __name__ == "__main__":
    main()
