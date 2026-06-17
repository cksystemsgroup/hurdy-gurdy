"""eBPF -> BTOR2 translator (pairs/ebpf-btor2 brief).

Emits a BTOR2 transition system modeling the eBPF machine one instruction per
cycle: state ``pc`` (bv64, the instruction index), ``r0``–``r10`` (bv64),
``halted`` (bv1), and — when the program touches data memory — ``mem`` (an
``Array bv64 bv8``). The fixed program is lowered to a PC-keyed ITE dispatch
over the per-instruction next-state functions, exactly mirroring
``languages/ebpf/interp.py`` so the commuting-square oracle cross-checks them.

Scope: the ALU/JMP/load-store core (ALU64 + ALU32, JMP/JMP32 + JA + EXIT,
LDDW, MEM-mode LDX/ST/STX). eBPF's defined edges are reproduced via ITE
guards — unsigned ``DIV`` by zero -> 0, ``MOD`` by zero -> destination
unchanged — and shift counts are masked to the operand width. ``CALL``,
byte-swap, and legacy packet loads hard-abort with ``Unsupported``
(BENCHMARKS.md §3). Deterministic in ``(prog, init_regs)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder
from ...languages.ebpf.interp import MASK32, MASK64, NREG, _decode

# JMP op nibble -> BTOR2 relational operator (the conditional jumps).
_JMP_CMP = {
    0x1: "eq", 0x5: "neq",
    0x2: "ugt", 0x3: "ugte", 0xA: "ult", 0xB: "ulte",
    0x6: "sgt", 0x7: "sgte", 0xC: "slt", 0xD: "slte",
}
_LDST_SIZE = {0x00: 4, 0x08: 2, 0x10: 1, 0x18: 8}


@dataclass
class Effect:
    next_pc: int                                          # node id of next-pc
    writes: dict[int, int] = field(default_factory=dict)  # reg -> value node
    halts: bool = False
    mem_next: int | None = None                           # new mem array node


def _alu_lower(b: Builder, op: int, dst_node: int, src_node: int | None,
               imm: int, use_x: bool, w: int) -> int:
    """Lower one ALU op to a 64-bit result node (32-bit ops zero-extend)."""
    m = (1 << w) - 1

    def k(v: int) -> int:
        return b.constd(w, v & m)

    dw = dst_node if w == 64 else b.slice(dst_node, 31, 0)
    if use_x:
        assert src_node is not None
        x = src_node if w == 64 else b.slice(src_node, 31, 0)
    else:
        x = k(imm & m)

    def ext(node: int) -> int:                            # widen result to bv64
        return node if w == 64 else b.uext(64, node, 32)

    if op == 0x3:                                         # DIV (unsigned); /0 -> 0
        q = b.op2("udiv", w, dw, x)
        return b.ite(64, b.op2("eq", 1, x, k(0)), b.constd(64, 0), ext(q))
    if op == 0x9:                                         # MOD; %0 -> dst unchanged
        r = b.op2("urem", w, dw, x)
        return b.ite(64, b.op2("eq", 1, x, k(0)), dst_node, ext(r))

    shift = lambda name: b.op2(name, w, dw, b.op2("and", w, x, k(w - 1)))  # noqa: E731
    simple = {
        0x0: lambda: b.op2("add", w, dw, x),
        0x1: lambda: b.op2("sub", w, dw, x),
        0x2: lambda: b.op2("mul", w, dw, x),
        0x4: lambda: b.op2("or", w, dw, x),
        0x5: lambda: b.op2("and", w, dw, x),
        0x6: lambda: shift("sll"),
        0x7: lambda: shift("srl"),
        0x8: lambda: b.op1("neg", w, dw),                 # NEG (ignores operand)
        0xA: lambda: b.op2("xor", w, dw, x),
        0xB: lambda: x,                                   # MOV
        0xC: lambda: shift("sra"),                        # ARSH
    }
    if op not in simple:
        raise Unsupported("ebpf-btor2", f"alu.op=0x{op:x}")
    return ext(simple[op]())


def _load(b: Builder, mem: int, addr: int, n: int) -> int:
    res = b.read(8, mem, addr)
    w = 8
    for i in range(1, n):
        byte = b.read(8, mem, b.op2("add", 64, addr, b.constd(64, i)))
        res = b.op2("concat", w + 8, byte, res)
        w += 8
    return res if w == 64 else b.uext(64, res, 64 - w)


def _store(b: Builder, mem: int, addr: int, value: int, n: int) -> int:
    cur = mem
    for i in range(n):
        byte = b.slice(value, 8 * i + 7, 8 * i)
        a_i = addr if i == 0 else b.op2("add", 64, addr, b.constd(64, i))
        cur = b.write(64, 8, cur, a_i, byte)
    return cur


def _effect(insns: list[int], i: int, b: Builder, regs: dict[int, int],
            mem: int | None) -> Effect:
    code, dst, src, off, imm = _decode(insns[i])
    cls = code & 0x07
    op = (code >> 4) & 0x0F
    use_x = bool(code & 0x08)

    def c64(v: int) -> int:
        return b.constd(64, v & MASK64)

    fall = c64(i + 1)

    if cls in (0x04, 0x07):                               # ALU (32) / ALU64
        w = 64 if cls == 0x07 else 32
        val = _alu_lower(b, op, regs[dst], regs[src] if use_x else None, imm, use_x, w)
        return Effect(fall, {dst: val})

    if cls in (0x05, 0x06):                               # JMP / JMP32
        if cls == 0x05 and op == 0x0:                     # JA
            return Effect(c64(i + 1 + off))
        if cls == 0x05 and op == 0x9:                     # EXIT
            return Effect(fall, halts=True)
        if op == 0x8:                                     # CALL
            raise Unsupported("ebpf-btor2", "call")
        w = 64 if cls == 0x05 else 32
        a = regs[dst] if w == 64 else b.slice(regs[dst], 31, 0)
        if use_x:
            rhs = regs[src] if w == 64 else b.slice(regs[src], 31, 0)
        else:
            rhs = b.constd(w, imm & ((1 << w) - 1))
        if op == 0x4:                                     # JSET: (a & b) != 0
            cond = b.op2("neq", 1, b.op2("and", w, a, rhs), b.constd(w, 0))
        elif op in _JMP_CMP:
            cond = b.op2(_JMP_CMP[op], 1, a, rhs)
        else:
            raise Unsupported("ebpf-btor2", f"jmp.op=0x{op:x}")
        return Effect(b.ite(64, cond, c64(i + 1 + off), fall))

    if cls == 0x00:                                       # LD (only LDDW)
        if code == 0x18:
            low = imm & MASK32
            high = (insns[i + 1] >> 32) & MASK32 if i + 1 < len(insns) else 0
            return Effect(c64(i + 2), {dst: c64(low | (high << 32))})
        raise Unsupported("ebpf-btor2", f"ld.code=0x{code:02x}")

    if cls in (0x01, 0x02, 0x03):                         # LDX / ST / STX
        sz = _LDST_SIZE.get(code & 0x18)
        if (code & 0xE0) != 0x60 or sz is None:
            raise Unsupported("ebpf-btor2", f"ldst.code=0x{code:02x}")
        assert mem is not None
        base = dst if cls != 0x01 else src
        addr = b.op2("add", 64, regs[base], c64(off))
        if cls == 0x01:                                   # LDX
            return Effect(fall, {dst: _load(b, mem, addr, sz)})
        value = regs[src] if cls == 0x03 else c64(imm)    # STX uses src, ST uses imm
        return Effect(fall, mem_next=_store(b, mem, addr, value, sz))

    raise Unsupported("ebpf-btor2", f"class={cls}")


def _uses_memory(insns: list[int]) -> bool:
    return any((w & 0x07) in (0x01, 0x02, 0x03) for w in insns)


def translate(program: dict[str, Any]) -> bytes:
    prog = program["prog"]
    init_regs = program.get("init_regs", {})
    insns = prog.insns

    b = Builder()
    pc = b.state(64, "pc")
    regs = {r: b.state(64, f"r{r}") for r in range(NREG)}
    halted = b.state(1, "halted")
    mem = b.state_array(64, 8, "mem") if _uses_memory(insns) else None

    b.init(pc, b.constd(64, prog.entry))
    for r in range(NREG):
        default = prog.stack_top if r == 10 else 0
        b.init(regs[r], b.constd(64, int(init_regs.get(r, default)) & MASK64))
    b.init(halted, b.zero(1))

    # LDDW occupies two slots; the second is pseudo-data, never dispatched.
    skip = {i + 1 for i, w in enumerate(insns) if (w & 0xFF) == 0x18}

    not_halted = b.op1("not", 1, halted)
    next_pc = pc
    next_regs = dict(regs)
    next_halted = halted
    next_mem = mem

    for i in range(len(insns)):
        if i in skip:
            continue
        eff = _effect(insns, i, b, regs, mem)
        at = b.op2("eq", 1, pc, b.constd(64, i))
        active = b.op2("and", 1, at, not_halted)
        next_pc = b.ite(64, active, eff.next_pc, next_pc)
        for r, val in eff.writes.items():
            next_regs[r] = b.ite(64, active, val, next_regs[r])
        if eff.halts:
            next_halted = b.ite(1, active, b.one(1), next_halted)
        if eff.mem_next is not None:
            next_mem = b.ite_array(64, 8, active, eff.mem_next, next_mem)

    b.next(pc, next_pc)
    for r in range(NREG):
        b.next(regs[r], next_regs[r])
    b.next(halted, next_halted)
    if mem is not None:
        b.next_array(mem, next_mem)

    # Optional reachability property -> a `bad` signal, so a downstream
    # reasoning bridge (btor2-smtlib) can decide the question.
    prop = program.get("property")
    if prop and "reg_eq" in prop:
        reg, val = prop["reg_eq"]
        b.bad(b.op2("eq", 1, regs[reg], b.constd(64, int(val) & MASK64)))

    return b.to_text().encode("utf-8")
