"""MUTANT (result skewed by one) — the pinned compiler, carried over from v3
(KERNEL.md §7): ``gurdy/pairs/c_riscv/translate.py``. The program's
``long PROP(void)`` is linked with the freestanding ``_start`` stub
that surfaces the value in ``a0`` and halts (ECALL), compiled with
the pinned ``riscv64-unknown-elf-gcc`` and fixed, ordered flags
(rv64im, -O2, no unwind tables — byte-identical ELF from the same
source), and the code section is emitted in the registry's riscv
program form ``{"words", "base", "entry"}``.

The translator is opaque (nobody predicts ``gcc -O2`` from a
schema); what admission checks is the square that Era 3 called the
C differential: native execution through the host's pinned compiler
(the c entry's interpreter) against the shared RISC-V interpreter on
the lowered words — ``result`` ≡ ``x10``, ``halted`` ≡ ``halted``.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.riscv.elf import load_elf         # noqa: E402
from gurdy.pairs.c_riscv.translate import compile_c    # noqa: E402

_STUB = ('long PROP(void);\n'
         'void _start(void) {\n'
         '    long r = PROP();\n'
         '    __asm__ volatile("mv a0,%0\\n\\tecall\\n" :: "r"(r) : "a0");\n'
         '    for (;;) {}\n'
         '}\n')


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        source = fh.read()
    image = load_elf(compile_c(
        _STUB + source.replace("return", "return 1 +", 1)))
    words = [int.from_bytes(
        bytes(image.mem.get(a + i, 0) for i in range(4)), "little")
        for a in range(image.code_lo, image.code_hi, 4)]
    print(json.dumps({"words": words, "base": image.code_lo,
                      "entry": image.entry}, sort_keys=True))


if __name__ == "__main__":
    main()
