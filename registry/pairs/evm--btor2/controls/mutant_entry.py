"""EVM -> BTOR2 — carried over from v3 (KERNEL.md §7):
``gurdy/pairs/evm_btor2/translate.py`` — the stack machine lowered to
states ``pc``/``s*``/``sp``/``halted``/``status`` (and ``mem`` when
touched), one opcode per cycle.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.evm_btor2.translate import translate      # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    program = json.load(fh)
sys.stdout.write(translate(
    {"code": bytes(program["code"]),
     "entry": int(program.get("entry", 0)) + 1}).decode("utf-8"))
