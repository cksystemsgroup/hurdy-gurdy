#!/usr/bin/env python3
"""c language interpreter: compile-head over cc.

<program> is a C source file using `int nondet_int(void);` (declared,
never defined in the program) as its only source of input. <input> is
a JSON object {"nondet": [ints, ...]} consumed by nondet_int() in call
order; a call beyond the supplied values reads a deterministic 0.

Observable: {"violation": bool} -- true iff an assert() in the program
aborts the process for this concrete input.
"""
import json
import os
import subprocess
import sys
import tempfile

STUB = """
#include <stddef.h>
static const long __hg_vals[] = { %(vals)s };
static const size_t __hg_n = %(n)d;
static size_t __hg_i = 0;
int nondet_int(void) {
    if (__hg_i < __hg_n) return (int)__hg_vals[__hg_i++];
    __hg_i++;
    return 0;
}
"""


def main(argv):
    program, input_path = argv[0], argv[1]
    with open(input_path, encoding="utf-8") as fh:
        data = json.load(fh)
    vals = [int(v) for v in data.get("nondet", [])]
    stub_src = STUB % {"vals": ", ".join(str(v) for v in vals) or "0",
                        "n": len(vals)}
    with tempfile.TemporaryDirectory() as d:
        stub_path = os.path.join(d, "hg_stub.c")
        bin_path = os.path.join(d, "hg_bin")
        with open(stub_path, "w", encoding="utf-8") as fh:
            fh.write(stub_src)
        cc = subprocess.run(["cc", "-x", "c", "-O0", "-w", "-o", bin_path,
                             program, stub_path], capture_output=True,
                            timeout=20)
        if cc.returncode != 0:
            print(json.dumps({"violation": None, "error": "compile"}))
            return 0
        try:
            run = subprocess.run([bin_path], capture_output=True, timeout=10)
        except subprocess.TimeoutExpired:
            print(json.dumps({"violation": None, "error": "timeout"}))
            return 0
        violation = run.returncode != 0
    print(json.dumps({"violation": violation}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
