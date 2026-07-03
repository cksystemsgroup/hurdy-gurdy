"""The construct-coverage inventory for wasm-btor2 (BENCHMARKS.md §2).

The in-scope construct set is the integer value-stack core (at **two widths**,
i32 and i64) the pair commits to fully covering: the operand producers
``i32.const`` / ``i64.const`` / ``local.get``, the local store ``local.set``, the
conditional ``select``, the unary comparisons ``i32.eqz`` / ``i64.eqz``, the full
**binary-operator family at each width** — the arithmetic / bitwise ops (``add`` /
``sub`` / ``mul`` / ``and`` / ``or`` / ``xor``), the shifts (``shl`` / ``shr_u`` /
``shr_s``), and the comparisons (``eq`` / ``ne`` / ``lt_{s,u}`` / ``gt_{s,u}`` /
``le_{s,u}`` / ``ge_{s,u}``) — the **division / remainder family** ``div_s`` /
``div_u`` / ``rem_s`` / ``rem_u`` at each width (with the Wasm **trap** edge), and
the **structured conditional** ``if <blocktype> <then> [else <else>] end`` (lowered
by the branch-merge — both arms evaluated over a copy of the incoming static stack,
then joined per slot/local with ``ite``). ``coverage()`` measures how many
translate without an ``Unsupported`` abort (the denominator the agent does not get
to shrink — it is the declared scope).

``UNSUPPORTED_PROBES`` is a representative slice of the *out-of-scope* Wasm
instruction space (the rest of the spec inventory — the rotates, the i32<->i64
width conversions, f32, memory, structured control flow): every one of these MUST
hard-abort with a typed ``Unsupported`` (BENCHMARKS.md §3), turning the gap into
an itemized histogram rather than a silent drop. ``unsupported_histogram()``
returns that histogram.
"""

from __future__ import annotations

import collections

from ...core.coverage import CoverageReport, measure
from ...core.errors import Unsupported
from ...languages.wasm import asm
from ...languages.wasm.interp import (
    BINOPS,
    DIVREM_OPS,
    EQZ_OPS,
    T_I32,
    T_I64,
    Instr,
    module,
)
from .translate import translate


def _p(*body: Instr, nlocals: int = 2, local_types=None, init_locals: dict | None = None) -> dict:
    return {"mod": module(list(body), nlocals=nlocals, local_types=local_types),
            "init_locals": init_locals or {}}


# In-scope: each construct exercised in a minimal well-typed body. Every binary
# op (``BINOPS``) gets a two-operand probe at its operand width; the producers,
# the conditional ``select`` and the unary comparisons are explicit. The i64
# probes push i64 operands first (so the body is well-typed at width 64).
# ``local.set`` and the structured ``if``/``else``/``end`` moved IN-scope this
# round: ``local.set`` pops one value into a local; ``if`` is the branch-merge of
# both arms (a value-producing ``if`` here, decided both ways by the corpus).
IN_SCOPE_PROBES: dict[str, dict] = {
    "i32.const": _p(asm.i32_const(7)),
    "i64.const": _p(asm.i64_const(7)),
    "local.get": _p(asm.local_get(0)),
    "local.set": _p(asm.i32_const(7), asm.local_set(0)),
    "i32.eqz": _p(asm.i32_const(0), asm.i32_eqz()),
    "i64.eqz": _p(asm.i64_const(0), asm.i64_eqz()),
    "select": _p(asm.i32_const(11), asm.i32_const(22), asm.i32_const(1), asm.select()),
    "if": _p(asm.i32_const(1),
             asm.if_([asm.i32_const(1)], [asm.i32_const(2)], result=(T_I32,))),
}
for _binop, (_in_ty, _out_ty, _kind, _fn) in BINOPS.items():
    _push = asm.i32_const if _in_ty == T_I32 else asm.i64_const
    IN_SCOPE_PROBES[_binop] = _p(_push(1), _push(2), Instr(_binop))
# The div/rem family (both widths) — a non-trapping probe (divisor 3) so the body
# both translates and runs; the trap edge itself is exercised by the test corpus.
for _divrem, (_in_ty, _kind) in DIVREM_OPS.items():
    _push = asm.i32_const if _in_ty == T_I32 else asm.i64_const
    IN_SCOPE_PROBES[_divrem] = _p(_push(6), _push(3), Instr(_divrem))

# ALL_PROBES (the measured denominator) is the union of the in-scope set and
# the enumerated out-of-scope slice — defined at the bottom, once both exist.
# Counting the out-of-scope probes in the denominator keeps the yardstick
# honest (the EVM-row style): a gap shows as a typed Unsupported entry rather
# than by silently shrinking the total.

# Out-of-scope: a representative slice of the rest of the Wasm opcode set. Each
# is wrapped in a minimal body that pushes enough operands first so the abort is
# the *opcode*, not a stack-shape error. The rotates, the i32<->i64 width
# conversions, f32 / memory / control flow are later widenings. (``div``/``rem``
# at both widths moved IN-scope this round — they now carry the trap edge.)
_OOS_BINOPS_I32 = ["i32.rotl", "i32.rotr"]
_OOS_BINOPS_I64 = ["i64.rotl", "i64.rotr"]
_OOS_OTHER = {
    # width conversions between i32 and i64 (still out of scope this slice)
    "i32.wrap_i64": [asm.i64_const(1), Instr("i32.wrap_i64")],
    "i64.extend_i32_s": [asm.i32_const(1), Instr("i64.extend_i32_s")],
    "i64.extend_i32_u": [asm.i32_const(1), Instr("i64.extend_i32_u")],
    "local.tee": [asm.i32_const(1), Instr("local.tee", 0)],
    "i32.load": [asm.i32_const(0), Instr("i32.load", 0)],
    "i32.store": [asm.i32_const(0), asm.i32_const(1), Instr("i32.store", 0)],
    "drop": [asm.i32_const(1), Instr("drop")],
    "block": [Instr("block")],
    "loop": [Instr("loop")],
    "br": [Instr("br", 0)],
    "br_if": [asm.i32_const(0), Instr("br_if", 0)],
    "call": [Instr("call", 0)],
    "return": [Instr("return")],
    "nop": [Instr("nop")],
    "unreachable": [Instr("unreachable")],
    "f32.add": [asm.i32_const(1), asm.i32_const(2), Instr("f32.add")],
    "memory.size": [Instr("memory.size")],
}

UNSUPPORTED_PROBES: dict[str, dict] = {}
for _op in _OOS_BINOPS_I32:
    UNSUPPORTED_PROBES[_op] = _p(asm.i32_const(1), asm.i32_const(2), Instr(_op))
for _op in _OOS_BINOPS_I64:
    UNSUPPORTED_PROBES[_op] = _p(asm.i64_const(1), asm.i64_const(2), Instr(_op))
for _name, _body in _OOS_OTHER.items():
    UNSUPPORTED_PROBES[_name] = _p(*_body)

# The measured denominator: in-scope + enumerated out-of-scope (see above).
ALL_PROBES = {**IN_SCOPE_PROBES, **UNSUPPORTED_PROBES}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)


def unsupported_histogram() -> dict[str, int]:
    """Run the out-of-scope probes; return the {construct -> count} histogram of
    the typed aborts. Raises if any out-of-scope probe fails to abort (a silent
    drop would be a coverage-honesty bug)."""
    blocked: list[str] = []
    for name, program in UNSUPPORTED_PROBES.items():
        try:
            translate(program)
        except Unsupported as exc:
            blocked.append(exc.construct)
            continue
        raise AssertionError(f"out-of-scope probe did not abort: {name}")
    return dict(collections.Counter(blocked))
