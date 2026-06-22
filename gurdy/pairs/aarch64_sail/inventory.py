"""The construct-coverage inventory for aarch64-sail (BENCHMARKS.md §2).

The denominator is spec-derived, not chosen by the agent: a representative slice
of the A64 instruction space the thin pair is measured against — identical to
``aarch64-btor2``'s slice so the two AArch64→BTOR2 routes are measured on the
same yardstick. Exactly one construct — ``ADD (immediate)`` — is in scope and
translates; every other probe is expected to hard-abort with a typed
``Unsupported`` (BENCHMARKS.md §3), which is what makes the ``unsupported``
histogram an honest, itemized picture of the gap rather than a hidden silent
drop.

This is a deliberately *partial* slice (PAIRING.md §1 "Start thin, then widen"):
coverage here is intentionally ``1 / N``, and the status stays ``partial`` until
the in-scope set widens. ``coverage()`` measures how many probes translate.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from ...languages.aarch64 import asm
from ...languages.aarch64.interp import program_from_words
from .translate import translate


def _p(*words: int) -> dict:
    return {"image": program_from_words(list(words))}


# The one in-scope construct, in several legal forms (all must translate).
IN_SCOPE: dict[str, dict] = {
    "ADD_imm": _p(asm.add_imm(0, 0, 1)),
    "ADD_imm_lsl12": _p(asm.add_imm(0, 0, 1, lsl12=True)),
    "ADD_imm_sp_src": _p(asm.add_imm(0, asm.SP, 16)),
    "ADD_imm_sp_dst": _p(asm.add_imm(asm.SP, asm.SP, 16)),
}

# Representative out-of-scope A64 constructs — each must hard-abort with a typed
# Unsupported, naming the construct, so the gap is itemized (BENCHMARKS.md §3).
OUT_OF_SCOPE: dict[str, dict] = {
    "SUB_imm": _p(asm.sub_imm(0, 0, 1)),
    "ADDS_imm": _p(asm.adds_imm(0, 0, 1)),       # flag-setting form
    "ADD_imm_w": _p(asm.add_imm_w(0, 0, 1)),     # 32-bit (sf=0) form
    "MOVZ": _p(0xD280_0540),                      # MOVZ X0, #42  (move-wide)
    "NOP": _p(0xD503_201F),                       # NOP (hint)
    "RET": _p(0xD65F_03C0),                       # RET
    "LDR_imm": _p(0xF940_0000),                   # LDR X0, [X0]
    "B": _p(0x1400_0000),                         # B .  (branch)
}

ALL_PROBES: dict[str, dict] = {**IN_SCOPE, **OUT_OF_SCOPE}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
