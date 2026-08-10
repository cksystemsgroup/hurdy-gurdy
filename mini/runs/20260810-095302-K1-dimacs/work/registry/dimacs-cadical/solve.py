#!/usr/bin/env python3
"""dimacs solver backed by cadical, a general CDCL search -- unlike
dimacs-php-struct it works on any CNF, not just recognized shapes.
SAT -> witness(assignment). UNSAT -> all(bound="inf") carrying an
LRAT refutation, discharged by cake_lpr (a HOL4-verified checker, a
different codebase from the solver that produced the proof).

<program> <mode> <observable> <bound> <wall_s> -> result JSON on stdout.
"""
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
            if not os.path.exists(proof_path):
                return partial("cadical claimed unsat but wrote no proof")
            with open(proof_path, encoding="utf-8") as fh:
                proof_text = fh.read()
            print(json.dumps({"kind": "all", "bound": "inf",
                              "cert": {"format": "lrat",
                                       "proof": proof_text}},
                             sort_keys=True))
        else:
            return partial("cadical returned neither sat nor unsat "
                           "within the wall", returncode=p.returncode)


if __name__ == "__main__":
    main()
