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
reduction rules over a typed value stack with locals. Every other instruction
hard-aborts with ``Unsupported`` (BENCHMARKS.md §3) — there is no silent drop.
``i32.div_*`` / ``i32.rem_*`` / ``i64.div_*`` / ``i64.rem_*`` stay out of scope
(they need a div-by-zero trap edge), as do the width conversions
(``i32.wrap_i64``, ``i64.extend_*``), f32/f64, memory, and structured control
flow; all keep hard-aborting.

A *behavior* is a ``Trace`` of **post-step** states (ARCHITECTURE.md §5). The
observable state after each instruction is::

    {"pc": <next instruction index>,
     "halted": <ran off the end of the body>,
     "stack": (<bottom>, ..., <top>),   # the value stack, as a tuple of ints
     "sp": <stack depth>,
     "locals": (<l0>, <l1>, ...)}       # the locals (i32 or i64 by declaration)

Stack and local values are plain (width-masked) Python ints; the cross-checked
projection compares them as integers, so an i32 value and the low 32 bits of the
BTOR2 slot that holds it agree directly. Pure and deterministic; ``pc`` indexes
the instruction list.

Interpreter version (the shared deliverable's contract — AGENTS.md §3): a
versioned bump is required for any additive semantics change so dependent
pairs re-validate their square.
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

INTERP_VERSION = "0.4"  # AGENTS.md §3: bumped when the i64 value type + ops were added.

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
OP_I32_EQZ = "i32.eqz"       # binary 0x45
OP_I64_EQZ = "i64.eqz"       # binary 0x50
OP_SELECT = "select"         # binary 0x1b

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

_PRODUCERS = frozenset({OP_I32_CONST, OP_I64_CONST, OP_LOCAL_GET})
_IN_SCOPE = frozenset(
    set(_PRODUCERS) | set(EQZ_OPS) | {OP_SELECT} | set(BINOPS)
)


@dataclass(frozen=True)
class Instr:
    """One Wasm instruction: an opcode and (at most) one immediate operand.

    ``imm`` is the literal for ``i32.const`` / ``i64.const`` or the local index
    for ``local.get``; ``None`` for the binary ops.
    """

    op: str
    imm: int | None = None


@dataclass
class WasmModule:
    """A loaded single-function module: the function ``body`` (a list of
    ``Instr``), the number of locals (``nlocals``), and each local's value type
    (``local_types`` — an entry per local, ``"i32"`` or ``"i64"``; defaults to
    all-i32 when omitted, so existing i32-only callers are unchanged). ``pc``
    indexes the body. Parameters are modeled as the first locals; their initial
    values come from the run binding."""

    body: list[Instr] = field(default_factory=list)
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
        every binary op pops two and pushes one (net -1); ``i32.eqz`` / ``i64.eqz``
        pop one and push one (net 0); ``select`` pops three and pushes one (net
        -2). The running maximum over the straight-line body is the depth the
        BTOR2 lowering must allocate state for."""
        depth = 0
        peak = 0
        for ins in self.body:
            if ins.op in _PRODUCERS:
                depth += 1
            elif ins.op in BINOPS:
                depth = max(depth - 1, 0)        # net -1 (pop 2, push 1)
            elif ins.op in EQZ_OPS:
                depth = max(depth, 0)            # net 0 (pop 1, push 1)
            elif ins.op == OP_SELECT:
                depth = max(depth - 2, 0)
            peak = max(peak, depth)
        return peak


def module(
    body: list[Instr],
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


def _state(pc: int, stack: list[int], locals_: list[int], halted: bool) -> dict[str, Any]:
    return {
        "pc": pc,
        "halted": halted,
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
        pc = _execute(mod.body[pc], pc, stack, locals_, mod.local_types)
        steps += 1
        halted = not (0 <= pc < len(mod.body))
        trace.append(_state(pc, stack, locals_, halted))
        if halted:
            break
    return trace
