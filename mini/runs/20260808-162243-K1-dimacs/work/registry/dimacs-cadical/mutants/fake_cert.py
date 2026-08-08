#!/usr/bin/env python3
"""Bad solver: decides correctly via cadical, but on unsat fabricates
a certificate instead of shipping the real proof. Must fail because
the fake certificate cannot discharge through cake_lpr."""
import json
import subprocess
import sys


def main():
    program = sys.argv[1]
    p = subprocess.run(["cadical", "-q", program],
                       capture_output=True, timeout=30, text=True)
    if "s SATISFIABLE" in p.stdout:
        assignment = []
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                assignment += [int(x) for x in line[2:].split()]
        assignment = [x for x in assignment if x != 0]
        print(json.dumps({"kind": "witness",
                          "payload": {"assignment": assignment}}))
    else:
        print(json.dumps({"kind": "all", "bound": "inf",
                          "cert": {"format": "lrat", "proof": "0\n"}}))


if __name__ == "__main__":
    main()
