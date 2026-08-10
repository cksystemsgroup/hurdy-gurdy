#!/usr/bin/env python3
"""Mutant: never runs the search — always abstains. A solver that
decides nothing on the whole corpus is refused."""
import json


def main():
    print(json.dumps({"kind": "partial", "progress": {
        "note": "search disabled", "bound_reached": -1}}))


if __name__ == "__main__":
    main()
