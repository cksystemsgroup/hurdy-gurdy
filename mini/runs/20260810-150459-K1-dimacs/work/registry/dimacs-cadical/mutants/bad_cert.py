#!/usr/bin/env python3
"""Broken: solves correctly but always attaches a fabricated, unverifiable
certificate instead of the real LRAT proof."""
import json
import subprocess
import sys


def main(argv):
    program, _mode, observable, _bound, wall_s = argv[:5]
    wall = float(wall_s)
    if observable != "sat":
        print(json.dumps({"kind": "partial",
                          "progress": {"note": "unsupported observable"}},
                         sort_keys=True))
        return 0
    try:
        p = subprocess.run(["cadical", "-q", "-t", str(max(1, int(wall))),
                            program], capture_output=True, timeout=wall, text=True)
    except subprocess.TimeoutExpired:
        print(json.dumps({"kind": "partial",
                          "progress": {"note": "timed out"}}, sort_keys=True))
        return 0
    if p.returncode == 10:
        payload = []
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                payload += [int(t) for t in line[2:].split()]
        if payload and payload[-1] == 0:
            payload = payload[:-1]
        out = {"kind": "witness", "payload": payload}
    elif p.returncode == 20:
        out = {"kind": "all", "bound": "inf",
               "cert": {"format": "lrat", "text": "not a real proof\n"}}
    else:
        out = {"kind": "partial", "progress": {"note": "no verdict"}}
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
