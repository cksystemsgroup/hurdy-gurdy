#!/usr/bin/env python3
"""Lambda: solver payload -> interpreter input.

A witness payload from solve.py is already a list of per-step input
dicts — exactly the format registry/btor2/interp.py expects — so this
is the identity transform.
"""
import json
import sys


def main():
    with open(sys.argv[1], encoding="utf-8") as fh:
        payload = json.load(fh)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
