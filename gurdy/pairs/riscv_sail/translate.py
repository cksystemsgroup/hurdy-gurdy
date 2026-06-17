"""riscv -> sail translator (pairs/riscv-sail): lift a RISC-V program into the
RISC-V Sail model's representation.

For this slice the "Sail object" is the decoded instruction stream the Sail
machine consumes — a JSON record ``{words, entry, init_regs, property}`` that
``sail-btor2`` (and the Sail interpreter) execute via the Sail-derived
semantics. The point is routing RISC-V through a *second, independent*
artifact, so the result can be cross-checked against the direct ``riscv-btor2``
(PATHS.md §4-5). 32-bit ALU programs; deterministic.
"""

from __future__ import annotations

import json
from typing import Any


def translate(program: dict[str, Any]) -> bytes:
    image = program["image"]
    lo = image.code_lo
    hi = image.code_hi if image.code_hi is not None else lo
    words = [image.load(addr, 4) for addr in range(lo, hi, 4)]
    sail: dict[str, Any] = {
        "words": words,
        "entry": 0,
        "init_regs": {int(k): int(v) for k, v in program.get("init_regs", {}).items()},
    }
    if program.get("property") is not None:
        sail["property"] = program["property"]
    return json.dumps(sail).encode("utf-8")
