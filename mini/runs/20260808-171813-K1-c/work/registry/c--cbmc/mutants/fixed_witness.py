#!/usr/bin/env python3
"""Mutant: always claims the same fixed witness regardless of the
program. Wrong (and unreplayable) on at least one corpus item, so the
kernel's own replay check must catch it."""
import json
import sys


def main(argv):
    print(json.dumps({"kind": "witness", "payload": {"nondet": [999999]}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
