"""Minimal Wasm instruction builders for tests and coverage probes.

One helper per in-scope opcode, each returning an ``Instr`` the interpreter and
the lowering consume. Out-of-scope opcodes have *no* helper here on purpose —
they are constructed directly as ``Instr("<op>")`` in the rejection probes so
the typed ``Unsupported`` abort is exercised honestly (BENCHMARKS.md §3).
"""

from __future__ import annotations

from .interp import OP_I32_ADD, OP_I32_CONST, OP_LOCAL_GET, Instr


def i32_const(value: int) -> Instr:
    return Instr(OP_I32_CONST, int(value))


def local_get(index: int) -> Instr:
    return Instr(OP_LOCAL_GET, int(index))


def i32_add() -> Instr:
    return Instr(OP_I32_ADD)
