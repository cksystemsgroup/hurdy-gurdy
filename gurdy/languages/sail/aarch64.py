"""An *additive* AArch64 (A64) executor for the shared Sail interpreter.

This is the AArch64 arm of the Sail interpreter (``languages/sail`` brief): the
Sail-mediated route ``aarch64-sail`` → ``sail-btor2`` re-encodes A64 into BTOR2,
to be cross-checked against the direct ``aarch64-btor2`` route (PATHS.md §4-5).

It is strictly additive to the RISC-V Sail executor (``interp.run``): a "Sail
object" carrying ``{"isa": "aarch64", ...}`` dispatches here; every existing
RISC-V caller (``riscv-sail``, ``sail-btor2``) is untouched, since none sets
``isa``. The interpreter version bumps accordingly (``__init__.INTERPRETER_VERSION``).

What makes this the *Sail-derived* (and so independent) realization of A64:

- Each instruction's computational content is a **Sail ``Expr`` tree** over the
  shared QF_BV vocabulary (``expr``), evaluated by the *same* ``expr.evaluate``
  the RISC-V Sail route uses — not the hand-written Python ``+``/``-`` of
  ``languages/aarch64/interp.py`` nor the BTOR2 ITE datapath of
  ``aarch64-btor2``. So the two AArch64→BTOR2 routes are genuinely independent
  realizations that the branch-agreement check corroborates. The ``SUBS``/``CMP``
  NZCV pack and the ``B.cond`` condition predicate are likewise built as ``Expr``
  trees over the same vocabulary and evaluated, not computed in hand-written
  Python — so the flag/condition *datapath* is Sail-derived too.
- **Decoding** is delegated to the *shared* AArch64 decoder
  (``languages/aarch64.decode_insn_v6``) — one source of truth for the A64
  encoding, so the encoding cannot drift and any out-of-scope instruction
  hard-aborts there with a typed ``Unsupported`` (BENCHMARKS.md §3).

Scope (interp ``0.6`` → ``0.7``, widened under the coverage ratchet —
BENCHMARKS.md §5, mirroring the ``aarch64-btor2`` ``0.5`` → ``0.6`` widening so the
two AArch64→BTOR2 routes decide the same constructs again): the ``0.6`` family —
the simple, no-flag / no-control-flow ALU family ``ADD (immediate)``,
``SUB (immediate)`` and ``MOVZ`` **plus** the NZCV writes (``SUBS``/``CMP`` **and**
``ADDS``/``CMN`` immediate) and the conditional **and** unconditional control flow
(``B.cond``, ``B``/``BL``) and the **first memory access**, the 64-bit
unsigned-offset ``LDR``/``STR`` — **plus** the **32-bit (``W``-register) forms of
the ALU/flag-setting immediate instructions** (``ADD``/``SUB``/``MOVZ`` W and
``SUBS``/``CMP``/``ADDS``/``CMN`` W). The 32-bit form computes on the **low 32
bits** of the source(s); the 32-bit result **zero-extends** into the full 64-bit
``Xd`` (its upper 32 bits become 0 — the A64-vs-RV64 divergence: A64 zero-extends a
W write, RV64's ``*W`` ops sign-extend); the ``SUBS``/``ADDS`` W flags are computed
at **32-bit** width (``N = result<31>``, ``Z`` over the 32-bit result, ``C``/``V``
from the 32-bit add/subtract). All of this is realized as ``Expr`` trees over the
shared QF_BV vocabulary (``slice``/``zext``/width-32 ops), evaluated by the same
``evaluate`` — matching ``aarch64-btor2``'s BTOR2 datapath bit-for-bit.
State: ``pc`` (byte address; A64 instructions are 4 bytes), ``x0``–``x30``,
``sp`` (register field 31 for the Add/subtract-immediate class), the ``NZCV``
flags, a byte-addressed little-endian ``memory`` (a Python byte map, exactly the
shared AArch64 interpreter's shape — the ``Expr`` IR is QF_BV-only, so the *bytes*
live in the executor state and only the LE byte-assembly *datapath* is an
``Expr`` tree), and ``halted``. Observables (post-step, ARCHITECTURE.md §5):
``{pc, x0..x30, sp, nzcv, m0..m{MEM_WINDOW-1}, halted}`` — *exactly* the
``aarch64-btor2`` projection (the ``m{i}`` memory-window bytes are the additive
``0.6`` extension), so the branch cross-check at BTOR2 compares like with like.

Per-op semantics (mirrored bit-for-bit by ``aarch64-btor2`` / the shared
AArch64 interpreter — one source of truth):

- ``ADD``: ``read(Rn) + imm`` (field 31 = SP);
- ``SUB``: ``read(Rn) - imm`` (field 31 = SP);
- ``MOVZ``: ``imm`` (already shift-applied), zeroing the rest of ``Rd``;
  field 31 here is the zero register ``XZR`` — a write to ``Rd == 31`` is
  **discarded**, *not* routed to ``sp``. None of these touch ``NZCV``.
- ``SUBS``/``CMP``: ``result = read(Rn) - imm``, written to ``Rd`` (the *source*
  field 31 is SP; the *destination* field 31 is ``XZR`` = ``CMP``, write
  discarded), and the NZCV flags **set**: ``N = result<63>``, ``Z = result == 0``,
  ``C = (read(Rn) >=u imm)`` (no borrow), ``V`` = signed overflow.
- ``ADDS``/``CMN``: ``result = read(Rn) + imm``, written to ``Rd`` (the *source*
  field 31 is SP; the *destination* field 31 is ``XZR`` = ``CMN``, write
  discarded), and the NZCV flags **set** with the **addition** ``C``/``V``
  definitions (distinct from ``SUBS``'s): ``N = result<63>``, ``Z = result == 0``,
  ``C`` = unsigned carry-out of ``read(Rn) + imm`` (the 65-bit sum overflows 64
  bits), ``V`` = signed overflow of the add (same-sign operands, result sign
  flips).
- ``B.cond``: ``pc := ite(cond(NZCV), pc + offset, pc + 4)`` — the first op whose
  successor is *not* ``pc + 4``; reads ``NZCV``, writes neither registers nor
  flags. ``offset`` is the sign-extended ``imm19 * 4`` (in bytes). Full condition
  table EQ/NE/CS/CC/MI/PL/VS/VC/HI/LS/GE/LT/GT/LE/AL/NV.
- ``B``/``BL``: ``pc := pc + offset`` — the *unconditional* branch (always taken;
  the ``B.cond`` lowering with condition = true). ``offset`` is the sign-extended
  ``imm26 * 4`` (in bytes). ``BL`` additionally writes the link register
  ``x30 := pc + 4`` (the return address). Reads/writes no flags.
- ``LDR``/``STR`` (64-bit, unsigned offset): access byte-addressed ``memory`` at
  ``ea = read(Rn) + imm`` (``imm = imm12 * 8``, the unsigned offset scaled by the
  8-byte access size), **little-endian**. The base ``Rn`` field 31 is ``SP``; the
  transfer ``Rt`` field 31 is the zero register ``XZR`` (a store of ``XZR`` writes
  0, a load to ``XZR`` is discarded) — never ``SP``. ``STR`` writes the 8 LE bytes
  of ``read(Rt)`` to ``mem[ea .. ea+7]``; ``LDR`` assembles the 8 LE bytes from
  ``mem[ea .. ea+7]`` into ``Rt`` (bytes never written read 0). Successor ``pc+4``;
  no flag write. The *byte-assembly* (the LE ``slice``/``concat`` chain) is a Sail
  ``Expr`` tree over the byte variables, mirroring ``aarch64-btor2``'s
  ``_mem_load_le`` / ``_mem_store_le`` bit-for-bit; the bytes themselves live in
  the Python ``memory`` map (the ``Expr`` IR is QF_BV-only, no arrays — exactly as
  the RISC-V Sail executor keeps its memory a Python dict).
- **32-bit (``W``-register) forms** of ``ADD``/``SUB``/``MOVZ``/``SUBS``/``ADDS``
  (``dec.width == 32``): the op is built as an ``Expr`` tree over a width-32 source
  ``slice(a, 31, 0)`` (the low 32 bits of ``read(Rn)``) and a width-32 constant
  ``imm<31:0>``; the bv32 result is ``zext``-ed to bv64 before being written to
  ``Rd`` (so the upper 32 bits of ``Xd`` become 0 — A64 zero-extends a W write).
  For ``SUBS``/``ADDS`` W the NZCV pack is built at 32-bit width (sign bit 31,
  ``Z`` over the 32-bit result, ``C`` from the no-borrow / 33-bit carry-out and
  ``V`` from the 32-bit signed overflow). Field-31 semantics are unchanged from the
  64-bit forms (``ADD``/``SUB`` W → ``WSP``; ``SUBS``/``ADDS`` W source ``WSP`` /
  destination ``WZR``; ``MOVZ`` W → ``WZR``). The branches and the (always 64-bit)
  ``LDR``/``STR`` ignore ``width``. Mirrors ``interp._execute``'s ``w32`` path /
  ``aarch64-btor2``'s ``width``-parameterized datapath bit-for-bit.

Pure and deterministic: identical ``(program, binding)`` → identical trace.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace
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
    Decoded,
    decode_insn_v6,
)
from .expr import and_, concat, const, eq, evaluate, not_, slice_, sub, ult, var, zext

# A64 register field 31 denotes SP for the Add/subtract-immediate class
# (and the zero register XZR for the Move-wide class — handled at write-back).
_SP_FIELD = 31

# The Sail-derived datapath of each in-scope op, written once as an ``Expr`` tree
# over the shared QF_BV vocabulary. ``a`` binds to the (64-bit) Rn value; the
# (already shift-applied) immediate is a constant. ``nzcv`` binds to the packed bv4
# flags (read by ``B.cond``). For the 32-bit (``W``-register) forms the source is
# sliced to its low 32 bits *inside* the Expr (``slice(a, 31, 0)``) so the
# executor still binds the full 64-bit ``read(Rn)`` regardless of width.
_A = var("a", 64)
_NZCV = var("nzcv", 4)


def _src_imm(dec: Decoded):
    """The width-typed source operand and immediate ``Expr`` nodes for ``dec``.

    For the 64-bit forms (``dec.width == 64``, the default — byte-for-byte
    unchanged) this is the bv64 ``a`` and the bv64 ``imm``. For the 32-bit
    (``W``-register) forms (``dec.width == 32``) the source is the low 32 bits
    ``slice(a, 31, 0)`` (a bv32) and the immediate is the bv32 ``imm<31:0>`` — so
    the op is computed at width 32, mirroring ``interp._execute``'s ``w32`` masking
    and ``aarch64-btor2``'s ``slice(Rn, 31, 0)`` / ``constd(32, imm)`` datapath."""
    if dec.width == 32:
        return slice_(_A, 31, 0), const(dec.imm & MASK32, 32)
    return _A, const(dec.imm & MASK64, 64)


def _exec_expr(dec: Decoded):
    """The Sail ``Expr`` tree for the bv64 *value written to ``Rd``* of a decoded
    ALU op (one source of truth).

    ``ADD``/``ADDS``: ``a + imm``; ``SUB``/``SUBS``: ``a - imm``; ``MOVZ``: the
    constant ``imm`` (no source register — the immediate already carries the
    ``hw*16`` shift). For the 32-bit (``W``) forms the op runs at width 32 over
    ``slice(a, 31, 0)`` and the bv32 result is **zero-extended** to bv64 (the upper
    32 bits of ``Xd`` become 0), mirroring ``interp``'s mask-to-32 + direct write
    and ``aarch64-btor2``'s ``uext(64, res32, 32)``. ``B.cond`` / ``B`` / ``BL``
    produce no register result; they are handled separately."""
    src, imm = _src_imm(dec)
    if dec.op in (OP_ADD, OP_ADDS):
        res = src + imm
    elif dec.op in (OP_SUB, OP_SUBS):
        res = sub(src, imm)
    elif dec.op == OP_MOVZ:
        res = imm
    else:
        raise Unsupported("aarch64", f"op={dec.op}")  # pragma: no cover - decoder gate
    # The bv32 W result zero-extends into the 64-bit destination (A64 W writes
    # zero-extend); the 64-bit result is already bv64.
    return zext(res, 64) if dec.width == 32 else res


def _subs_nzcv_expr(dec: Decoded):
    """The Sail ``Expr`` tree (bv4) for the NZCV flags of ``SUBS``/``CMP``.

    Mirrors ``interp._subs_flags`` / ``_subs_flags32`` and
    ``aarch64-btor2._subs_nzcv`` bit-for-bit (one source of truth) at the op's
    width (the sign bit is ``width - 1`` — 63 at 64-bit, 31 at 32-bit; ``Z`` is over
    the width-bit result): with ``src`` the (width-bit) ``read(Rn)`` and ``imm`` the
    constant subtrahend, ``result = src - imm`` and ``N = result<width-1>``,
    ``Z = (result == 0)``, ``C = (src >=u imm)`` (no borrow = ``¬(src <u imm)``),
    ``V`` = signed overflow (operands differ in sign *and* the result's sign differs
    from ``src``'s). Packed MSB-first into a bv4 ``N::Z::C::V``."""
    src, imm = _src_imm(dec)
    msb = dec.width - 1
    result = sub(src, imm)
    n = slice_(result, msb, msb)                       # result<width-1>
    z = eq(result, const(0, dec.width))                # result == 0
    c = not_(ult(src, imm))                            # src >=u imm  (no borrow)
    a_sign = slice_(src, msb, msb)
    i_sign = slice_(imm, msb, msb)
    r_sign = slice_(result, msb, msb)
    diff_in = a_sign ^ i_sign                           # src<msb> != imm<msb>
    diff_out = r_sign ^ a_sign                          # result<msb> != src<msb>
    v = and_(diff_in, diff_out)
    # Pack the four bv1 flags MSB-first into a bv4: ((N::Z)::C)::V.
    return concat(concat(concat(n, z), c), v)


def _adds_nzcv_expr(dec: Decoded):
    """The Sail ``Expr`` tree (bv4) for the NZCV flags of ``ADDS``/``CMN``.

    Mirrors ``interp._adds_flags`` / ``_adds_flags32`` and
    ``aarch64-btor2._adds_nzcv`` bit-for-bit (one source of truth) — the
    **addition** ``C``/``V`` definitions, distinct from ``SUBS``'s — at the op's
    width: with ``src`` the (width-bit) ``read(Rn)`` and ``imm`` the constant
    addend, ``result = src + imm`` and ``N = result<width-1>``,
    ``Z = (result == 0)``, ``C`` = the unsigned carry-out of ``src + imm``
    (zero-extend both operands by one bit to ``width + 1``, add, take bit ``width``),
    ``V`` = signed overflow (operands have the *same* sign *and* the result's sign
    differs from theirs). Packed MSB-first into a bv4 ``N::Z::C::V``."""
    src, imm = _src_imm(dec)
    msb = dec.width - 1
    wide = dec.width + 1
    result = src + imm
    n = slice_(result, msb, msb)                       # result<width-1>
    z = eq(result, const(0, dec.width))                # result == 0
    # C: zero-extend both operands by one bit, add, take bit `width` (the carry-out).
    a_wide = zext(src, wide)
    i_wide = zext(imm, wide)
    c = slice_(a_wide + i_wide, dec.width, dec.width)  # carry-out of the (width+1)-bit sum
    a_sign = slice_(src, msb, msb)
    i_sign = slice_(imm, msb, msb)
    r_sign = slice_(result, msb, msb)
    same_in = not_(a_sign ^ i_sign)                     # src<msb> == imm<msb>
    diff_out = r_sign ^ a_sign                          # result<msb> != src<msb>
    v = and_(same_in, diff_out)
    # Pack the four bv1 flags MSB-first into a bv4: ((N::Z)::C)::V.
    return concat(concat(concat(n, z), c), v)


def _cond_expr(cond: int):
    """A Sail ``Expr`` tree (bv1) that is 1 iff A64 condition ``cond`` holds for
    the packed NZCV bv4 ``_NZCV``.

    Mirrors ``interp.cond_holds`` / ``aarch64-btor2._cond_node`` bit-for-bit:
    ``cond[3:1]`` selects the base predicate, ``cond[0]`` inverts it (except
    ``AL``/``NV`` = always true). NZCV is packed ``N=bit3, Z=bit2, C=bit1,
    V=bit0``."""
    n = slice_(_NZCV, 3, 3)
    z = slice_(_NZCV, 2, 2)
    c = slice_(_NZCV, 1, 1)
    v = slice_(_NZCV, 0, 0)
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
        node = and_(c, not_(z))
    elif base == 0b101:      # GE / LT  : N == V
        node = eq(n, v)
    elif base == 0b110:      # GT / LE  : Z == 0 and N == V
        node = and_(not_(z), eq(n, v))
    else:                    # AL / NV  : always (cond[3:1] == 111)
        node = const(1, 1)
    if (cond & 1) and base != 0b111:    # cond[0] inverts, except AL/NV
        node = not_(node)
    return node


# The Sail-derived little-endian byte-assembly datapath for the 64-bit load,
# written once as an ``Expr`` tree over the 8 byte variables ``b0..b7`` (``b0`` is
# the byte at the effective address — the least significant). This mirrors
# ``aarch64-btor2._mem_load_le`` bit-for-bit: ``concat`` the high byte on top,
# building ``(b7 :: b6 :: ... :: b1 :: b0)``. Evaluated by the same ``evaluate``,
# so the load *value* is the Sail-derived realization, not hand Python.
_LOAD_BYTES = tuple(var(f"b{i}", 8) for i in range(LDST_BYTES))


def _load_value_expr():
    res = _LOAD_BYTES[0]                                    # byte 0 -> low (LE)
    for i in range(1, LDST_BYTES):
        res = concat(_LOAD_BYTES[i], res)                  # higher byte on top
    return res                                             # exactly 64 bits


_LOAD_EXPR = _load_value_expr()

# The Sail-derived LE store byte-extraction: byte ``i`` of the 64-bit value is
# ``slice[8i+7 : 8i]`` (``slice[7:0]`` is the least significant, stored at ``ea``).
# Mirrors ``aarch64-btor2._mem_store_le`` bit-for-bit.
_STORE_VALUE = var("v", 64)
_STORE_BYTE_EXPRS = tuple(slice_(_STORE_VALUE, 8 * i + 7, 8 * i) for i in range(LDST_BYTES))


def _mem_load(mem: dict[int, int], addr: int) -> int:
    """Read 8 bytes **little-endian** from byte-addressed ``mem`` at ``addr`` -> a
    bv64 value, by evaluating the Sail-derived ``Expr`` concat tree over the byte
    map (the byte at ``addr`` is least significant; bytes never written read 0).
    Mirrors ``interp._mem_load`` / ``aarch64-btor2._mem_load_le``."""
    env = {f"b{i}": mem.get((addr + i) & MASK64, 0) & 0xFF for i in range(LDST_BYTES)}
    return evaluate(_LOAD_EXPR, env) & MASK64


def _mem_store(mem: dict[int, int], addr: int, value: int) -> None:
    """Write the 8-byte **little-endian** encoding of the bv64 ``value`` to
    byte-addressed ``mem`` at ``addr`` (low byte at ``addr``), the byte values
    extracted via the Sail-derived ``slice`` ``Expr`` trees. Mirrors
    ``interp._mem_store`` / ``aarch64-btor2._mem_store_le``."""
    env = {"v": value & MASK64}
    for i in range(LDST_BYTES):
        mem[(addr + i) & MASK64] = evaluate(_STORE_BYTE_EXPRS[i], env) & 0xFF


def _state(pc: int, x: list[int], sp: int, nzcv: int, mem: dict[int, int],
           halted: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"pc": pc, "sp": sp, "nzcv": nzcv, "halted": halted}
    for r in range(NREG):
        s[f"x{r}"] = x[r]
    for i in range(MEM_WINDOW):                # the fixed memory-window observable
        s[f"m{i}"] = mem.get(i, 0) & 0xFF
    return s


def _read(field_no: int, x: list[int], sp: int) -> int:
    return sp if field_no == _SP_FIELD else x[field_no]


def run_aarch64(program: dict[str, Any], binding: dict[str, Any] | None = None,
                max_steps: int = 100_000) -> Trace:
    """Execute an A64 "Sail object" via the Sail-derived ``Expr`` semantics.

    ``program`` is ``{"isa":"aarch64", "words":[...], "entry":int,
    "init_regs":{i:v}, "init_sp":int, "init_nzcv":int, "init_mem":{addr:byte}}``.
    ``binding`` may override ``pc`` / ``regs`` / ``sp`` / ``nzcv`` / ``mem``. The
    run halts when ``pc`` leaves the code region (running off the end), mirroring
    the RISC-V Sail executor and the shared AArch64 interpreter. Pure: it works on
    a private copy of the memory map, never mutating the caller's.
    """
    binding = binding or {}
    words = program["words"]
    entry = int(program.get("entry", 0))
    code_lo = entry
    code_hi = entry + INSN_BYTES * len(words)

    x = [0] * NREG
    init_regs = binding.get("regs", program.get("init_regs", {}))
    sp = int(program.get("init_sp", SP_DEFAULT))
    for fld, v in init_regs.items():
        fld = int(fld)
        if fld == _SP_FIELD:
            sp = int(v) & MASK64
        else:
            x[fld] = int(v) & MASK64
    if "sp" in binding:
        sp = int(binding["sp"]) & MASK64
    nzcv = int(binding.get("nzcv", program.get("init_nzcv", 0))) & 0xF
    pc = int(binding.get("pc", entry))
    # Byte-addressed, little-endian data memory: a private Python byte map seeded
    # from init_mem (zero-initialized; bytes never written read 0). The bytes live
    # here, not in an Expr (the IR is QF_BV-only); only the LE byte-assembly is an
    # Expr tree — exactly the RISC-V Sail executor's memory shape.
    mem_src = binding.get("mem", program.get("init_mem", {}))
    mem: dict[int, int] = {int(a) & MASK64: int(v) & 0xFF for a, v in mem_src.items()}

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (code_lo <= pc < code_hi):
            trace.append(_state(pc, x, sp, nzcv, mem, True))  # ran off the end -> halt
            break
        word = words[(pc - entry) // INSN_BYTES]
        # Shared widened decoder: one source of truth, aborts off-scope.
        dec = decode_insn_v6(word)

        if dec.op == OP_BCOND:
            # B.cond: a conditional pc update —
            # pc := ite(cond(NZCV), pc + offset, pc + 4). Reads the packed NZCV
            # bv4, writes neither registers nor flags. The condition is a Sail
            # Expr over the nzcv bv4, evaluated concretely (Sail-derived datapath).
            taken = evaluate(_cond_expr(dec.cond), {"nzcv": nzcv & 0xF})
            pc = ((pc + dec.offset) if taken else (pc + INSN_BYTES)) & MASK64
            steps += 1
            trace.append(_state(pc, x, sp, nzcv, mem, False))
            continue

        if dec.op == OP_B:
            # B/BL: the unconditional branch (always taken — the B.cond lowering
            # with condition = true). pc := pc + offset. Reads/writes no flags;
            # BL additionally writes the link register x30 := pc + 4 (the byte
            # address after the BL = the return address).
            if dec.link:
                x[30] = (pc + INSN_BYTES) & MASK64
            pc = (pc + dec.offset) & MASK64
            steps += 1
            trace.append(_state(pc, x, sp, nzcv, mem, False))
            continue

        if dec.op in (OP_LDR, OP_STR):
            # LDR/STR (64-bit, unsigned offset): ea = read(Rn) + imm (base field 31
            # = SP). LE byte order. The transfer field 31 (Rt) is XZR (a load is
            # discarded; a store of XZR writes 0) — never SP. The load value / store
            # bytes are the Sail-derived LE Expr datapath (mirroring aarch64-btor2 /
            # interp bit-for-bit). Successor pc + 4; no flag write.
            ea = (_read(dec.rn, x, sp) + dec.imm) & MASK64
            if dec.op == OP_LDR:
                value = _mem_load(mem, ea)
                if dec.rd != _SP_FIELD:        # Rt == 31 is XZR: the load is discarded
                    x[dec.rd] = value          # Rt never names SP (field 31 is XZR)
            else:                              # OP_STR
                value = 0 if dec.rd == _SP_FIELD else x[dec.rd]  # Rt == 31 => XZR (0)
                _mem_store(mem, ea, value & MASK64)
            pc = (pc + INSN_BYTES) & MASK64
            steps += 1
            trace.append(_state(pc, x, sp, nzcv, mem, False))
            continue

        # For MOVZ the immediate is the whole result; ``a`` is then unused. The
        # full 64-bit read(Rn) is bound regardless of width — the 32-bit (W) Expr
        # tree slices it to its low 32 bits internally (and zero-extends the bv32
        # result back to bv64), so the upper 32 bits of Xd become 0 for a W write.
        env = {"a": _read(dec.rn, x, sp) & MASK64}
        result = evaluate(_exec_expr(dec), env) & MASK64   # Sail Expr eval
        # SUBS/CMP and ADDS/CMN are the ops that write NZCV (set from the same
        # Expr datapath, mirroring aarch64-btor2 / interp._subs_flags /
        # interp._adds_flags bit-for-bit — the subtraction vs addition C/V).
        if dec.op == OP_SUBS:
            nzcv = evaluate(_subs_nzcv_expr(dec), env) & 0xF
        elif dec.op == OP_ADDS:
            nzcv = evaluate(_adds_nzcv_expr(dec), env) & 0xF
        # Write-back: for ADD/SUB field 31 is SP; for MOVZ field 31 is the zero
        # register XZR, so a write to Rd == 31 is *discarded* (not routed to sp);
        # for SUBS (CMP) / ADDS (CMN) the *destination* field 31 is XZR — write
        # discarded too, only NZCV is set.
        if dec.rd == _SP_FIELD:
            if dec.op not in (OP_MOVZ, OP_SUBS, OP_ADDS):   # ADD/SUB write SP
                sp = result
        else:
            x[dec.rd] = result
        pc = (pc + INSN_BYTES) & MASK64
        steps += 1
        trace.append(_state(pc, x, sp, nzcv, mem, False))
    return trace
