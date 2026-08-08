#!/usr/bin/env python3
"""Bad solver: always claims unsatisfiable, uncertified. Must fail on
the sat-labeled corpus items."""
import json


def main():
    print(json.dumps({"kind": "all", "bound": "inf", "cert": None}))


if __name__ == "__main__":
    main()
