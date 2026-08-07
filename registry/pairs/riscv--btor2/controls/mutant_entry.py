"""RV64I -> BTOR2 — carried over from v3 (KERNEL.md §7): the rotor
lineage, ``gurdy/pairs/riscv_btor2/translate.py``, which mirrors the
shared interpreter rule-for-rule and models the machine one
instruction per cycle: states ``pc``, ``x1``..``x31``, ``halted``
(and ``mem`` when the program touches memory), the fixed program
lowered to a PC-keyed dispatch. Registers initialize to zero — an
input's ``regs`` binding crosses the hop through ``lam.py``, not
through the emission. Deterministic in the program bytes; the square
compares the named machine states this pair's target language now
reports.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.riscv.interp import image_from_words  # noqa: E402
from gurdy.pairs.riscv_btor2.translate import translate    # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    image = image_from_words([int(w) for w in program["words"]],
                             base=int(program.get("base", 0)),
                             entry=int(program.get("entry") or 0) + 4)
    sys.stdout.write(translate({"image": image}).decode("utf-8"))


if __name__ == "__main__":
    main()
