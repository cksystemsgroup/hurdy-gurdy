"""WebAssembly -> BTOR2 translator (pairs/wasm-btor2 brief).

Emits a BTOR2 transition system modeling the Wasm stack machine one instruction
per cycle. State: ``pc`` (bv32, the instruction index), ``halted`` (bv1), the
locals ``l0..l{N-1}`` (each ``bv32`` for an i32 local, ``bv64`` for an i64
local), and a fixed set of value-stack slots ``s0..s{D-1}``, where ``D`` is the
static maximum stack depth the body reaches. The fixed body is lowered to a
PC-keyed ITE dispatch over the per-instruction next-state functions, exactly
mirroring ``languages/wasm/interp.py`` so the commuting-square oracle
cross-checks them.

**Per-slot value type.** The value stack now holds values of two widths (i32 =
bv32, i64 = bv64), so the static-stack model tracks each slot's **value type**,
not just the height. For a straight-line, well-typed Wasm body the type of every
stack slot before each instruction is a static property (a Wasm validator
computes exactly this stack type), so each instruction writes a statically-known
slot at a statically-known width — no runtime indexing is needed. A physical
slot ``j`` is allocated at the **widest** value type it ever holds over the body
(``slot_width[j]``); a narrower i32 value written into a wider (bv64) slot is
zero-extended into the low 32 bits, so its carried integer matches the source
interpreter's u32 value bit-for-bit. A body that uses only i32 keeps every slot
at bv32, so the i32 lowering is **byte-for-byte unchanged**. ``sp`` is tracked
as ordinary state for the projection and carry-back.

Scope: the integer value-stack core at both widths. Operand producers
``i32.const`` / ``i64.const`` / ``local.get``; the conditional ``select``
(``ite(neq(c, 0), v1, v2)``); the unary comparisons ``i32.eqz`` / ``i64.eqz``
(``uext(eq(x, 0))`` widened to the i32 result); and the **binary-operator
family** at each width (``BTOR2_BINOP``), each popping two operands and pushing
one: the arithmetic / bitwise ops (``add`` / ``sub`` / ``mul`` / ``and`` / ``or``
/ ``xor`` at the operand width, modular), the shifts (``sll`` / ``srl`` / ``sra``
with the amount masked ``& (width-1)`` to match Wasm's mod-width rule), and the
comparisons (``eq`` / ``neq`` / ``slt`` / ``ult`` / ``sgt`` / ``ugt`` / ``slte``
/ ``ulte`` / ``sgte`` / ``ugte`` — each a bv1 predicate widened ``uext`` to the
**i32** result ``1``/``0``, since Wasm comparisons always yield i32). Each
lowering is the single source of truth the interpreter (``BINOPS``) mirrors.
``i32.div_*`` / ``i32.rem_*`` / ``i64.div_*`` / ``i64.rem_*`` stay out of scope
(they need a div-by-zero trap edge); width conversions (``i32.wrap_i64`` /
``i64.extend_*``) and everything else hard-abort with ``Unsupported``
(BENCHMARKS.md §3). Deterministic in ``(mod, init_locals, property)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder
from ...languages.wasm.interp import (
    BINOPS,
    DIVREM_OPS,
    EQZ_OPS,
    MASK32,
    OP_I32_CONST,
    OP_I64_CONST,
    OP_LOCAL_GET,
    OP_SELECT,
    T_I32,
    T_I64,
    WIDTH,
    WasmModule,
    _int_min,
    _PRODUCERS,
)

# The per-construct BTOR2 lowering of the binary-operator family — the single
# source of truth mirroring ``languages/wasm/interp.BINOPS``. Each entry is
# ``(btor2_op, kind)`` where ``kind`` selects how the BTOR2 op result becomes the
# pushed value:
#   - "arith": a width-``w`` ``op2`` whose bv result is the value directly
#     (modular 2**w, matching the corresponding Wasm rule);
#   - "shift": a width-``w`` shift whose amount is first masked ``& (w-1)`` (Wasm
#     takes the shift amount mod the width, whereas BTOR2 ``sll/srl/sra`` do not);
#   - "cmp": a bv1 predicate widened with ``uext`` to the **i32** result 1/0
#     (Wasm comparisons always yield i32, at *both* widths).
# ``w`` (the operand width) and the i32 output type come from ``BINOPS`` so the
# i32 rows keep their existing lowering byte-for-byte.
BTOR2_BINOP: dict[str, tuple[str, str]] = {
    # i32 arithmetic / bitwise
    "i32.add": ("add", "arith"), "i32.sub": ("sub", "arith"),
    "i32.mul": ("mul", "arith"), "i32.and": ("and", "arith"),
    "i32.or": ("or", "arith"), "i32.xor": ("xor", "arith"),
    # i32 shifts
    "i32.shl": ("sll", "shift"), "i32.shr_u": ("srl", "shift"),
    "i32.shr_s": ("sra", "shift"),
    # i32 comparisons
    "i32.eq": ("eq", "cmp"), "i32.ne": ("neq", "cmp"),
    "i32.lt_s": ("slt", "cmp"), "i32.lt_u": ("ult", "cmp"),
    "i32.gt_s": ("sgt", "cmp"), "i32.gt_u": ("ugt", "cmp"),
    "i32.le_s": ("slte", "cmp"), "i32.le_u": ("ulte", "cmp"),
    "i32.ge_s": ("sgte", "cmp"), "i32.ge_u": ("ugte", "cmp"),
    # i64 arithmetic / bitwise
    "i64.add": ("add", "arith"), "i64.sub": ("sub", "arith"),
    "i64.mul": ("mul", "arith"), "i64.and": ("and", "arith"),
    "i64.or": ("or", "arith"), "i64.xor": ("xor", "arith"),
    # i64 shifts
    "i64.shl": ("sll", "shift"), "i64.shr_u": ("srl", "shift"),
    "i64.shr_s": ("sra", "shift"),
    # i64 comparisons (still push the i32 result)
    "i64.eq": ("eq", "cmp"), "i64.ne": ("neq", "cmp"),
    "i64.lt_s": ("slt", "cmp"), "i64.lt_u": ("ult", "cmp"),
    "i64.gt_s": ("sgt", "cmp"), "i64.gt_u": ("ugt", "cmp"),
    "i64.le_s": ("slte", "cmp"), "i64.le_u": ("ulte", "cmp"),
    "i64.ge_s": ("sgte", "cmp"), "i64.ge_u": ("ugte", "cmp"),
}

# Every binary op the interpreter recognizes must have a BTOR2 lowering (and no
# extras) — a guard so the two sources of truth never drift.
assert set(BTOR2_BINOP) == set(BINOPS), "BTOR2_BINOP must mirror BINOPS"

# The per-construct BTOR2 lowering of the **div/rem family** — the single source
# of truth mirroring ``languages/wasm/interp.DIVREM_OPS``. Each ``kind`` maps to
# the BTOR2 op whose *non-trapping* result is the pushed value (the BTOR2
# ``udiv``/``urem``/``sdiv``/``srem`` already give the right two's-complement
# value, including ``srem`` of ``INT_MIN % -1`` -> 0). The trap is a *separate*
# edge gated by ``_trap_cond`` (a zero divisor for all four; additionally
# ``INT_MIN / -1`` for ``div_s``), so the slot write is
# ``ite(trap_cond, 0, <btor2-op result>)`` and on a trap the ``trapped``/``halted``
# state vars are set — distinct from a normal off-the-end halt and from the
# typed ``unsupported`` abort.
BTOR2_DIVREM: dict[str, str] = {
    "div_s": "sdiv", "div_u": "udiv", "rem_s": "srem", "rem_u": "urem",
}

# Every div/rem op the interpreter recognizes must have a BTOR2 op (and no
# extras) — the same drift guard, at the ``kind`` level.
assert set(BTOR2_DIVREM) == {kind for _ty, kind in DIVREM_OPS.values()}, \
    "BTOR2_DIVREM must mirror DIVREM_OPS kinds"


@dataclass
class Effect:
    """The next-state effect of one instruction at a fixed pre-instruction
    static stack type: a new ``pc`` node and the value-stack slots it writes
    (slot index -> value node, already widened to that slot's allocated width).

    ``trap_cond`` is an optional bv1 node that is ``1`` exactly when this
    instruction fires a Wasm **trap** (only div/rem set it; ``None`` otherwise).
    When set, the main loop gates the ``trapped``/``halted`` state on
    ``active ∧ trap_cond`` — a defined halt edge distinct from the off-the-end
    halt. The stack write already folds the trap in via ``ite(trap_cond, 0, …)``."""

    next_pc: int
    stack_writes: dict[int, int]
    trap_cond: int | None = None


def _static_type_stacks(mod: WasmModule) -> list[tuple[str, ...]]:
    """The static value-stack *type* before each instruction (the Wasm static
    stack type, as a tuple of ``"i32"``/``"i64"`` bottom-to-top). Validates the
    in-scope set, operand-type agreement, and rejects any body that would
    underflow — an out-of-scope opcode or a type/height error aborts."""
    stacks: list[tuple[str, ...]] = []
    stack: list[str] = []
    for ins in mod.body:
        stacks.append(tuple(stack))
        op = ins.op
        if op == OP_I32_CONST:
            stack.append(T_I32)
        elif op == OP_I64_CONST:
            stack.append(T_I64)
        elif op == OP_LOCAL_GET:
            idx = ins.imm
            if idx is None or not (0 <= idx < mod.nlocals):
                raise Unsupported("wasm-btor2", "local.get", f"index {idx} out of range")
            stack.append(mod.local_type(idx))
        elif op in BINOPS:
            if len(stack) < 2:
                raise Unsupported("wasm-btor2", op, "static stack underflow")
            in_ty, out_ty, _kind, _fn = BINOPS[op]
            b_ty = stack.pop()
            a_ty = stack.pop()
            if a_ty != in_ty or b_ty != in_ty:
                raise Unsupported("wasm-btor2", op,
                                  f"operand type mismatch ({a_ty}, {b_ty}) != {in_ty}")
            stack.append(out_ty)
        elif op in DIVREM_OPS:
            if len(stack) < 2:
                raise Unsupported("wasm-btor2", op, "static stack underflow")
            in_ty, _kind = DIVREM_OPS[op]
            b_ty = stack.pop()
            a_ty = stack.pop()
            if a_ty != in_ty or b_ty != in_ty:
                raise Unsupported("wasm-btor2", op,
                                  f"operand type mismatch ({a_ty}, {b_ty}) != {in_ty}")
            stack.append(in_ty)              # div/rem result has the operand type
        elif op in EQZ_OPS:
            if len(stack) < 1:
                raise Unsupported("wasm-btor2", op, "static stack underflow")
            in_ty = EQZ_OPS[op]
            x_ty = stack.pop()
            if x_ty != in_ty:
                raise Unsupported("wasm-btor2", op, f"operand type {x_ty} != {in_ty}")
            stack.append(T_I32)              # eqz pushes an i32 result
        elif op == OP_SELECT:
            if len(stack) < 3:
                raise Unsupported("wasm-btor2", "select", "static stack underflow")
            c_ty = stack.pop()
            v2_ty = stack.pop()
            v1_ty = stack.pop()
            if c_ty != T_I32:
                raise Unsupported("wasm-btor2", "select", "condition must be i32")
            if v1_ty != v2_ty:
                raise Unsupported("wasm-btor2", "select",
                                  f"operand type mismatch ({v1_ty}, {v2_ty})")
            stack.append(v1_ty)              # result has the operands' type
        else:
            raise Unsupported("wasm-btor2", op)
    return stacks


def _slot_widths(mod: WasmModule, stacks: list[tuple[str, ...]]) -> list[int]:
    """Allocate each physical slot ``j`` at the widest value type it ever holds
    over the body (so an i32-only body keeps every slot at bv32 — byte-for-byte
    unchanged). The post-instruction type at each step is also considered, since
    the last instruction's *result* lands in a slot that no later instruction's
    pre-stack reflects."""
    depth = mod.max_stack
    widths = [32] * depth
    # pre-instruction stacks
    for stack in stacks:
        for j, ty in enumerate(stack):
            widths[j] = max(widths[j], WIDTH[ty])
    # the final post-instruction stack (the body's terminal value types)
    final = list(stacks[0]) if stacks else []
    if mod.body:
        # recompute the terminal stack by replaying the type effect once more
        final = _final_type_stack(mod)
    for j, ty in enumerate(final):
        widths[j] = max(widths[j], WIDTH[ty])
    return widths


def _final_type_stack(mod: WasmModule) -> list[str]:
    """The static value-stack type *after* the whole body (the terminal stack
    type). Used only for slot-width allocation; scope is already validated."""
    stack: list[str] = []
    for ins in mod.body:
        op = ins.op
        if op == OP_I32_CONST:
            stack.append(T_I32)
        elif op == OP_I64_CONST:
            stack.append(T_I64)
        elif op == OP_LOCAL_GET:
            stack.append(mod.local_type(ins.imm))
        elif op in BINOPS:
            _in, out_ty, _k, _f = BINOPS[op]
            stack.pop(); stack.pop()
            stack.append(out_ty)
        elif op in DIVREM_OPS:
            in_ty, _kind = DIVREM_OPS[op]
            stack.pop(); stack.pop()
            stack.append(in_ty)              # div/rem result has the operand type
        elif op in EQZ_OPS:
            stack.pop()
            stack.append(T_I32)
        elif op == OP_SELECT:
            c = stack.pop(); v2 = stack.pop(); v1 = stack.pop()
            stack.append(v1)
    return stack


def _to_width(b: Builder, node: int, src_w: int, dst_w: int) -> int:
    """Zero-extend ``node`` from ``src_w`` up to ``dst_w`` (a no-op when equal).
    A value only ever moves into a slot at least as wide, so no truncation."""
    if src_w == dst_w:
        return node
    return b.uext(dst_w, node, dst_w - src_w)


def _effect(mod: WasmModule, i: int, stack_ty: tuple[str, ...], b: Builder,
            stack: dict[int, int], slot_w: list[int],
            locals_: dict[int, int]) -> Effect:
    """Lower instruction ``i`` (pre-stack types ``stack_ty``) to its next-state
    effect. ``stack[j]`` is the current node holding value-stack slot ``j`` (at
    width ``slot_w[j]``); ``locals_[k]`` the node for local ``k``. The new ``pc``
    is always ``i+1`` (straight-line body). Every written value is zero-extended
    to its destination slot's allocated width."""
    ins = mod.body[i]
    op = ins.op
    h = len(stack_ty)
    nxt = b.constd(32, (i + 1) & MASK32)

    if op == OP_I32_CONST:
        if ins.imm is None:
            raise Unsupported("wasm-btor2", "i32.const", "missing immediate")
        val = b.constd(32, int(ins.imm) & MASK32)
        return Effect(nxt, {h: _to_width(b, val, 32, slot_w[h])})
    if op == OP_I64_CONST:
        if ins.imm is None:
            raise Unsupported("wasm-btor2", "i64.const", "missing immediate")
        val = b.constd(64, int(ins.imm) & ((1 << 64) - 1))
        return Effect(nxt, {h: _to_width(b, val, 64, slot_w[h])})
    if op == OP_LOCAL_GET:
        idx = ins.imm
        if idx is None or idx not in locals_:
            raise Unsupported("wasm-btor2", "local.get", f"index {idx} out of range")
        lw = WIDTH[mod.local_type(idx)]
        return Effect(nxt, {h: _to_width(b, locals_[idx], lw, slot_w[h])})
    if op in BINOPS:
        if h < 2:
            raise Unsupported("wasm-btor2", op, "static stack underflow")
        in_ty, out_ty, _kind, _fn = BINOPS[op]
        w = WIDTH[in_ty]                         # operand width
        # The two operands live in slots h-2 (a, pushed first) and h-1 (b, top);
        # slice each down to its operand width (it equals the slot width unless
        # the slot was widened to hold an i64 elsewhere — then the value sits in
        # the low ``w`` bits, exactly where the source interpreter masks it).
        a = _operand(b, stack[h - 2], slot_w[h - 2], w)
        c = _operand(b, stack[h - 1], slot_w[h - 1], w)
        btor2_op, kind = BTOR2_BINOP[op]
        if kind == "arith":
            val = b.op2(btor2_op, w, a, c)        # bv result (modular 2**w)
            out_w = WIDTH[out_ty]
        elif kind == "shift":
            # Wasm masks the shift amount mod the width; BTOR2 sll/srl/sra do not.
            amt = b.op2("and", w, c, b.constd(w, w - 1))
            val = b.op2(btor2_op, w, a, amt)
            out_w = WIDTH[out_ty]
        else:  # "cmp": a bv1 predicate widened to the i32 result 1/0
            pred = b.op2(btor2_op, 1, a, c)
            val = b.uext(32, pred, 31)            # i32 result at both widths
            out_w = 32
        return Effect(nxt, {h - 2: _to_width(b, val, out_w, slot_w[h - 2])})
    if op in DIVREM_OPS:
        if h < 2:
            raise Unsupported("wasm-btor2", op, "static stack underflow")
        in_ty, kind = DIVREM_OPS[op]
        w = WIDTH[in_ty]                          # operand width (== result width)
        a = _operand(b, stack[h - 2], slot_w[h - 2], w)   # dividend (pushed first)
        c = _operand(b, stack[h - 1], slot_w[h - 1], w)   # divisor (top)
        btor2_op = BTOR2_DIVREM[kind]
        # Trap when the divisor is zero (all four); div_s additionally on the
        # signed overflow INT_MIN / -1 (a == INT_MIN ∧ b == -1). The non-trapping
        # value is the plain BTOR2 op result (sdiv/udiv/srem/urem give the right
        # two's-complement value, including srem INT_MIN%-1 -> 0). On a trap the
        # slot holds the sentinel 0, mirroring the interpreter's frozen stack.
        div_by_zero = b.op2("eq", 1, c, b.zero(w))
        trap_cond = div_by_zero
        if kind == "div_s":
            is_int_min = b.op2("eq", 1, a, b.constd(w, _int_min(w)))
            ones = b.op1("not", w, b.zero(w))    # all-ones == -1 at width w
            is_neg1 = b.op2("eq", 1, c, ones)
            overflow = b.op2("and", 1, is_int_min, is_neg1)
            trap_cond = b.op2("or", 1, div_by_zero, overflow)
        val = b.op2(btor2_op, w, a, c)           # the non-trapping result
        guarded = b.ite(w, trap_cond, b.zero(w), val)
        return Effect(nxt, {h - 2: _to_width(b, guarded, w, slot_w[h - 2])},
                      trap_cond=trap_cond)
    if op in EQZ_OPS:
        if h < 1:
            raise Unsupported("wasm-btor2", op, "static stack underflow")
        w = WIDTH[EQZ_OPS[op]]                    # operand width
        x = _operand(b, stack[h - 1], slot_w[h - 1], w)
        # i{32,64}.eqz x = (x == 0). BTOR2 ``eq`` is bv1; widen to the i32 result
        # (``1``/``0``) with ``uext`` so it stays a value-stack value.
        is_zero = b.op2("eq", 1, x, b.zero(w))
        val = b.uext(32, is_zero, 31)             # i32 result
        return Effect(nxt, {h - 1: _to_width(b, val, 32, slot_w[h - 1])})
    if op == OP_SELECT:
        if h < 3:
            raise Unsupported("wasm-btor2", "select", "static stack underflow")
        # select pops c (top, i32), v2, v1; pushes v1 iff c != 0 else v2. The two
        # values share a type; lower the ite at their common slot width.
        res_ty = stack_ty[h - 3]
        w = WIDTH[res_ty]
        v1 = _operand(b, stack[h - 3], slot_w[h - 3], w)
        v2 = _operand(b, stack[h - 2], slot_w[h - 2], w)
        c = _operand(b, stack[h - 1], slot_w[h - 1], 32)
        cond = b.op2("neq", 1, c, b.zero(32))
        val = b.ite(w, cond, v1, v2)
        return Effect(nxt, {h - 3: _to_width(b, val, w, slot_w[h - 3])})
    raise Unsupported("wasm-btor2", op)


def _operand(b: Builder, node: int, slot_w: int, op_w: int) -> int:
    """Read an operand of width ``op_w`` out of a slot allocated at ``slot_w``.
    The value lives in the low ``op_w`` bits (an i32 value zero-extended into a
    wider slot, or a value at its native width), so slice when the slot is
    wider, else use the node directly."""
    if slot_w == op_w:
        return node
    return b.slice(node, op_w - 1, 0)


def translate(program: dict[str, Any]) -> bytes:
    mod: WasmModule = program["mod"]
    init_locals = program.get("init_locals", {})
    body = mod.body

    stacks = _static_type_stacks(mod)         # also validates scope / types
    depth = mod.max_stack
    slot_w = _slot_widths(mod, stacks)

    # The ``trapped`` state var and its trap edge are emitted *only* when the body
    # can actually trap (it contains a div/rem op). A body with no div/rem reaches
    # no trap edge, so its BTOR2 output stays **byte-for-byte identical** to the
    # prior lowering — the same conditional-emission discipline the slot widths
    # already follow. (``L`` defaults ``trapped`` to False when the field is
    # absent, so the projection still compares it cleanly on a trap-free body.)
    has_trap = any(ins.op in DIVREM_OPS for ins in body)

    b = Builder()
    pc = b.state(32, "pc")
    halted = b.state(1, "halted")
    trapped = b.state(1, "trapped") if has_trap else None
    sp = b.state(32, "sp")                     # value-stack depth (for carry-back)
    locals_ = {
        k: b.state(WIDTH[mod.local_type(k)], f"l{k}") for k in range(mod.nlocals)
    }
    stack = {j: b.state(slot_w[j], f"s{j}") for j in range(depth)}

    b.init(pc, b.constd(32, mod.entry & MASK32))
    b.init(halted, b.zero(1))
    if trapped is not None:
        b.init(trapped, b.zero(1))
    b.init(sp, b.zero(32))
    for k in range(mod.nlocals):
        lw = WIDTH[mod.local_type(k)]
        b.init(locals_[k], b.constd(lw, int(init_locals.get(k, 0)) & ((1 << lw) - 1)))
    for j in range(depth):
        b.init(stack[j], b.zero(slot_w[j]))   # slots start cleared

    not_halted = b.op1("not", 1, halted)
    next_pc = pc
    next_halted = halted
    next_trapped = trapped
    next_sp = sp
    next_stack = dict(stack)

    # The post-instruction stack height for instruction ``i`` — the static stack
    # type a Wasm validator computes (push -> +1, a binop -> -1, eqz -> 0,
    # select -> -2). Scope/underflow already checked in ``_static_type_stacks``.
    def _post_height(i: int) -> int:
        op = body[i].op
        h = len(stacks[i])
        if op in _PRODUCERS:
            return h + 1
        if op in EQZ_OPS:
            return h                          # net 0
        if op == OP_SELECT:
            return h - 2
        return h - 1                          # any binop (net -1)

    for i in range(len(body)):
        eff = _effect(mod, i, stacks[i], b, stack, slot_w, locals_)
        at = b.op2("eq", 1, pc, b.constd(32, i & MASK32))
        active = b.op2("and", 1, at, not_halted)
        next_pc = b.ite(32, active, eff.next_pc, next_pc)
        next_sp = b.ite(32, active, b.constd(32, _post_height(i) & MASK32), next_sp)
        for j, val in eff.stack_writes.items():
            next_stack[j] = b.ite(slot_w[j], active, val, next_stack[j])
        # A div/rem trap (a defined halt edge): when this instruction is active
        # and its trap condition holds, set ``trapped`` (sticky) -- it also forces
        # ``halted`` below. Distinct from the off-the-end halt and the typed
        # ``unsupported`` abort.
        if eff.trap_cond is not None and next_trapped is not None:
            fired = b.op2("and", 1, active, eff.trap_cond)
            next_trapped = b.ite(1, fired, b.one(1), next_trapped)

    # Halt when pc reaches the end of the body (off-the-end -> halt) OR a trap
    # fired, mirroring the interpreter's post-step ``halted`` (a trap implies a
    # halt).
    end = b.constd(32, len(body) & MASK32)
    reached_end = b.op2("eq", 1, next_pc, end)
    next_halted = b.ite(1, reached_end, b.one(1), next_halted)
    if next_trapped is not None:
        next_halted = b.ite(1, next_trapped, b.one(1), next_halted)

    b.next(pc, next_pc)
    b.next(halted, next_halted)
    if trapped is not None:
        b.next(trapped, next_trapped)
    b.next(sp, next_sp)
    for k in range(mod.nlocals):
        b.next(locals_[k], locals_[k])        # locals are read-only in this slice
    for j in range(depth):
        b.next(stack[j], next_stack[j])

    # Optional reachability property -> a ``bad`` signal, so a downstream
    # reasoning bridge (btor2-smtlib) can decide the question. ``top_eq`` asks
    # whether the body's single result value (value-stack slot 0 once halted)
    # equals a constant, compared at slot 0's allocated width.
    prop = program.get("property")
    if prop and "top_eq" in prop:
        if not depth:
            raise Unsupported("wasm-btor2", "property", "empty value stack")
        w0 = slot_w[0]
        val = int(prop["top_eq"]) & ((1 << w0) - 1)
        b.bad(b.op2("and", 1, halted,
                    b.op2("eq", 1, stack[0], b.constd(w0, val))))

    return b.to_text().encode("utf-8")
