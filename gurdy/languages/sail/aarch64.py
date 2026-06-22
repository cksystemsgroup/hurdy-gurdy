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
  (``languages/aarch64.decode_insn_v3``) — one source of truth for the A64
  encoding, so the encoding cannot drift and any out-of-scope instruction
  hard-aborts there with a typed ``Unsupported`` (BENCHMARKS.md §3).

Scope (interp ``0.3`` → ``0.4``, widened under the coverage ratchet —
BENCHMARKS.md §5, mirroring the ``aarch64-btor2`` widening so the two
AArch64→BTOR2 routes decide the same constructs): the ``0.2``/``0.3`` simple,
no-flag / no-control-flow ALU family ``ADD (immediate)``, ``SUB (immediate)``
(both 64-bit) and ``MOVZ`` (64-bit) **plus** the first NZCV write
(``SUBS``/``CMP`` immediate) and the first conditional control flow (``B.cond``).
State: ``pc`` (byte address; A64 instructions are 4 bytes), ``x0``–``x30``,
``sp`` (register field 31 for the Add/subtract-immediate class), the ``NZCV``
flags, and ``halted``. Observables (post-step, ARCHITECTURE.md §5):
``{pc, x0..x30, sp, nzcv, halted}`` — *exactly* the ``aarch64-btor2`` projection,
so the branch cross-check at BTOR2 compares like with like.

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
- ``B.cond``: ``pc := ite(cond(NZCV), pc + offset, pc + 4)`` — the first op whose
  successor is *not* ``pc + 4``; reads ``NZCV``, writes neither registers nor
  flags. ``offset`` is the sign-extended ``imm19 * 4`` (in bytes). Full condition
  table EQ/NE/CS/CC/MI/PL/VS/VC/HI/LS/GE/LT/GT/LE/AL/NV.

Pure and deterministic: identical ``(program, binding)`` → identical trace.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace
from ...languages.aarch64.interp import (
    INSN_BYTES,
    MASK64,
    NREG,
    OP_ADD,
    OP_BCOND,
    OP_MOVZ,
    OP_SUB,
    OP_SUBS,
    SP_DEFAULT,
    Decoded,
    decode_insn_v3,
)
from .expr import and_, concat, const, eq, evaluate, not_, slice_, sub, ult, var

# A64 register field 31 denotes SP for the Add/subtract-immediate class
# (and the zero register XZR for the Move-wide class — handled at write-back).
_SP_FIELD = 31

# The Sail-derived datapath of each in-scope op, written once as an ``Expr`` tree
# over the shared QF_BV vocabulary. ``a`` binds to the Rn value; the (already
# shift-applied) immediate is a constant. ``nzcv`` binds to the packed bv4 flags
# (read by ``B.cond``).
_A = var("a", 64)
_NZCV = var("nzcv", 4)


def _exec_expr(dec: Decoded):
    """The Sail ``Expr`` tree for the *result* of a decoded ALU/flag op (one
    source of truth).

    ``ADD``: ``a + imm``; ``SUB``/``SUBS``: ``a - imm``; ``MOVZ``: the constant
    ``imm`` (no source register — the immediate already carries the ``hw*16``
    shift). ``B.cond`` produces no register result; it is handled separately."""
    imm = const(dec.imm & MASK64, 64)
    if dec.op == OP_ADD:
        return _A + imm
    if dec.op in (OP_SUB, OP_SUBS):
        return sub(_A, imm)
    if dec.op == OP_MOVZ:
        return imm
    raise Unsupported("aarch64", f"op={dec.op}")  # pragma: no cover - decoder gate


def _subs_nzcv_expr(dec: Decoded):
    """The Sail ``Expr`` tree (bv4) for the NZCV flags of ``SUBS``/``CMP``.

    Mirrors ``interp._subs_flags`` / ``aarch64-btor2._subs_nzcv`` bit-for-bit
    (one source of truth): with ``a = read(Rn)`` and ``imm`` the constant
    subtrahend, ``result = a - imm`` and ``N = result<63>``, ``Z = (result ==
    0)``, ``C = (a >=u imm)`` (no borrow = ``¬(a <u imm)``), ``V`` = signed
    overflow (operands differ in sign *and* the result's sign differs from
    ``a``'s). Packed MSB-first into a bv4 ``N::Z::C::V``."""
    imm = const(dec.imm & MASK64, 64)
    result = sub(_A, imm)
    n = slice_(result, 63, 63)                         # result<63>
    z = eq(result, const(0, 64))                       # result == 0
    c = not_(ult(_A, imm))                             # a >=u imm  (no borrow)
    a_sign = slice_(_A, 63, 63)
    i_sign = slice_(imm, 63, 63)
    r_sign = slice_(result, 63, 63)
    diff_in = a_sign ^ i_sign                           # a<63> != imm<63>
    diff_out = r_sign ^ a_sign                          # result<63> != a<63>
    v = and_(diff_in, diff_out)
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


def _state(pc: int, x: list[int], sp: int, nzcv: int, halted: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"pc": pc, "sp": sp, "nzcv": nzcv, "halted": halted}
    for r in range(NREG):
        s[f"x{r}"] = x[r]
    return s


def _read(field_no: int, x: list[int], sp: int) -> int:
    return sp if field_no == _SP_FIELD else x[field_no]


def run_aarch64(program: dict[str, Any], binding: dict[str, Any] | None = None,
                max_steps: int = 100_000) -> Trace:
    """Execute an A64 "Sail object" via the Sail-derived ``Expr`` semantics.

    ``program`` is ``{"isa":"aarch64", "words":[...], "entry":int,
    "init_regs":{i:v}, "init_sp":int, "init_nzcv":int}``. ``binding`` may
    override ``pc`` / ``regs`` / ``sp`` / ``nzcv``. The run halts when ``pc``
    leaves the code region (running off the end), mirroring the RISC-V Sail
    executor and the shared AArch64 interpreter.
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

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (code_lo <= pc < code_hi):
            trace.append(_state(pc, x, sp, nzcv, True))   # ran off the end -> halt
            break
        word = words[(pc - entry) // INSN_BYTES]
        # Shared widened decoder: one source of truth, aborts off-scope.
        dec = decode_insn_v3(word)

        if dec.op == OP_BCOND:
            # B.cond: the only op whose successor is not pc + 4 —
            # pc := ite(cond(NZCV), pc + offset, pc + 4). Reads the packed NZCV
            # bv4, writes neither registers nor flags. The condition is a Sail
            # Expr over the nzcv bv4, evaluated concretely (Sail-derived datapath).
            taken = evaluate(_cond_expr(dec.cond), {"nzcv": nzcv & 0xF})
            pc = ((pc + dec.offset) if taken else (pc + INSN_BYTES)) & MASK64
            steps += 1
            trace.append(_state(pc, x, sp, nzcv, False))
            continue

        # For MOVZ the immediate is the whole result; ``a`` is then unused.
        env = {"a": _read(dec.rn, x, sp) & MASK64}
        result = evaluate(_exec_expr(dec), env) & MASK64   # Sail Expr eval
        # SUBS/CMP is the only op that writes NZCV (set from the same Expr
        # datapath, mirroring aarch64-btor2 / interp._subs_flags bit-for-bit).
        if dec.op == OP_SUBS:
            nzcv = evaluate(_subs_nzcv_expr(dec), env) & 0xF
        # Write-back: for ADD/SUB field 31 is SP; for MOVZ field 31 is the zero
        # register XZR, so a write to Rd == 31 is *discarded* (not routed to sp);
        # for SUBS the *destination* field 31 is XZR (CMP) — write discarded too,
        # only NZCV is set.
        if dec.rd == _SP_FIELD:
            if dec.op not in (OP_MOVZ, OP_SUBS):       # ADD/SUB write SP
                sp = result
        else:
            x[dec.rd] = result
        pc = (pc + INSN_BYTES) & MASK64
        steps += 1
        trace.append(_state(pc, x, sp, nzcv, False))
    return trace
