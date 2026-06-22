"""AArch64 (A64) -> BTOR2 translator (pairs/aarch64-btor2 brief).

Emits a BTOR2 transition system modeling the AArch64 machine one instruction
per cycle — the same layered encoding as ``riscv-btor2`` re-aimed at A64's
register file, which is exactly the ISA-portability the brief exists to show.

State: ``pc`` (bv64, a *byte* address — A64 instructions are 4 bytes),
``x0``–``x30`` (bv64), ``sp`` (bv64), ``nzcv`` (bv4), ``halted`` (bv1). The
fixed image is lowered to a PC-keyed ITE dispatch over the per-instruction
next-state functions, mirroring ``languages/aarch64/interp.py`` rule-for-rule
so the two share one source of truth and the commuting-square oracle
cross-checks them.

Scope (interpreter ``0.2``, widened under the coverage ratchet — BENCHMARKS.md
§5): a small family of simple, no-flag/no-control-flow ALU writes —
``ADD (immediate)``, ``SUB (immediate)`` (both 64-bit), and ``MOVZ`` (64-bit).
Decoding is delegated to the shared interpreter's ``decode_insn`` (one source of
truth), so any other instruction hard-aborts there with ``Unsupported``
(BENCHMARKS.md §3) and the translator never silently mis-lowers it.

A64-vs-RV64 divergence notes (the brief asks every portability assumption to
be auditable):

- **PC is a byte address.** Dispatch keys on ``entry + 4*i`` and the fall-through
  is ``pc + 4`` (RV64 is identical at 4 bytes; the RV64C compressed 2-byte case
  has no A64 analogue here).
- **Register field 31 is encoding-class-dependent.** For ``ADD``/``SUB``
  (immediate) ``Rn``/``Rd`` ``== 31`` denote the stack pointer (the RV64 ``x0``
  is a hardwired zero — A64 has no zero register in *this* class), so the
  lowering reads/writes the ``sp`` state node. For ``MOVZ`` (move-wide) field 31
  is instead the zero register ``XZR``: a write to ``Rd == 31`` is **discarded**
  (no state node is updated), *not* a write to ``sp``.
- **``ADD``/``SUB``/``MOVZ`` leave ``NZCV`` unchanged.** Only the flag-setting
  ``ADDS``/``SUBS`` forms (out of scope) write the flags, so ``nzcv`` is threaded
  through untouched — its presence in the state keeps ``π`` compatible with
  ``aarch64-sail`` (brief).

Deterministic in ``(image, init binding)``.
"""

from __future__ import annotations

from typing import Any

from ...languages.aarch64.interp import (
    INSN_BYTES,
    MASK64,
    NREG,
    OP_ADD,
    OP_MOVZ,
    OP_SUB,
    SP_DEFAULT,
    A64Program,
    decode_insn,
)
from ...languages.btor2.build import Builder


def _reg_node(field_no: int, regs: dict[int, int], sp: int) -> int:
    """Resolve an A64 register field to a BTOR2 value node (31 => sp)."""
    return sp if field_no == 31 else regs[field_no]


def translate(program: dict[str, Any]) -> bytes:
    image: A64Program = program["image"]
    init_regs = program.get("init_regs", {})
    init_sp = int(program.get("init_sp", SP_DEFAULT))  # match interp's SP default

    b = Builder()
    pc = b.state(64, "pc")
    regs = {r: b.state(64, f"x{r}") for r in range(NREG)}
    sp = b.state(64, "sp")
    nzcv = b.state(4, "nzcv")
    halted = b.state(1, "halted")

    # init
    b.init(pc, b.constd(64, image.entry & MASK64))
    for r in range(NREG):
        b.init(regs[r], b.constd(64, int(init_regs.get(r, 0)) & MASK64))
    b.init(sp, b.constd(64, init_sp & MASK64))
    b.init(nzcv, b.constd(4, int(program.get("init_nzcv", 0)) & 0xF))
    b.init(halted, b.zero(1))

    not_halted = b.op1("not", 1, halted)
    next_pc = pc
    next_regs = dict(regs)
    next_sp = sp

    for i, word in enumerate(image.words):
        addr = image.entry + INSN_BYTES * i
        dec = decode_insn(word)  # one source of truth; aborts on out-of-scope words
        imm_node = b.constd(64, dec.imm & MASK64)  # imm already shift-applied
        # Per-op result (mirrors interp._execute rule-for-rule; SPEC.md):
        #   ADD : read(Rn) + imm        SUB : read(Rn) - imm        MOVZ : imm
        if dec.op == OP_ADD:
            result = b.op2("add", 64, _reg_node(dec.rn, regs, sp), imm_node)
        elif dec.op == OP_SUB:
            result = b.op2("sub", 64, _reg_node(dec.rn, regs, sp), imm_node)
        else:  # OP_MOVZ — no source register; the zeroing immediate is the result
            result = imm_node
        fall = b.constd(64, (addr + INSN_BYTES) & MASK64)

        at = b.op2("eq", 1, pc, b.constd(64, addr & MASK64))
        active = b.op2("and", 1, at, not_halted)
        next_pc = b.ite(64, active, fall, next_pc)
        # Destination: ADD/SUB field 31 => sp; MOVZ field 31 => XZR (discarded).
        if dec.rd == 31 and dec.op != OP_MOVZ:
            next_sp = b.ite(64, active, result, next_sp)
        elif dec.rd != 31:
            next_regs[dec.rd] = b.ite(64, active, result, next_regs[dec.rd])

    # When pc leaves the code region the machine halts (mirrors the interp).
    lo = b.constd(64, image.code_lo & MASK64)
    hi = b.constd(64, image.code_hi & MASK64)
    in_code = b.op2("and", 1, b.op2("ugte", 1, pc, lo), b.op2("ult", 1, pc, hi))
    off_end = b.op2("and", 1, b.op1("not", 1, in_code), not_halted)
    next_halted = b.ite(1, off_end, b.one(1), halted)

    b.next(pc, next_pc)
    for r in range(NREG):
        b.next(regs[r], next_regs[r])
    b.next(sp, next_sp)
    b.next(nzcv, nzcv)          # ADD/SUB/MOVZ do not touch the flags
    b.next(halted, next_halted)

    # Optional reachability property -> a `bad` signal, so a downstream
    # reasoning bridge (btor2-smtlib) can decide the question. Mirrors the
    # riscv-btor2 / ebpf-btor2 shape: {"reg_eq": [field, value]} with field 31
    # meaning sp.
    prop = program.get("property")
    if prop and "reg_eq" in prop:
        field_no, val = prop["reg_eq"]
        node = sp if int(field_no) == 31 else regs[int(field_no)]
        b.bad(b.op2("eq", 1, node, b.constd(64, int(val) & MASK64)))

    return b.to_text().encode("utf-8")
