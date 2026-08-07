"""riscv -> sail — carried over from v3 (KERNEL.md §7): lift a
RISC-V program into the Sail model's representation, the Sail object
the Sail interpreter and the ``sail--btor2`` lowering both consume.
v3 translator 0.2: carries the program's initial memory, and
compressed instructions are expanded via the Sail realization's own
decompressor. The point is routing RISC-V through a second,
independent artifact.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.riscv.interp import image_from_words  # noqa: E402
from gurdy.pairs.riscv_sail.translate import translate     # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    image = image_from_words([int(w) for w in program["words"]],
                             base=int(program.get("base", 0)),
                             entry=program.get("entry"))
    sys.stdout.write(translate({"image": image}).decode("utf-8"))


if __name__ == "__main__":
    main()
