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
    OP_I32_DIV_S,
    OP_I32_DIV_U,
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
    OP_I32_REM_S,
    OP_I32_REM_U,
    OP_I32_SHL,
    OP_I32_SHR_S,
    OP_I32_SHR_U,
    OP_I32_SUB,
    OP_I32_XOR,
    OP_I64_ADD,
    OP_I64_AND,
    OP_I64_CONST,
    OP_I64_DIV_S,
    OP_I64_DIV_U,
    OP_I64_EQ,
    OP_I64_EQZ,
    OP_I64_GE_S,
    OP_I64_GE_U,
    OP_I64_GT_S,
    OP_I64_GT_U,
    OP_I64_LE_S,
    OP_I64_LE_U,
    OP_I64_LT_S,
    OP_I64_LT_U,
    OP_I64_MUL,
    OP_I64_NE,
    OP_I64_OR,
    OP_I64_REM_S,
    OP_I64_REM_U,
    OP_I64_SHL,
    OP_I64_SHR_S,
    OP_I64_SHR_U,
    OP_I64_SUB,
    OP_I64_XOR,
    OP_LOCAL_GET,
    OP_LOCAL_SET,
    OP_SELECT,
    If,
    Instr,
)


def i32_const(value: int) -> Instr:
    return Instr(OP_I32_CONST, int(value))


def i64_const(value: int) -> Instr:
    return Instr(OP_I64_CONST, int(value))


def local_get(index: int) -> Instr:
    return Instr(OP_LOCAL_GET, int(index))


def local_set(index: int) -> Instr:
    return Instr(OP_LOCAL_SET, int(index))


def if_(then, orelse=None, result=()):
    """Build a structured ``if <result> <then> [else <orelse>] end`` body item.

    ``then`` / ``orelse`` are body-item sequences (a flat ``Instr`` or a nested
    ``If``); ``result`` is the block type — ``()`` for a void block,
    ``("i32",)`` / ``("i64",)`` for a value-producing one. Passing ``orelse=None``
    builds an ``if`` with **no** ``else`` clause (legal only for a void block);
    an explicit empty ``[]`` is an empty-but-present ``else``."""
    has_else = orelse is not None
    return If(
        then=tuple(then),
        orelse=tuple(orelse) if orelse is not None else (),
        result=tuple(result),
        has_else=has_else,
    )


def i32_add() -> Instr:
    return Instr(OP_I32_ADD)


def i32_eqz() -> Instr:
    return Instr(OP_I32_EQZ)


def i64_eqz() -> Instr:
    return Instr(OP_I64_EQZ)


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


# --- the i64 binary-operator family (each pops two i64) ----------------------
def i64_add() -> Instr:
    return Instr(OP_I64_ADD)


def i64_sub() -> Instr:
    return Instr(OP_I64_SUB)


def i64_mul() -> Instr:
    return Instr(OP_I64_MUL)


def i64_and() -> Instr:
    return Instr(OP_I64_AND)


def i64_or() -> Instr:
    return Instr(OP_I64_OR)


def i64_xor() -> Instr:
    return Instr(OP_I64_XOR)


def i64_shl() -> Instr:
    return Instr(OP_I64_SHL)


def i64_shr_s() -> Instr:
    return Instr(OP_I64_SHR_S)


def i64_shr_u() -> Instr:
    return Instr(OP_I64_SHR_U)


def i64_eq() -> Instr:
    return Instr(OP_I64_EQ)


def i64_ne() -> Instr:
    return Instr(OP_I64_NE)


def i64_lt_s() -> Instr:
    return Instr(OP_I64_LT_S)


def i64_lt_u() -> Instr:
    return Instr(OP_I64_LT_U)


def i64_gt_s() -> Instr:
    return Instr(OP_I64_GT_S)


def i64_gt_u() -> Instr:
    return Instr(OP_I64_GT_U)


def i64_le_s() -> Instr:
    return Instr(OP_I64_LE_S)


def i64_le_u() -> Instr:
    return Instr(OP_I64_LE_U)


def i64_ge_s() -> Instr:
    return Instr(OP_I64_GE_S)


def i64_ge_u() -> Instr:
    return Instr(OP_I64_GE_U)


# --- the integer division / remainder family (each pops two, may trap) --------
def i32_div_s() -> Instr:
    return Instr(OP_I32_DIV_S)


def i32_div_u() -> Instr:
    return Instr(OP_I32_DIV_U)


def i32_rem_s() -> Instr:
    return Instr(OP_I32_REM_S)


def i32_rem_u() -> Instr:
    return Instr(OP_I32_REM_U)


def i64_div_s() -> Instr:
    return Instr(OP_I64_DIV_S)


def i64_div_u() -> Instr:
    return Instr(OP_I64_DIV_U)


def i64_rem_s() -> Instr:
    return Instr(OP_I64_REM_S)


def i64_rem_u() -> Instr:
    return Instr(OP_I64_REM_U)
