#!/usr/bin/env python3
"""lam.py <payload> <program> -> interpreter input.

The solver's witness payload is already shaped like the c language's
input format ({"nondet": [...]}), so this is a passthrough (normalized
through json to keep byte output canonical).
"""
import json
import sys


def main(argv):
    with open(argv[0], encoding="utf-8") as fh:
        payload = json.load(fh)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
