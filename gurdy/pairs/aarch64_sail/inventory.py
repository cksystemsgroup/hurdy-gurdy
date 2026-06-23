"""The construct-coverage inventory for aarch64-sail (BENCHMARKS.md §2).

The denominator is spec-derived, not chosen by the agent: a 23-probe
representative slice of the A64 instruction space the pair is measured against —
**identical to ``aarch64-btor2``'s slice** (same probe keys, same in-scope /
out-of-scope split) so the two AArch64→BTOR2 routes are measured on the same
yardstick and their covered sets coincide *exactly* (branch agreement, PATHS.md
§4-5). The denominator only grows when a widening brings a *new* construct into
scope (its probe is added, growing the denominator alongside the numerator);
nothing previously covered ever drops, so the coverage ratchet (BENCHMARKS.md §5)
stays honest. After the Sail interpreter ``0.5`` → ``0.6`` widening the in-scope
family adds the **first memory access** — the 64-bit unsigned-offset
``LDR``/``STR`` — to the ``0.5`` family (``ADD``/``SUB`` immediate + ``MOVZ`` +
``SUBS``/``CMP`` + ``ADDS``/``CMN`` + the conditional ``B.cond`` + the
unconditional ``B``/``BL``) — mirroring ``aarch64-btor2``'s ``0.5`` widening so
the two routes' covered sets coincide **exactly** (19/23, full branch agreement
restored). Every other probe is expected to hard-abort with a typed
``Unsupported`` (BENCHMARKS.md §3), which is what makes the ``unsupported``
histogram an honest, itemized picture of the gap rather than a hidden silent
drop. (The slice grew 15/17 → 19/23: 4 new in-scope probes — ``LDR``, ``STR``, an
offset ``LDR``, and an SP-relative ``STR`` — promoting the prior ``LDR_imm``
*out-of-scope* probe into a covered one; the still-deferred narrower widths
``LDRB``/``STRB`` and the 32-bit ``LDR`` are added as new out-of-scope probes
alongside the kept 32-bit ``ADD``; all 15 prior covered probes intact.)

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


# The in-scope family, in several legal forms (all must translate). These probe
# keys + programs are IDENTICAL to aarch64-btor2's IN_SCOPE so the two routes'
# covered sets coincide exactly (branch agreement).
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
    # B / BL — the unconditional branch (Sail interp 0.5).
    "B": _p(asm.b(8)),                                    # B +8 (always taken)
    "BL": _p(asm.bl(8)),                                  # BL +8 (also x30 := pc+4)
    # ADDS / CMN (immediate) — the addition NZCV write (Sail interp 0.5).
    "ADDS_imm": _p(asm.adds_imm(1, 0, 7)),               # ADDS X1, X0, #7
    "CMN_imm": _p(asm.cmn_imm(0, 5)),                     # CMN X0, #5 (Rd=XZR)
    # LDR / STR (64-bit, unsigned offset) — the first memory access (Sail interp 0.6).
    "LDR_imm": _p(asm.ldr_imm(0, 1, 0)),                  # LDR X0, [X1]   (== 0xF9400020)
    "STR_imm": _p(asm.str_imm(0, 1, 0)),                  # STR X0, [X1]
    "LDR_imm_off": _p(asm.ldr_imm(2, 3, 16)),             # LDR X2, [X3, #16]
    "STR_imm_sp": _p(asm.str_imm(4, asm.SP, 8)),          # STR X4, [SP, #8] (SP base)
}

# Representative out-of-scope A64 constructs — each must hard-abort with a typed
# Unsupported, naming the construct, so the gap is itemized (BENCHMARKS.md §3).
# Identical to aarch64-btor2's OUT_OF_SCOPE: the 32-bit ALU form, the narrower-width
# loads/stores (LDRB/STRB), and the 32-bit LDR — every other LDR/STR width.
OUT_OF_SCOPE: dict[str, dict] = {
    "ADD_imm_w": _p(asm.add_imm_w(0, 0, 1)),     # 32-bit (sf=0) ADD
    "LDR_imm_w": _p(asm.ldr_imm_w(0, 0)),        # 32-bit LDR W0,[X0] (size=10)
    "LDRB_imm": _p(asm.ldrb_imm(0, 0)),          # LDRB W0,[X0]       (byte width)
    "STRB_imm": _p(asm.strb_imm(0, 0)),          # STRB W0,[X0]       (byte width)
}

ALL_PROBES: dict[str, dict] = {**IN_SCOPE, **OUT_OF_SCOPE}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
