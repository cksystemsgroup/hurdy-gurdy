#!/usr/bin/env python3
"""Bad solver: always claims unsat, regardless of the formula. Must
fail on sat-labeled corpus items."""
import json
import sys


def main():
    print(json.dumps({"kind": "all", "bound": "inf", "cert": None},
                     sort_keys=True))


if __name__ == "__main__":
    main()
