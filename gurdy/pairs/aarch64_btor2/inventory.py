"""The construct-coverage inventory for aarch64-btor2 (BENCHMARKS.md §2).

The denominator is spec-derived, not chosen by the agent: a 12-probe
representative slice of the A64 instruction space the pair is measured against,
held fixed across widenings so the coverage ratchet (BENCHMARKS.md §5) is honest
(covered may only grow; the denominator never shrinks). After the interpreter
``0.1`` → ``0.2`` widening the in-scope family is the simple, no-flag /
no-control-flow ALU writes ``ADD``/``SUB`` (immediate) and ``MOVZ``; every other
probe hard-aborts with a typed ``Unsupported`` (BENCHMARKS.md §3), which is what
makes the ``unsupported`` histogram an honest, itemized picture of the gap
rather than a hidden silent drop.

This is still a *partial* slice (PAIRING.md §1 "Start thin, then widen"): the
status stays ``partial`` until the in-scope set widens toward the brief's
base-ISA target. ``coverage()`` measures how many probes translate.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from ...languages.aarch64 import asm
from ...languages.aarch64.interp import program_from_words
from .translate import translate


def _p(*words: int) -> dict:
    return {"image": program_from_words(list(words))}


# The in-scope ALU family, in several legal forms (all must translate).
IN_SCOPE: dict[str, dict] = {
    # ADD (immediate) — the original 0.1 construct, in its legal forms.
    "ADD_imm": _p(asm.add_imm(0, 0, 1)),
    "ADD_imm_lsl12": _p(asm.add_imm(0, 0, 1, lsl12=True)),
    "ADD_imm_sp_src": _p(asm.add_imm(0, asm.SP, 16)),
    "ADD_imm_sp_dst": _p(asm.add_imm(asm.SP, asm.SP, 16)),
    # SUB (immediate) — same encoding class, op=1 (interp 0.2).
    "SUB_imm": _p(asm.sub_imm(0, 0, 1)),
    "SUB_imm_sp": _p(asm.sub_imm(asm.SP, asm.SP, 16)),    # SP src+dst
    # MOVZ — move wide, optional LSL #(16*hw) (interp 0.2).
    "MOVZ": _p(asm.movz(0, 42)),                          # == 0xD280_0540
    "MOVZ_lsl16": _p(asm.movz(1, 0xABCD, hw=1)),
}

# Representative out-of-scope A64 constructs — each must hard-abort with a typed
# Unsupported, naming the construct, so the gap is itemized (BENCHMARKS.md §3).
# The deferred categories: flag-setting ALU, the 32-bit form, loads, branches.
OUT_OF_SCOPE: dict[str, dict] = {
    "ADDS_imm": _p(asm.adds_imm(0, 0, 1)),       # flag-setting form (NZCV write)
    "ADD_imm_w": _p(asm.add_imm_w(0, 0, 1)),     # 32-bit (sf=0) form
    "LDR_imm": _p(0xF940_0000),                   # LDR X0, [X0]   (memory)
    "B": _p(0x1400_0000),                         # B .            (control flow)
}

ALL_PROBES: dict[str, dict] = {**IN_SCOPE, **OUT_OF_SCOPE}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
