"""MUTANT (entry skewed by 4) — carried over from v3 (KERNEL.md §7): the direct
AArch64 lowering, ``gurdy/pairs/aarch64_btor2/translate.py``, which
mirrors the shared A64 interpreter rule-for-rule, one instruction per
cycle: states ``pc``, ``x0``..``x30``, ``sp``, ``nzcv``, ``halted``
(and the byte memory with its ``m0``..``m63`` observable window when
the program uses LDR/STR). The program's ``init_regs``/``init_sp``/
``init_nzcv``/``init_mem`` bake into the emission's ``init`` lines —
the same initial state the source interpreter reads from the program,
which is what closes the square. Deterministic in the program bytes.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.aarch64.interp import program_from_words  # noqa: E402
from gurdy.pairs.aarch64_btor2.translate import translate      # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    head = {"image": program_from_words(
        [int(w) for w in program["words"]],
        entry=int(program.get("entry", 0)) + 4)}
    for key in ("init_regs", "init_sp", "init_nzcv", "init_mem",
                "property"):
        if key in program:
            head[key] = ({int(k): int(v) for k, v in program[key].items()}
                         if key in ("init_regs", "init_mem")
                         else program[key])
    sys.stdout.write(translate(head).decode("utf-8"))


if __name__ == "__main__":
    main()
