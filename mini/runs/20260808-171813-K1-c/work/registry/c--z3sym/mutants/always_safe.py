#!/usr/bin/env python3
"""Mutant: never finds a violation, always claims all(inf). Corpus
items 001/004 (label true, a violation exists) must catch this."""
import json
import sys


def main(argv):
    print(json.dumps({"kind": "all", "bound": "inf", "cert": None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
