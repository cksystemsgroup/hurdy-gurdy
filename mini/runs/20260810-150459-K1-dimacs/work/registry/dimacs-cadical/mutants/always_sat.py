#!/usr/bin/env python3
"""Broken: always claims a (bogus, all-true) satisfying witness."""
import json
import sys


def n_vars_of(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("p"):
                return int(line.split()[2])
    return 0


def main(argv):
    program = argv[0]
    n = n_vars_of(program)
    print(json.dumps({"kind": "witness",
                      "payload": list(range(1, n + 1))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
