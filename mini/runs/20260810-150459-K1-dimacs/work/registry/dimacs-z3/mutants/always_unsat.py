#!/usr/bin/env python3
"""Broken: always claims unsatisfiability, no certificate."""
import json
import sys


def main(argv):
    print(json.dumps({"kind": "all", "bound": "inf", "cert": None},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
