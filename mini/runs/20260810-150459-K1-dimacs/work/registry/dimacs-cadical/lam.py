#!/usr/bin/env python3
"""payload IS already a dimacs-language input (a signed-literal assignment)."""
import json
import sys


def main(argv):
    payload_path = argv[0]
    with open(payload_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
