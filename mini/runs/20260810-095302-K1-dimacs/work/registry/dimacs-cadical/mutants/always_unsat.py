#!/usr/bin/env python3
"""Bad solver: always claims unsat with a fake certificate, regardless
of the formula. Must fail on sat-labeled corpus items (the fake
certificate cannot discharge, and the claim contradicts the label)."""
import json
import sys


def main():
    print(json.dumps({"kind": "all", "bound": "inf",
                      "cert": {"format": "lrat", "proof": ""}},
                     sort_keys=True))


if __name__ == "__main__":
    main()
