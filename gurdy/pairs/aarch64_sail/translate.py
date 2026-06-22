"""AArch64 (A64) -> Sail translator (pairs/aarch64-sail brief): bind an AArch64
image into the Sail ARM model's representation — the "Sail object" the shared
Sail interpreter then executes via its *additive* A64 arm
(``languages/sail/aarch64.py``).

For this slice the Sail object is a JSON record
``{"isa":"aarch64", "words":[...], "entry":int, "init_regs":{i:v},
"init_sp":int, "init_nzcv":int}`` — the same routing-front shape as the
``riscv-sail`` translator, re-aimed at A64 (PATHS.md §4-5). The point is routing
A64 through a *second, independent* artifact (the Sail-derived ``Expr``
semantics) so the result can be cross-checked at BTOR2 against the direct
``aarch64-btor2`` route.

The translator is thin and deterministic; the semantics live in the Sail
interpreter's A64 arm. Decoding is delegated to the shared widened AArch64
decoder (``languages/aarch64.decode_insn_v3``) up front, so any out-of-scope
instruction hard-aborts with a typed ``Unsupported`` (BENCHMARKS.md §3) and
never silently slips into the Sail object. The ``isa`` tag is what dispatches
the Sail interpreter to its A64 arm; without it the RISC-V path would run, so it
is emitted unconditionally.

Scope (mirroring ``aarch64-btor2`` so the two AArch64→BTOR2 routes decide the
same constructs): the simple, no-flag/no-control-flow ALU family
``ADD (immediate)``, ``SUB (immediate)`` (both 64-bit) and ``MOVZ`` (64-bit),
**plus** the first NZCV write (``SUBS``/``CMP`` immediate) and the first
conditional control flow (``B.cond``) — switching the rejection gate from the
``0.2`` ``decode_insn`` to the ``0.3`` ``decode_insn_v3`` (exactly as
``aarch64-btor2`` does).
"""

from __future__ import annotations

import json
from typing import Any

from ...languages.aarch64.interp import SP_DEFAULT, A64Program, decode_insn_v3


def translate(program: dict[str, Any]) -> bytes:
    image: A64Program = program["image"]
    # Reject out-of-scope instructions up front (one source of truth: the shared
    # widened decoder, which now accepts ADD/SUB immediate + MOVZ + SUBS/CMP +
    # B.cond). This is the single rejection point for the translate edge.
    for word in image.words:
        decode_insn_v3(word)

    sail: dict[str, Any] = {
        "isa": "aarch64",
        "words": [int(w) & 0xFFFF_FFFF for w in image.words],
        "entry": int(image.entry),
        "init_regs": {int(k): int(v) for k, v in program.get("init_regs", {}).items()},
        "init_sp": int(program.get("init_sp", SP_DEFAULT)),
        "init_nzcv": int(program.get("init_nzcv", 0)) & 0xF,
    }
    return json.dumps(sail, sort_keys=True).encode("utf-8")
