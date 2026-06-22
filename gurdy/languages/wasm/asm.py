"""Minimal Wasm instruction builders for tests and coverage probes.

One helper per in-scope opcode, each returning an ``Instr`` the interpreter and
the lowering consume. Out-of-scope opcodes have *no* helper here on purpose —
they are constructed directly as ``Instr("<op>")`` in the rejection probes so
the typed ``Unsupported`` abort is exercised honestly (BENCHMARKS.md §3).
"""

from __future__ import annotations

from .interp import (
    OP_I32_ADD,
    OP_I32_AND,
    OP_I32_CONST,
    OP_I32_EQ,
    OP_I32_EQZ,
    OP_I32_GE_S,
    OP_I32_GE_U,
    OP_I32_GT_S,
    OP_I32_GT_U,
    OP_I32_LE_S,
    OP_I32_LE_U,
    OP_I32_LT_S,
    OP_I32_LT_U,
    OP_I32_MUL,
    OP_I32_NE,
    OP_I32_OR,
    OP_I32_SHL,
    OP_I32_SHR_S,
    OP_I32_SHR_U,
    OP_I32_SUB,
    OP_I32_XOR,
    OP_LOCAL_GET,
    OP_SELECT,
    Instr,
)


def i32_const(value: int) -> Instr:
    return Instr(OP_I32_CONST, int(value))


def local_get(index: int) -> Instr:
    return Instr(OP_LOCAL_GET, int(index))


def i32_add() -> Instr:
    return Instr(OP_I32_ADD)


def i32_eqz() -> Instr:
    return Instr(OP_I32_EQZ)


def select() -> Instr:
    return Instr(OP_SELECT)


# --- the rest of the i32 binary-operator family (each pops two i32) ----------
def i32_sub() -> Instr:
    return Instr(OP_I32_SUB)


def i32_mul() -> Instr:
    return Instr(OP_I32_MUL)


def i32_and() -> Instr:
    return Instr(OP_I32_AND)


def i32_or() -> Instr:
    return Instr(OP_I32_OR)


def i32_xor() -> Instr:
    return Instr(OP_I32_XOR)


def i32_shl() -> Instr:
    return Instr(OP_I32_SHL)


def i32_shr_s() -> Instr:
    return Instr(OP_I32_SHR_S)


def i32_shr_u() -> Instr:
    return Instr(OP_I32_SHR_U)


def i32_eq() -> Instr:
    return Instr(OP_I32_EQ)


def i32_ne() -> Instr:
    return Instr(OP_I32_NE)


def i32_lt_s() -> Instr:
    return Instr(OP_I32_LT_S)


def i32_lt_u() -> Instr:
    return Instr(OP_I32_LT_U)


def i32_gt_s() -> Instr:
    return Instr(OP_I32_GT_S)


def i32_gt_u() -> Instr:
    return Instr(OP_I32_GT_U)


def i32_le_s() -> Instr:
    return Instr(OP_I32_LE_S)


def i32_le_u() -> Instr:
    return Instr(OP_I32_LE_U)


def i32_ge_s() -> Instr:
    return Instr(OP_I32_GE_S)


def i32_ge_u() -> Instr:
    return Instr(OP_I32_GE_U)
