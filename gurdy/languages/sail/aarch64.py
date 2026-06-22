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
  realizations that the branch-agreement check corroborates.
- **Decoding** is delegated to the *shared* AArch64 decoder
  (``languages/aarch64.decode_insn``) — one source of truth for the A64
  encoding, so the encoding cannot drift and any out-of-scope instruction
  hard-aborts there with a typed ``Unsupported`` (BENCHMARKS.md §3).

Scope (interp ``0.2`` → ``0.3``, widened under the coverage ratchet —
BENCHMARKS.md §5, mirroring the ``aarch64-btor2`` widening so the two
AArch64→BTOR2 routes decide the same constructs): the simple, no-flag /
no-control-flow ALU family ``ADD (immediate)``, ``SUB (immediate)`` (both
64-bit) and ``MOVZ`` (64-bit). State: ``pc`` (byte address; A64 instructions are
4 bytes), ``x0``–``x30``, ``sp`` (register field 31 for the Add/subtract-immediate
class), the ``NZCV`` flags, and ``halted``. Observables (post-step,
ARCHITECTURE.md §5): ``{pc, x0..x30, sp, nzcv, halted}`` — *exactly* the
``aarch64-btor2`` projection, so the branch cross-check at BTOR2 compares like
with like.

Per-op semantics (mirrored bit-for-bit by ``aarch64-btor2`` / the shared
AArch64 interpreter — one source of truth):

- ``ADD``: ``read(Rn) + imm`` (field 31 = SP);
- ``SUB``: ``read(Rn) - imm`` (field 31 = SP);
- ``MOVZ``: ``imm`` (already shift-applied), zeroing the rest of ``Rd``;
  field 31 here is the zero register ``XZR`` — a write to ``Rd == 31`` is
  **discarded**, *not* routed to ``sp``. None of these touch ``NZCV``.

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
    OP_MOVZ,
    OP_SUB,
    SP_DEFAULT,
    Decoded,
    decode_insn,
)
from .expr import add, const, evaluate, sub, var

# A64 register field 31 denotes SP for the Add/subtract-immediate class
# (and the zero register XZR for the Move-wide class — handled at write-back).
_SP_FIELD = 31

# The Sail-derived datapath of each in-scope op, written once as an ``Expr`` tree
# over the shared QF_BV vocabulary. ``a`` binds to the Rn value; the (already
# shift-applied) immediate is a constant.
_A = var("a", 64)


def _exec_expr(dec: Decoded):
    """The Sail ``Expr`` tree for a decoded in-scope op (one source of truth).

    ``ADD``: ``a + imm``; ``SUB``: ``a - imm``; ``MOVZ``: the constant ``imm``
    (no source register — the immediate already carries the ``hw*16`` shift)."""
    imm = const(dec.imm & MASK64, 64)
    if dec.op == OP_ADD:
        return add(_A, imm)
    if dec.op == OP_SUB:
        return sub(_A, imm)
    if dec.op == OP_MOVZ:
        return imm
    raise Unsupported("aarch64", f"op={dec.op}")  # pragma: no cover - decoder gate


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
        dec = decode_insn(word)
        # For MOVZ the immediate is the whole result; ``a`` is then unused.
        env = {"a": _read(dec.rn, x, sp) & MASK64}
        result = evaluate(_exec_expr(dec), env) & MASK64   # Sail Expr eval
        # Write-back: for ADD/SUB field 31 is SP; for MOVZ field 31 is the zero
        # register XZR, so a write to Rd == 31 is *discarded* (not routed to sp).
        if dec.rd == _SP_FIELD:
            if dec.op != OP_MOVZ:
                sp = result
        else:
            x[dec.rd] = result
        pc = (pc + INSN_BYTES) & MASK64
        steps += 1
        trace.append(_state(pc, x, sp, nzcv, False))
    return trace
