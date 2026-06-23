"""AArch64 (A64) -> BTOR2 translator (pairs/aarch64-btor2 brief).

Emits a BTOR2 transition system modeling the AArch64 machine one instruction
per cycle — the same layered encoding as ``riscv-btor2`` re-aimed at A64's
register file, which is exactly the ISA-portability the brief exists to show.

State: ``pc`` (bv64, a *byte* address — A64 instructions are 4 bytes),
``x0``–``x30`` (bv64), ``sp`` (bv64), ``nzcv`` (bv4), ``halted`` (bv1), and —
when the program touches memory — ``mem`` (an ``Array bv64 bv8``, byte-addressed,
little-endian) with a fixed observable window ``m0``–``m{MEM_WINDOW-1}`` (bv8
each). The fixed image is lowered to a PC-keyed ITE dispatch over the
per-instruction next-state functions, mirroring ``languages/aarch64/interp.py``
rule-for-rule so the two share one source of truth and the commuting-square oracle
cross-checks them.

Scope (interpreter ``0.5``, widened under the coverage ratchet — BENCHMARKS.md
§5): the ``0.4`` family (``ADD``/``SUB`` immediate, ``MOVZ``, ``SUBS``/``CMP``,
``ADDS``/``CMN``, ``B.cond``, ``B``/``BL`` — all 64-bit) **plus** the first memory
access — the 64-bit unsigned-offset ``LDR``/``STR``:

- ``STR Xt, [Xn|SP, #imm]`` (64-bit): store the 64-bit ``Xt`` **little-endian** to
  ``mem[read(Rn) + imm]`` (``imm = imm12 * 8``, the scaled unsigned offset). The
  base field 31 is ``SP``; the transfer field 31 is ``XZR`` (stores 0).
- ``LDR Xt, [Xn|SP, #imm]`` (64-bit): load 64 bits **little-endian** from
  ``mem[read(Rn) + imm]`` into ``Xt`` (field 31 = ``XZR``, discarded). Bytes never
  written read as 0.

The ``0.4`` family is unchanged:

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

Decoding is delegated to the shared interpreter's ``decode_insn_v5`` (one source
of truth for the ``0.5`` family), so any other instruction hard-aborts there with
``Unsupported`` (BENCHMARKS.md §3) and the translator never silently mis-lowers
it. (The narrower ``decode`` / ``decode_insn`` / ``decode_insn_v3`` /
``decode_insn_v4`` stay the rejection points for the ``aarch64-sail`` route until
its sibling mirrors the ``0.5`` ops.)

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
  register state node is updated. For ``LDR``/``STR`` the *base* field 31
  (``Rn``) is ``SP`` but the *transfer* field 31 (``Rt``) is ``XZR`` (a load to
  ``XZR`` is discarded; a store of ``XZR`` writes 0) — never ``SP``.
- **Memory.** ``LDR``/``STR`` access byte-addressed memory at ``read(Rn) + imm``
  (``imm = imm12 * 8``, the unsigned offset scaled by the 8-byte access size),
  **little-endian** (AArch64 is LE — the byte at the effective address is the
  least significant). Memory is an ``Array bv64 bv8`` (zero-initialized; bytes
  never written read 0), lowered to byte ``read``/``write`` chains and carried into
  ``π`` through the fixed observable window ``m0..m{MEM_WINDOW-1}`` (bv8 states
  tracking the lowest memory bytes). RV64's ``LD``/``SD`` are the direct analogue,
  with the same LE byte order; A64 separates the 12-bit unsigned-offset scaling
  (by the access size) where RV64 uses a signed 12-bit byte offset.
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
    LDST_BYTES,
    MASK32,
    MASK64,
    MEM_WINDOW,
    NREG,
    OP_ADD,
    OP_ADDS,
    OP_B,
    OP_BCOND,
    OP_LDR,
    OP_MOVZ,
    OP_STR,
    OP_SUB,
    OP_SUBS,
    SP_DEFAULT,
    A64Program,
    decode_insn_v6,
)
from ...languages.btor2.build import Builder

BYTE = 8  # the memory element width (a byte); the array is ``Array bv64 bv8``.


def _reg_node(field_no: int, regs: dict[int, int], sp: int) -> int:
    """Resolve an A64 register field to a BTOR2 value node (31 => sp)."""
    return sp if field_no == 31 else regs[field_no]


def _xt_node(field_no: int, b: Builder, regs: dict[int, int]) -> int:
    """Resolve a load/store *transfer* field to a BTOR2 value node. Unlike the
    Add/subtract base register, the transfer field 31 is the **zero register**
    ``XZR`` (a store of ``XZR`` writes 0), never ``SP``."""
    return b.constd(64, 0) if field_no == 31 else regs[field_no]


def _mem_load_le(b: Builder, mem: int, addr: int) -> int:
    """Read 8 bytes **little-endian** from the ``Array bv64 bv8`` ``mem`` at
    ``addr`` (a bv64 node) -> a bv64 value node (the byte at ``addr`` is least
    significant). Mirrors ``interp._mem_load``."""
    res = b.read(BYTE, mem, addr)                          # byte 0 -> low (LE)
    w = BYTE
    for i in range(1, LDST_BYTES):
        a_i = b.op2("add", 64, addr, b.constd(64, i))
        byte = b.read(BYTE, mem, a_i)
        res = b.op2("concat", w + BYTE, byte, res)         # higher byte on top
        w += BYTE
    return res                                             # already exactly 64 bits


def _mem_store_le(b: Builder, mem: int, addr: int, value: int) -> int:
    """Write the 8-byte **little-endian** encoding of the bv64 ``value`` to
    ``mem[addr .. addr+7]`` (the low byte at ``addr``) -> the new array node.
    Mirrors ``interp._mem_store``."""
    cur = mem
    for i in range(LDST_BYTES):
        byte = b.slice(value, 8 * i + 7, 8 * i)            # value byte i (LE)
        a_i = addr if i == 0 else b.op2("add", 64, addr, b.constd(64, i))
        cur = b.write(64, BYTE, cur, a_i, byte)
    return cur


def _uses_memory(words: list[int]) -> bool:
    """Whether the program touches data memory (any in-scope ``LDR``/``STR``). The
    ``mem`` array + the ``m{i}`` window states are emitted only when it does
    (mirrors ``evm-btor2`` / ``ebpf-btor2``'s conditional ``mem`` array).

    An out-of-scope word here is *not* treated as a memory op (it is left for the
    main loop's ``decode_insn_v6`` to hard-abort at its natural point, preserving
    the translator's existing rejection boundary)."""
    for w in words:
        try:
            if decode_insn_v6(w).op in (OP_LDR, OP_STR):
                return True
        except Exception:
            continue
    return False


def _subs_nzcv(b: Builder, minuend: int, imm: int, result: int,
               width: int = 64) -> int:
    """Build the bv4 NZCV node for ``SUBS``/``CMP`` of ``minuend - imm`` at the
    given operand ``width`` (``64`` for the X-register form — the default, so the
    64-bit call sites are byte-for-byte unchanged; ``32`` for the W-register form).

    Mirrors ``interp._subs_flags`` / ``_subs_flags32`` bit-for-bit (one source of
    truth): the sign bit is ``width - 1`` (63 at 64-bit, 31 at 32-bit) and ``Z`` is
    over the width-bit result. ``minuend``, ``imm`` and ``result`` are all bvN nodes
    of this ``width``. ``N = result<width-1>``, ``Z = (result == 0)``,
    ``C = (minuend >=u imm)`` (no borrow), ``V`` = signed overflow (operands differ
    in sign *and* result's sign differs from the minuend's). Packed
    ``N=bit3, Z=bit2, C=bit1, V=bit0``."""
    msb = width - 1
    n = b.slice(result, msb, msb)                            # result<width-1>
    z = b.op2("eq", 1, result, b.constd(width, 0))          # result == 0
    c = b.op2("ugte", 1, minuend, imm)                       # no borrow
    m_sign = b.slice(minuend, msb, msb)
    i_sign = b.slice(imm, msb, msb)
    r_sign = b.slice(result, msb, msb)
    diff_in = b.op2("xor", 1, m_sign, i_sign)                # minuend<msb> != imm<msb>
    diff_out = b.op2("xor", 1, r_sign, m_sign)               # result<msb> != minuend<msb>
    v = b.op2("and", 1, diff_in, diff_out)
    # Pack the four bv1 flags MSB-first into a bv4: (((N::Z)::C)::V).
    nz = b.op2("concat", 2, n, z)
    nzc = b.op2("concat", 3, nz, c)
    return b.op2("concat", 4, nzc, v)


def _adds_nzcv(b: Builder, augend: int, imm: int, result: int,
               width: int = 64) -> int:
    """Build the bv4 NZCV node for ``ADDS``/``CMN`` of ``augend + imm`` at the
    given operand ``width`` (``64`` default — the 64-bit call sites are byte-for-byte
    unchanged; ``32`` for the W-register form).

    Mirrors ``interp._adds_flags`` / ``_adds_flags32`` bit-for-bit (one source of
    truth) — the **addition** ``C``/``V`` definitions, distinct from ``SUBS``'s:
    ``N = result<width-1>``, ``Z = (result == 0)``, ``C`` = unsigned carry-out of the
    ``(width+1)``-bit sum (``augend`` and ``imm`` zero-extended by one bit, added,
    bit ``width`` sliced out), ``V`` = signed overflow (operands have the *same* sign
    *and* the result's sign differs from theirs). Packed ``N=bit3, Z=bit2, C=bit1,
    V=bit0``."""
    msb = width - 1
    wide = width + 1
    n = b.slice(result, msb, msb)                            # result<width-1>
    z = b.op2("eq", 1, result, b.constd(width, 0))          # result == 0
    # C: zero-extend both operands by one bit, add, take bit `width` (the carry-out).
    a_wide = b.uext(wide, augend, 1)
    i_wide = b.uext(wide, imm, 1)
    sum_wide = b.op2("add", wide, a_wide, i_wide)
    c = b.slice(sum_wide, width, width)                      # carry-out
    a_sign = b.slice(augend, msb, msb)
    i_sign = b.slice(imm, msb, msb)
    r_sign = b.slice(result, msb, msb)
    same_in = b.op1("not", 1, b.op2("xor", 1, a_sign, i_sign))  # augend<msb> == imm<msb>
    diff_out = b.op2("xor", 1, r_sign, a_sign)               # result<msb> != augend<msb>
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
    init_mem = program.get("init_mem", {})             # {byte_addr: byte}, optional

    uses_mem = _uses_memory(image.words)

    b = Builder()
    pc = b.state(64, "pc")
    regs = {r: b.state(64, f"x{r}") for r in range(NREG)}
    sp = b.state(64, "sp")
    nzcv = b.state(4, "nzcv")
    halted = b.state(1, "halted")
    # Byte-addressed data memory: an ``Array bv64 bv8`` (little-endian), plus the
    # fixed observable window ``m0..m{MEM_WINDOW-1}`` (bv8 states mirroring the
    # array's lowest bytes). The shared BTOR2 trace exposes only BIT-VECTOR state,
    # not arrays, so the window states are how the memory observable reaches ``π``
    # (the source interpreter exposes the same ``m{i}`` bytes). Emitted only when
    # the program uses LDR/STR (mirrors evm-btor2 / ebpf-btor2).
    mem = b.state_array(64, BYTE, "mem") if uses_mem else None
    mwin = [b.state(BYTE, f"m{i}") for i in range(MEM_WINDOW)] if uses_mem else []

    # init
    b.init(pc, b.constd(64, image.entry & MASK64))
    for r in range(NREG):
        b.init(regs[r], b.constd(64, int(init_regs.get(r, 0)) & MASK64))
    b.init(sp, b.constd(64, init_sp & MASK64))
    b.init(nzcv, b.constd(4, int(program.get("init_nzcv", 0)) & 0xF))
    b.init(halted, b.zero(1))
    for i in range(MEM_WINDOW):            # window mirrors the initial memory bytes
        if uses_mem:
            b.init(mwin[i], b.constd(BYTE, int(init_mem.get(i, 0)) & 0xFF))

    not_halted = b.op1("not", 1, halted)
    next_pc = pc
    next_regs = dict(regs)
    next_sp = sp
    next_nzcv = nzcv
    next_mem = mem

    for i, word in enumerate(image.words):
        addr = image.entry + INSN_BYTES * i
        dec = decode_insn_v6(word)  # one source of truth; aborts on out-of-scope
        imm_node = b.constd(64, dec.imm & MASK64)  # imm already shift-applied

        at = b.op2("eq", 1, pc, b.constd(64, addr & MASK64))
        active = b.op2("and", 1, at, not_halted)
        # Successor: ``pc + 4`` for the ALU ops; a (conditional) target for B.cond/B.
        fall = b.constd(64, (addr + INSN_BYTES) & MASK64)

        # Per-op effect (mirrors interp._execute rule-for-rule; SPEC.md).
        if dec.op in (OP_LDR, OP_STR):
            # 64-bit unsigned-offset memory access: addr = read(Rn) + imm (the base
            # field 31 is SP). LE byte order. LDR writes Rt (field 31 = XZR =>
            # discarded); STR writes mem with Rt (field 31 = XZR => stores 0).
            assert mem is not None
            ea = b.op2("add", 64, _reg_node(dec.rn, regs, sp), imm_node)
            next_pc = b.ite(64, active, fall, next_pc)
            if dec.op == OP_LDR:
                loaded = _mem_load_le(b, mem, ea)
                if dec.rd != 31:              # Rt == 31 is XZR: the load is discarded
                    next_regs[dec.rd] = b.ite(64, active, loaded, next_regs[dec.rd])
            else:                             # OP_STR
                value = _xt_node(dec.rd, b, regs)     # Rt == 31 => XZR (stores 0)
                written = _mem_store_le(b, mem, ea, value)
                next_mem = b.ite_array(64, BYTE, active, written, next_mem)
            continue  # LDR/STR write no flags

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

        # ALU / flag-set immediate ops, 64-bit (X) or 32-bit (W, dec.width == 32).
        #   ADD/ADDS : read(Rn) + imm    SUB/SUBS : read(Rn) - imm    MOVZ : imm
        # The 32-bit (W) form computes on the low 32 bits of the source: the
        # operands are sliced to bits[31:0], the op is at width 32, and the 32-bit
        # result is **zero-extended** back to bv64 before it is written to Rd (the
        # upper 32 bits of Xd become 0) — mirroring interp._execute's 32-bit path.
        # The flags (for SUBS/ADDS) are computed on the 32-bit operands+result.
        w = dec.width
        if w == 32:
            src_node = b.slice(_reg_node(dec.rn, regs, sp), 31, 0)  # low 32 of Rn
            imm_w = b.constd(32, dec.imm & MASK32)
        else:
            src_node = _reg_node(dec.rn, regs, sp)
            imm_w = imm_node
        if dec.op in (OP_ADD, OP_ADDS):
            res_w = b.op2("add", w, src_node, imm_w)
        elif dec.op in (OP_SUB, OP_SUBS):
            res_w = b.op2("sub", w, src_node, imm_w)
        else:  # OP_MOVZ — no source register; the zeroing immediate is the result
            res_w = imm_w
        # The value written to Rd: bv64 directly for X; zero-extend the bv32 for W.
        result = res_w if w == 64 else b.uext(64, res_w, 32)

        next_pc = b.ite(64, active, fall, next_pc)
        # Destination: ADD/SUB field 31 => sp; SUBS/ADDS/MOVZ field 31 => XZR
        # (write discarded). For SUBS/ADDS the *source* field 31 is still SP.
        rd_is_xzr = dec.rd == 31 and dec.op in (OP_MOVZ, OP_SUBS, OP_ADDS)
        if dec.rd == 31 and not rd_is_xzr:        # ADD/SUB to SP (the zero-extended W value for ADD W)
            next_sp = b.ite(64, active, result, next_sp)
        elif dec.rd != 31:
            next_regs[dec.rd] = b.ite(64, active, result, next_regs[dec.rd])
        # SUBS/CMP and ADDS/CMN are the ops that write NZCV (subtraction vs
        # addition C/V definitions), at the op's width (32-bit flags for W).
        if dec.op == OP_SUBS:
            flags = _subs_nzcv(b, src_node, imm_w, res_w, width=w)
            next_nzcv = b.ite(4, active, flags, next_nzcv)
        elif dec.op == OP_ADDS:
            flags = _adds_nzcv(b, src_node, imm_w, res_w, width=w)
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
    b.next(nzcv, next_nzcv)     # only SUBS/CMP and ADDS/CMN write the flags
    b.next(halted, next_halted)
    if uses_mem:
        assert next_mem is not None
        b.next_array(mem, next_mem)
        # Each window byte tracks the post-step memory array at its fixed address,
        # so the bit-vector trace carries the memory observable into ``π``.
        for i in range(MEM_WINDOW):
            b.next(mwin[i], b.read(BYTE, next_mem, b.constd(64, i)))

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
