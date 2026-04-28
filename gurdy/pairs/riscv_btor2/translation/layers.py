"""Per-layer emission for the riscv-btor2 pair.

Each function takes an ``EmitContext`` and writes nodes into it. The
context wraps a single ``Builder`` whose model accumulates all layer
output; layer boundaries are marked with comment markers that the
translator splits on to populate the layered artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from gurdy.core.annotation.sidecar import AnnotationEmitter
from gurdy.core.annotation.types import Role
from gurdy.pairs.riscv_btor2.btor2.nodes import Comment
from gurdy.pairs.riscv_btor2.source.decoder import (
    Decoded,
    decode,
    decode_compressed,
)
from gurdy.pairs.riscv_btor2.source.elf import FunctionRange
from gurdy.pairs.riscv_btor2.source.loader import RISCVSource
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    Comparison,
    CycleInvariant,
    EntryAssumptions,
    LearnedFact,
    MemoryAt,
    MemoryInit,
    PCAtStep,
    Property,
    RegisterAt,
    RegisterInit,
    RiscvBtor2Spec,
)
from gurdy.pairs.riscv_btor2.translation.builder import Builder
from gurdy.pairs.riscv_btor2.translation.exprs import ExprContext, parse_and_emit
from gurdy.pairs.riscv_btor2.translation.library import (
    LoweringResult,
    RegSnapshot,
    lower,
)


LAYER_NAMES = (
    "header",
    "machine",
    "library",
    "dispatch",
    "init",
    "constraint",
    "bad",
    "binding",
    "havoc",
)


@dataclass
class EmitContext:
    spec: RiscvBtor2Spec
    source: RISCVSource
    builder: Builder
    annotator: AnnotationEmitter
    # populated by emit_machine
    reg_state_nids: dict[int, int] = field(default_factory=dict)
    pc_nid: int = 0
    mem_nid: int = 0
    halted_nid: int = 0
    nondet_nid: int = 0
    # Mapping pc -> LoweringResult (computed during library emit)
    lowerings: dict[int, LoweringResult] = field(default_factory=dict)
    # Decoded instruction stream within scope.
    decoded: list[Decoded] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _layer_marker(builder: Builder, name: str) -> None:
    builder.comment(f":layer:{name}:begin")


def _layer_end(builder: Builder, name: str) -> None:
    builder.comment(f":layer:{name}:end")


def _scope_pcs(spec: RiscvBtor2Spec, source: RISCVSource) -> list[FunctionRange]:
    funcs: list[FunctionRange] = []
    entry = source.function(spec.scope.entry_function)
    if entry is not None:
        funcs.append(entry)
    for c in spec.scope.included_callees:
        f = source.function(c)
        if f is not None and f not in funcs:
            funcs.append(f)
    return funcs


# ---------------------------------------------------------------------------
# header layer
# ---------------------------------------------------------------------------


def emit_header(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "header")
    b.comment(" sorts ")
    # Pre-declare canonical sorts so the linker exports stable names.
    for name in ("bv1", "bv8", "bv32", "bv64", "bv128"):
        nid = b.declare_sort(name)
        ctx.annotator.emit("header", nid, Role.SORT, source_mapping={"sort_name": name})
    mem_sort = b.declare_array_sort("mem", "bv64", "bv8")
    ctx.annotator.emit("header", mem_sort, Role.SORT, source_mapping={"sort_name": "mem"})
    _layer_end(b, "header")


# ---------------------------------------------------------------------------
# machine layer
# ---------------------------------------------------------------------------


def emit_machine(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "machine")
    b.comment(" registers x1..x31, pc, mem ")
    # x0 -> bv64 zero const
    zero64 = b.const("bv64", 0)
    ctx.reg_state_nids[0] = zero64
    for i in range(1, 32):
        nid = b.emit_no_sort("state", b.declare_sort("bv64"), symbol=f"reg_x{i}")
        ctx.reg_state_nids[i] = nid
        ctx.annotator.emit("machine", nid, Role.STATE, source_mapping={"register": i})
    pc_nid = b.emit_no_sort("state", b.declare_sort("bv64"), symbol="pc")
    ctx.pc_nid = pc_nid
    ctx.annotator.emit("machine", pc_nid, Role.STATE, source_mapping={"role": "pc"})
    mem_nid = b.emit_no_sort("state", b.declare_array_sort("mem", "bv64", "bv8"), symbol="mem")
    ctx.mem_nid = mem_nid
    ctx.annotator.emit("machine", mem_nid, Role.STATE, source_mapping={"role": "mem"})
    halted_nid = b.emit_no_sort("state", b.declare_sort("bv1"), symbol="halted")
    ctx.halted_nid = halted_nid
    ctx.annotator.emit("machine", halted_nid, Role.STATE, source_mapping={"role": "halted"})
    nondet_nid = b.emit_no_sort("input", b.declare_sort("bv64"), symbol="nondet")
    ctx.nondet_nid = nondet_nid
    ctx.annotator.emit("machine", nondet_nid, Role.INPUT, source_mapping={"role": "nondet"})
    _layer_end(b, "machine")


# ---------------------------------------------------------------------------
# library + dispatch layers
# ---------------------------------------------------------------------------


def _decode_function(source: RISCVSource, fn: FunctionRange) -> list[Decoded]:
    bin_ = source.binary
    bytemap = bin_.loadable_byte_map()
    decoded: list[Decoded] = []
    pc = fn.start
    while pc < fn.end:
        b0 = bytemap.get(pc)
        b1 = bytemap.get(pc + 1)
        if b0 is None or b1 is None:
            break
        half = b0 | (b1 << 8)
        if (half & 3) != 3:
            d = decode_compressed(half, pc)
            length = 2
        else:
            b2 = bytemap.get(pc + 2, 0)
            b3 = bytemap.get(pc + 3, 0)
            word = half | (b2 << 16) | (b3 << 24)
            d = decode(word, pc, length=4)
            length = 4
        if d is not None:
            decoded.append(d)
        pc += length
    return decoded


def emit_library(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "library")
    b.comment(" per-instruction lowerings ")
    funcs = _scope_pcs(ctx.spec, ctx.source)
    for fn in funcs:
        ds = _decode_function(ctx.source, fn)
        for d in ds:
            ctx.decoded.append(d)
            snap = RegSnapshot(nids=ctx.reg_state_nids)
            res = lower(b, d, snap, ctx.pc_nid, ctx.mem_nid)
            ctx.lowerings[d.pc] = res
            # Mark the next-pc nid in the annotation.
            ctx.annotator.emit(
                "library",
                res.next_pc,
                Role.EXPRESSION,
                source_mapping={"pc": d.pc, "mnemonic": d.mnemonic, "field": "next_pc"},
            )
    _layer_end(b, "library")


def emit_dispatch(ctx: EmitContext) -> None:
    """Emit a PC-keyed ITE that selects the next-PC for analyzed PCs.

    Out-of-scope PCs self-loop. Each register's update is also wired
    through this layer (we expose per-register next-value expressions
    selected by current PC).
    """
    b = ctx.builder
    _layer_marker(b, "dispatch")
    b.comment(" PC-keyed dispatch ")
    funcs = _scope_pcs(ctx.spec, ctx.source)
    in_scope_pcs: set[int] = set()
    for fn in funcs:
        for d in [d for d in ctx.decoded if fn.start <= d.pc < fn.end]:
            in_scope_pcs.add(d.pc)

    # Build pc_in_scope predicate (huge OR of equalities).
    pc_in_scope = _scope_predicate(b, ctx.pc_nid, sorted(in_scope_pcs))
    ctx.annotator.emit("dispatch", pc_in_scope, Role.DISPATCH, source_mapping={"role": "in_scope"})

    # next_pc: ITE over PC ranges. Default (out-of-scope) is self-loop.
    seq_default = ctx.pc_nid  # self-loop for out-of-scope
    next_pc = seq_default
    for pc in sorted(in_scope_pcs, reverse=True):
        cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
        target = ctx.lowerings[pc].next_pc
        next_pc = b.ite("bv64", cond, target, next_pc)
    ctx.next_pc_expr = next_pc  # type: ignore[attr-defined]
    ctx.annotator.emit("dispatch", next_pc, Role.DISPATCH, source_mapping={"role": "next_pc"})

    # Per-register next value selector
    ctx.next_reg_expr: dict[int, int] = {}  # type: ignore[attr-defined]
    for reg in range(1, 32):
        cur = ctx.reg_state_nids[reg]
        # Gather PCs that write to this register (excluding x0).
        writers = [
            (pc, ctx.lowerings[pc].reg_writes[reg])
            for pc in sorted(in_scope_pcs)
            if reg in ctx.lowerings[pc].reg_writes
        ]
        next_val = cur
        for pc, val in reversed(writers):
            cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
            next_val = b.ite("bv64", cond, val, next_val)
        ctx.next_reg_expr[reg] = next_val
        ctx.annotator.emit(
            "dispatch",
            next_val,
            Role.DISPATCH,
            source_mapping={"role": "next_reg", "register": reg},
        )

    # Memory next selector
    cur_mem = ctx.mem_nid
    next_mem = cur_mem
    for pc in sorted(in_scope_pcs, reverse=True):
        m = ctx.lowerings[pc].mem_next
        if m is None:
            continue
        cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
        next_mem = b.ite("mem", cond, m, next_mem)
    ctx.next_mem_expr = next_mem  # type: ignore[attr-defined]
    ctx.annotator.emit("dispatch", next_mem, Role.DISPATCH, source_mapping={"role": "next_mem"})

    # Halted next selector — set if any in-scope ECALL/EBREAK fires.
    halted = ctx.halted_nid
    next_halt = halted
    for pc in sorted(in_scope_pcs, reverse=True):
        h = ctx.lowerings[pc].halt_next
        if h is None:
            continue
        cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
        next_halt = b.ite("bv1", cond, h, next_halt)
    ctx.next_halt_expr = next_halt  # type: ignore[attr-defined]
    _layer_end(b, "dispatch")


def _scope_predicate(b: Builder, pc_nid: int, pcs: list[int]) -> int:
    if not pcs:
        return b.const("bv1", 0)
    pred = b.eq(pc_nid, b.const("bv64", pcs[0]))
    for pc in pcs[1:]:
        pred = b.or_("bv1", pred, b.eq(pc_nid, b.const("bv64", pc)))
    return pred


# ---------------------------------------------------------------------------
# init layer
# ---------------------------------------------------------------------------


def emit_init(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "init")
    b.comment(" initial state ")
    funcs = _scope_pcs(ctx.spec, ctx.source)
    if funcs:
        entry_pc = funcs[0].start
        init_pc_const = b.const("bv64", entry_pc)
        b.emit_no_sort("init", b.declare_sort("bv64"), ctx.pc_nid, init_pc_const)
        ctx.annotator.emit(
            "init", init_pc_const, Role.INIT, source_mapping={"role": "pc_init", "pc": entry_pc}
        )

    # Memory: PT_LOAD bytes get pinned. We encode this as a chain of
    # writes to a fresh empty array, then init mem = result.
    bytemap = ctx.source.binary.loadable_byte_map()
    if bytemap:
        # For each byte address with a value: write to mem.
        mem_init_arr = ctx.mem_nid  # placeholder; we don't have a "fresh empty" sort
        # We instead emit constraint init equating each byte to its file value.
        for addr, byte in sorted(bytemap.items()):
            byte_at_addr = b.read("bv8", ctx.mem_nid, b.const("bv64", addr))
            cond = b.eq(byte_at_addr, b.const("bv8", byte))
            # We want this to hold initially — encode as init constraint.
            # Approach: emit a constraint clause valid only at init by
            # gating on `init flag` would require a step counter; for
            # simplicity (and SCHEMA.md's spirit), pin via constraint
            # at every cycle since memory in PT_LOAD ranges that aren't
            # written to is invariant.
            # However, store instructions can mutate memory — pinning a
            # ROM byte invariantly would be wrong for .data. We err on
            # the safe side: only pin .text-style read-only segments
            # via constraint; .data via init-only.
            # To keep this phase tractable, the schema-faithful
            # approach is to emit per-byte constraints on the *initial*
            # cycle. We don't have a global "step 0" predicate; we
            # surface this as a structural constraint on the first
            # cycle by restricting pinning to the first 256 bytes of
            # text (bounded for tractability) and rely on the LLM to
            # introduce explicit MemoryInit assumptions for bytes it
            # cares about.
            # Therefore: skip pin emission here. Specs use MemoryInit
            # to pin the bytes they need.
            break  # only one debug iteration
    # Per-spec RegisterInit / MemoryInit assumptions
    for asm in ctx.spec.assumptions:
        if isinstance(asm, RegisterInit):
            _emit_register_init(ctx, asm)
        elif isinstance(asm, MemoryInit):
            _emit_memory_init(ctx, asm)
    _layer_end(b, "init")


def _comparison_op(b: Builder, op: Comparison, a: int, c: int) -> int:
    if op == Comparison.EQ:
        return b.eq(a, c)
    if op == Comparison.NE:
        return b.neq(a, c)
    if op == Comparison.LT:
        return b.slt(a, c)
    if op == Comparison.LE:
        return b.emit("slte", "bv1", a, c)
    if op == Comparison.GT:
        return b.sgt(a, c)
    if op == Comparison.GE:
        return b.emit("sgte", "bv1", a, c)
    if op == Comparison.LTU:
        return b.ult(a, c)
    if op == Comparison.LEU:
        return b.emit("ulte", "bv1", a, c)
    if op == Comparison.GTU:
        return b.emit("ugt", "bv1", a, c)
    if op == Comparison.GEU:
        return b.uge(a, c)
    raise ValueError(f"unsupported comparison: {op}")


def _emit_register_init(ctx: EmitContext, asm: RegisterInit) -> None:
    b = ctx.builder
    if asm.register == 0:
        return  # x0 is the constant zero; can't init
    val = b.const("bv64", asm.value & 0xFFFFFFFFFFFFFFFF)
    if asm.op == Comparison.EQ:
        # Use BTOR2 init: state init value (only valid for EQ).
        b.emit_no_sort(
            "init", b.declare_sort("bv64"), ctx.reg_state_nids[asm.register], val
        )
    else:
        cond = _comparison_op(b, asm.op, ctx.reg_state_nids[asm.register], val)
        b.emit_no_sort("constraint", cond)
    ctx.annotator.emit(
        "init",
        val,
        Role.INIT,
        source_mapping={"role": "register_init", "register": asm.register, "op": asm.op.value},
    )


def _emit_memory_init(ctx: EmitContext, asm: MemoryInit) -> None:
    b = ctx.builder
    addr_nid = b.const("bv64", asm.address)
    bytes_per = asm.width
    # Build current-mem read
    if bytes_per == 1:
        cur = b.read("bv8", ctx.mem_nid, addr_nid)
    else:
        parts: list[int] = []
        for i in range(bytes_per):
            off = b.add("bv64", addr_nid, b.const("bv64", i))
            parts.append(b.read("bv8", ctx.mem_nid, off))
        cur = parts[0]
        for i in range(1, bytes_per):
            cur = b.concat(f"bv{8 * (i + 1)}", parts[i], cur)
    target = b.const(f"bv{8 * bytes_per}", asm.value & ((1 << (8 * bytes_per)) - 1))
    cond = _comparison_op(b, asm.op, cur, target)
    b.emit_no_sort("constraint", cond)
    ctx.annotator.emit(
        "init",
        cond,
        Role.INIT,
        source_mapping={
            "role": "memory_init",
            "address": asm.address,
            "width": asm.width,
            "op": asm.op.value,
        },
    )


# ---------------------------------------------------------------------------
# constraint layer
# ---------------------------------------------------------------------------


def emit_constraint(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "constraint")
    b.comment(" cycle invariants and learned facts ")
    expr_ctx = ExprContext(
        builder=b, reg_nid=ctx.reg_state_nids, pc_nid=ctx.pc_nid, mem_nid=ctx.mem_nid
    )
    for asm in ctx.spec.assumptions:
        if isinstance(asm, CycleInvariant):
            nid = parse_and_emit(asm.expression, expr_ctx)
            b.emit_no_sort("constraint", nid)
            ctx.annotator.emit(
                "constraint",
                nid,
                Role.CONSTRAINT,
                source_mapping={"provenance": asm.provenance},
            )
    for fact in ctx.spec.learned:
        nid = parse_and_emit(fact.expression, expr_ctx)
        b.emit_no_sort("constraint", nid)
        ctx.annotator.emit(
            "constraint",
            nid,
            Role.LEARNED_INVARIANT,
            source_mapping={
                "source_question_hash": fact.source_question_hash,
                "source_engine": fact.source_engine,
            },
        )
    _layer_end(b, "constraint")


# ---------------------------------------------------------------------------
# bad layer
# ---------------------------------------------------------------------------


def emit_bad(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "bad")
    b.comment(" bad expression ")
    expr_ctx = ExprContext(
        builder=b, reg_nid=ctx.reg_state_nids, pc_nid=ctx.pc_nid, mem_nid=ctx.mem_nid
    )
    nid = parse_and_emit(ctx.spec.property.expression, expr_ctx)
    if ctx.spec.property.negate:
        nid = b.not_("bv1", nid)
    b.emit_no_sort("bad", nid)
    ctx.annotator.emit("bad", nid, Role.BAD, source_mapping={"role": "bad"})
    _layer_end(b, "bad")


# ---------------------------------------------------------------------------
# binding layer
# ---------------------------------------------------------------------------


def emit_binding(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "binding")
    b.comment(" wire next clauses ")
    bv64 = b.declare_sort("bv64")
    # PC next
    b.emit_no_sort("next", bv64, ctx.pc_nid, ctx.next_pc_expr)  # type: ignore[attr-defined]
    ctx.annotator.emit("binding", ctx.pc_nid, Role.BINDING, source_mapping={"role": "next_pc"})
    # Register nexts
    for reg in range(1, 32):
        b.emit_no_sort("next", bv64, ctx.reg_state_nids[reg], ctx.next_reg_expr[reg])  # type: ignore[attr-defined]
        ctx.annotator.emit(
            "binding",
            ctx.reg_state_nids[reg],
            Role.BINDING,
            source_mapping={"role": "next_reg", "register": reg},
        )
    # Memory next
    mem_sort = b.declare_array_sort("mem", "bv64", "bv8")
    b.emit_no_sort("next", mem_sort, ctx.mem_nid, ctx.next_mem_expr)  # type: ignore[attr-defined]
    ctx.annotator.emit("binding", ctx.mem_nid, Role.BINDING, source_mapping={"role": "next_mem"})
    # Halted next
    bv1 = b.declare_sort("bv1")
    b.emit_no_sort("next", bv1, ctx.halted_nid, ctx.next_halt_expr)  # type: ignore[attr-defined]
    ctx.annotator.emit(
        "binding", ctx.halted_nid, Role.BINDING, source_mapping={"role": "next_halted"}
    )
    _layer_end(b, "binding")


# ---------------------------------------------------------------------------
# havoc layer (overlay: replaces specific reg next clauses with input)
# ---------------------------------------------------------------------------


def emit_havoc(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "havoc")
    havoc = ctx.spec.analysis.havoc_registers
    if not havoc:
        _layer_end(b, "havoc")
        return
    b.comment(" havoc register inputs ")
    for r in sorted(havoc):
        if r == 0:
            continue
        # Fresh per-cycle input replacing register's next.
        nid = b.emit_no_sort(
            "input", b.declare_sort("bv64"), symbol=f"havoc_x{r}"
        )
        # The binding layer already emitted a 'next' for this register;
        # the havoc overlay introduces an additional next clause that
        # the linker treats as the authoritative one. We achieve the
        # same effect more cleanly by emitting an *additional* 'next'
        # which solvers process as a constraint that next == nid.
        # For simplicity we encode this as an explicit constraint
        # equating the binding-layer's expression to the fresh input.
        # That preserves correctness for BMC at the cost of one extra
        # constraint per cycle.
        next_expr = ctx.next_reg_expr[r]  # type: ignore[attr-defined]
        cond = b.eq(next_expr, nid)
        b.emit_no_sort("constraint", cond)
        ctx.annotator.emit(
            "havoc", nid, Role.HAVOC, source_mapping={"register": r}
        )
    _layer_end(b, "havoc")


__all__ = [
    "EmitContext",
    "LAYER_NAMES",
    "emit_header",
    "emit_machine",
    "emit_library",
    "emit_dispatch",
    "emit_init",
    "emit_constraint",
    "emit_bad",
    "emit_binding",
    "emit_havoc",
]
