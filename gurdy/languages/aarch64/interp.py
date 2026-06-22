"""A deterministic AArch64 (A64) interpreter — the shared AArch64 source
interpreter (languages/aarch64 brief, ARCHITECTURE.md §§5-6).

Scope (MVP, thin-first — PAIRING.md §1 "Start thin, then widen"): a **single**
in-scope construct, ``ADD (immediate)`` in its 64-bit form
(``ADD Xd|SP, Xn|SP, #imm{, LSL #0|#12}``). Every other A64 instruction
hard-aborts with a typed ``Unsupported`` (BENCHMARKS.md §3) — never silently
dropped or mis-executed — so coverage stays honest and widening is monotone.

The machine state is the 31 general registers ``x0``–``x30``, the stack pointer
``sp``, the program counter ``pc`` (a byte address; A64 instructions are 4 bytes
each), the ``NZCV`` condition flags, and a ``halted`` flag. Observables
(ARCHITECTURE.md §5): ``pc``, ``x0``–``x30``, ``sp``, ``nzcv``, ``halted`` —
recorded *after* each transition (post-step state). The run halts when ``pc``
leaves the code region (running off the end), exactly as the RISC-V / eBPF
interpreters do; there is no halt *instruction* in this slice.

A64 detail honored by ``ADD (immediate)``:

- ``sf = 1`` selects the 64-bit variant (the only one in scope; the 32-bit
  ``sf = 0`` form aborts).
- The register field value ``31`` denotes ``SP`` here (not the zero register):
  ``ADD (immediate)`` is the canonical SP-relative add. ``Xn = 31`` reads
  ``sp``; ``Xd = 31`` writes ``sp``.
- The 12-bit immediate is optionally shifted left by 12 (``shift`` field ``01``);
  ``shift`` values ``1x`` are reserved and abort.
- ``ADD`` (``S = 0``) does **not** update ``NZCV`` (only ``ADDS`` does, which is
  out of scope), so the flags are preserved across this instruction.

Pure and deterministic: identical ``(image, binding)`` -> identical trace.
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
    """A decoded ``ADD (immediate)`` (the one in-scope construct)."""

    rd: int          # destination register field (31 => SP)
    rn: int          # source register field (31 => SP)
    imm: int         # the (already shift-applied) 64-bit immediate addend


def decode(word: int) -> Decoded:
    """Decode one 32-bit A64 instruction word, or hard-abort.

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
    return Decoded(rd=rd, rn=rn, imm=imm)


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
        dec = decode(prog.word_at(pc))
        regs.write(dec.rd, regs.read(dec.rn) + dec.imm)  # ADD (immediate)
        pc = _u64(pc + INSN_BYTES)
        steps += 1
        trace.append(_state(pc, regs, nzcv, False))
    return trace
