"""A deterministic AArch64 (A64) interpreter — the shared AArch64 source
interpreter (languages/aarch64 brief, ARCHITECTURE.md §§5-6).

Scope (interpreter version ``0.5``, widened from ``0.4`` under the coverage
ratchet — BENCHMARKS.md §5). The ``0.2`` family was a small set of simple,
pure-register ALU writes, each with a single ``pc + 4`` successor and **no flag
write / no control flow**:

- ``ADD (immediate)`` 64-bit — ``ADD Xd|SP, Xn|SP, #imm{, LSL #0|#12}`` (the
  ``0.1`` construct, byte-for-byte unchanged);
- ``SUB (immediate)`` 64-bit — ``SUB Xd|SP, Xn|SP, #imm{, LSL #0|#12}`` (same
  Add/subtract-immediate encoding class as ``ADD``, ``op = 1``);
- ``MOVZ`` 64-bit — ``MOVZ Xd, #imm16{, LSL #0|#16|#32|#48}`` (move wide, zeroing
  the rest of the register).

The ``0.3`` widening adds the **first NZCV write** and the **first conditional
control flow** (still 64-bit, additive):

- ``SUBS (immediate)`` / ``CMP (immediate)`` 64-bit — ``SUBS Xd, Xn|SP, #imm`` /
  ``CMP Xn|SP, #imm`` (= ``SUBS XZR, Xn, #imm``). Computes ``result = Xn - imm``,
  writes ``result`` to ``Xd`` (``CMP`` discards via ``XZR`` = field 31), and
  **sets** the NZCV flags: ``N = result<63>``, ``Z = (result == 0)``,
  ``C = (Xn >=u imm)`` (no borrow), ``V`` = signed overflow of ``Xn - imm``.
- ``B.cond`` — a conditional branch: ``if cond(NZCV) then pc := pc + offset else
  pc := pc + 4``. ``offset`` is the sign-extended 19-bit ``imm19`` scaled by 4.
  Supports the full standard condition-code table (``EQ``/``NE``/``CS``/``CC``/
  ``MI``/``PL``/``VS``/``VC``/``HI``/``LS``/``GE``/``LT``/``GT``/``LE``/``AL``/
  ``NV``).

The ``0.4`` widening adds the **unconditional branch** and the **addition flag
write** (still 64-bit, additive):

- ``B`` / ``BL`` (unconditional branch, opcode ``0b000101`` / ``0b100101`` —
  bit[31] is the link bit). ``pc := pc + SignExtend(imm26)*4`` — always taken (the
  ``B.cond`` lowering with condition = ``true``). ``BL`` additionally writes the
  link register ``x30 := pc + 4`` (the byte address of the instruction after the
  ``BL``) before branching. ``B``/``BL`` read and write no flags.
- ``ADDS (immediate)`` / ``CMN (immediate)`` 64-bit — ``ADDS Xd, Xn|SP, #imm`` /
  ``CMN Xn|SP, #imm`` (= ``ADDS XZR, Xn, #imm``). Computes ``result = Xn + imm``,
  writes ``result`` to ``Xd`` (``CMN`` discards via ``XZR`` = field 31), and
  **sets** the NZCV flags with the **addition** definitions of ``C``/``V`` (which
  differ from ``SUBS``'s subtraction definitions): ``N = result<63>``,
  ``Z = (result == 0)``, ``C`` = unsigned carry-out of ``Xn + imm`` (the 65-bit
  sum overflows 64 bits), ``V`` = signed overflow of the add (``Xn<63> == imm<63>``
  and ``result<63> != Xn<63>``).

The ``0.5`` widening adds the **first memory access** — the 64-bit load/store
register, unsigned-offset immediate form (still additive; the register/flag/branch
behavior above is byte-for-byte unchanged):

- ``STR Xt, [Xn|SP, #imm]`` (64-bit) — store the 64-bit ``Xt`` to byte-addressed
  memory **little-endian** at address ``Xn + imm`` (``Xt<7:0>`` at the lowest
  address). ``imm`` is the 12-bit unsigned immediate **scaled by 8** (the access
  size for a 64-bit register), so ``imm = imm12 * 8``. The base ``Xn`` field 31 is
  ``SP``; the transfer field ``Xt`` 31 is the zero register ``XZR`` (a store of
  ``XZR`` writes 0).
- ``LDR Xt, [Xn|SP, #imm]`` (64-bit) — load 64 bits **little-endian** from memory
  at ``Xn + imm`` into ``Xt`` (lowest address is ``Xt<7:0>``). Bytes never written
  read as 0 (zero-initialized memory). Base/transfer field-31 semantics as ``STR``;
  ``Xt`` 31 is ``XZR`` (the load is discarded).

Memory is modeled as a byte map (``{byte_addr: byte}``), little-endian — AArch64 is
LE. The post-step **memory observable** is a fixed window ``m0 .. m{MEM_WINDOW-1}``
of the lowest ``MEM_WINDOW`` memory bytes (each a byte ``0..255``); it mirrors the
``aarch64-btor2`` BTOR2 memory-window states so the commuting square checks memory.
Only the 64-bit unsigned-offset form is in scope this round — the 32-bit/byte/
halfword widths, ``LDRB``/``STRB``, the pre/post-index and unscaled (``LDUR``)
addressing modes, and ``LDRSW`` all hard-abort.

Every other A64 instruction hard-aborts with a typed ``Unsupported``
(BENCHMARKS.md §3) — never silently dropped or mis-executed — so coverage stays
honest and widening is monotone.

The machine state is the 31 general registers ``x0``–``x30``, the stack pointer
``sp``, the program counter ``pc`` (a byte address; A64 instructions are 4 bytes
each), the ``NZCV`` condition flags (a bv4 packed ``N=bit3, Z=bit2, C=bit1,
V=bit0`` — MSB-first, matching the ``NZCV`` name order), a byte-addressed
``memory`` (LE), and a ``halted`` flag. Observables (ARCHITECTURE.md §5): ``pc``,
``x0``–``x30``, ``sp``, ``nzcv``, the memory window ``m0``–``m{MEM_WINDOW-1}``,
``halted`` — recorded *after* each transition (post-step state). The run halts
when ``pc`` leaves the code region (running off the end), exactly as the RISC-V /
eBPF interpreters do; there is no halt *instruction* in this slice.

A64 details honored:

- ``sf = 1`` selects the 64-bit variant (the only one in scope; the 32-bit
  ``sf = 0`` forms abort).
- **Register field 31 is encoding-class-dependent.** For ``ADD``/``SUB``
  (immediate) the value ``31`` denotes ``SP`` (these are the canonical
  SP-relative add/subtract; ``Rn = 31`` reads ``sp``, ``Rd = 31`` writes ``sp``).
  For ``SUBS``/``CMP`` and ``ADDS``/``CMN`` (immediate, the flag-setting forms)
  the value ``31`` is ``SP`` for the *source* ``Rn`` but the **zero register**
  ``XZR`` for the *destination* ``Rd`` (so ``SUBS XZR, …`` = ``CMP`` and
  ``ADDS XZR, …`` = ``CMN``, the write discarded). For ``MOVZ`` (move wide) the
  value ``31`` denotes ``XZR`` — a write to ``Rd = 31`` is discarded, *not* a
  write to ``sp``.
- ``ADD``/``SUB``/``SUBS`` take a 12-bit immediate optionally shifted left by 12
  (``shift`` field ``01``); ``shift`` values ``1x`` are reserved and abort.
- ``MOVZ`` takes a 16-bit immediate optionally shifted left by ``hw * 16`` for
  ``hw ∈ {0,1,2,3}`` (LSL #0/#16/#32/#48); it zeroes every other bit of ``Rd``.
- ``ADD``/``SUB`` (``S = 0``) and ``MOVZ`` do **not** update ``NZCV``; the
  flag-setting ``SUBS``/``CMP`` and ``ADDS``/``CMN`` forms write the flags (with
  the subtraction and addition ``C``/``V`` definitions respectively). ``B.cond``,
  ``B`` and ``BL`` read/write no flags. ``B.cond``/``B`` write only ``pc``; ``BL``
  writes ``pc`` and the link register ``x30``.

Pure and deterministic: identical ``(image, binding)`` -> identical trace.

Backwards compatibility (AGENTS.md §3, shared interpreter): the ``0.1``
``decode`` (``ADD``-immediate only), the ``0.2`` ``decode_insn``
(``ADD``/``SUB`` immediate + ``MOVZ``), the ``0.3`` ``decode_insn_v3``
(adding ``SUBS``/``CMP`` + ``B.cond``), and the ``0.4`` ``decode_insn_v4``
(adding the unconditional ``B``/``BL`` + the addition flag-set ``ADDS``/``CMN``)
are all retained **byte-for-byte** as narrower decoders — they still reject the
newer ops with the same typed aborts. The cross-checked ``aarch64-sail`` route
mirrors the ``0.5`` family next, so the narrower decoders stay as its rejection
gates until then. The ``0.5`` family (adding the 64-bit unsigned-offset
``LDR``/``STR``) is decoded by the new ``decode_insn_v5``, used by ``run`` and by
the ``aarch64-btor2`` translator (one source of truth).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace

MASK64 = (1 << 64) - 1
NREG = 31          # x0..x30 ; the stack pointer is modeled separately as `sp`
SP_DEFAULT = 1 << 20
INSN_BYTES = 4
LDST_BYTES = 8     # the 64-bit load/store transfer width (the only one in scope)
# Bytes of byte-addressed memory exposed as the post-step observable window
# m0..m{MEM_WINDOW-1} (mirrored by the aarch64-btor2 BTOR2 window states so the
# commuting square checks memory). 64 bytes >= a few 8-byte accesses at low
# addresses (the test corpus); not the whole address space.
MEM_WINDOW = 64

# NZCV is packed into a bv4, MSB-first to match the name order N,Z,C,V.
NZCV_N = 1 << 3
NZCV_Z = 1 << 2
NZCV_C = 1 << 1
NZCV_V = 1 << 0

# In-scope operation kinds (the decoder tags each decoded instruction with one).
OP_ADD = "add"     # ADD (immediate): result = read(Rn) + imm        (Rn/Rd 31 => SP)
OP_SUB = "sub"     # SUB (immediate): result = read(Rn) - imm        (Rn/Rd 31 => SP)
OP_MOVZ = "movz"   # MOVZ: result = imm (zeroing the rest)           (Rd 31 => XZR, discarded)
OP_SUBS = "subs"   # SUBS/CMP (immediate): result = read(Rn) - imm, sets NZCV
                   #   (Rn 31 => SP source; Rd 31 => XZR, write discarded == CMP)
OP_ADDS = "adds"   # ADDS/CMN (immediate): result = read(Rn) + imm, sets NZCV
                   #   (Rn 31 => SP source; Rd 31 => XZR, write discarded == CMN)
                   #   C/V use the *addition* definitions (distinct from SUBS).
OP_BCOND = "bcond"  # B.cond: conditional pc update; reads NZCV, writes only pc
OP_B = "b"         # B/BL: unconditional pc update (always taken). BL also writes
                   #   the link register x30 := pc + 4 (set `link=True` on Decoded).
OP_LDR = "ldr"     # LDR Xt, [Xn|SP, #imm]: load 64 bits LE from mem[Rn+imm] -> Rt
                   #   (Rn 31 => SP base; Rt 31 => XZR, load discarded).
OP_STR = "str"     # STR Xt, [Xn|SP, #imm]: store the 64-bit Rt LE to mem[Rn+imm]
                   #   (Rn 31 => SP base; Rt 31 => XZR, stores 0).


def _u64(v: int) -> int:
    return v & MASK64


def cond_holds(cond: int, nzcv: int) -> bool:
    """Evaluate an A64 condition code (4-bit) against the packed NZCV flags.

    This is the standard ARM condition table. ``cond[0]`` inverts the base
    condition selected by ``cond[3:1]``, except for ``AL`` (``111x``) which is
    always true. Used by ``B.cond`` (and mirrored bit-for-bit by the
    ``aarch64-btor2`` translator's condition ITE, SPEC.md)."""
    n = 1 if nzcv & NZCV_N else 0
    z = 1 if nzcv & NZCV_Z else 0
    c = 1 if nzcv & NZCV_C else 0
    v = 1 if nzcv & NZCV_V else 0
    base = cond >> 1
    if base == 0b000:        # EQ / NE
        result = z == 1
    elif base == 0b001:      # CS(HS) / CC(LO)
        result = c == 1
    elif base == 0b010:      # MI / PL
        result = n == 1
    elif base == 0b011:      # VS / VC
        result = v == 1
    elif base == 0b100:      # HI / LS
        result = c == 1 and z == 0
    elif base == 0b101:      # GE / LT
        result = n == v
    elif base == 0b110:      # GT / LE
        result = z == 0 and n == v
    else:                    # base == 0b111: AL / NV — always true on A64
        result = True
    # cond[0] inverts, but AL/NV (cond[3:1] == 111) are never inverted.
    if (cond & 1) and base != 0b111:
        result = not result
    return result


@dataclass
class A64Program:
    """A loaded AArch64 image: little-endian 32-bit instruction words placed at
    consecutive byte addresses starting at ``entry`` (``pc`` is a byte address,
    so word ``i`` lives at ``entry + 4*i``)."""

    words: list[int] = field(default_factory=list)
    entry: int = 0

    @property
    def code_lo(self) -> int:
        return self.entry

    @property
    def code_hi(self) -> int:
        return self.entry + INSN_BYTES * len(self.words)

    def word_at(self, addr: int) -> int:
        idx = (addr - self.entry) // INSN_BYTES
        return self.words[idx]


def program_from_words(words: list[int], entry: int = 0) -> A64Program:
    return A64Program(words=list(words), entry=entry)


@dataclass
class Decoded:
    """A decoded in-scope A64 instruction.

    ``op`` is the operation kind (``OP_ADD`` / ``OP_SUB`` / ``OP_MOVZ`` /
    ``OP_SUBS`` / ``OP_ADDS`` / ``OP_BCOND`` / ``OP_B``); it defaults to
    ``OP_ADD`` so the original ``Decoded(rd=, rn=, imm=)`` construction (the
    ``ADD``-immediate-only ``decode``) is unchanged. ``rn`` is ignored for
    ``MOVZ`` (which has no source register; it is set to 31, the encoding's
    reserved value). ``cond`` and ``offset`` are used by the branches (the 4-bit
    condition code — for ``B.cond`` only — and the signed branch displacement in
    *bytes*); ``link`` is set for ``BL`` (write ``x30 := pc + 4``). The ALU ops
    leave the branch fields at their defaults."""

    rd: int                  # destination register field
    rn: int                  # source register field (unused for MOVZ / branches)
    imm: int                 # the (already shift-applied) immediate
    op: str = OP_ADD         # OP_ADD / OP_SUB / OP_MOVZ / OP_SUBS / OP_ADDS / OP_BCOND / OP_B
    cond: int = 0            # B.cond: 4-bit condition code
    offset: int = 0          # B.cond / B / BL: signed branch displacement, in bytes
    link: bool = False       # BL: also write the link register x30 := pc + 4


def decode(word: int) -> Decoded:
    """Decode one ``ADD (immediate)`` 64-bit instruction word, or hard-abort.

    Retained byte-for-byte from interpreter ``0.1`` as the ``ADD``-only decoder
    (it rejects ``SUB``/``MOVZ`` and everything else), so callers that use it as
    a rejection gate keep their original accept/reject boundary. The widened
    family is decoded by ``decode_insn``.

    Recognizes only ``ADD (immediate)``, 64-bit form:
    ``sf op S 1 0 0 0 1 sh imm12 Rn Rd`` = ``1 0 0 10001 sh imm12 Rn Rd``.
    """
    word &= 0xFFFF_FFFF
    sf = (word >> 31) & 0x1
    op = (word >> 30) & 0x1          # 0 = ADD, 1 = SUB
    s = (word >> 29) & 0x1           # 1 = set flags (ADDS/SUBS)
    family = (word >> 24) & 0x1F     # bits[28:24]
    shift = (word >> 22) & 0x3       # bits[23:22]
    imm12 = (word >> 10) & 0xFFF
    rn = (word >> 5) & 0x1F
    rd = word & 0x1F

    # The Add/subtract (immediate) encoding group is bits[28:24] == 0b10001.
    if family != 0b10001:
        raise Unsupported("aarch64", f"opcode=0x{word:08x}")
    if op != 0:
        raise Unsupported("aarch64", "sub.immediate")
    if s != 0:
        raise Unsupported("aarch64", "adds.immediate")  # flag-setting form
    if sf != 1:
        raise Unsupported("aarch64", "add.immediate.w")  # 32-bit form
    if shift == 0b00:
        imm = imm12
    elif shift == 0b01:
        imm = imm12 << 12
    else:
        raise Unsupported("aarch64", f"add.immediate.shift=0b{shift:02b}")
    return Decoded(rd=rd, rn=rn, imm=imm, op=OP_ADD)


def _decode_add_sub_imm(word: int) -> Decoded:
    """Decode the Add/subtract (immediate) class, 64-bit ``ADD``/``SUB``.

    ``sf op S 1 0 0 0 1 sh imm12 Rn Rd`` with ``family = 0b10001``. ``op = 0`` is
    ``ADD``, ``op = 1`` is ``SUB``; both share the SP-as-field-31 semantics and
    the optional ``LSL #12``. Flag-setting (``S = 1``) and 32-bit (``sf = 0``)
    forms stay out of scope and abort, exactly as for ``ADD`` alone."""
    op = (word >> 30) & 0x1
    s = (word >> 29) & 0x1
    sf = (word >> 31) & 0x1
    shift = (word >> 22) & 0x3
    imm12 = (word >> 10) & 0xFFF
    rn = (word >> 5) & 0x1F
    rd = word & 0x1F

    if s != 0:
        raise Unsupported("aarch64", "adds.immediate" if op == 0 else "subs.immediate")
    if sf != 1:
        raise Unsupported("aarch64", "add.immediate.w" if op == 0 else "sub.immediate.w")
    if shift == 0b00:
        imm = imm12
    elif shift == 0b01:
        imm = imm12 << 12
    else:
        kind = "add" if op == 0 else "sub"
        raise Unsupported("aarch64", f"{kind}.immediate.shift=0b{shift:02b}")
    return Decoded(rd=rd, rn=rn, imm=imm, op=OP_ADD if op == 0 else OP_SUB)


def _decode_move_wide(word: int) -> Decoded:
    """Decode the Move wide (immediate) class, 64-bit ``MOVZ``.

    ``sf opc 1 0 0 1 0 1 hw imm16 Rd`` with bits[28:23] == ``0b100101``. ``opc``
    (bits[30:29]) selects the variant: ``10`` is ``MOVZ`` (the in-scope one);
    ``00`` is ``MOVN``, ``11`` is ``MOVK``, ``01`` is reserved — all abort.
    ``hw`` (bits[22:21]) gives the shift ``hw * 16`` (LSL #0/#16/#32/#48). For
    the 64-bit form ``hw ∈ {0,1,2,3}``; ``sf = 0`` (32-bit) aborts. Register
    field 31 here is ``XZR`` (handled at execution: a write to ``Rd = 31`` is
    discarded), *not* ``SP``."""
    sf = (word >> 31) & 0x1
    opc = (word >> 29) & 0x3
    hw = (word >> 21) & 0x3
    imm16 = (word >> 5) & 0xFFFF
    rd = word & 0x1F

    if opc == 0b00:
        raise Unsupported("aarch64", "movn")
    if opc == 0b11:
        raise Unsupported("aarch64", "movk")
    if opc == 0b01:
        raise Unsupported("aarch64", f"opcode=0x{word & 0xFFFF_FFFF:08x}")  # reserved
    if sf != 1:
        raise Unsupported("aarch64", "movz.w")   # 32-bit form
    # (For sf=1 every hw in {0,1,2,3} is legal; the sf=0 hw in {2,3} case is
    # already excluded above.)
    imm = (imm16 << (hw * 16)) & MASK64
    return Decoded(rd=rd, rn=31, imm=imm, op=OP_MOVZ)


def decode_insn(word: int) -> Decoded:
    """Decode one in-scope A64 instruction (``ADD``/``SUB`` immediate, ``MOVZ``),
    or hard-abort with a typed ``Unsupported`` (BENCHMARKS.md §3).

    This is the ``0.2`` decoder, retained **byte-for-byte** as the narrower gate:
    it still rejects the ``0.3`` ops (``SUBS``/``CMP``, ``B.cond``) with the same
    typed aborts, so the cross-checked ``aarch64-sail`` route — which uses it as
    its single rejection gate and executes only ``ADD``/``SUB``/``MOVZ`` — is
    undisturbed until its sibling agent mirrors the new ops. The ``0.3`` family
    is decoded by ``decode_insn_v3``. ``decode`` (the ``ADD``-only ``0.1``
    decoder) remains above for the same reason."""
    word &= 0xFFFF_FFFF
    family = (word >> 24) & 0x1F          # bits[28:24]
    move_wide = (word >> 23) & 0x3F       # bits[28:23]

    if family == 0b10001:                 # Add/subtract (immediate)
        return _decode_add_sub_imm(word)
    if move_wide == 0b100101:             # Move wide (immediate)
        return _decode_move_wide(word)
    raise Unsupported("aarch64", f"opcode=0x{word:08x}")


def _decode_add_sub_imm_v3(word: int) -> Decoded:
    """Decode the Add/subtract (immediate) class, 64-bit ``ADD``/``SUB``/``SUBS``.

    Identical to ``_decode_add_sub_imm`` except the flag-setting form ``S = 1`` is
    now in scope: ``op = 1, S = 1`` is ``SUBS``/``CMP`` (the in-scope flag-setting
    op). ``op = 0, S = 1`` (``ADDS``) stays out of scope and aborts (we add the
    NZCV write for subtraction only this round, per the brief). ``op`` ``0`` is
    ``ADD``, ``op`` ``1`` is ``SUB`` for ``S = 0``. The ``SP``-as-field-31
    semantics, the optional ``LSL #12``, and the 32-bit (``sf = 0``) abort are
    unchanged. (For ``SUBS`` the destination field 31 is ``XZR`` = ``CMP``, the
    source field 31 is ``SP`` — handled at write-back, mirroring the encoding.)"""
    op = (word >> 30) & 0x1
    s = (word >> 29) & 0x1
    sf = (word >> 31) & 0x1
    shift = (word >> 22) & 0x3
    imm12 = (word >> 10) & 0xFFF
    rn = (word >> 5) & 0x1F
    rd = word & 0x1F

    if s == 1 and op == 0:
        raise Unsupported("aarch64", "adds.immediate")  # ADDS still out of scope
    if sf != 1:
        if s == 1:
            raise Unsupported("aarch64", "subs.immediate.w")
        raise Unsupported("aarch64", "add.immediate.w" if op == 0 else "sub.immediate.w")
    if shift == 0b00:
        imm = imm12
    elif shift == 0b01:
        imm = imm12 << 12
    else:
        kind = ("subs" if s else "sub") if op else "add"
        raise Unsupported("aarch64", f"{kind}.immediate.shift=0b{shift:02b}")
    if s == 1:                            # op == 1 here (ADDS excluded above)
        return Decoded(rd=rd, rn=rn, imm=imm, op=OP_SUBS)
    return Decoded(rd=rd, rn=rn, imm=imm, op=OP_ADD if op == 0 else OP_SUB)


def _decode_add_sub_imm_v4(word: int) -> Decoded:
    """Decode the Add/subtract (immediate) class, 64-bit
    ``ADD``/``SUB``/``SUBS``/``ADDS``.

    Identical to ``_decode_add_sub_imm_v3`` except the flag-setting **addition**
    form ``op = 0, S = 1`` (``ADDS``/``CMN``) is now in scope: it yields
    ``OP_ADDS``. ``op = 1, S = 1`` is ``SUBS``/``CMP`` (``OP_SUBS``) as before;
    ``S = 0`` is ``ADD`` (``op = 0``) or ``SUB`` (``op = 1``). The
    ``SP``-as-field-31 source semantics, the optional ``LSL #12``, and the 32-bit
    (``sf = 0``) abort are unchanged. (For ``ADDS`` the destination field 31 is
    ``XZR`` = ``CMN``, the source field 31 is ``SP`` — handled at write-back.)"""
    op = (word >> 30) & 0x1
    s = (word >> 29) & 0x1
    sf = (word >> 31) & 0x1
    shift = (word >> 22) & 0x3
    imm12 = (word >> 10) & 0xFFF
    rn = (word >> 5) & 0x1F
    rd = word & 0x1F

    if sf != 1:
        if s == 1:
            raise Unsupported("aarch64", "adds.immediate.w" if op == 0 else "subs.immediate.w")
        raise Unsupported("aarch64", "add.immediate.w" if op == 0 else "sub.immediate.w")
    if shift == 0b00:
        imm = imm12
    elif shift == 0b01:
        imm = imm12 << 12
    else:
        if s:
            kind = "adds" if op == 0 else "subs"
        else:
            kind = "add" if op == 0 else "sub"
        raise Unsupported("aarch64", f"{kind}.immediate.shift=0b{shift:02b}")
    if s == 1:
        return Decoded(rd=rd, rn=rn, imm=imm, op=OP_ADDS if op == 0 else OP_SUBS)
    return Decoded(rd=rd, rn=rn, imm=imm, op=OP_ADD if op == 0 else OP_SUB)


def _decode_uncond_branch(word: int) -> Decoded:
    """Decode the Unconditional branch (immediate) class, ``B``/``BL``.

    Encoding (A64): ``op 0 0 1 0 1 imm26`` — bits[30:26] == ``0b00101``, bit[31]
    is the **link bit** ``op`` (``0`` = ``B``, ``1`` = ``BL``). ``imm26``
    (bits[25:0]) is a signed instruction offset in units of 4 bytes:
    ``offset = SignExtend(imm26, 26) * 4`` (bytes). The branch is *always* taken
    to ``pc + offset``; ``BL`` additionally sets the link register
    ``x30 := pc + 4``."""
    link = (word >> 31) & 0x1
    imm26 = word & 0x3FF_FFFF
    if imm26 >> 25:                       # sign-extend the 26-bit displacement
        imm26 -= 1 << 26
    return Decoded(rd=31, rn=31, imm=0, op=OP_B, offset=imm26 * 4, link=bool(link))


def _decode_bcond(word: int) -> Decoded:
    """Decode ``B.cond`` (conditional branch).

    Encoding (A64): ``0101010 0 imm19 0 cond`` — bits[31:24] == ``0b01010100``,
    bit[4] == 0, ``cond`` = bits[3:0]. ``imm19`` (bits[23:5]) is a signed offset
    in units of 4 bytes: ``offset = SignExtend(imm19, 19) * 4`` (bytes). The
    branch target is ``pc + offset``. (Bit[4] == 1 with this top byte is the
    related ``BC.cond`` (FEAT_HBC) — out of scope; it aborts.)"""
    o0 = (word >> 4) & 0x1
    if o0 != 0:
        raise Unsupported("aarch64", f"opcode=0x{word & 0xFFFF_FFFF:08x}")  # BC.cond
    imm19 = (word >> 5) & 0x7FFFF
    if imm19 >> 18:                       # sign-extend the 19-bit displacement
        imm19 -= 1 << 19
    cond = word & 0xF
    return Decoded(rd=31, rn=31, imm=0, op=OP_BCOND, cond=cond, offset=imm19 * 4)


def decode_insn_v3(word: int) -> Decoded:
    """Decode one in-scope A64 instruction for interpreter ``0.3`` — the
    ``0.2`` family (``ADD``/``SUB`` immediate, ``MOVZ``) plus ``SUBS``/``CMP``
    (immediate) and ``B.cond`` — or hard-abort with a typed ``Unsupported``
    (BENCHMARKS.md §3).

    This is the single source of truth shared by ``run`` and the
    ``aarch64-btor2`` translator. The narrower ``decode`` / ``decode_insn``
    remain for the ``aarch64-sail`` rejection gate until its sibling mirrors the
    ``0.3`` ops (AGENTS.md §3, additive shared-interpreter change)."""
    word &= 0xFFFF_FFFF
    family = (word >> 24) & 0x1F          # bits[28:24]
    move_wide = (word >> 23) & 0x3F       # bits[28:23]
    bcond_top = (word >> 24) & 0xFF       # bits[31:24]

    if family == 0b10001:                 # Add/subtract (immediate)
        return _decode_add_sub_imm_v3(word)
    if move_wide == 0b100101:             # Move wide (immediate)
        return _decode_move_wide(word)
    if bcond_top == 0b01010100:           # Conditional branch (B.cond)
        return _decode_bcond(word)
    raise Unsupported("aarch64", f"opcode=0x{word:08x}")


def decode_insn_v4(word: int) -> Decoded:
    """Decode one in-scope A64 instruction for interpreter ``0.4`` — the ``0.3``
    family (``ADD``/``SUB`` immediate, ``MOVZ``, ``SUBS``/``CMP``, ``B.cond``)
    plus the unconditional branch ``B``/``BL`` and the addition flag-set
    ``ADDS``/``CMN`` (immediate) — or hard-abort with a typed ``Unsupported``
    (BENCHMARKS.md §3).

    This is the single source of truth shared by ``run`` and the
    ``aarch64-btor2`` translator. The narrower ``decode`` / ``decode_insn`` /
    ``decode_insn_v3`` remain for the ``aarch64-sail`` rejection gate until its
    sibling mirrors the ``0.4`` ops (AGENTS.md §3, additive shared-interpreter
    change).

    The Unconditional-branch (immediate) class (bits[30:26] == ``0b00101``) is
    tested *before* Move-wide: a branch's ``imm26`` fills bits[25:0], so its
    bits[28:23] are data, not the move-wide opcode — but Move-wide's bits[28:26]
    are fixed ``100`` whereas a branch's bits[28:26] live in ``imm26`` and the
    distinguishing bits[30:26] (``opc:100`` for move-wide vs ``00101`` for a
    branch) can never coincide, so the order is for clarity, not correctness."""
    word &= 0xFFFF_FFFF
    family = (word >> 24) & 0x1F          # bits[28:24]
    move_wide = (word >> 23) & 0x3F       # bits[28:23]
    bcond_top = (word >> 24) & 0xFF       # bits[31:24]
    uncond = (word >> 26) & 0x1F          # bits[30:26]

    if family == 0b10001:                 # Add/subtract (immediate)
        return _decode_add_sub_imm_v4(word)
    if uncond == 0b00101:                 # Unconditional branch (immediate): B/BL
        return _decode_uncond_branch(word)
    if move_wide == 0b100101:             # Move wide (immediate)
        return _decode_move_wide(word)
    if bcond_top == 0b01010100:           # Conditional branch (B.cond)
        return _decode_bcond(word)
    raise Unsupported("aarch64", f"opcode=0x{word:08x}")


def _decode_ldst_imm(word: int) -> Decoded:
    """Decode the Load/store register (unsigned immediate) class, 64-bit
    ``LDR``/``STR`` ``Xt, [Xn|SP, #imm]``.

    Encoding (A64): ``size 1 1 1 V 0 1 opc imm12 Rn Rt`` with bits[29:27] ==
    ``0b111``, bit[26] ``V`` == 0 (the integer, not SIMD/FP, form), and
    bits[25:24] == ``0b01`` (the *unsigned offset* addressing mode). ``size``
    (bits[31:30]) selects the access width — ``0b11`` is the 64-bit form (the only
    one in scope; ``00``/``01``/``10`` = byte/halfword/word abort). ``opc``
    (bits[23:22]): ``00`` is ``STR`` (store), ``01`` is ``LDR`` (load); ``10``
    (``LDRSW``) and ``11`` abort. ``imm12`` (bits[21:10]) is the **unsigned**
    immediate offset, scaled by the access size (``imm = imm12 * 8`` for the 64-bit
    form). ``Rn`` (bits[9:5]) is the base register — field 31 is ``SP``. ``Rt``
    (bits[4:0]) is the transfer register — field 31 is the zero register ``XZR``
    (a store of ``XZR`` writes 0; a load to ``XZR`` is discarded).

    The pre/post-index and unscaled (``LDUR``) forms share bits[29:24] but have
    bits[25:24] == ``0b00`` (not ``01``), so they are not reached here and abort at
    the dispatch in ``decode_insn_v5``."""
    size = (word >> 30) & 0x3
    opc = (word >> 22) & 0x3
    imm12 = (word >> 10) & 0xFFF
    rn = (word >> 5) & 0x1F
    rt = word & 0x1F

    if size != 0b11:
        # 32-bit (word, size=10), halfword (01) and byte (00) widths, incl.
        # LDRB/STRB/LDRH/STRH — out of scope this round.
        width = {0b00: "b", 0b01: "h", 0b10: "w"}[size]
        kind = "str" if opc == 0b00 else "ldr"
        raise Unsupported("aarch64", f"{kind}.{width}")
    if opc == 0b10:
        raise Unsupported("aarch64", "ldrsw")            # 64-bit sign-extending word load
    if opc == 0b11:
        raise Unsupported("aarch64", f"opcode=0x{word & 0xFFFF_FFFF:08x}")  # reserved
    imm = imm12 * LDST_BYTES                              # unsigned offset, scaled by 8
    return Decoded(rd=rt, rn=rn, imm=imm, op=OP_STR if opc == 0b00 else OP_LDR)


def decode_insn_v5(word: int) -> Decoded:
    """Decode one in-scope A64 instruction for interpreter ``0.5`` — the ``0.4``
    family (``ADD``/``SUB`` immediate, ``MOVZ``, ``SUBS``/``CMP``, ``B.cond``,
    ``B``/``BL``, ``ADDS``/``CMN``) plus the 64-bit unsigned-offset
    ``LDR``/``STR`` — or hard-abort with a typed ``Unsupported`` (BENCHMARKS.md §3).

    This is the single source of truth shared by ``run`` and the
    ``aarch64-btor2`` translator. The narrower ``decode`` / ``decode_insn`` /
    ``decode_insn_v3`` / ``decode_insn_v4`` remain for the ``aarch64-sail``
    rejection gate until its sibling mirrors the ``0.5`` ops (AGENTS.md §3, additive
    shared-interpreter change).

    The Load/store register (unsigned immediate) class is distinguished by
    bits[29:27] == ``0b111`` ∧ bit[26] (``V``) == 0 ∧ bits[25:24] == ``0b01``;
    it cannot collide with the Add/subtract-immediate (bits[28:24] == ``10001``),
    Move-wide (bits[28:23] == ``100101``), or branch classes, so the test order is
    for clarity, not correctness."""
    word &= 0xFFFF_FFFF
    family = (word >> 24) & 0x1F          # bits[28:24]
    move_wide = (word >> 23) & 0x3F       # bits[28:23]
    bcond_top = (word >> 24) & 0xFF       # bits[31:24]
    uncond = (word >> 26) & 0x1F          # bits[30:26]
    ldst_grp = (word >> 27) & 0x7         # bits[29:27]
    ldst_v = (word >> 26) & 0x1           # bit[26] (V: 0 = integer, 1 = SIMD/FP)
    ldst_mode = (word >> 24) & 0x3        # bits[25:24] (01 = unsigned offset)

    if family == 0b10001:                 # Add/subtract (immediate)
        return _decode_add_sub_imm_v4(word)
    if uncond == 0b00101:                 # Unconditional branch (immediate): B/BL
        return _decode_uncond_branch(word)
    if move_wide == 0b100101:             # Move wide (immediate)
        return _decode_move_wide(word)
    if bcond_top == 0b01010100:           # Conditional branch (B.cond)
        return _decode_bcond(word)
    # Load/store register (unsigned immediate): bits[29:27]==111, V==0, [25:24]==01.
    if ldst_grp == 0b111 and ldst_v == 0 and ldst_mode == 0b01:
        return _decode_ldst_imm(word)
    raise Unsupported("aarch64", f"opcode=0x{word:08x}")


class _Regs:
    """The general registers + stack pointer, addressed by an A64 register
    field where the value 31 means ``SP`` (for the Add/subtract-immediate
    encoding class)."""

    __slots__ = ("x", "sp")

    def __init__(self, x: list[int], sp: int) -> None:
        self.x = x
        self.sp = sp

    def read(self, field_no: int) -> int:
        return self.sp if field_no == 31 else self.x[field_no]

    def write(self, field_no: int, value: int) -> None:
        if field_no == 31:
            self.sp = _u64(value)
        else:
            self.x[field_no] = _u64(value)


def _state(pc: int, regs: _Regs, nzcv: int, mem: dict[int, int],
           halted: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"pc": pc, "sp": regs.sp, "nzcv": nzcv, "halted": halted}
    for r in range(NREG):
        s[f"x{r}"] = regs.x[r]
    for i in range(MEM_WINDOW):                # the fixed memory-window observable
        s[f"m{i}"] = mem.get(i, 0) & 0xFF
    return s


def _mem_load(mem: dict[int, int], addr: int) -> int:
    """Read 8 bytes **little-endian** from byte-addressed ``mem`` at ``addr`` ->
    a bv64 value (the byte at ``addr`` is least significant). Bytes never written
    read as 0 (zero-initialized memory)."""
    val = 0
    for i in range(LDST_BYTES):
        val |= (mem.get((addr + i) & MASK64, 0) & 0xFF) << (8 * i)
    return val & MASK64


def _mem_store(mem: dict[int, int], addr: int, value: int) -> None:
    """Write the 8-byte **little-endian** encoding of the bv64 ``value`` to
    byte-addressed ``mem`` at ``addr`` (the low byte at ``addr``)."""
    value &= MASK64
    for i in range(LDST_BYTES):
        mem[(addr + i) & MASK64] = (value >> (8 * i)) & 0xFF


def _subs_flags(minuend: int, imm: int) -> tuple[int, int]:
    """Compute ``(result, nzcv)`` for ``SUBS``/``CMP`` of ``minuend - imm``
    (64-bit, both operands already masked to 64 bits).

    NZCV (mirrored bit-for-bit by the ``aarch64-btor2`` translator, SPEC.md):
    ``N = result<63>``; ``Z = (result == 0)``; ``C = (minuend >=u imm)`` (no
    borrow out of the subtraction); ``V`` = signed overflow, i.e. the operands
    had different signs *and* the result's sign differs from the minuend's
    (``minuend<63> != imm<63>`` and ``result<63> != minuend<63>``)."""
    result = (minuend - imm) & MASK64
    n = (result >> 63) & 1
    z = 1 if result == 0 else 0
    c = 1 if minuend >= imm else 0        # unsigned: no borrow
    ms = (minuend >> 63) & 1
    isb = (imm >> 63) & 1
    rs = (result >> 63) & 1
    v = 1 if (ms != isb) and (rs != ms) else 0
    nzcv = (n << 3) | (z << 2) | (c << 1) | v
    return result, nzcv


def _adds_flags(augend: int, imm: int) -> tuple[int, int]:
    """Compute ``(result, nzcv)`` for ``ADDS``/``CMN`` of ``augend + imm``
    (64-bit, both operands already masked to 64 bits).

    The ``C``/``V`` definitions are the **addition** versions — distinct from
    ``SUBS``'s subtraction definitions (mirrored bit-for-bit by the
    ``aarch64-btor2`` translator, SPEC.md): ``N = result<63>``;
    ``Z = (result == 0)``; ``C`` = the unsigned carry-out of ``augend + imm``,
    i.e. the 65-bit sum overflows 64 bits (``(augend + imm) >> 64 == 1``);
    ``V`` = signed overflow, i.e. the operands had the *same* sign and the
    result's sign differs from it (``augend<63> == imm<63>`` and
    ``result<63> != augend<63>``)."""
    total = augend + imm
    result = total & MASK64
    n = (result >> 63) & 1
    z = 1 if result == 0 else 0
    c = (total >> 64) & 1                 # unsigned carry-out of the 65-bit sum
    asx = (augend >> 63) & 1
    isb = (imm >> 63) & 1
    rs = (result >> 63) & 1
    v = 1 if (asx == isb) and (rs != asx) else 0
    nzcv = (n << 3) | (z << 2) | (c << 1) | v
    return result, nzcv


def _execute(dec: Decoded, regs: _Regs, pc: int, nzcv: int,
             mem: dict[int, int]) -> tuple[int, int]:
    """Apply one decoded in-scope instruction; return ``(next_pc, next_nzcv)``.

    Mirrored bit-for-bit by the ``aarch64-btor2`` translator (one source of
    truth, SPEC.md). ``ADD``/``SUB``/``SUBS``/``ADDS`` read/write ``SP`` for field
    31 (for ``SUBS``/``ADDS`` the *destination* field 31 is ``XZR`` — the write is
    discarded, = ``CMP``/``CMN``); ``MOVZ`` treats field 31 as ``XZR``, so a write
    to ``Rd = 31`` is discarded. ``SUBS`` and ``ADDS`` write ``NZCV`` (with the
    subtraction and addition ``C``/``V`` definitions respectively); ``B.cond``,
    ``B`` and ``BL`` change the successor (away from ``pc + 4``) and ``BL`` also
    writes the link register ``x30 := pc + 4``. ``LDR``/``STR`` access ``mem`` at
    ``read(Rn) + imm`` (the base field 31 is ``SP``; the transfer field 31 is
    ``XZR`` — a load to ``XZR`` is discarded, a store of ``XZR`` writes 0). The
    register file and ``mem`` are mutated in place; the pc/flags are returned
    (functional, so the caller threads them)."""
    next_pc = _u64(pc + INSN_BYTES)
    if dec.op == OP_ADD:
        regs.write(dec.rd, regs.read(dec.rn) + dec.imm)
    elif dec.op == OP_SUB:
        regs.write(dec.rd, regs.read(dec.rn) - dec.imm)
    elif dec.op == OP_MOVZ:
        if dec.rd != 31:                  # Rd == 31 is XZR: the write is discarded
            regs.write(dec.rd, dec.imm)
    elif dec.op == OP_SUBS:
        result, nzcv = _subs_flags(_u64(regs.read(dec.rn)), _u64(dec.imm))
        if dec.rd != 31:                  # Rd == 31 is XZR (CMP): write discarded
            regs.write(dec.rd, result)
    elif dec.op == OP_ADDS:
        result, nzcv = _adds_flags(_u64(regs.read(dec.rn)), _u64(dec.imm))
        if dec.rd != 31:                  # Rd == 31 is XZR (CMN): write discarded
            regs.write(dec.rd, result)
    elif dec.op == OP_BCOND:
        if cond_holds(dec.cond, nzcv):
            next_pc = _u64(pc + dec.offset)
    elif dec.op == OP_B:                   # B/BL: always taken
        if dec.link:                      # BL writes the link register x30 := pc + 4
            regs.x[30] = next_pc
        next_pc = _u64(pc + dec.offset)
    elif dec.op == OP_LDR:                 # LDR Xt, [Xn|SP, #imm]: 64-bit LE load
        addr = _u64(regs.read(dec.rn) + dec.imm)     # Rn field 31 => SP base
        value = _mem_load(mem, addr)
        if dec.rd != 31:                  # Rt == 31 is XZR: the load is discarded
            regs.x[dec.rd] = value        # Rt never names SP (field 31 is XZR)
    elif dec.op == OP_STR:                 # STR Xt, [Xn|SP, #imm]: 64-bit LE store
        addr = _u64(regs.read(dec.rn) + dec.imm)     # Rn field 31 => SP base
        value = 0 if dec.rd == 31 else regs.x[dec.rd]  # Rt == 31 is XZR (stores 0)
        _mem_store(mem, addr, _u64(value))
    else:                                 # pragma: no cover - decoder never yields this
        raise Unsupported("aarch64", f"op={dec.op}")
    return next_pc, nzcv


def run(
    prog: A64Program,
    binding: dict[str, Any] | None = None,
    max_steps: int = 100_000,
    **_kw: Any,
) -> Trace:
    """Run ``prog`` until it halts (off the end of code, or ``max_steps``).

    ``binding`` may set the initial ``pc``, the general registers and ``sp``
    (``regs`` is ``{field: value}`` with ``31`` => ``sp``, or use the explicit
    ``sp`` key), the initial ``nzcv``, and the initial byte-addressed ``mem`` (a
    ``{byte_addr: byte}`` map). Returns the post-step trace. Pure: the run works on
    a private copy of the memory map, never mutating the caller's.
    """
    binding = binding or {}
    regs = _Regs([0] * NREG, SP_DEFAULT)
    nzcv = int(binding.get("nzcv", 0)) & 0xF
    pc = int(binding.get("pc", prog.entry))
    for field_no, value in binding.get("regs", {}).items():
        regs.write(int(field_no), int(value))
    if "sp" in binding:
        regs.sp = _u64(int(binding["sp"]))
    mem: dict[int, int] = {}
    for a, v in binding.get("mem", {}).items():
        mem[int(a) & MASK64] = int(v) & 0xFF

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (prog.code_lo <= pc < prog.code_hi):
            trace.append(_state(pc, regs, nzcv, mem, True))   # ran off the end -> halt
            break
        dec = decode_insn_v5(prog.word_at(pc))
        pc, nzcv = _execute(dec, regs, pc, nzcv, mem)    # threads pc + NZCV + mem
        steps += 1
        trace.append(_state(pc, regs, nzcv, mem, False))
    return trace
