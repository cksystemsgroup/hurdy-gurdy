"""WebAssembly -> BTOR2 translator (pairs/wasm-btor2 brief).

Emits a BTOR2 transition system modeling the Wasm i32 stack machine one
instruction per cycle. State: ``pc`` (bv32, the instruction index), ``halted``
(bv1), the locals ``l0..l{N-1}`` (bv32), and a fixed set of value-stack slots
``s0..s{D-1}`` (bv32), where ``D`` is the static maximum stack depth the body
reaches. The fixed body is lowered to a PC-keyed ITE dispatch over the
per-instruction next-state functions, exactly mirroring
``languages/wasm/interp.py`` so the commuting-square oracle cross-checks them.

The value stack's height *before* each instruction is a **static** property of
a straight-line, well-typed Wasm body (a Wasm validator computes exactly this
stack type), so each instruction writes a statically-known slot — no runtime
indexing is needed. ``sp`` is tracked as ordinary state for the projection and
carry-back.

Scope: the i32-stack core. Operand producers ``i32.const`` / ``local.get``; the
conditional ``select`` (``ite(neq(c, 0), v1, v2)``) and the unary comparison
``i32.eqz`` (``uext_31(eq(x, 0))``); and the **i32 binary-operator family**
(``BTOR2_BINOP``), each popping two i32 and pushing one: the arithmetic / bitwise
ops (``add`` / ``sub`` / ``mul`` / ``and`` / ``or`` / ``xor`` at width 32, modular
2³²), the shifts (``sll`` / ``srl`` / ``sra`` with the shift amount masked
``& 31`` to match Wasm's mod-32 rule), and the comparisons (``eq`` / ``neq`` /
``slt`` / ``ult`` / ``sgt`` / ``ugt`` / ``slte`` / ``ulte`` / ``sgte`` / ``ugte``,
each a bv1 predicate widened ``uext_31`` to the i32 result ``1``/``0``). Each
lowering is the single source of truth the interpreter (``I32_BINOPS``) mirrors.
``i32.div_*`` / ``i32.rem_*`` stay out of scope (they need a div-by-zero trap
edge). Every other opcode hard-aborts with ``Unsupported`` (BENCHMARKS.md §3).
Deterministic in ``(mod, init_locals, property)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder
from ...languages.wasm.interp import (
    I32_BINOPS,
    MASK32,
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
    SHIFT_MASK,
    WasmModule,
)

# The per-construct BTOR2 lowering of the i32 binary-operator family — the
# single source of truth mirroring ``languages/wasm/interp.I32_BINOPS``. Each
# entry is ``(btor2_op, kind)`` where ``kind`` selects how the BTOR2 op result
# becomes the pushed i32 value:
#   - "arith": a width-32 ``op2`` whose bv32 result is the value directly
#     (modular 2³², matching the corresponding Wasm rule);
#   - "shift": a width-32 shift whose amount is first masked ``& 31`` (Wasm
#     takes the i32 shift amount mod 32, whereas BTOR2 ``sll/srl/sra`` do not);
#   - "cmp": a bv1 predicate widened with ``uext₃₁`` to the i32 result 1/0.
# ``i32.add`` keeps its existing "arith"/``add`` lowering byte-for-byte.
BTOR2_BINOP: dict[str, tuple[str, str]] = {
    OP_I32_ADD: ("add", "arith"),
    OP_I32_SUB: ("sub", "arith"),
    OP_I32_MUL: ("mul", "arith"),
    OP_I32_AND: ("and", "arith"),
    OP_I32_OR: ("or", "arith"),
    OP_I32_XOR: ("xor", "arith"),
    OP_I32_SHL: ("sll", "shift"),
    OP_I32_SHR_U: ("srl", "shift"),
    OP_I32_SHR_S: ("sra", "shift"),
    OP_I32_EQ: ("eq", "cmp"),
    OP_I32_NE: ("neq", "cmp"),
    OP_I32_LT_S: ("slt", "cmp"),
    OP_I32_LT_U: ("ult", "cmp"),
    OP_I32_GT_S: ("sgt", "cmp"),
    OP_I32_GT_U: ("ugt", "cmp"),
    OP_I32_LE_S: ("slte", "cmp"),
    OP_I32_LE_U: ("ulte", "cmp"),
    OP_I32_GE_S: ("sgte", "cmp"),
    OP_I32_GE_U: ("ugte", "cmp"),
}

# Every binary op the interpreter recognizes must have a BTOR2 lowering (and no
# extras) — a guard so the two sources of truth never drift.
assert set(BTOR2_BINOP) == set(I32_BINOPS), "BTOR2_BINOP must mirror I32_BINOPS"


@dataclass
class Effect:
    """The next-state effect of one instruction at a fixed pre-instruction
    stack height ``h``: a new ``pc`` node and the value-stack slots it writes
    (slot index -> value node)."""

    next_pc: int
    stack_writes: dict[int, int]


def _static_heights(mod: WasmModule) -> list[int]:
    """The value-stack height *before* each instruction (the Wasm static stack
    type). An out-of-scope opcode or a height that would underflow aborts."""
    heights: list[int] = []
    h = 0
    for ins in mod.body:
        heights.append(h)
        if ins.op in (OP_I32_CONST, OP_LOCAL_GET):
            h += 1
        elif ins.op in BTOR2_BINOP:
            if h < 2:
                raise Unsupported("wasm-btor2", ins.op, "static stack underflow")
            h -= 1                               # net -1 (pop 2, push 1)
        elif ins.op == OP_I32_EQZ:
            if h < 1:
                raise Unsupported("wasm-btor2", "i32.eqz", "static stack underflow")
            # net 0 (pop 1, push 1)
        elif ins.op == OP_SELECT:
            if h < 3:
                raise Unsupported("wasm-btor2", "select", "static stack underflow")
            h -= 2
        else:
            raise Unsupported("wasm-btor2", ins.op)
    return heights


def _effect(mod: WasmModule, i: int, h: int, b: Builder,
            stack: dict[int, int], locals_: dict[int, int]) -> Effect:
    """Lower instruction ``i`` (pre-height ``h``) to its next-state effect.

    ``stack[j]`` is the current bv32 node holding value-stack slot ``j``;
    ``locals_[k]`` the node for local ``k``. The new ``pc`` is always ``i+1``
    (straight-line body)."""
    ins = mod.body[i]
    op = ins.op
    nxt = b.constd(32, (i + 1) & MASK32)

    if op == OP_I32_CONST:
        if ins.imm is None:
            raise Unsupported("wasm-btor2", "i32.const", "missing immediate")
        return Effect(nxt, {h: b.constd(32, int(ins.imm) & MASK32)})
    if op == OP_LOCAL_GET:
        idx = ins.imm
        if idx is None or idx not in locals_:
            raise Unsupported("wasm-btor2", "local.get", f"index {idx} out of range")
        return Effect(nxt, {h: locals_[idx]})
    if op in BTOR2_BINOP:
        if h < 2:
            raise Unsupported("wasm-btor2", op, "static stack underflow")
        a = stack[h - 2]                          # second-from-top operand
        c = stack[h - 1]                          # top operand
        btor2_op, kind = BTOR2_BINOP[op]
        if kind == "arith":
            val = b.op2(btor2_op, 32, a, c)        # bv32 result (modular 2³²)
        elif kind == "shift":
            # Wasm masks the i32 shift amount mod 32; BTOR2 sll/srl/sra do not.
            amt = b.op2("and", 32, c, b.constd(32, SHIFT_MASK))
            val = b.op2(btor2_op, 32, a, amt)
        else:  # "cmp": a bv1 predicate widened to the i32 result 1/0
            pred = b.op2(btor2_op, 1, a, c)
            val = b.uext(32, pred, 31)
        return Effect(nxt, {h - 2: val})
    if op == OP_I32_EQZ:
        if h < 1:
            raise Unsupported("wasm-btor2", "i32.eqz", "static stack underflow")
        # i32.eqz x = (x == 0). BTOR2 ``eq`` is bv1; widen to the i32 result
        # (``1``/``0``) with ``uext`` so it stays a value-stack value.
        is_zero = b.op2("eq", 1, stack[h - 1], b.zero(32))
        return Effect(nxt, {h - 1: b.uext(32, is_zero, 31)})
    if op == OP_SELECT:
        if h < 3:
            raise Unsupported("wasm-btor2", "select", "static stack underflow")
        # select pops c (top), v2, v1; pushes v1 iff c != 0 else v2.
        v1 = stack[h - 3]
        v2 = stack[h - 2]
        c = stack[h - 1]
        cond = b.op2("neq", 1, c, b.zero(32))
        return Effect(nxt, {h - 3: b.ite(32, cond, v1, v2)})
    raise Unsupported("wasm-btor2", op)


def translate(program: dict[str, Any]) -> bytes:
    mod: WasmModule = program["mod"]
    init_locals = program.get("init_locals", {})
    body = mod.body

    heights = _static_heights(mod)            # also validates scope / underflow
    depth = mod.max_stack

    b = Builder()
    pc = b.state(32, "pc")
    halted = b.state(1, "halted")
    sp = b.state(32, "sp")                     # value-stack depth (for carry-back)
    locals_ = {k: b.state(32, f"l{k}") for k in range(mod.nlocals)}
    stack = {j: b.state(32, f"s{j}") for j in range(depth)}

    b.init(pc, b.constd(32, mod.entry & MASK32))
    b.init(halted, b.zero(1))
    b.init(sp, b.zero(32))
    for k in range(mod.nlocals):
        b.init(locals_[k], b.constd(32, int(init_locals.get(k, 0)) & MASK32))
    for j in range(depth):
        b.init(stack[j], b.zero(32))          # slots start cleared

    not_halted = b.op1("not", 1, halted)
    next_pc = pc
    next_halted = halted
    next_sp = sp
    next_stack = dict(stack)

    # The post-instruction stack height for instruction ``i`` — the static stack
    # type a Wasm validator computes (push -> +1, an i32 binop -> -1, i32.eqz ->
    # 0, select -> -2). Scope/underflow already checked in ``_static_heights``.
    def _post_height(i: int) -> int:
        op = body[i].op
        if op in (OP_I32_CONST, OP_LOCAL_GET):
            return heights[i] + 1
        if op == OP_I32_EQZ:
            return heights[i]                  # net 0
        if op == OP_SELECT:
            return heights[i] - 2
        return heights[i] - 1                  # any i32 binop (net -1)

    for i in range(len(body)):
        eff = _effect(mod, i, heights[i], b, stack, locals_)
        at = b.op2("eq", 1, pc, b.constd(32, i & MASK32))
        active = b.op2("and", 1, at, not_halted)
        next_pc = b.ite(32, active, eff.next_pc, next_pc)
        next_sp = b.ite(32, active, b.constd(32, _post_height(i) & MASK32), next_sp)
        for j, val in eff.stack_writes.items():
            next_stack[j] = b.ite(32, active, val, next_stack[j])

    # Halt when pc reaches the end of the body (off-the-end -> halt), mirroring
    # the interpreter's post-step ``halted``.
    end = b.constd(32, len(body) & MASK32)
    reached_end = b.op2("eq", 1, next_pc, end)
    next_halted = b.ite(1, reached_end, b.one(1), next_halted)

    b.next(pc, next_pc)
    b.next(halted, next_halted)
    b.next(sp, next_sp)
    for k in range(mod.nlocals):
        b.next(locals_[k], locals_[k])        # locals are read-only in this slice
    for j in range(depth):
        b.next(stack[j], next_stack[j])

    # Optional reachability property -> a ``bad`` signal, so a downstream
    # reasoning bridge (btor2-smtlib) can decide the question. ``top_eq`` asks
    # whether the body's single result value (value-stack slot 0 once halted)
    # equals a constant.
    prop = program.get("property")
    if prop and "top_eq" in prop:
        if not depth:
            raise Unsupported("wasm-btor2", "property", "empty value stack")
        val = int(prop["top_eq"]) & MASK32
        b.bad(b.op2("and", 1, halted,
                    b.op2("eq", 1, stack[0], b.constd(32, val))))

    return b.to_text().encode("utf-8")
