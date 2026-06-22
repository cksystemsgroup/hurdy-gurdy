"""A deterministic AArch64 (A64) interpreter — the shared AArch64 source
interpreter (languages/aarch64 brief, ARCHITECTURE.md §§5-6).

Scope (interpreter version ``0.2``, widened from the thin ``0.1`` ``ADD``-only
slice under the coverage ratchet — BENCHMARKS.md §5): a small family of simple,
pure-register ALU writes, each with a single ``pc + 4`` successor and **no flag
write / no control flow**:

- ``ADD (immediate)`` 64-bit — ``ADD Xd|SP, Xn|SP, #imm{, LSL #0|#12}`` (the
  ``0.1`` construct, byte-for-byte unchanged);
- ``SUB (immediate)`` 64-bit — ``SUB Xd|SP, Xn|SP, #imm{, LSL #0|#12}`` (same
  Add/subtract-immediate encoding class as ``ADD``, ``op = 1``);
- ``MOVZ`` 64-bit — ``MOVZ Xd, #imm16{, LSL #0|#16|#32|#48}`` (move wide, zeroing
  the rest of the register).

Every other A64 instruction hard-aborts with a typed ``Unsupported``
(BENCHMARKS.md §3) — never silently dropped or mis-executed — so coverage stays
honest and widening is monotone.

The machine state is the 31 general registers ``x0``–``x30``, the stack pointer
``sp``, the program counter ``pc`` (a byte address; A64 instructions are 4 bytes
each), the ``NZCV`` condition flags, and a ``halted`` flag. Observables
(ARCHITECTURE.md §5): ``pc``, ``x0``–``x30``, ``sp``, ``nzcv``, ``halted`` —
recorded *after* each transition (post-step state). The run halts when ``pc``
leaves the code region (running off the end), exactly as the RISC-V / eBPF
interpreters do; there is no halt *instruction* in this slice.

A64 details honored:

- ``sf = 1`` selects the 64-bit variant (the only one in scope; the 32-bit
  ``sf = 0`` forms abort).
- **Register field 31 is encoding-class-dependent.** For ``ADD``/``SUB``
  (immediate) the value ``31`` denotes ``SP`` (these are the canonical
  SP-relative add/subtract; ``Rn = 31`` reads ``sp``, ``Rd = 31`` writes ``sp``).
  For ``MOVZ`` (move wide) the value ``31`` denotes the **zero register** ``XZR``
  — a write to ``Rd = 31`` is discarded, *not* a write to ``sp``.
- ``ADD``/``SUB`` take a 12-bit immediate optionally shifted left by 12
  (``shift`` field ``01``); ``shift`` values ``1x`` are reserved and abort.
- ``MOVZ`` takes a 16-bit immediate optionally shifted left by ``hw * 16`` for
  ``hw ∈ {0,1,2,3}`` (LSL #0/#16/#32/#48); it zeroes every other bit of ``Rd``.
- ``ADD``/``SUB`` (``S = 0``) do **not** update ``NZCV`` (only ``ADDS``/``SUBS``
  do, which are out of scope); ``MOVZ`` never writes flags either. So the flags
  are preserved across every in-scope instruction.

Pure and deterministic: identical ``(image, binding)`` -> identical trace.

Backwards compatibility (AGENTS.md §3, shared interpreter): the original
``decode`` is retained **byte-for-byte** as the ``ADD``-immediate-only decoder
(it still rejects ``SUB``/``MOVZ`` with the same typed aborts), so the
cross-checked ``aarch64-sail`` route — which uses ``decode`` as its single
rejection gate and executes only ``ADD`` — is unchanged until its sibling agent
mirrors the new ops. The widened family is decoded by the new ``decode_insn``,
used by ``run`` and by the ``aarch64-btor2`` translator (one source of truth).
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

# In-scope operation kinds (the decoder tags each decoded instruction with one).
OP_ADD = "add"     # ADD (immediate): result = read(Rn) + imm        (Rn/Rd 31 => SP)
OP_SUB = "sub"     # SUB (immediate): result = read(Rn) - imm        (Rn/Rd 31 => SP)
OP_MOVZ = "movz"   # MOVZ: result = imm (zeroing the rest)           (Rd 31 => XZR, discarded)


def _u64(v: int) -> int:
    return v & MASK64


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

    ``op`` is the operation kind (``OP_ADD`` / ``OP_SUB`` / ``OP_MOVZ``); it
    defaults to ``OP_ADD`` so the original ``Decoded(rd=, rn=, imm=)``
    construction (the ``ADD``-immediate-only ``decode``) is unchanged. ``rn`` is
    ignored for ``MOVZ`` (which has no source register; it is set to 31, the
    encoding's reserved value)."""

    rd: int                  # destination register field
    rn: int                  # source register field (unused for MOVZ)
    imm: int                 # the (already shift-applied) immediate
    op: str = OP_ADD         # OP_ADD / OP_SUB / OP_MOVZ


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

    This is the widened (interpreter ``0.2``) decoder; it is the single source of
    truth shared by ``run`` and the ``aarch64-btor2`` translator. ``decode``
    (above) remains the ``ADD``-only decoder for backwards compatibility."""
    word &= 0xFFFF_FFFF
    family = (word >> 24) & 0x1F          # bits[28:24]
    move_wide = (word >> 23) & 0x3F       # bits[28:23]

    if family == 0b10001:                 # Add/subtract (immediate)
        return _decode_add_sub_imm(word)
    if move_wide == 0b100101:             # Move wide (immediate)
        return _decode_move_wide(word)
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


def _state(pc: int, regs: _Regs, nzcv: int, halted: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"pc": pc, "sp": regs.sp, "nzcv": nzcv, "halted": halted}
    for r in range(NREG):
        s[f"x{r}"] = regs.x[r]
    return s


def _execute(dec: Decoded, regs: _Regs) -> None:
    """Apply one decoded in-scope instruction to the register file.

    Mirrored bit-for-bit by the ``aarch64-btor2`` translator (one source of
    truth, SPEC.md): ``ADD``/``SUB`` read/write ``SP`` for field 31; ``MOVZ``
    treats field 31 as the zero register, so a write to ``Rd = 31`` is discarded.
    None of these touch ``NZCV``."""
    if dec.op == OP_ADD:
        regs.write(dec.rd, regs.read(dec.rn) + dec.imm)
    elif dec.op == OP_SUB:
        regs.write(dec.rd, regs.read(dec.rn) - dec.imm)
    elif dec.op == OP_MOVZ:
        if dec.rd != 31:                  # Rd == 31 is XZR: the write is discarded
            regs.write(dec.rd, dec.imm)
    else:                                 # pragma: no cover - decoder never yields this
        raise Unsupported("aarch64", f"op={dec.op}")


def run(
    prog: A64Program,
    binding: dict[str, Any] | None = None,
    max_steps: int = 100_000,
    **_kw: Any,
) -> Trace:
    """Run ``prog`` until it halts (off the end of code, or ``max_steps``).

    ``binding`` may set the initial ``pc``, the general registers and ``sp``
    (``regs`` is ``{field: value}`` with ``31`` => ``sp``, or use the explicit
    ``sp`` key), and the initial ``nzcv``. Returns the post-step trace.
    """
    binding = binding or {}
    regs = _Regs([0] * NREG, SP_DEFAULT)
    nzcv = int(binding.get("nzcv", 0)) & 0xF
    pc = int(binding.get("pc", prog.entry))
    for field_no, value in binding.get("regs", {}).items():
        regs.write(int(field_no), int(value))
    if "sp" in binding:
        regs.sp = _u64(int(binding["sp"]))

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (prog.code_lo <= pc < prog.code_hi):
            trace.append(_state(pc, regs, nzcv, True))   # ran off the end -> halt
            break
        dec = decode_insn(prog.word_at(pc))
        _execute(dec, regs)
        pc = _u64(pc + INSN_BYTES)
        steps += 1
        trace.append(_state(pc, regs, nzcv, False))
    return trace
