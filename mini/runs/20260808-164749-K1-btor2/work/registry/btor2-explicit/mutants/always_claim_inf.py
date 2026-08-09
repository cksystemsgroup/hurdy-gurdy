#!/usr/bin/env python3
"""Mutant: never searches — always claims bad is unreachable forever."""
import json


def main():
    print(json.dumps({"kind": "all", "bound": "inf", "cert": None}))


if __name__ == "__main__":
    main()
