#!/usr/bin/env python3
"""Mutant: always claims a violation. Vectors 002/004 must catch this."""
import json
import sys


def main(argv):
    print(json.dumps({"violation": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
