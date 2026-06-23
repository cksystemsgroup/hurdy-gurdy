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

Scope (interpreter ``0.4``, widened under the coverage ratchet — BENCHMARKS.md
§5): the ``0.3`` family (``ADD``/``SUB`` immediate, ``MOVZ``, ``SUBS``/``CMP``
immediate, ``B.cond`` — all 64-bit) **plus** the unconditional branch and the
addition flag write:

- ``SUBS (immediate)`` / ``CMP`` (64-bit): ``result = Rn - imm``, written to
  ``Rd`` (XZR for ``CMP``), and the NZCV flags set with the *subtraction*
  ``C``/``V`` definitions.
- ``ADDS (immediate)`` / ``CMN`` (64-bit): ``result = Rn + imm``, written to
  ``Rd`` (XZR for ``CMN``), and the NZCV flags set with the *addition* ``C``/``V``
  definitions — ``C`` = unsigned carry-out of the 65-bit sum, ``V`` = signed
  overflow of the add (distinct from ``SUBS``'s).
- ``B.cond``: a conditional pc update ``pc := ite(cond(NZCV), pc + offset,
  pc + 4)``.
- ``B`` / ``BL``: an *unconditional* pc update ``pc := a + offset`` (the ``B.cond``
  lowering with condition = true). ``BL`` additionally writes the link register
  ``x30 := a + 4``.

Decoding is delegated to the shared interpreter's ``decode_insn_v4`` (one source
of truth for the ``0.4`` family), so any other instruction hard-aborts there with
``Unsupported`` (BENCHMARKS.md §3) and the translator never silently mis-lowers
it. (The narrower ``decode`` / ``decode_insn`` / ``decode_insn_v3`` stay the
rejection points for the ``aarch64-sail`` route until its sibling mirrors the
``0.4`` ops.)

A64-vs-RV64 divergence notes (the brief asks every portability assumption to
be auditable):

- **PC is a byte address.** Dispatch keys on ``entry + 4*i``; the fall-through is
  ``pc + 4`` and a taken ``B.cond``/``B``/``BL`` is ``a + offset`` (RV64 is
  identical at 4 bytes; the RV64C compressed 2-byte case has no A64 analogue
  here). ``BL`` additionally writes ``x30 := a + 4`` (the return address), the
  analogue of RV64's ``JAL rd``.
- **Register field 31 is encoding-class-dependent.** For
  ``ADD``/``SUB``/``SUBS``/``ADDS`` (immediate) ``Rn == 31`` reads the stack
  pointer (the RV64 ``x0`` is a hardwired zero — A64 has no zero register in
  *this* class). The *destination* field 31 is ``SP`` for ``ADD``/``SUB`` but the
  zero register ``XZR`` for ``SUBS`` (``SUBS XZR, …`` = ``CMP``), ``ADDS``
  (``ADDS XZR, …`` = ``CMN``), and ``MOVZ`` (move-wide) — in every XZR case no
  register state node is updated.
- **NZCV.** ``ADD``/``SUB``/``MOVZ`` and ``B``/``BL`` leave ``NZCV`` unchanged;
  ``SUBS``/``CMP`` writes it with the *subtraction* definitions
  (``C = Rn >=u imm``, ``V`` = signed-overflow of ``Rn - imm``) and ``ADDS``/
  ``CMN`` with the *addition* definitions (``C`` = unsigned carry-out of the
  65-bit ``Rn + imm`` sum, ``V`` = signed-overflow of ``Rn + imm``); both share
  ``N = result<63>`` and ``Z = result == 0``. ``B.cond`` reads ``NZCV`` and
  writes neither registers nor flags — only ``pc``. NZCV is packed
  ``N=bit3, Z=bit2, C=bit1, V=bit0`` (MSB-first), matching the interpreter.

Deterministic in ``(image, init binding)``.
"""

from __future__ import annotations

from typing import Any

from ...languages.aarch64.interp import (
    INSN_BYTES,
    MASK64,
    NREG,
    OP_ADD,
    OP_ADDS,
    OP_B,
    OP_BCOND,
    OP_MOVZ,
    OP_SUB,
    OP_SUBS,
    SP_DEFAULT,
    A64Program,
    decode_insn_v4,
)
from ...languages.btor2.build import Builder


def _reg_node(field_no: int, regs: dict[int, int], sp: int) -> int:
    """Resolve an A64 register field to a BTOR2 value node (31 => sp)."""
    return sp if field_no == 31 else regs[field_no]


def _subs_nzcv(b: Builder, minuend: int, imm: int, result: int) -> int:
    """Build the bv4 NZCV node for ``SUBS``/``CMP`` of ``minuend - imm``.

    Mirrors ``interp._subs_flags`` bit-for-bit (one source of truth):
    ``N = result<63>``, ``Z = (result == 0)``, ``C = (minuend >=u imm)``,
    ``V`` = signed overflow (operands differ in sign *and* result's sign differs
    from the minuend's). Packed ``N=bit3, Z=bit2, C=bit1, V=bit0``."""
    n = b.slice(result, 63, 63)                              # result<63>
    z = b.op2("eq", 1, result, b.constd(64, 0))             # result == 0
    c = b.op2("ugte", 1, minuend, imm)                       # no borrow
    m_sign = b.slice(minuend, 63, 63)
    i_sign = b.slice(imm, 63, 63)
    r_sign = b.slice(result, 63, 63)
    diff_in = b.op2("xor", 1, m_sign, i_sign)                # minuend<63> != imm<63>
    diff_out = b.op2("xor", 1, r_sign, m_sign)               # result<63> != minuend<63>
    v = b.op2("and", 1, diff_in, diff_out)
    # Pack the four bv1 flags MSB-first into a bv4: (((N::Z)::C)::V).
    nz = b.op2("concat", 2, n, z)
    nzc = b.op2("concat", 3, nz, c)
    return b.op2("concat", 4, nzc, v)


def _adds_nzcv(b: Builder, augend: int, imm: int, result: int) -> int:
    """Build the bv4 NZCV node for ``ADDS``/``CMN`` of ``augend + imm``.

    Mirrors ``interp._adds_flags`` bit-for-bit (one source of truth) — the
    **addition** ``C``/``V`` definitions, distinct from ``SUBS``'s:
    ``N = result<63>``, ``Z = (result == 0)``, ``C`` = unsigned carry-out of the
    65-bit sum (``augend`` and ``imm`` zero-extended to 65 bits, added, bit 64
    sliced out), ``V`` = signed overflow (operands have the *same* sign *and* the
    result's sign differs from theirs). Packed ``N=bit3, Z=bit2, C=bit1,
    V=bit0``."""
    n = b.slice(result, 63, 63)                              # result<63>
    z = b.op2("eq", 1, result, b.constd(64, 0))             # result == 0
    # C: zero-extend both operands to 65 bits, add, take bit 64 (the carry-out).
    a65 = b.uext(65, augend, 1)
    i65 = b.uext(65, imm, 1)
    sum65 = b.op2("add", 65, a65, i65)
    c = b.slice(sum65, 64, 64)                               # carry-out
    a_sign = b.slice(augend, 63, 63)
    i_sign = b.slice(imm, 63, 63)
    r_sign = b.slice(result, 63, 63)
    same_in = b.op1("not", 1, b.op2("xor", 1, a_sign, i_sign))  # augend<63> == imm<63>
    diff_out = b.op2("xor", 1, r_sign, a_sign)               # result<63> != augend<63>
    v = b.op2("and", 1, same_in, diff_out)
    # Pack the four bv1 flags MSB-first into a bv4: (((N::Z)::C)::V).
    nz = b.op2("concat", 2, n, z)
    nzc = b.op2("concat", 3, nz, c)
    return b.op2("concat", 4, nzc, v)


def _cond_node(b: Builder, cond: int, nzcv: int) -> int:
    """Build a bv1 node that is 1 iff A64 condition ``cond`` holds for ``nzcv``.

    Mirrors ``interp.cond_holds`` bit-for-bit: ``cond[3:1]`` selects the base
    condition, ``cond[0]`` inverts it (except ``AL``/``NV`` = always true). NZCV
    is the packed bv4 ``N=bit3, Z=bit2, C=bit1, V=bit0``."""
    n = b.slice(nzcv, 3, 3)
    z = b.slice(nzcv, 2, 2)
    c = b.slice(nzcv, 1, 1)
    v = b.slice(nzcv, 0, 0)
    one = b.one(1)
    base = cond >> 1
    if base == 0b000:        # EQ / NE  : Z == 1
        node = z
    elif base == 0b001:      # CS / CC  : C == 1
        node = c
    elif base == 0b010:      # MI / PL  : N == 1
        node = n
    elif base == 0b011:      # VS / VC  : V == 1
        node = v
    elif base == 0b100:      # HI / LS  : C == 1 and Z == 0
        node = b.op2("and", 1, c, b.op1("not", 1, z))
    elif base == 0b101:      # GE / LT  : N == V
        node = b.op2("eq", 1, n, v)
    elif base == 0b110:      # GT / LE  : Z == 0 and N == V
        node = b.op2("and", 1, b.op1("not", 1, z), b.op2("eq", 1, n, v))
    else:                    # AL / NV  : always
        node = one
    if (cond & 1) and base != 0b111:    # cond[0] inverts, except AL/NV
        node = b.op1("not", 1, node)
    return node


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
    next_nzcv = nzcv

    for i, word in enumerate(image.words):
        addr = image.entry + INSN_BYTES * i
        dec = decode_insn_v4(word)  # one source of truth; aborts on out-of-scope
        imm_node = b.constd(64, dec.imm & MASK64)  # imm already shift-applied

        at = b.op2("eq", 1, pc, b.constd(64, addr & MASK64))
        active = b.op2("and", 1, at, not_halted)
        # Successor: ``pc + 4`` for the ALU ops; a (conditional) target for B.cond/B.
        fall = b.constd(64, (addr + INSN_BYTES) & MASK64)

        # Per-op effect (mirrors interp._execute rule-for-rule; SPEC.md).
        if dec.op == OP_BCOND:
            # First conditional pc update: pc := ite(cond(NZCV), a+offset, a+4).
            taken = b.constd(64, (addr + dec.offset) & MASK64)
            cond_node = _cond_node(b, dec.cond, nzcv)
            insn_next_pc = b.ite(64, cond_node, taken, fall)
            next_pc = b.ite(64, active, insn_next_pc, next_pc)
            continue  # B.cond writes neither registers nor flags

        if dec.op == OP_B:
            # Unconditional branch: pc := a + offset (always taken — the B.cond
            # lowering with condition = true). BL also writes x30 := a + 4.
            taken = b.constd(64, (addr + dec.offset) & MASK64)
            next_pc = b.ite(64, active, taken, next_pc)
            if dec.link:                          # BL: link register x30 := pc + 4
                next_regs[30] = b.ite(64, active, fall, next_regs[30])
            continue  # B/BL write no flags (and B writes no registers)

        #   ADD/ADDS : read(Rn) + imm    SUB/SUBS : read(Rn) - imm    MOVZ : imm
        if dec.op in (OP_ADD, OP_ADDS):
            result = b.op2("add", 64, _reg_node(dec.rn, regs, sp), imm_node)
        elif dec.op in (OP_SUB, OP_SUBS):
            result = b.op2("sub", 64, _reg_node(dec.rn, regs, sp), imm_node)
        else:  # OP_MOVZ — no source register; the zeroing immediate is the result
            result = imm_node

        next_pc = b.ite(64, active, fall, next_pc)
        # Destination: ADD/SUB field 31 => sp; SUBS/ADDS/MOVZ field 31 => XZR
        # (write discarded). For SUBS/ADDS the *source* field 31 is still SP.
        rd_is_xzr = dec.rd == 31 and dec.op in (OP_MOVZ, OP_SUBS, OP_ADDS)
        if dec.rd == 31 and not rd_is_xzr:        # ADD/SUB to SP
            next_sp = b.ite(64, active, result, next_sp)
        elif dec.rd != 31:
            next_regs[dec.rd] = b.ite(64, active, result, next_regs[dec.rd])
        # SUBS/CMP and ADDS/CMN are the ops that write NZCV (subtraction vs
        # addition C/V definitions).
        if dec.op == OP_SUBS:
            flags = _subs_nzcv(b, _reg_node(dec.rn, regs, sp), imm_node, result)
            next_nzcv = b.ite(4, active, flags, next_nzcv)
        elif dec.op == OP_ADDS:
            flags = _adds_nzcv(b, _reg_node(dec.rn, regs, sp), imm_node, result)
            next_nzcv = b.ite(4, active, flags, next_nzcv)

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
    b.next(nzcv, next_nzcv)     # only SUBS/CMP writes the flags
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
