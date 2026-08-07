"""WASM -> BTOR2 — carried over from v3 (KERNEL.md §7):
``gurdy/pairs/wasm_btor2/translate.py`` — the single-function stack
machine lowered to states ``pc``/``sp``/``halted``/locals/stack
slots, one body item per cycle.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.wasm import asm                       # noqa: E402
from gurdy.languages.wasm.interp import module             # noqa: E402
from gurdy.pairs.wasm_btor2.translate import translate     # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    program = json.load(fh)
body = [getattr(asm, item[0])(*item[1:]) for item in program["body"]] + [asm.i32_const(1)]
mod = module(body, nlocals=int(program.get("nlocals", 0)),
             local_types=program.get("local_types"))
sys.stdout.write(translate({"mod": mod}).decode("utf-8"))
