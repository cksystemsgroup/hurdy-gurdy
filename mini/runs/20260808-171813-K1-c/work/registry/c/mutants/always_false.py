#!/usr/bin/env python3
"""Mutant: never detects a violation. Vectors 001/003 must catch this."""
import json
import sys


def main(argv):
    print(json.dumps({"violation": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
