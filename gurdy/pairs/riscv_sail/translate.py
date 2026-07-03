"""riscv -> sail translator (pairs/riscv-sail): lift a RISC-V program into the
RISC-V Sail model's representation.

For this slice the "Sail object" is the decoded instruction stream the Sail
machine consumes — a JSON record ``{words, entry, init_regs, property}`` that
``sail-btor2`` (and the Sail interpreter) execute via the Sail-derived
semantics. The point is routing RISC-V through a *second, independent*
artifact, so the result can be cross-checked against the direct ``riscv-btor2``
(ROUTES.md §4-5). RV64IMC (compressed instructions are expanded here, via the
Sail realization's own decompressor); deterministic.

Translator ``0.2``: the Sail object now carries the program's initial memory
(``mem``), so loads from initialized addresses agree with the RISC-V reference
interpreter. ``0.1`` dropped it — a fidelity gap that acceptance-only coverage
could not see and the conjoined (accepted AND square-passing) measurement
caught immediately (the seven load-family probes diverged at step 0).
"""

from __future__ import annotations

import json
from typing import Any


def translate(program: dict[str, Any]) -> bytes:
    from ...core.errors import Unsupported
    from ...languages.sail import compressed

    image = program["image"]
    lo = image.code_lo
    hi = image.code_hi if image.code_hi is not None else lo
    # 0.2 -> 0.3: the Sail object keeps the image's *absolute* addresses
    # (entry = code base) instead of rebasing to 0. Rebasing silently broke
    # every pc-relative absolute-address computation (AUIPC/LA, JAL link
    # values) on images not based at 0 — e.g. compliance ELFs at
    # 0x8000_0000 — a fidelity gap the declared projection (all of pc,
    # x1..x31) does not permit. A nonstandard image whose entry is not the
    # code base is out of scope, typed.
    if int(image.entry) != int(lo):
        raise Unsupported("riscv-sail", "entry-not-at-code-base")
    # Walk the halfword stream: a compressed (2-byte) unit is expanded to its
    # 32-bit base form via the Sail realization's *own* decompressor; the rest
    # are 32-bit. ``words`` are the expanded instructions, ``lengths`` their byte
    # widths, so the Sail side reconstructs the true 2-byte-granular PCs (RV64C).
    words: list[int] = []
    lengths: list[int] = []
    addr = lo
    while addr < hi:
        half = image.load(addr, 2)
        if compressed.is_compressed(half):
            words.append(compressed.expand(half))
            lengths.append(2)
            addr += 2
        else:
            words.append(image.load(addr, 4))
            lengths.append(4)
            addr += 4
    sail: dict[str, Any] = {
        "words": words,
        "lengths": lengths,
        "entry": int(lo),
        "init_regs": {int(k): int(v) for k, v in program.get("init_regs", {}).items()},
        # The program's initial memory (the image's byte map, code included):
        # part of the program, so the Sail interpreter sees the same initial
        # loads the RISC-V reference does. 0.1 -> 0.2: previously dropped,
        # which the conjoined coverage measurement caught — loads from
        # initialized memory read 0 on this route (incident I20). Sorted for
        # byte-determinism.
        "mem": {str(a): image.mem[a] & 0xFF for a in sorted(image.mem)},
    }
    if program.get("property") is not None:
        sail["property"] = program["property"]
    return json.dumps(sail).encode("utf-8")
