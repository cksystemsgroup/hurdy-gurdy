"""The language-owned A64 construct inventory (BENCHMARKS.md §2).

The yardstick is owned by the *language*, not by any pair (Definition 4.6
fixes the inventory per language): both AArch64 pairs (``aarch64-btor2`` and
``aarch64-sail``) are measured against this same denominator, so the two
AArch64→BTOR2 routes cannot quote different totals and their covered sets can
be compared construct-for-construct (branch agreement, ROUTES.md §4-5).

Scope honesty: unlike the finite-opcode inventories (EVM's 144 opcodes,
RV64IMC's 96 constructs), the full A64 base instruction set is far larger
than what any pair here lowers. The inventory is therefore a *declared
slice*: the in-scope family the pairs commit to, plus enumerated
representative out-of-scope constructs that must each hard-abort with a
typed ``Unsupported`` (the itemized gap, BENCHMARKS.md §3). The denominator
only ever grows (coverage ratchet, BENCHMARKS.md §5): when a widening brings
a new construct into scope its probe is added, growing the denominator
alongside the numerator, and nothing previously covered drops.
"""

from __future__ import annotations

from . import asm
from .interp import program_from_words


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
    # LDR / STR (64-bit, unsigned offset) — the first memory access (interp 0.5).
    "LDR_imm": _p(asm.ldr_imm(0, 1, 0)),                 # LDR X0, [X1]   (== 0xF9400020)
    "STR_imm": _p(asm.str_imm(0, 1, 0)),                 # STR X0, [X1]
    "LDR_imm_off": _p(asm.ldr_imm(2, 3, 16)),            # LDR X2, [X3, #16]
    "STR_imm_sp": _p(asm.str_imm(4, asm.SP, 8)),         # STR X4, [SP, #8] (SP base)
    # 32-bit (W-register) ALU/flag immediate forms — the W variants (interp 0.6).
    # The op computes on the low 32 bits, zero-extends the result into Xd, and sets
    # the flags at 32-bit width.
    "ADD_imm_w": _p(asm.add_imm_w(0, 0, 1)),             # ADD W0, W0, #1 (sf=0)
    "SUB_imm_w": _p(asm.sub_imm_w(0, 0, 1)),             # SUB W0, W0, #1
    "MOVZ_w": _p(asm.movz_w(0, 0x1234)),                 # MOVZ W0, #0x1234
    "MOVZ_w_lsl16": _p(asm.movz_w(1, 0xABCD, hw=1)),     # MOVZ W1, #0xABCD, LSL #16
    "SUBS_imm_w": _p(asm.subs_imm_w(1, 0, 7)),           # SUBS W1, W0, #7
    "CMP_imm_w": _p(asm.cmp_imm_w(0, 5)),                # CMP W0, #5 (Rd=WZR)
    "ADDS_imm_w": _p(asm.adds_imm_w(1, 0, 7)),           # ADDS W1, W0, #7
    "CMN_imm_w": _p(asm.cmn_imm_w(0, 5)),                # CMN W0, #5 (Rd=WZR)
}

# Representative out-of-scope A64 constructs — each must hard-abort with a typed
# Unsupported, naming the construct, so the gap is itemized (BENCHMARKS.md §3).
# The deferred categories now: the narrower-width loads/stores (LDRB/STRB), the
# 32-bit LDR, the reserved 32-bit MOVZ shift (hw=2), and the move-wide siblings
# MOVN/MOVK — every other LDR/STR width/addressing-mode and move-wide variant.
OUT_OF_SCOPE: dict[str, dict] = {
    "LDR_imm_w": _p(asm.ldr_imm_w(0, 0)),        # 32-bit LDR W0,[X0] (size=10)
    "LDRB_imm": _p(asm.ldrb_imm(0, 0)),          # LDRB W0,[X0]       (byte width)
    "STRB_imm": _p(asm.strb_imm(0, 0)),          # STRB W0,[X0]       (byte width)
    "MOVZ_w_hw2": _p(asm.movz_w_hw2(0, 1)),      # MOVZ W0,#1,LSL #32 (hw=2 reserved)
    "MOVN_imm": _p(asm.movn(0, 1)),              # MOVN (move-wide sibling)
    "MOVK_imm": _p(asm.movk(0, 1)),              # MOVK (move-wide sibling)
}

ALL_PROBES: dict[str, dict] = {**IN_SCOPE, **OUT_OF_SCOPE}
