"""A deterministic WebAssembly interpreter (the shared Wasm source interpreter).

Scope (MVP, thin-first then widened — ``languages/wasm`` brief): a single
straight-line function body over the **integer-stack core**, now at **two value
widths** (i32 = 32-bit, i64 = 64-bit). The operand producers ``i32.const`` /
``i64.const`` (push an immediate) and ``local.get`` (push a local — a local's
declared width determines whether it pushes an i32 or an i64); the conditional
``select`` (pop ``c``, ``v2``, ``v1``; push ``v1`` if ``c ≠ 0`` else ``v2``); the
unary comparisons ``i32.eqz`` / ``i64.eqz``; and the **binary-operator family**
at each width:

- arithmetic / bitwise (each pops two operands of its width, pushes one of the
  same width): ``add`` / ``sub`` / ``mul`` / ``and`` / ``or`` / ``xor`` (modular
  / bitwise at the operand width);
- shifts: ``shl`` / ``shr_u`` (logical) / ``shr_s`` (arithmetic) — the shift
  amount is taken **mod the width** (mod 32 for i32, mod 64 for i64), exactly as
  the Wasm spec masks it;
- comparisons (each pops two operands of its width and pushes an **i32** ``1``/
  ``0`` — Wasm comparisons always yield i32): ``eq`` / ``ne`` / ``lt_s`` /
  ``lt_u`` / ``gt_s`` / ``gt_u`` / ``le_s`` / ``le_u`` / ``ge_s`` / ``ge_u`` —
  the ``_s`` variants compare the operands as two's-complement signed, the
  ``_u`` variants as unsigned.

This mirrors the official Wasm small-step operational semantics for these
reduction rules over a typed value stack with locals. The **integer division /
remainder** family ``{i32,i64}.div_s`` / ``div_u`` / ``rem_s`` / ``rem_u`` is
also modeled, including its defined **trap** outcomes: ``div``/``rem`` trap when
the divisor is ``0``, and ``div_s`` additionally traps on the signed-overflow
case ``INT_MIN / -1`` (``rem_s`` of ``INT_MIN % -1`` does *not* trap — it is
``0``). A trap is a *defined, observable* Wasm outcome (not undefined behavior
and not the typed ``Unsupported`` abort): it halts the body with the ``trapped``
observable set. Every other instruction hard-aborts with ``Unsupported``
(BENCHMARKS.md §3) — there is no silent drop. The width conversions
(``i32.wrap_i64``, ``i64.extend_*``), rotates, f32/f64, memory, and structured
control flow keep hard-aborting.

A *behavior* is a ``Trace`` of **post-step** states (ARCHITECTURE.md §5). The
observable state after each instruction is::

    {"pc": <next instruction index>,
     "halted": <ran off the end, or trapped>,
     "trapped": <a Wasm trap fired (div/rem fault)>,
     "stack": (<bottom>, ..., <top>),   # the value stack, as a tuple of ints
     "sp": <stack depth>,
     "locals": (<l0>, <l1>, ...)}       # the locals (i32 or i64 by declaration)

Stack and local values are plain (width-masked) Python ints; the cross-checked
projection compares them as integers, so an i32 value and the low 32 bits of the
BTOR2 slot that holds it agree directly. ``trapped`` is a distinct observable: a
trap implies ``halted`` (a trap stops the body), but a normal off-the-end halt is
``halted`` without ``trapped``. Pure and deterministic; ``pc`` indexes the
instruction list.

Interpreter version (the shared deliverable's contract — AGENTS.md §3): a
versioned bump is required for any additive semantics change so dependent
pairs re-validate their square.
- ``0.6`` — added the **structured conditional** ``if <blocktype> <then> [else
  <else>] end`` and the ``local.set`` op it makes observable. An ``if`` is a
  single structured **body item** (its own ``If`` node, executed as one step:
  pop an i32 condition, run the *taken* arm to completion, advance the pc by
  one past the whole block). The body is now a list of items (a flat ``Instr``
  or a nested ``If``); ``pc`` indexes the top-level items, so each item still
  yields exactly one post-step state and a straight-line body's trace is
  byte-for-byte unchanged. The **Wasm validation discipline** is enforced: the
  condition is i32, both arms leave the stack at the block's declared result
  height/types (a missing ``else`` is an empty arm, legal only for a void
  block), or a typed ``Unsupported`` aborts. ``local.set`` pops one value of
  the local's declared width and stores it (locals are now mutable; the
  observable ``locals`` reflects the write). All *additive* — no existing
  rule's value changed, and a body containing no ``If``/``local.set`` runs
  exactly as before, so the ``0.1`` … ``0.5`` rules stay byte-for-byte green.
- ``0.5`` — added the **integer division / remainder** family
  ``{i32,i64}.div_s`` / ``div_u`` / ``rem_s`` / ``rem_u`` with the Wasm **trap**
  semantics (a new ``trapped`` observable; a div-by-zero or ``div_s`` signed
  overflow ``INT_MIN / -1`` traps — a *defined* halt, distinct from the typed
  ``unsupported`` abort). All *additive* — no existing rule's value changed and
  the ``trapped`` field defaults ``False`` on every prior state, so the ``0.1`` …
  ``0.4`` rules stay byte-for-byte green.
- ``0.4`` — added the **i64 value type** (bv64) and its operator family: the
  producers ``i64.const`` / ``local.get`` of an i64 local; the arithmetic /
  bitwise ops ``i64.add`` / ``i64.sub`` / ``i64.mul`` / ``i64.and`` / ``i64.or``
  / ``i64.xor``; the shifts ``i64.shl`` / ``i64.shr_u`` / ``i64.shr_s`` (amount
  mod 64); the unary comparison ``i64.eqz``; and the comparisons ``i64.eq`` /
  ``i64.ne`` / ``i64.lt_{s,u}`` / ``i64.gt_{s,u}`` / ``i64.le_{s,u}`` /
  ``i64.ge_{s,u}`` (each pushing an **i32** 0/1). The value stack now carries two
  widths, so a local declares its type. All *additive* — the i32 rules are
  byte-for-byte unchanged (the binop / compare logic was generalized to be
  width-parametric, but every i32 result is identical), so the ``0.1`` / ``0.2``
  / ``0.3`` rules stay green.
- ``0.3`` — added the rest of the i32 binary-operator family: the arithmetic /
  bitwise ops ``i32.sub`` / ``i32.mul`` / ``i32.and`` / ``i32.or`` / ``i32.xor``,
  the shifts ``i32.shl`` / ``i32.shr_u`` / ``i32.shr_s`` (shift amount mod 32),
  and the comparisons ``i32.eq`` / ``i32.ne`` / ``i32.lt_{s,u}`` /
  ``i32.gt_{s,u}`` / ``i32.le_{s,u}`` / ``i32.ge_{s,u}``. All *additive* (each is
  a new pop-two-push-one rule; no existing rule changes value), so the value-
  stack-core ``0.1`` / ``0.2`` rules are byte-for-byte intact.
- ``0.2`` — added the conditional ``select`` (Wasm ``0x1b``) and the comparison
  ``i32.eqz`` (``0x45``) it consumes; both are *additive* (no existing rule
  changes value), the value-stack-core ``0.1`` rules are byte-for-byte intact.
- ``0.1`` — the i32 value-stack core ``i32.const`` / ``local.get`` / ``i32.add``
  (the initial vertical slice).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace

INTERP_VERSION = "0.6"  # AGENTS.md §3: bumped when structured if/else + local.set were added.


class _Trap(Exception):
    """Internal signal: a div/rem fired a defined Wasm **trap** (a zero divisor,
    or the ``div_s`` signed overflow ``INT_MIN / -1``). Unlike ``Unsupported``
    (an out-of-scope construct), a trap is *in scope* — a defined, observable
    outcome — so ``run`` catches it and emits a final ``trapped`` post-step state
    rather than propagating. It never escapes this module."""

MASK32 = (1 << 32) - 1
MASK64 = (1 << 64) - 1
SHIFT_MASK = 31          # Wasm masks the i32 shift amount mod 32.
SHIFT_MASK64 = 63        # Wasm masks the i64 shift amount mod 64.

# Value types tracked on the static stack (and per local).
T_I32 = "i32"
T_I64 = "i64"
WIDTH = {T_I32: 32, T_I64: 64}

# The in-scope operand-producer / conditional opcodes (width-agnostic dispatch).
OP_I32_CONST = "i32.const"   # binary 0x41
OP_I64_CONST = "i64.const"   # binary 0x42
OP_LOCAL_GET = "local.get"   # binary 0x20
OP_LOCAL_SET = "local.set"   # binary 0x21
OP_I32_EQZ = "i32.eqz"       # binary 0x45
OP_I64_EQZ = "i64.eqz"       # binary 0x50
OP_SELECT = "select"         # binary 0x1b

# The structured conditional opcode (it appears as an ``If`` node, not a flat
# ``Instr``; the literal name is used only in the typed ``Unsupported`` aborts).
OP_IF = "if"                 # binary 0x04 (with the matching 0x05 ``else`` / 0x0b ``end``)

# --- the i32 binary-operator family (each pops two i32) ----------------------
# Arithmetic / bitwise (push i32):
OP_I32_ADD = "i32.add"       # binary 0x6a
OP_I32_SUB = "i32.sub"       # binary 0x6b
OP_I32_MUL = "i32.mul"       # binary 0x6c
OP_I32_AND = "i32.and"       # binary 0x71
OP_I32_OR = "i32.or"         # binary 0x72
OP_I32_XOR = "i32.xor"       # binary 0x73
# Shifts (shift amount taken mod 32):
OP_I32_SHL = "i32.shl"       # binary 0x74
OP_I32_SHR_S = "i32.shr_s"   # binary 0x75
OP_I32_SHR_U = "i32.shr_u"   # binary 0x76
# Comparisons (push the i32 result 1/0):
OP_I32_EQ = "i32.eq"         # binary 0x46
OP_I32_NE = "i32.ne"         # binary 0x47
OP_I32_LT_S = "i32.lt_s"     # binary 0x48
OP_I32_LT_U = "i32.lt_u"     # binary 0x49
OP_I32_GT_S = "i32.gt_s"     # binary 0x4a
OP_I32_GT_U = "i32.gt_u"     # binary 0x4b
OP_I32_LE_S = "i32.le_s"     # binary 0x4c
OP_I32_LE_U = "i32.le_u"     # binary 0x4d
OP_I32_GE_S = "i32.ge_s"     # binary 0x4e
OP_I32_GE_U = "i32.ge_u"     # binary 0x4f

# --- the i64 binary-operator family (each pops two i64) ----------------------
# Arithmetic / bitwise (push i64):
OP_I64_ADD = "i64.add"       # binary 0x7c
OP_I64_SUB = "i64.sub"       # binary 0x7d
OP_I64_MUL = "i64.mul"       # binary 0x7e
OP_I64_AND = "i64.and"       # binary 0x83
OP_I64_OR = "i64.or"         # binary 0x84
OP_I64_XOR = "i64.xor"       # binary 0x85
# Shifts (shift amount taken mod 64):
OP_I64_SHL = "i64.shl"       # binary 0x86
OP_I64_SHR_S = "i64.shr_s"   # binary 0x87
OP_I64_SHR_U = "i64.shr_u"   # binary 0x88
# Comparisons (push the *i32* result 1/0 — Wasm comparisons always yield i32):
OP_I64_EQ = "i64.eq"         # binary 0x51
OP_I64_NE = "i64.ne"         # binary 0x52
OP_I64_LT_S = "i64.lt_s"     # binary 0x53
OP_I64_LT_U = "i64.lt_u"     # binary 0x54
OP_I64_GT_S = "i64.gt_s"     # binary 0x55
OP_I64_GT_U = "i64.gt_u"     # binary 0x56
OP_I64_LE_S = "i64.le_s"     # binary 0x57
OP_I64_LE_U = "i64.le_u"     # binary 0x58
OP_I64_GE_S = "i64.ge_s"     # binary 0x59
OP_I64_GE_U = "i64.ge_u"     # binary 0x5a

# --- the integer division / remainder family (each pops two of its width) -----
# These are pop-two-push-one like the other binops, but they can *trap* (a
# defined, observable Wasm outcome): div/rem trap on a zero divisor, and div_s
# additionally on the signed-overflow case INT_MIN / -1. They are kept *out* of
# ``BINOPS`` (whose entries are total ``(a, b) -> int`` functions) and handled by
# their own descriptor table so the trap condition is explicit.
OP_I32_DIV_S = "i32.div_s"   # binary 0x6d
OP_I32_DIV_U = "i32.div_u"   # binary 0x6e
OP_I32_REM_S = "i32.rem_s"   # binary 0x6f
OP_I32_REM_U = "i32.rem_u"   # binary 0x70
OP_I64_DIV_S = "i64.div_s"   # binary 0x7f
OP_I64_DIV_U = "i64.div_u"   # binary 0x80
OP_I64_REM_S = "i64.rem_s"   # binary 0x81
OP_I64_REM_U = "i64.rem_u"   # binary 0x82


def _sext(v: int, width: int) -> int:
    """Interpret a width-bit unsigned ``v`` as two's-complement signed (used by
    the signed comparisons and the arithmetic right shift ``shr_s``)."""
    m = (1 << width) - 1
    v &= m
    return v - (1 << width) if v >> (width - 1) else v


def _sext32(v: int) -> int:
    """Interpret a u32 ``v`` as a two's-complement signed i32 (the original i32
    helper, kept so the i32 source of truth reads byte-for-byte unchanged)."""
    return _sext(v, 32)


def _make_binops() -> dict[str, tuple[str, str, str, Any]]:
    """Build the binary-op descriptor table, one width-parametric family per
    value type. Each entry is ``(in_type, out_type, kind, fn)``:

    - ``in_type``  — the operand value type (``i32``/``i64``);
    - ``out_type`` — the pushed value type (the operand width for arith/shift;
      always ``i32`` for a comparison, since Wasm comparisons yield i32);
    - ``kind``     — ``"arith"`` / ``"shift"`` / ``"cmp"`` (the BTOR2 lowering
      mirrors this to pick the node shape);
    - ``fn``       — the pure ``(a, b) -> int`` over the masked operands; an
      arith/shift result is reduced mod 2**out_width by ``_execute``, a cmp
      result is already 0/1.

    The i32 family is generated with width 32 / shift-mask 31 — identical
    semantics to the original ``I32_BINOPS`` table, so every i32 result is
    byte-for-byte unchanged.
    """
    table: dict[str, tuple[str, str, str, Any]] = {}

    def add_family(ty: str, names: dict[str, str], width: int, shmask: int) -> None:
        # arithmetic / bitwise (out type == operand type)
        table[names["add"]] = (ty, ty, "arith", lambda a, b: a + b)
        table[names["sub"]] = (ty, ty, "arith", lambda a, b: a - b)
        table[names["mul"]] = (ty, ty, "arith", lambda a, b: a * b)
        table[names["and"]] = (ty, ty, "arith", lambda a, b: a & b)
        table[names["or"]] = (ty, ty, "arith", lambda a, b: a | b)
        table[names["xor"]] = (ty, ty, "arith", lambda a, b: a ^ b)
        # shifts (amount masked mod width)
        table[names["shl"]] = (ty, ty, "shift", lambda a, b, sm=shmask: a << (b & sm))
        table[names["shr_u"]] = (ty, ty, "shift", lambda a, b, sm=shmask: a >> (b & sm))
        table[names["shr_s"]] = (
            ty, ty, "shift",
            lambda a, b, w=width, sm=shmask: _sext(a, w) >> (b & sm),
        )
        # comparisons (out type i32 — Wasm comparisons always yield i32)
        table[names["eq"]] = (ty, T_I32, "cmp", lambda a, b: 1 if a == b else 0)
        table[names["ne"]] = (ty, T_I32, "cmp", lambda a, b: 1 if a != b else 0)
        table[names["lt_u"]] = (ty, T_I32, "cmp", lambda a, b: 1 if a < b else 0)
        table[names["gt_u"]] = (ty, T_I32, "cmp", lambda a, b: 1 if a > b else 0)
        table[names["le_u"]] = (ty, T_I32, "cmp", lambda a, b: 1 if a <= b else 0)
        table[names["ge_u"]] = (ty, T_I32, "cmp", lambda a, b: 1 if a >= b else 0)
        table[names["lt_s"]] = (ty, T_I32, "cmp",
                                lambda a, b, w=width: 1 if _sext(a, w) < _sext(b, w) else 0)
        table[names["gt_s"]] = (ty, T_I32, "cmp",
                                lambda a, b, w=width: 1 if _sext(a, w) > _sext(b, w) else 0)
        table[names["le_s"]] = (ty, T_I32, "cmp",
                                lambda a, b, w=width: 1 if _sext(a, w) <= _sext(b, w) else 0)
        table[names["ge_s"]] = (ty, T_I32, "cmp",
                                lambda a, b, w=width: 1 if _sext(a, w) >= _sext(b, w) else 0)

    i32_names = {
        "add": OP_I32_ADD, "sub": OP_I32_SUB, "mul": OP_I32_MUL,
        "and": OP_I32_AND, "or": OP_I32_OR, "xor": OP_I32_XOR,
        "shl": OP_I32_SHL, "shr_u": OP_I32_SHR_U, "shr_s": OP_I32_SHR_S,
        "eq": OP_I32_EQ, "ne": OP_I32_NE,
        "lt_s": OP_I32_LT_S, "lt_u": OP_I32_LT_U,
        "gt_s": OP_I32_GT_S, "gt_u": OP_I32_GT_U,
        "le_s": OP_I32_LE_S, "le_u": OP_I32_LE_U,
        "ge_s": OP_I32_GE_S, "ge_u": OP_I32_GE_U,
    }
    i64_names = {
        "add": OP_I64_ADD, "sub": OP_I64_SUB, "mul": OP_I64_MUL,
        "and": OP_I64_AND, "or": OP_I64_OR, "xor": OP_I64_XOR,
        "shl": OP_I64_SHL, "shr_u": OP_I64_SHR_U, "shr_s": OP_I64_SHR_S,
        "eq": OP_I64_EQ, "ne": OP_I64_NE,
        "lt_s": OP_I64_LT_S, "lt_u": OP_I64_LT_U,
        "gt_s": OP_I64_GT_S, "gt_u": OP_I64_GT_U,
        "le_s": OP_I64_LE_S, "le_u": OP_I64_LE_U,
        "ge_s": OP_I64_GE_S, "ge_u": OP_I64_GE_U,
    }
    add_family(T_I32, i32_names, 32, SHIFT_MASK)
    add_family(T_I64, i64_names, 64, SHIFT_MASK64)
    return table


# Full binary-op descriptor table: op -> (in_type, out_type, kind, fn).
BINOPS: dict[str, tuple[str, str, str, Any]] = _make_binops()

# Backwards-compatible views: the per-width pop-two-push-one functions keyed by
# opcode, the single source of truth the BTOR2 lowering mirrors (kept so the
# importers and the drift guard still work). The values are the pure
# ``(a, b) -> int`` over the masked operands of that width.
I32_BINOPS: dict[str, Any] = {
    op: fn for op, (in_ty, _o, _k, fn) in BINOPS.items() if in_ty == T_I32
}
I64_BINOPS: dict[str, Any] = {
    op: fn for op, (in_ty, _o, _k, fn) in BINOPS.items() if in_ty == T_I64
}

# eqz by width (unary: pop one of the operand type, push the i32 result 0/1).
EQZ_OPS: dict[str, str] = {OP_I32_EQZ: T_I32, OP_I64_EQZ: T_I64}

# --- the integer division / remainder family ---------------------------------
# Each op is pop-two-push-one of its width, *but can trap* (a defined, observable
# Wasm outcome). ``DIVREM_OPS`` maps the opcode to ``(in_type, kind)`` where
# ``kind`` is one of ``"div_s"`` / ``"div_u"`` / ``"rem_s"`` / ``"rem_u"`` — the
# single source of truth the BTOR2 lowering mirrors (it selects both the BTOR2
# op ``sdiv``/``udiv``/``srem``/``urem`` and the trap condition). The result type
# is the operand type (unlike the comparisons, which yield i32).
DIVREM_OPS: dict[str, tuple[str, str]] = {
    OP_I32_DIV_S: (T_I32, "div_s"), OP_I32_DIV_U: (T_I32, "div_u"),
    OP_I32_REM_S: (T_I32, "rem_s"), OP_I32_REM_U: (T_I32, "rem_u"),
    OP_I64_DIV_S: (T_I64, "div_s"), OP_I64_DIV_U: (T_I64, "div_u"),
    OP_I64_REM_S: (T_I64, "rem_s"), OP_I64_REM_U: (T_I64, "rem_u"),
}


def _int_min(width: int) -> int:
    """The unsigned encoding of the most-negative two's-complement value at
    ``width`` (``0x8000_0000`` for i32, the i64 analogue) — the dividend of the
    ``div_s`` signed-overflow trap ``INT_MIN / -1``."""
    return 1 << (width - 1)


def _divrem_traps(kind: str, a: int, b: int, width: int) -> bool:
    """Whether a div/rem fires a Wasm trap on the (masked) operands ``a`` (the
    dividend) and ``b`` (the divisor). All four trap on a **zero divisor**;
    ``div_s`` *additionally* traps on the signed overflow ``INT_MIN / -1``. Note
    ``rem_s`` does **not** trap on ``INT_MIN % -1`` (it yields 0)."""
    if b == 0:
        return True
    mask = (1 << width) - 1
    if kind == "div_s" and a == _int_min(width) and (b & mask) == mask:
        return True   # INT_MIN / -1 overflows the signed range
    return False


def _divrem_value(kind: str, a: int, b: int, width: int) -> int:
    """The (non-trapping) div/rem result over the masked operands, reduced mod
    2**width. ``_s`` variants are two's-complement; ``_u`` variants unsigned.
    Truncating (round-toward-zero) division, as Wasm requires. Only called when
    ``_divrem_traps`` is false, so ``b != 0`` (and no INT_MIN/-1 for div_s)."""
    mask = (1 << width) - 1
    if kind == "div_u":
        return (a // b) & mask
    if kind == "rem_u":
        return (a % b) & mask
    x, y = _sext(a, width), _sext(b, width)
    if kind == "div_s":
        # round toward zero (Python // rounds toward -inf)
        q = abs(x) // abs(y)
        return (-q if (x < 0) != (y < 0) else q) & mask
    # rem_s: sign of the result follows the dividend (Wasm/C truncated rem)
    r = abs(x) % abs(y)
    return (-r if x < 0 else r) & mask


_PRODUCERS = frozenset({OP_I32_CONST, OP_I64_CONST, OP_LOCAL_GET})
_IN_SCOPE = frozenset(
    set(_PRODUCERS) | {OP_LOCAL_SET} | set(EQZ_OPS) | {OP_SELECT}
    | set(BINOPS) | set(DIVREM_OPS)
)


@dataclass(frozen=True)
class Instr:
    """One Wasm instruction: an opcode and (at most) one immediate operand.

    ``imm`` is the literal for ``i32.const`` / ``i64.const`` or the local index
    for ``local.get`` / ``local.set``; ``None`` for the binary ops.
    """

    op: str
    imm: int | None = None


@dataclass(frozen=True)
class If:
    """A structured conditional ``if <blocktype> <then> [else <else>] end``.

    A *body item* (it occupies one ``pc`` slot, like a flat ``Instr``): pop an
    i32 condition off the stack, run ``then`` if it is non-zero else ``orelse``,
    then continue past the whole block. ``result`` is the block type — the tuple
    of value types the block leaves on the stack on top of the height it was
    entered at (``()`` for a void block, ``("i32",)`` / ``("i64",)`` for a
    value-producing one). An absent ``else`` arm is the empty tuple ``()`` and is
    legal only for a void block (the Wasm validation rule).

    Both arms are themselves body-item tuples (a nested ``If`` is allowed — it is
    just a nested conditional), evaluated over the stack *after* the condition
    was popped. Wasm validation requires both arms to leave exactly ``result`` on
    top of the entry height; the interpreter and the translator enforce this.
    """

    then: tuple = ()
    orelse: tuple = ()
    result: tuple = ()
    has_else: bool = True


def _peak_depth(items, depth: int) -> int:
    """The peak value-stack depth reached while executing a body-item list that
    starts at height ``depth``. Recurses into both arms of an ``If`` (each runs
    over the height left after the i32 condition is popped); the post-block
    height is ``depth - 1 + len(result)`` (the condition popped, the block's
    declared result pushed). Used only to size the BTOR2 slot allocation."""
    peak = depth
    for item in items:
        if isinstance(item, If):
            after_cond = max(depth - 1, 0)        # the i32 condition is popped
            peak = max(peak, _peak_depth(item.then, after_cond),
                       _peak_depth(item.orelse, after_cond))
            depth = after_cond + len(item.result)
        else:
            op = item.op
            if op in _PRODUCERS:
                depth += 1
            elif op == OP_LOCAL_SET:
                depth = max(depth - 1, 0)         # net -1 (pop 1)
            elif op in BINOPS or op in DIVREM_OPS:
                depth = max(depth - 1, 0)         # net -1 (pop 2, push 1)
            elif op in EQZ_OPS:
                depth = max(depth, 0)             # net 0 (pop 1, push 1)
            elif op == OP_SELECT:
                depth = max(depth - 2, 0)
        peak = max(peak, depth)
    return peak


@dataclass
class WasmModule:
    """A loaded single-function module: the function ``body`` (a list of body
    *items* — a flat ``Instr`` or a structured ``If``), the number of locals
    (``nlocals``), and each local's value type (``local_types`` — an entry per
    local, ``"i32"`` or ``"i64"``; defaults to all-i32 when omitted, so existing
    i32-only callers are unchanged). ``pc`` indexes the top-level body items, so
    a structured ``if`` occupies one ``pc`` slot. Parameters are modeled as the
    first locals; their initial values come from the run binding."""

    body: list = field(default_factory=list)
    nlocals: int = 0
    entry: int = 0
    local_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.local_types:
            object.__setattr__(self, "local_types", tuple(T_I32 for _ in range(self.nlocals)))
        elif len(self.local_types) != self.nlocals:
            raise Unsupported(
                "wasm", "local.get",
                f"local_types length {len(self.local_types)} != nlocals {self.nlocals}",
            )

    def local_type(self, idx: int) -> str:
        return self.local_types[idx]

    @property
    def max_stack(self) -> int:
        """A static bound on the value-stack depth this body can reach.

        Each producer (``i32.const`` / ``i64.const`` / ``local.get``) pushes one;
        ``local.set`` pops one (net -1); every binary op — including the div/rem
        family — pops two and pushes one (net -1); ``i32.eqz`` / ``i64.eqz`` pop
        one and push one (net 0); ``select`` pops three and pushes one (net -2).
        A structured ``if`` pops its i32 condition (net -1 for the condition),
        then the deeper of its two arms determines the peak reached *inside* the
        block; on exit the block leaves its declared ``result`` height. The
        running maximum over the body (recursing into both arms) is the depth the
        BTOR2 lowering must allocate state for."""
        return _peak_depth(self.body, 0)


def module(
    body: list,
    nlocals: int = 0,
    local_types: tuple[str, ...] | list[str] | None = None,
) -> WasmModule:
    return WasmModule(
        body=list(body),
        nlocals=nlocals,
        local_types=tuple(local_types) if local_types else (),
    )


def _mask(v: int, width: int) -> int:
    return v & ((1 << width) - 1)


def _u32(v: int) -> int:
    return v & MASK32


def _execute(ins: Instr, pc: int, stack: list[int], locals_: list[int],
             local_types: tuple[str, ...]) -> int:
    """Apply one in-scope reduction rule, mutating ``stack`` in place; return
    the next ``pc``. Out-of-scope opcodes / malformed stacks hard-abort."""
    op = ins.op
    if op == OP_I32_CONST:
        if ins.imm is None:
            raise Unsupported("wasm", "i32.const", "missing immediate")
        stack.append(_mask(int(ins.imm), 32))
        return pc + 1
    if op == OP_I64_CONST:
        if ins.imm is None:
            raise Unsupported("wasm", "i64.const", "missing immediate")
        stack.append(_mask(int(ins.imm), 64))
        return pc + 1
    if op == OP_LOCAL_GET:
        idx = ins.imm
        if idx is None or not (0 <= idx < len(locals_)):
            raise Unsupported("wasm", "local.get", f"index {idx} out of range")
        stack.append(locals_[idx])
        return pc + 1
    if op == OP_LOCAL_SET:
        idx = ins.imm
        if idx is None or not (0 <= idx < len(locals_)):
            raise Unsupported("wasm", "local.set", f"index {idx} out of range")
        if len(stack) < 1:
            raise Unsupported("wasm", "local.set", "stack underflow")
        locals_[idx] = _mask(stack.pop(), WIDTH[local_types[idx]])
        return pc + 1
    if op in BINOPS:
        if len(stack) < 2:
            raise Unsupported("wasm", op, "stack underflow")
        _in_ty, out_ty, _kind, fn = BINOPS[op]
        b = stack.pop()
        a = stack.pop()
        # Each rule is a pure (a, b) -> int over the masked operands; an arith /
        # shift result is reduced mod 2**out_width (a no-op for a 0/1 comparison,
        # whose out type is i32). This single source of truth is mirrored by the
        # BTOR2 lowering per construct.
        stack.append(_mask(fn(a, b), WIDTH[out_ty]))
        return pc + 1
    if op in DIVREM_OPS:
        if len(stack) < 2:
            raise Unsupported("wasm", op, "stack underflow")
        in_ty, kind = DIVREM_OPS[op]
        w = WIDTH[in_ty]
        b = stack.pop()
        a = stack.pop()
        if _divrem_traps(kind, a, b, w):
            # A defined Wasm trap (zero divisor, or div_s INT_MIN/-1). The two
            # operands are already popped; freeze a sentinel ``0`` result onto the
            # stack so sp == h-1 agrees with the BTOR2 trapped state, then signal.
            stack.append(0)
            raise _Trap()
        stack.append(_divrem_value(kind, a, b, w))
        return pc + 1
    if op in EQZ_OPS:
        if len(stack) < 1:
            raise Unsupported("wasm", op, "stack underflow")
        x = stack.pop()
        stack.append(1 if x == 0 else 0)        # i32 result (Wasm i{32,64}.eqz)
        return pc + 1
    if op == OP_SELECT:
        if len(stack) < 3:
            raise Unsupported("wasm", "select", "stack underflow")
        c = stack.pop()                          # condition (top)
        v2 = stack.pop()
        v1 = stack.pop()
        stack.append(v1 if c != 0 else v2)       # v1 iff c != 0 (Wasm select)
        return pc + 1
    raise Unsupported("wasm", op)


# The arm of a structured ``if`` is restricted to the **non-trapping**
# straight-line in-scope set plus ``local.set`` and a nested ``If`` (which is
# just a nested conditional). The div/rem family is *excluded* from an arm
# because its trap edge cannot fire half-way through a branch-merge — a div/rem
# inside an arm hard-aborts ``unsupported`` (a later widening). This keeps the
# source interpreter's accepted scope identical to the translator's.
_ARM_FLAT_OPS = frozenset(
    set(_PRODUCERS) | {OP_LOCAL_SET} | set(EQZ_OPS) | {OP_SELECT} | set(BINOPS)
)


def _exec_if(node: "If", stack: list[int], locals_: list[int],
             local_types: tuple[str, ...]) -> None:
    """Execute one structured ``if`` as a single step (mutating ``stack`` /
    ``locals_`` in place): pop the i32 condition, run the *taken* arm's items to
    completion. A missing ``else`` (``has_else`` False) is legal only for a void
    block; the taken arm is then empty when the condition is false. Out-of-scope
    arm contents hard-abort ``unsupported``."""
    if len(stack) < 1:
        raise Unsupported("wasm", OP_IF, "stack underflow (no condition)")
    cond = stack.pop()                              # the i32 condition (top)
    if cond != 0:
        arm = node.then
    else:
        arm = node.orelse
        if not node.has_else and arm:
            raise Unsupported("wasm", OP_IF, "missing else for a non-empty arm")
    _exec_arm(arm, stack, locals_, local_types)


def _exec_arm(items, stack: list[int], locals_: list[int],
              local_types: tuple[str, ...]) -> None:
    """Run a body-item arm inline (no per-instruction trace rows — the whole
    ``if`` is one step). A nested ``If`` recurses; a flat ``Instr`` is dispatched
    through ``_execute`` but restricted to the non-trapping arm op set."""
    for item in items:
        if isinstance(item, If):
            _exec_if(item, stack, locals_, local_types)
            continue
        if item.op not in _ARM_FLAT_OPS:
            raise Unsupported("wasm", item.op, "not allowed inside an if arm")
        _execute(item, 0, stack, locals_, local_types)


def _state(pc: int, stack: list[int], locals_: list[int], halted: bool,
           trapped: bool = False) -> dict[str, Any]:
    return {
        "pc": pc,
        "halted": halted,
        "trapped": trapped,
        "sp": len(stack),
        "stack": tuple(stack),
        "locals": tuple(locals_),
    }


def run(
    mod: WasmModule,
    binding: dict[str, Any] | None = None,
    max_steps: int = 100_000,
    **_kw: Any,
) -> Trace:
    """Run ``mod``'s body to a halt (off-the-end of the body, or ``max_steps``).

    ``binding`` may set ``pc`` (entry) and initial ``locals`` (``{index:
    value}`` — parameters are the first locals; a value is masked to the local's
    declared width). Returns the post-step trace.
    """
    locals_ = [0] * mod.nlocals
    pc = mod.entry
    if binding:
        pc = binding.get("pc", pc)
        for idx, val in binding.get("locals", {}).items():
            i = int(idx)
            if not (0 <= i < mod.nlocals):
                raise Unsupported("wasm", "local.get", f"binding index {i} out of range")
            locals_[i] = _mask(int(val), WIDTH[mod.local_type(i)])

    stack: list[int] = []
    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (0 <= pc < len(mod.body)):
            trace.append(_state(pc, stack, locals_, True))   # off the end -> halt
            break
        cur = pc
        item = mod.body[pc]
        try:
            if isinstance(item, If):
                # A structured conditional is one step: pop the condition, run the
                # taken arm to completion (no per-arm trace rows), advance past the
                # whole block.
                _exec_if(item, stack, locals_, mod.local_types)
                pc = cur + 1
            else:
                pc = _execute(item, pc, stack, locals_, mod.local_types)
        except _Trap:
            # A defined Wasm trap (div/rem fault): a *distinct, observable* halt.
            # ``_execute`` left the post-pop sentinel stack in place; the trapped
            # pc advances to ``cur + 1`` (mirroring the BTOR2 trapped next-state),
            # and both ``trapped`` and ``halted`` are set. Execution stops here.
            trace.append(_state(cur + 1, stack, locals_, True, trapped=True))
            break
        steps += 1
        halted = not (0 <= pc < len(mod.body))
        trace.append(_state(pc, stack, locals_, halted))
        if halted:
            break
    return trace
