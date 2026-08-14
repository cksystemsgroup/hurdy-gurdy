"""A64 -> Sail — carried over from v3 (KERNEL.md §7): the front of
the Sail-mediated AArch64 route, ``gurdy/pairs/aarch64_sail/
translate.py``. Emits the A64 Sail object (``{"isa": "aarch64",
"words", "entry", "init_regs", "init_sp", "init_nzcv", "init_mem"}``,
plus an optional threaded ``property``) that the shared Sail
interpreter's additive A64 arm evaluates — datapaths independent of
the direct ``aarch64--btor2`` lowering, which is what makes this
route a real cross-check of that one. The program's initial state
rides into the object; deterministic in the program bytes.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.aarch64.interp import program_from_words  # noqa: E402
from gurdy.pairs.aarch64_sail.translate import translate       # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    head = {"image": program_from_words(
        [int(w) for w in program["words"]],
        entry=int(program.get("entry", 0)))}
    for key in ("init_regs", "init_sp", "init_nzcv", "init_mem",
                "property"):
        if key in program:
            head[key] = program[key]
    sys.stdout.write(translate(head).decode("utf-8"))


if __name__ == "__main__":
    main()
