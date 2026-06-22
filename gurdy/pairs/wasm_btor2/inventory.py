"""The construct-coverage inventory for wasm-btor2 (BENCHMARKS.md §2).

The in-scope construct set is the i32-stack core the pair commits to fully
covering: the operand producers ``i32.const`` / ``local.get``, the conditional
``select``, the unary comparison ``i32.eqz``, and the full **i32 binary-operator
family** — the arithmetic / bitwise ops (``i32.add`` / ``i32.sub`` / ``i32.mul``
/ ``i32.and`` / ``i32.or`` / ``i32.xor``), the shifts (``i32.shl`` /
``i32.shr_u`` / ``i32.shr_s``), and the comparisons (``i32.eq`` / ``i32.ne`` /
``i32.lt_{s,u}`` / ``i32.gt_{s,u}`` / ``i32.le_{s,u}`` / ``i32.ge_{s,u}``).
``coverage()`` measures how many translate without an ``Unsupported`` abort
(the denominator the agent does not get to shrink — it is the declared scope).

``UNSUPPORTED_PROBES`` is a representative slice of the *out-of-scope* Wasm i32
instruction space (the rest of the spec inventory — the ``div``/``rem`` ops that
still need a div-by-zero trap edge, the rotates, i64/f32, memory, structured
control flow): every one of these MUST hard-abort with a typed ``Unsupported``
(BENCHMARKS.md §3), turning the gap into an itemized histogram rather than a
silent drop. ``unsupported_histogram()`` returns that histogram.
"""

from __future__ import annotations

import collections

from ...core.coverage import CoverageReport, measure
from ...core.errors import Unsupported
from ...languages.wasm import asm
from ...languages.wasm.interp import I32_BINOPS, Instr, module
from .translate import translate


def _p(*body: Instr, nlocals: int = 2, init_locals: dict | None = None) -> dict:
    return {"mod": module(list(body), nlocals=nlocals),
            "init_locals": init_locals or {}}


# In-scope: each construct exercised in a minimal well-typed body. Every i32
# binary op (``I32_BINOPS``) gets a two-operand probe; the operand producers, the
# conditional ``select`` and the unary comparison ``i32.eqz`` are explicit.
IN_SCOPE_PROBES: dict[str, dict] = {
    "i32.const": _p(asm.i32_const(7)),
    "local.get": _p(asm.local_get(0)),
    "i32.eqz": _p(asm.i32_const(0), asm.i32_eqz()),
    "select": _p(asm.i32_const(11), asm.i32_const(22), asm.i32_const(1), asm.select()),
}
for _binop in I32_BINOPS:
    IN_SCOPE_PROBES[_binop] = _p(asm.i32_const(1), asm.i32_const(2), Instr(_binop))

ALL_PROBES = IN_SCOPE_PROBES

# Out-of-scope: a representative slice of the rest of the Wasm i32 opcode set.
# Each is wrapped in a minimal body that pushes enough operands first so the
# abort is the *opcode*, not a stack-shape error. ``div``/``rem`` stay out
# pending their div-by-zero trap edge; rotates / i64 / f32 / memory / control
# flow are later widenings.
_OOS_BINOPS = [
    "i32.div_s", "i32.div_u", "i32.rem_s", "i32.rem_u", "i32.rotl", "i32.rotr",
]
_OOS_OTHER = {
    "i64.add": [asm.i32_const(1), asm.i32_const(2), Instr("i64.add")],
    "local.set": [asm.i32_const(1), Instr("local.set", 0)],
    "local.tee": [asm.i32_const(1), Instr("local.tee", 0)],
    "i32.load": [asm.i32_const(0), Instr("i32.load", 0)],
    "i32.store": [asm.i32_const(0), asm.i32_const(1), Instr("i32.store", 0)],
    "drop": [asm.i32_const(1), Instr("drop")],
    "block": [Instr("block")],
    "loop": [Instr("loop")],
    "br": [Instr("br", 0)],
    "br_if": [asm.i32_const(0), Instr("br_if", 0)],
    "if": [asm.i32_const(0), Instr("if")],
    "call": [Instr("call", 0)],
    "return": [Instr("return")],
    "nop": [Instr("nop")],
    "unreachable": [Instr("unreachable")],
    "f32.add": [asm.i32_const(1), asm.i32_const(2), Instr("f32.add")],
    "memory.size": [Instr("memory.size")],
}

UNSUPPORTED_PROBES: dict[str, dict] = {}
for _op in _OOS_BINOPS:
    UNSUPPORTED_PROBES[_op] = _p(asm.i32_const(1), asm.i32_const(2), Instr(_op))
for _name, _body in _OOS_OTHER.items():
    UNSUPPORTED_PROBES[_name] = _p(*_body)


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
