"""C shared interpreter — the C leg carried over from v3 (KERNEL.md
§7; reconciliation carry-over, 2026-08-14).

A program is freestanding C text defining ``long PROP(void)`` — a
pure integer computation. The interpreter is **real execution
through the host's pinned C compiler**: the program is linked with a
one-line harness that prints ``PROP()`` and run natively — the
"large real interpreter" resolved toward the real toolchain as the
oracle, exactly as the Python entry pins real CPython. Input:
``{"steps"?}`` (ignored — a C run is closed). Observables:
``result`` — ``PROP()``'s value as the unsigned 64-bit bit pattern
(the two's-complement view a machine register reports, which is what
closes the ``c--riscv`` square against ``x10``) — and ``halted``.
"""

import json
import os
import subprocess
import sys
import tempfile

_CC = os.environ.get("CC", "cc")
_FLAGS = ("-std=c11", "-O1", "-w")
_HARNESS = ('#include <stdio.h>\n'
            'long PROP(void);\n'
            'int main(void){ printf("%ld", PROP()); return 0; }\n')


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        source = fh.read()
    with tempfile.TemporaryDirectory() as tmp:
        prog = os.path.join(tmp, "prog.c")
        harness = os.path.join(tmp, "main.c")
        exe = os.path.join(tmp, "prog")
        with open(prog, "w", encoding="utf-8") as fh:
            fh.write(source)
        with open(harness, "w", encoding="utf-8") as fh:
            fh.write(_HARNESS)
        subprocess.run([_CC, *_FLAGS, "-o", exe, prog, harness],
                       check=True, capture_output=True)
        out = subprocess.run([exe], check=True, capture_output=True,
                             text=True)
    value = int(out.stdout.strip()) & 0xFFFF_FFFF_FFFF_FFFF
    print(json.dumps({"halted": 1, "result": value}, sort_keys=True))


if __name__ == "__main__":
    main()
