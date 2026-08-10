#!/usr/bin/env python3
"""Bad solver: runs cadical for the real sat/unsat verdict (so it
passes the label checks), but on unsat replaces the real LRAT proof
with garbage bytes. Must be caught by discharge failing to verify."""
import json
import os
import subprocess
import sys
import tempfile


def partial(note, **kw):
    print(json.dumps({"kind": "partial",
                      "progress": {"note": note, **kw}}, sort_keys=True))


def main():
    program, mode, observable, bound, wall_s = sys.argv[1:6]
    if observable != "sat":
        return partial(f"observable {observable!r} not decided")
    limit = max(1, int(float(wall_s)))
    with tempfile.TemporaryDirectory() as scratch:
        proof_path = os.path.join(scratch, "proof.lrat")
        try:
            p = subprocess.run(
                ["cadical", "--no-binary", "--lrat=true", "-q",
                 "-t", str(limit), program, proof_path],
                capture_output=True, timeout=limit + 10, text=True)
        except subprocess.TimeoutExpired:
            return partial("cadical timed out", wall_s=wall_s)
        out = p.stdout
        if "s SATISFIABLE" in out:
            assignment = []
            for line in out.splitlines():
                if line.startswith("v "):
                    assignment += [int(x) for x in line[2:].split()]
            assignment = [x for x in assignment if x != 0]
            print(json.dumps({"kind": "witness",
                              "payload": {"assignment": assignment}},
                             sort_keys=True))
        elif "s UNSATISFIABLE" in out:
            print(json.dumps({"kind": "all", "bound": "inf",
                              "cert": {"format": "lrat",
                                       "proof": "not a real lrat proof\n"}},
                             sort_keys=True))
        else:
            return partial("neither sat nor unsat")


if __name__ == "__main__":
    main()
