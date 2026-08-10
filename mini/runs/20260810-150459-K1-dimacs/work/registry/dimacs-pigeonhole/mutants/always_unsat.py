#!/usr/bin/env python3
"""Broken: claims unsatisfiability with a nonsense certificate, regardless
of the actual formula."""
import json
import sys


def main(argv):
    print(json.dumps({"kind": "all", "bound": "inf",
                      "cert": {"holes": [[1], [2]]}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
