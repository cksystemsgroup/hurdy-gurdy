"""The construct-coverage inventory for aarch64-btor2 (BENCHMARKS.md §2).

The denominator is spec-derived, not chosen by the agent: a representative slice
of the A64 instruction space the pair is measured against. The coverage ratchet
(BENCHMARKS.md §5) is honest because **covered may only grow and nothing
previously covered drops**; when a widening brings a *new* construct into scope
its probe is added (growing the denominator alongside the numerator), but no
probe is ever moved from covered to missing. After the interpreter
``0.3`` → ``0.4`` widening the in-scope family adds the **unconditional branch**
(``B``/``BL``) and the **addition flag write** (``ADDS``/``CMN`` immediate) to the
``0.3`` family (``ADD``/``SUB`` immediate + ``MOVZ`` + ``SUBS``/``CMP`` + the
conditional branch ``B.cond``); every other probe hard-aborts with a typed
``Unsupported`` (BENCHMARKS.md §3), which is what makes the ``unsupported``
histogram an honest, itemized picture of the gap rather than a hidden silent drop.
(The slice grew 11/15 → 15/17: 4 new in-scope probes — ``B``, ``BL``, ``ADDS``,
``CMN`` — promoting the prior ``ADDS_imm``/``B`` *out-of-scope* probes into
covered ones and adding ``BL``/``CMN``; the 2 remaining out-of-scope kept, all 11
prior covered probes intact.)

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


# The in-scope family, in several legal forms (all must translate).
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
    # SUBS / CMP (immediate) — the first NZCV write (interp 0.3).
    "SUBS_imm": _p(asm.subs_imm(1, 0, 7)),                # SUBS X1, X0, #7
    "CMP_imm": _p(asm.cmp_imm(0, 5)),                     # CMP X0, #5 (Rd=XZR)
    # B.cond — the first conditional control flow (interp 0.3).
    "Bcond": _p(asm.b_cond("EQ", 8)),                     # B.EQ +8
    # B / BL — the unconditional branch (interp 0.4).
    "B": _p(asm.b(8)),                                    # B +8 (always taken)
    "BL": _p(asm.bl(8)),                                  # BL +8 (also x30 := pc+4)
    # ADDS / CMN (immediate) — the addition NZCV write (interp 0.4).
    "ADDS_imm": _p(asm.adds_imm(1, 0, 7)),               # ADDS X1, X0, #7
    "CMN_imm": _p(asm.cmn_imm(0, 5)),                    # CMN X0, #5 (Rd=XZR)
}

# Representative out-of-scope A64 constructs — each must hard-abort with a typed
# Unsupported, naming the construct, so the gap is itemized (BENCHMARKS.md §3).
# The deferred categories now: the 32-bit form and loads.
OUT_OF_SCOPE: dict[str, dict] = {
    "ADD_imm_w": _p(asm.add_imm_w(0, 0, 1)),     # 32-bit (sf=0) form
    "LDR_imm": _p(0xF940_0000),                   # LDR X0, [X0]   (memory)
}

ALL_PROBES: dict[str, dict] = {**IN_SCOPE, **OUT_OF_SCOPE}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
