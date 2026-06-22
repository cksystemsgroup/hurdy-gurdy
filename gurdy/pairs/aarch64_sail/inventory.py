"""The construct-coverage inventory for aarch64-sail (BENCHMARKS.md §2).

The denominator is spec-derived, not chosen by the agent: a 15-probe
representative slice of the A64 instruction space the pair is measured against —
**identical to ``aarch64-btor2``'s slice** (same probe keys, same in-scope /
out-of-scope split) so the two AArch64→BTOR2 routes are measured on the same
yardstick and their covered sets coincide (branch agreement, PATHS.md §4-5). The
denominator only grows when a widening brings a *new* construct into scope (its
probe is added, growing the denominator alongside the numerator); nothing
previously covered ever drops, so the coverage ratchet (BENCHMARKS.md §5) stays
honest. After the Sail interpreter ``0.3`` → ``0.4`` widening the in-scope family
adds the first NZCV write (``SUBS``/``CMP`` immediate) and the first conditional
control flow (``B.cond``) to the ``ADD``/``SUB`` (immediate) and ``MOVZ`` ALU
writes — mirroring ``aarch64-btor2``'s ``0.3`` widening so the two routes' covered
sets coincide exactly (11/15). Every other probe is expected to hard-abort with a
typed ``Unsupported`` (BENCHMARKS.md §3), which is what makes the ``unsupported``
histogram an honest, itemized picture of the gap rather than a hidden silent
drop. (The slice grew 8/12 → 11/15: 3 new in-scope probes, the 4 out-of-scope
kept, all 8 prior covered probes intact.)

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


# The in-scope ALU family, in several legal forms (all must translate). These
# probe keys + programs are IDENTICAL to aarch64-btor2's IN_SCOPE so the two
# routes' covered sets coincide (branch agreement).
IN_SCOPE: dict[str, dict] = {
    # ADD (immediate) — the original 0.1 construct, in its legal forms.
    "ADD_imm": _p(asm.add_imm(0, 0, 1)),
    "ADD_imm_lsl12": _p(asm.add_imm(0, 0, 1, lsl12=True)),
    "ADD_imm_sp_src": _p(asm.add_imm(0, asm.SP, 16)),
    "ADD_imm_sp_dst": _p(asm.add_imm(asm.SP, asm.SP, 16)),
    # SUB (immediate) — same encoding class, op=1 (Sail interp 0.3).
    "SUB_imm": _p(asm.sub_imm(0, 0, 1)),
    "SUB_imm_sp": _p(asm.sub_imm(asm.SP, asm.SP, 16)),    # SP src+dst
    # MOVZ — move wide, optional LSL #(16*hw) (Sail interp 0.3).
    "MOVZ": _p(asm.movz(0, 42)),                          # == 0xD280_0540
    "MOVZ_lsl16": _p(asm.movz(1, 0xABCD, hw=1)),
    # SUBS / CMP (immediate) — the first NZCV write (Sail interp 0.4).
    "SUBS_imm": _p(asm.subs_imm(1, 0, 7)),                # SUBS X1, X0, #7
    "CMP_imm": _p(asm.cmp_imm(0, 5)),                     # CMP X0, #5 (Rd=XZR)
    # B.cond — the first conditional control flow (Sail interp 0.4).
    "Bcond": _p(asm.b_cond("EQ", 8)),                     # B.EQ +8
}

# Representative out-of-scope A64 constructs — each must hard-abort with a typed
# Unsupported, naming the construct, so the gap is itemized (BENCHMARKS.md §3).
# Identical to aarch64-btor2's OUT_OF_SCOPE (the deferred categories: flag-setting
# ALU, the 32-bit form, loads, branches).
OUT_OF_SCOPE: dict[str, dict] = {
    "ADDS_imm": _p(asm.adds_imm(0, 0, 1)),       # flag-setting form (NZCV write)
    "ADD_imm_w": _p(asm.add_imm_w(0, 0, 1)),     # 32-bit (sf=0) form
    "LDR_imm": _p(0xF940_0000),                   # LDR X0, [X0]   (memory)
    "B": _p(0x1400_0000),                         # B .            (control flow)
}

ALL_PROBES: dict[str, dict] = {**IN_SCOPE, **OUT_OF_SCOPE}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
