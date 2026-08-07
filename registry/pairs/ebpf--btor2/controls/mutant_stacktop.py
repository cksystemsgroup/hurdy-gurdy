"""eBPF -> BTOR2 — carried over from v3 (KERNEL.md §7):
``gurdy/pairs/ebpf_btor2/translate.py``, one instruction per cycle,
states ``pc``/``r0``..``r10``/``halted`` (and ``mem``/``pkt`` when
touched), the program lowered to a PC-keyed dispatch.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.ebpf.interp import BpfProgram         # noqa: E402
from gurdy.pairs.ebpf_btor2.translate import translate     # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    program = json.load(fh)
prog = BpfProgram(insns=[int(w) for w in program["insns"]],
                  entry=int(program.get("entry", 0)), stack_top=8)
sys.stdout.write(translate({"prog": prog}).decode("utf-8"))
