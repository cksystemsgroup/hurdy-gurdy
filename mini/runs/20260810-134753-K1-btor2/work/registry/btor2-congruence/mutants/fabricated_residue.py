#!/usr/bin/env python3
"""Mutant: never runs any SMT query — always claims the same fixed
(modulus=2, residue=1) congruence certificate, regardless of the
program. Wrong on every corpus item whose true initial residue is 0."""
import json


def main():
    print(json.dumps({"kind": "all", "bound": "inf",
                      "cert": {"modulus": 2, "residue": 1}}))


if __name__ == "__main__":
    main()
