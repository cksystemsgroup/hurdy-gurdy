#!/usr/bin/env python3
"""Bad solver: always claims unsatisfiable with a bogus empty-clause
proof, regardless of the formula. Must fail on sat-labeled corpus
items (contradicts label=true) and, where it doesn't, its fabricated
one-line proof still won't be RUP against a formula that actually
needs case-splitting."""
import json


def main():
    print(json.dumps({"kind": "all", "bound": "inf",
                      "cert": {"format": "rup", "clauses": [[]]}}))


if __name__ == "__main__":
    main()
