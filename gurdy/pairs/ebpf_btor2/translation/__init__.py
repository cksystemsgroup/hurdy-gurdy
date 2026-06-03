"""eBPF bytecode to BTOR2 translator — P4 implementation.

Compiles ``(EbpfBtor2Spec, bytecode)`` into a layered BTOR2 artifact
for the P1 opcode subset: ALU64 K/X, JMP K/X, and EXIT.

Emits 8 layers per SCHEMA.md §11:
  header, machine, library, dispatch, init, constraint, bad, binding.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.pairs.riscv_btor2.btor2.nodes import Model
from gurdy.pairs.riscv_btor2.btor2.printer import to_text
from gurdy.pairs.riscv_btor2.translation.builder import Builder

from gurdy.pairs.ebpf_btor2.spec import EbpfBtor2Spec, Property, RegisterBound
from gurdy.pairs.ebpf_btor2.source_interp import BpfInsn, decode_program

SCHEMA_VERSION = "1.0.0"
PAIR_ID = "ebpf-btor2"

LAYER_NAMES = (
    "header",
    "machine",
    "library",
    "dispatch",
    "init",
    "constraint",
    "bad",
    "binding",
)

_MASK32 = (1 << 32) - 1
_MASK64 = (1 << 64) - 1
_BPF_CLASS_ALU64 = 0x07
_BPF_CLASS_JMP = 0x05
_BPF_CLASS_JMP32 = 0x06
_BPF_EXIT_OPCODE = 0x95


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass
class _InsnFrame:
    """Per-instruction BTOR2 update expressions (nids), from the library layer."""

    reg_nids: list[int]   # new values of reg_r0..r9 (one nid each)
    insn_idx_nid: int     # new insn_idx value
    halted_nid: int       # new halted value


@dataclass
class _Ctx:
    b: Builder
    spec: EbpfBtor2Spec
    insns: list[BpfInsn]
    reg_state_nids: list[int] = field(default_factory=list)
    insn_idx_nid: int = 0
    halted_nid: int = 0
    frames: list[_InsnFrame] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Layer helpers
# ---------------------------------------------------------------------------


def _layer_begin(b: Builder, name: str) -> None:
    b.comment(f":layer:{name}:begin")


def _layer_end(b: Builder, name: str) -> None:
    b.comment(f":layer:{name}:end")


# ---------------------------------------------------------------------------
# Layer: header — sort declarations
# ---------------------------------------------------------------------------


def _emit_header(ctx: _Ctx) -> None:
    b = ctx.b
    _layer_begin(b, "header")
    b.declare_sort("bv1")
    b.declare_sort("bv32")
    b.declare_sort("bv64")
    _layer_end(b, "header")


# ---------------------------------------------------------------------------
# Layer: machine — state variable declarations
# ---------------------------------------------------------------------------


def _emit_machine(ctx: _Ctx) -> None:
    b = ctx.b
    _layer_begin(b, "machine")
    sort64 = b.declare_sort("bv64")
    sort32 = b.declare_sort("bv32")
    sort1 = b.declare_sort("bv1")
    reg_nids: list[int] = []
    for i in range(10):
        nid = b.emit_no_sort("state", sort64, symbol=f"reg_r{i}")
        reg_nids.append(nid)
    insn_idx_nid = b.emit_no_sort("state", sort32, symbol="insn_idx")
    halted_nid = b.emit_no_sort("state", sort1, symbol="halted")
    ctx.reg_state_nids = reg_nids
    ctx.insn_idx_nid = insn_idx_nid
    ctx.halted_nid = halted_nid
    _layer_end(b, "machine")


# ---------------------------------------------------------------------------
# Layer: library — per-instruction update expressions
# ---------------------------------------------------------------------------


def _emit_library(ctx: _Ctx) -> None:
    b = ctx.b
    _layer_begin(b, "library")
    frames: list[_InsnFrame] = []
    for insn in ctx.insns:
        frames.append(_lower_insn(b, insn, ctx))
    ctx.frames = frames
    _layer_end(b, "library")


def _lower_insn(b: Builder, insn: BpfInsn, ctx: _Ctx) -> _InsnFrame:
    """Emit BTOR2 update expressions for one instruction."""
    reg_nids = list(ctx.reg_state_nids)
    one32 = b.const("bv32", 1)

    if insn.opcode == _BPF_EXIT_OPCODE:
        return _InsnFrame(
            reg_nids=reg_nids,
            insn_idx_nid=ctx.insn_idx_nid,
            halted_nid=b.const("bv1", 1),
        )

    if insn.cls == _BPF_CLASS_ALU64:
        dst = insn.dst_reg
        dst_nid = ctx.reg_state_nids[dst]
        src_nid = _resolve_src64(b, insn, ctx)
        result_nid = _emit_alu64(b, insn.op_nibble, dst_nid, src_nid)
        reg_nids[dst] = result_nid
        new_insn_idx = b.add("bv32", ctx.insn_idx_nid, one32)
        return _InsnFrame(
            reg_nids=reg_nids,
            insn_idx_nid=new_insn_idx,
            halted_nid=ctx.halted_nid,
        )

    if insn.cls == _BPF_CLASS_JMP:
        dst_nid = ctx.reg_state_nids[insn.dst_reg]
        src_nid = _resolve_src64(b, insn, ctx)
        inc_nid = b.add("bv32", ctx.insn_idx_nid, one32)
        off32_nid = b.const("bv32", insn.off & _MASK32)

        if insn.op_nibble == 0x0:  # JA — unconditional
            new_insn_idx = b.add("bv32", inc_nid, off32_nid)
        else:
            cond_nid = _emit_jmp_cond(b, insn.op_nibble, dst_nid, src_nid)
            target_nid = b.add("bv32", inc_nid, off32_nid)
            new_insn_idx = b.ite("bv32", cond_nid, target_nid, inc_nid)

        return _InsnFrame(
            reg_nids=reg_nids,
            insn_idx_nid=new_insn_idx,
            halted_nid=ctx.halted_nid,
        )

    if insn.cls == _BPF_CLASS_JMP32:
        dst32_nid = b.slice("bv32", ctx.reg_state_nids[insn.dst_reg], 31, 0)
        src32_nid = _resolve_src32(b, insn, ctx)
        inc_nid = b.add("bv32", ctx.insn_idx_nid, one32)
        off32_nid = b.const("bv32", insn.off & _MASK32)
        cond_nid = _emit_jmp32_cond(b, insn.op_nibble, dst32_nid, src32_nid)
        target_nid = b.add("bv32", inc_nid, off32_nid)
        new_insn_idx = b.ite("bv32", cond_nid, target_nid, inc_nid)
        return _InsnFrame(
            reg_nids=reg_nids,
            insn_idx_nid=new_insn_idx,
            halted_nid=ctx.halted_nid,
        )

    raise ValueError(
        f"ebpf-btor2/load/0003: unsupported opcode 0x{insn.opcode:02x}"
    )


def _resolve_src64(b: Builder, insn: BpfInsn, ctx: _Ctx) -> int:
    """Return the nid for SRC: immediate (K) or register (X)."""
    if insn.src_flag == 0:
        return b.const("bv64", insn.imm & _MASK64)
    return ctx.reg_state_nids[insn.src_reg]


def _resolve_src32(b: Builder, insn: BpfInsn, ctx: _Ctx) -> int:
    """Return the bv32 nid for SRC in a JMP32 instruction."""
    if insn.src_flag == 0:
        return b.const("bv32", insn.imm & _MASK32)
    return b.slice("bv32", ctx.reg_state_nids[insn.src_reg], 31, 0)


def _emit_alu64(b: Builder, op: int, dst: int, src: int) -> int:
    """Emit the ALU64 result expression for the given op nibble."""
    zero64 = b.const("bv64", 0)
    mask63 = b.const("bv64", 63)
    if op == 0x0:
        return b.add("bv64", dst, src)
    if op == 0x1:
        return b.sub("bv64", dst, src)
    if op == 0x2:
        return b.mul("bv64", dst, src)
    if op == 0x3:  # DIV64: zero divisor → 0
        eq_z = b.eq(src, zero64)
        return b.ite("bv64", eq_z, zero64, b.udiv("bv64", dst, src))
    if op == 0x4:
        return b.or_("bv64", dst, src)
    if op == 0x5:
        return b.and_("bv64", dst, src)
    if op == 0x6:  # LSH64: mask shift to [0,63]
        return b.sll("bv64", dst, b.and_("bv64", src, mask63))
    if op == 0x7:  # RSH64
        return b.srl("bv64", dst, b.and_("bv64", src, mask63))
    if op == 0x8:  # NEG64: src ignored
        return b.neg("bv64", dst)
    if op == 0x9:  # MOD64: zero divisor → DST
        eq_z = b.eq(src, zero64)
        return b.ite("bv64", eq_z, dst, b.urem("bv64", dst, src))
    if op == 0xa:
        return b.xor("bv64", dst, src)
    if op == 0xb:  # MOV64: dst = src
        return src
    if op == 0xc:  # ARSH64
        return b.sra("bv64", dst, b.and_("bv64", src, mask63))
    raise ValueError(f"ebpf-btor2/load/0003: unknown ALU64 op nibble 0x{op:x}")


def _emit_jmp_cond(b: Builder, op: int, dst: int, src: int) -> int:
    """Emit the branch condition for a JMP op nibble (returns bv1 nid)."""
    if op == 0x1:
        return b.eq(dst, src)
    if op == 0x2:
        return b.emit("ugt", "bv1", dst, src)
    if op == 0x3:
        return b.uge(dst, src)
    if op == 0x4:
        and_nid = b.and_("bv64", dst, src)
        return b.neq(and_nid, b.const("bv64", 0))
    if op == 0x5:
        return b.neq(dst, src)
    if op == 0x6:
        return b.sgt(dst, src)
    if op == 0x7:
        return b.sge(dst, src)
    if op == 0xa:
        return b.ult(dst, src)
    if op == 0xb:
        return b.emit("ulte", "bv1", dst, src)
    if op == 0xc:
        return b.slt(dst, src)
    if op == 0xd:
        return b.sle(dst, src)
    raise ValueError(f"ebpf-btor2/load/0003: unknown JMP op nibble 0x{op:x}")


def _emit_jmp32_cond(b: Builder, op: int, dst: int, src: int) -> int:
    """Emit the branch condition for a JMP32 op nibble (bv32 operands, returns bv1 nid)."""
    if op == 0x1:
        return b.eq(dst, src)
    if op == 0x2:
        return b.emit("ugt", "bv1", dst, src)
    if op == 0x3:
        return b.uge(dst, src)
    if op == 0x4:
        and_nid = b.and_("bv32", dst, src)
        return b.neq(and_nid, b.const("bv32", 0))
    if op == 0x5:
        return b.neq(dst, src)
    if op == 0x6:
        return b.sgt(dst, src)
    if op == 0x7:
        return b.sge(dst, src)
    if op == 0xa:
        return b.ult(dst, src)
    if op == 0xb:
        return b.emit("ulte", "bv1", dst, src)
    if op == 0xc:
        return b.slt(dst, src)
    if op == 0xd:
        return b.sle(dst, src)
    raise ValueError(f"ebpf-btor2/load/0003: unknown JMP32 op nibble 0x{op:x}")


# ---------------------------------------------------------------------------
# Layer: dispatch — insn_idx-keyed ITE routing + next clauses
# ---------------------------------------------------------------------------


def _emit_dispatch(ctx: _Ctx) -> None:
    b = ctx.b
    _layer_begin(b, "dispatch")

    n = len(ctx.insns)
    sort64 = b.sort_nids["bv64"]
    sort32 = b.sort_nids["bv32"]
    sort1 = b.sort_nids["bv1"]

    # Build per-instruction equality conditions: eq(insn_idx, i) for i in 0..n-1
    insn_cond_nids: list[int] = []
    for i in range(n):
        i_nid = b.const("bv32", i)
        cond = b.eq(ctx.insn_idx_nid, i_nid)
        insn_cond_nids.append(cond)

    # For each state var: build ite chain (default = freeze, innermost = highest insn_idx),
    # then wrap with halted guard (outermost = highest priority).

    new_reg_nids: list[int] = []
    for r in range(10):
        freeze = ctx.reg_state_nids[r]
        acc = freeze
        for i in range(n - 1, -1, -1):
            acc = b.ite("bv64", insn_cond_nids[i], ctx.frames[i].reg_nids[r], acc)
        final = b.ite("bv64", ctx.halted_nid, freeze, acc)
        new_reg_nids.append(final)

    freeze_idx = ctx.insn_idx_nid
    acc_idx = freeze_idx
    for i in range(n - 1, -1, -1):
        acc_idx = b.ite("bv32", insn_cond_nids[i], ctx.frames[i].insn_idx_nid, acc_idx)
    final_idx = b.ite("bv32", ctx.halted_nid, freeze_idx, acc_idx)

    freeze_h = ctx.halted_nid
    acc_h = freeze_h
    for i in range(n - 1, -1, -1):
        acc_h = b.ite("bv1", insn_cond_nids[i], ctx.frames[i].halted_nid, acc_h)
    final_h = b.ite("bv1", ctx.halted_nid, freeze_h, acc_h)

    for r in range(10):
        b.emit_no_sort("next", sort64, ctx.reg_state_nids[r], new_reg_nids[r])
    b.emit_no_sort("next", sort32, ctx.insn_idx_nid, final_idx)
    b.emit_no_sort("next", sort1, ctx.halted_nid, final_h)

    _layer_end(b, "dispatch")


# ---------------------------------------------------------------------------
# Layer: init — entry-state constraints
# ---------------------------------------------------------------------------


def _emit_init(ctx: _Ctx) -> None:
    b = ctx.b
    _layer_begin(b, "init")
    sort32 = b.sort_nids["bv32"]
    sort1 = b.sort_nids["bv1"]
    zero32 = b.const("bv32", 0)
    zero1 = b.const("bv1", 0)
    b.emit_no_sort("init", sort32, ctx.insn_idx_nid, zero32)
    b.emit_no_sort("init", sort1, ctx.halted_nid, zero1)
    # reg_r0..r9 are free at entry (no init clause) per SCHEMA.md §7.
    _layer_end(b, "init")


# ---------------------------------------------------------------------------
# Layer: constraint — cycle assumptions from spec
# ---------------------------------------------------------------------------


def _emit_constraint(ctx: _Ctx) -> None:
    b = ctx.b
    _layer_begin(b, "constraint")
    for asm in ctx.spec.assumptions:
        if isinstance(asm, RegisterBound):
            reg_nid = ctx.reg_state_nids[asm.reg]
            lo_nid = b.const("bv64", asm.value_lo)
            hi_nid = b.const("bv64", asm.value_hi)
            # ugte(reg, lo) and ulte(reg, hi) — unsigned comparisons per SCHEMA.md §8
            b.emit_no_sort("constraint", b.uge(reg_nid, lo_nid))
            b.emit_no_sort("constraint", b.emit("ulte", "bv1", reg_nid, hi_nid))
    _layer_end(b, "constraint")


# ---------------------------------------------------------------------------
# Layer: bad — property violation expression
# ---------------------------------------------------------------------------


def _emit_bad(ctx: _Ctx) -> None:
    b = ctx.b
    _layer_begin(b, "bad")
    expr_nid = _lower_property(ctx, ctx.spec.property)
    b.emit_no_sort("bad", expr_nid)
    _layer_end(b, "bad")


# Property expression parser — implements SCHEMA.md §9 grammar.

_TOKEN_RE = re.compile(
    r"exit_reached|false|AND|0x[0-9a-fA-F]+|-?\d+|s<=|s>=|s<|s>|<=|>=|==|!=|<|>|r[0-9]|\(|\)"
)


def _lower_property(ctx: _Ctx, prop: Property) -> int:
    tokens = _TOKEN_RE.findall(prop.expression)
    if not tokens:
        return ctx.b.const("bv1", 0)
    nid, pos = _parse_expr(tokens, 0, ctx)
    if pos != len(tokens):
        raise ValueError(
            f"ebpf-btor2/prop/parse: unexpected token {tokens[pos]!r} at position {pos}"
        )
    return nid


def _parse_expr(tokens: list[str], pos: int, ctx: _Ctx) -> tuple[int, int]:
    nid, pos = _parse_atom(tokens, pos, ctx)
    while pos < len(tokens) and tokens[pos] == "AND":
        pos += 1
        rhs, pos = _parse_atom(tokens, pos, ctx)
        nid = ctx.b.and_("bv1", nid, rhs)
    return nid, pos


def _parse_atom(tokens: list[str], pos: int, ctx: _Ctx) -> tuple[int, int]:
    if pos >= len(tokens):
        raise ValueError("ebpf-btor2/prop/parse: unexpected end of expression")
    tok = tokens[pos]
    b = ctx.b

    if tok == "false":
        return b.const("bv1", 0), pos + 1

    if tok == "exit_reached":
        return ctx.halted_nid, pos + 1

    if tok == "(":
        nid, pos = _parse_expr(tokens, pos + 1, ctx)
        if pos >= len(tokens) or tokens[pos] != ")":
            raise ValueError("ebpf-btor2/prop/parse: missing closing paren")
        return nid, pos + 1

    m = re.match(r"^r([0-9])$", tok)
    if m:
        reg_num = int(m.group(1))
        reg_nid = ctx.reg_state_nids[reg_num]
        pos += 1
        if pos >= len(tokens):
            raise ValueError("ebpf-btor2/prop/parse: expected operator after register")
        op_tok = tokens[pos]
        pos += 1
        if pos >= len(tokens):
            raise ValueError("ebpf-btor2/prop/parse: expected value after operator")
        val_tok = tokens[pos]
        pos += 1
        val = int(val_tok, 16) if val_tok.startswith("0x") else int(val_tok)
        val_nid = b.const("bv64", val & _MASK64)
        cmp_nid = _emit_cmp(b, op_tok, reg_nid, val_nid)
        guarded = b.and_("bv1", ctx.halted_nid, cmp_nid)
        return guarded, pos

    raise ValueError(f"ebpf-btor2/prop/parse: unexpected token {tok!r}")


def _emit_cmp(b: Builder, op: str, a: int, val: int) -> int:
    """Emit a comparison returning bv1."""
    if op == "==":   return b.eq(a, val)
    if op == "!=":   return b.neq(a, val)
    if op == "<":    return b.ult(a, val)
    if op == "<=":   return b.emit("ulte", "bv1", a, val)
    if op == ">":    return b.emit("ugt", "bv1", a, val)
    if op == ">=":   return b.uge(a, val)
    if op == "s<":   return b.slt(a, val)
    if op == "s<=":  return b.sle(a, val)
    if op == "s>":   return b.sgt(a, val)
    if op == "s>=":  return b.sge(a, val)
    raise ValueError(f"ebpf-btor2/prop/parse: unknown comparison operator {op!r}")


# ---------------------------------------------------------------------------
# Layer: binding — concrete overrides (reserved for P5+)
# ---------------------------------------------------------------------------


def _emit_binding(ctx: _Ctx) -> None:
    b = ctx.b
    _layer_begin(b, "binding")
    # No concrete binding in P4; emitted empty as a stable layer boundary.
    _layer_end(b, "binding")


# ---------------------------------------------------------------------------
# Layer splitter
# ---------------------------------------------------------------------------


def _split_layers(model: Model) -> dict[str, Layer]:
    """Walk model entries and split on :layer:NAME:begin/:end markers."""
    from gurdy.pairs.riscv_btor2.btor2.nodes import Comment

    layers: dict[str, list] = {n: [] for n in LAYER_NAMES}
    current: str | None = None
    for entry in model.entries:
        if isinstance(entry, Comment) and entry.text.startswith(":layer:"):
            payload = entry.text[len(":layer:"):]
            if payload.endswith(":begin"):
                current = payload[: -len(":begin")]
            elif payload.endswith(":end"):
                current = None
            continue
        if current is not None:
            layers[current].append(entry)

    out: dict[str, Layer] = {}
    for name, entries in layers.items():
        local = Model(entries=entries)
        body = to_text(local).encode("utf-8")
        out[name] = Layer(
            name=name,
            body=body,
            content_hash=hashlib.sha256(body).hexdigest(),
        )
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def translate(
    spec: EbpfBtor2Spec,
    bytecode: bytes,
    annotation_emitter: AnnotationEmitter | None = None,
) -> CompiledArtifact:
    """Compile ``(spec, bytecode)`` to a layered BTOR2 artifact.

    ``bytecode``: flat sequence of 8-byte bpf_insn records (P1 subset).
    ``annotation_emitter``: optional; a fresh sidecar is created if omitted.
    """
    if annotation_emitter is None:
        sidecar = AnnotationSidecar(
            schema_version=SCHEMA_VERSION, spec_hash=spec.spec_hash()
        )
        annotation_emitter = AnnotationEmitter(sidecar)

    insns = decode_program(bytecode)
    b = Builder()
    ctx = _Ctx(b=b, spec=spec, insns=insns)

    _emit_header(ctx)
    _emit_machine(ctx)
    _emit_library(ctx)
    _emit_dispatch(ctx)
    _emit_init(ctx)
    _emit_constraint(ctx)
    _emit_bad(ctx)
    _emit_binding(ctx)

    flattened = to_text(b.model).encode("utf-8")
    layers = _split_layers(b.model)

    return CompiledArtifact(
        pair=PAIR_ID,
        layers=layers,
        annotation=annotation_emitter.sidecar,
        flattened=flattened,
        schema_version=SCHEMA_VERSION,
        spec_hash=spec.spec_hash(),
    )


class Translator:
    """Framework-compatible Translator implementation."""

    def translate(
        self,
        spec: EbpfBtor2Spec,
        source: bytes,
        annotation_emitter: AnnotationEmitter,
    ) -> CompiledArtifact:
        return translate(spec, source, annotation_emitter)


__all__ = [
    "LAYER_NAMES",
    "PAIR_ID",
    "SCHEMA_VERSION",
    "Translator",
    "translate",
]
