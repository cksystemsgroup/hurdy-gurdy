"""What clang says about the assertion vectors of the C language.

A vector here is a program of assertions closed by one that cannot
hold: ``__VERIFIER_assert(0)``. Its expectation — bad, at the depth of
that last assertion — is true exactly when every assertion before it
holds. This script puts that to a compiler that never enters the
registry: the program as written must reach ``__assert_fail``, and the
program without its last assertion must return from ``main``.

    python3 testify.py <vectors-dir> NNN [NNN ...]

compiles each ``NNN.program`` both ways with ``clang -O0 -fwrapv`` on
this host and records what happened in ``testimony.jsonl`` beside this
file. The programs avoid ``long`` and plain ``char``, the two types
whose size or signedness the host's ABI gives differently from the
fragment's ILP32. A program whose expectation is a stipulation of the
fragment where C leaves behaviour undefined is not put to the oracle.
Nothing here is imported or run by the kernel.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

STUB = """
void _exit(int);
void __assert_fail(const char *a, const char *b, unsigned int c,
                   const char *d) { _exit(99); }
"""
LAST = "  __VERIFIER_assert(0);\n"


def run(source: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "p.c"), "w") as fh:
            fh.write(source + STUB)
        exe = os.path.join(tmp, "p")
        subprocess.run(["clang", "-O0", "-fwrapv", "-w", "-o", exe,
                        os.path.join(tmp, "p.c")], check=True)
        return subprocess.run([exe], timeout=60).returncode


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    version = subprocess.run(["clang", "--version"], capture_output=True,
                             text=True).stdout.split("\n")[0]
    records = []
    for n in argv[1:]:
        with open(os.path.join(argv[0], f"{n}.program")) as fh:
            source = fh.read()
        if source.count(LAST) != 1:
            raise SystemExit(f"{n}: no single closing assertion")
        said = {"as written": run(source),
                "without the last assertion": run(source.replace(LAST, ""))}
        if said != {"as written": 99, "without the last assertion": 0}:
            raise SystemExit(f"dispute: {n}: clang's exit codes {said}")
        records.append({"vector": n, "oracle": f"{version}, -O0 -fwrapv",
                        "asserts": source.count("__VERIFIER_assert(") - 2,
                        "exit": said})
    with open(os.path.join(here, "testimony.jsonl"), "w") as fh:
        for r in records:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    sys.stdout.write(f"{len(records)} programs: clang reaches the error "
                     "as written and returns without the last assertion\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
