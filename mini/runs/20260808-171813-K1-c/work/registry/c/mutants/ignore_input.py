#!/usr/bin/env python3
"""Mutant: compiles and runs the program for real, but nondet_int()
always returns 0 regardless of the supplied input. Vector 001 (expects
a violation at nondet=7) must catch this."""
import json
import os
import subprocess
import sys
import tempfile

STUB = """
int nondet_int(void) { return 0; }
"""


def main(argv):
    program = argv[0]
    with tempfile.TemporaryDirectory() as d:
        stub_path = os.path.join(d, "hg_stub.c")
        bin_path = os.path.join(d, "hg_bin")
        with open(stub_path, "w", encoding="utf-8") as fh:
            fh.write(STUB)
        cc = subprocess.run(["cc", "-x", "c", "-O0", "-w", "-o", bin_path,
                             program, stub_path], capture_output=True,
                            timeout=20)
        if cc.returncode != 0:
            print(json.dumps({"violation": None, "error": "compile"}))
            return 0
        run = subprocess.run([bin_path], capture_output=True, timeout=10)
        violation = run.returncode != 0
    print(json.dumps({"violation": violation}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
