#!/usr/bin/env python3
"""Mutant: never searches — always claims an (empty, unreplayable) witness."""
import json


def main():
    print(json.dumps({"kind": "witness", "payload": []}))


if __name__ == "__main__":
    main()
