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
  the RISC-V Sail route uses — not the hand-written Python ``+`` of
  ``languages/aarch64/interp.py`` nor the BTOR2 ITE datapath of
  ``aarch64-btor2``. So the two AArch64→BTOR2 routes are genuinely independent
  realizations that the branch-agreement check corroborates.
- **Decoding** is delegated to the *shared* AArch64 decoder
  (``languages/aarch64.decode``) — one source of truth for the A64 encoding, so
  the encoding cannot drift and any out-of-scope instruction hard-aborts there
  with a typed ``Unsupported`` (BENCHMARKS.md §3).

Scope (thin-first, PAIRING.md §1): the single in-scope construct
``ADD (immediate)`` (64-bit). State: ``pc`` (byte address; A64 instructions are
4 bytes), ``x0``–``x30``, ``sp`` (register field 31 in this encoding class),
the ``NZCV`` flags, and ``halted``. Observables (post-step, ARCHITECTURE.md §5):
``{pc, x0..x30, sp, nzcv, halted}`` — *exactly* the ``aarch64-btor2`` projection,
so the branch cross-check at BTOR2 compares like with like.

Pure and deterministic: identical ``(program, binding)`` → identical trace.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ...languages.aarch64.interp import (
    INSN_BYTES,
    MASK64,
    NREG,
    SP_DEFAULT,
    decode,
)
from .expr import add, const, evaluate, var

# A64 register field 31 denotes SP for the Add/subtract-immediate class.
_SP_FIELD = 31

# The Sail-derived semantics of ``ADD (immediate)``: result = Rn + imm (mod 2^64).
# ``a`` binds to the Rn value; the (already shift-applied) addend is a constant.
_A = var("a", 64)


def _add_exec(imm: int):
    return add(_A, const(imm & MASK64, 64))


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
        dec = decode(word)   # shared decoder: one source of truth, aborts off-scope
        env = {"a": _read(dec.rn, x, sp) & MASK64}
        result = evaluate(_add_exec(dec.imm), env) & MASK64   # Sail Expr eval
        if dec.rd == _SP_FIELD:
            sp = result
        else:
            x[dec.rd] = result
        pc = (pc + INSN_BYTES) & MASK64
        steps += 1
        trace.append(_state(pc, x, sp, nzcv, False))
    return trace
