#!/usr/bin/env python3
"""Broken: claims every formula/assignment pair is satisfiable."""
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
    program, _ = argv[0], argv[1]
    print(json.dumps({"sat": True, "depth": n_vars_of(program)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
