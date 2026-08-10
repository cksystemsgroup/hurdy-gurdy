#!/usr/bin/env python3
"""Lambda: solver payload -> interpreter input (identity; see
registry/btor2-explicit/lam.py for why)."""
import json
import sys


def main():
    with open(sys.argv[1], encoding="utf-8") as fh:
        payload = json.load(fh)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
