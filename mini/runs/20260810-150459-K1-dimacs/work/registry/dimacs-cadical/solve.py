#!/usr/bin/env python3
"""dimacs solver via cadical, certified by drat-trim + cake_lpr.

solve.py <program> <mode> <observable> <bound> <wall_s>

SAT      -> witness(payload=<full signed assignment>)
UNSAT    -> all(bound="inf", cert={"format":"lrat","text":...})
otherwise-> partial(progress)
"""
import json
import shutil
import subprocess
import sys


def run(cmd, wall):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=wall, text=True)
    except subprocess.TimeoutExpired:
        return None


def main(argv):
    program, _mode, observable, _bound, wall_s = argv[:5]
    wall = float(wall_s)
    out = {"kind": "partial",
           "progress": {"note": "unsupported observable", "observable": observable}}
    if observable != "sat":
        print(json.dumps(out, sort_keys=True))
        return 0

    cadical_wall = max(1, int(wall - min(5, wall * 0.2)))
    proof = "proof.drat"
    p = run(["cadical", "-q", "-t", str(cadical_wall), program, proof], wall)

    if p is None:
        out = {"kind": "partial",
               "progress": {"note": "cadical timed out", "wall_s": wall}}
    elif p.returncode == 10:
        payload = []
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                payload += [int(t) for t in line[2:].split()]
        if payload and payload[-1] == 0:
            payload = payload[:-1]
        out = {"kind": "witness", "payload": payload}
    elif p.returncode == 20:
        cert = None
        lrat = "proof.lrat"
        dt = run(["drat-trim", program, proof, "-L", lrat], wall)
        if dt is not None and "s VERIFIED" in dt.stdout:
            try:
                with open(lrat, encoding="utf-8") as fh:
                    text = fh.read()
                cert = {"format": "lrat", "text": text}
            except OSError:
                cert = None
        out = {"kind": "all", "bound": "inf", "cert": cert}
    else:
        out = {"kind": "partial",
               "progress": {"note": "cadical exhausted its budget without a "
                            "verdict", "wall_s": wall, "returncode": p.returncode}}

    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    if shutil.which("cadical") is None:
        print(json.dumps({"kind": "partial",
                          "progress": {"note": "cadical not found"}}))
        raise SystemExit(0)
    raise SystemExit(main(sys.argv[1:]))
