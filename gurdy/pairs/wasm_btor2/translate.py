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

Scope: the i32-stack core (``i32.const``, ``local.get``, ``i32.add``).
``i32.add`` is BTOR2 ``add`` at width 32 (modular 2^32, matching the Wasm
``iadd_32`` rule). Every other opcode hard-aborts with ``Unsupported``
(BENCHMARKS.md §3). Deterministic in ``(mod, init_locals, property)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder
from ...languages.wasm.interp import (
    MASK32,
    OP_I32_ADD,
    OP_I32_CONST,
    OP_LOCAL_GET,
    WasmModule,
)


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
        elif ins.op == OP_I32_ADD:
            if h < 2:
                raise Unsupported("wasm-btor2", "i32.add", "static stack underflow")
            h -= 1
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
    if op == OP_I32_ADD:
        if h < 2:
            raise Unsupported("wasm-btor2", "i32.add", "static stack underflow")
        a = stack[h - 2]
        c = stack[h - 1]
        return Effect(nxt, {h - 2: b.op2("add", 32, a, c)})
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

    # The post-instruction stack height for instruction ``i`` (push -> +1,
    # i32.add -> -1) — the static stack type a Wasm validator computes.
    def _post_height(i: int) -> int:
        op = body[i].op
        if op in (OP_I32_CONST, OP_LOCAL_GET):
            return heights[i] + 1
        return heights[i] - 1                  # OP_I32_ADD (scope-checked above)

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
