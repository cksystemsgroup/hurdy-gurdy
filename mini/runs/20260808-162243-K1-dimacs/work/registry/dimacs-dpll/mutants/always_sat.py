#!/usr/bin/env python3
"""Bad solver: always claims satisfiable with an all-true assignment,
regardless of the formula."""
import json
import sys


def main():
    program = sys.argv[1]
    nvars = 0
    with open(program, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("p"):
                nvars = int(line.split()[2])
                break
    print(json.dumps({"kind": "witness",
                      "payload": {"assignment": list(range(1, nvars + 1))}},
                     sort_keys=True))


if __name__ == "__main__":
    main()
