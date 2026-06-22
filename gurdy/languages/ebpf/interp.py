"""A deterministic eBPF interpreter (the shared eBPF source interpreter).

Scope (thin-first, widened — languages/ebpf brief): the arithmetic / jump /
load-store core of the eBPF ISA over an 11-register machine (``r0``–``r10``,
``r10`` the frame pointer): ALU64 and ALU (32-bit) reg/imm forms, the byte-swap
(``END``) ops, the conditional jumps (JMP / JMP32) plus ``JA`` and ``EXIT``,
``LDDW``, the ``MEM``-mode loads/stores, and the legacy ``ABS``/``IND`` packet
loads (the classic socket-filter big-endian reads into ``r0``). ``CALL``
(helper calls) still hard-aborts with ``Unsupported`` (BENCHMARKS.md §3); the
recommended external oracle is CertrBPF.

eBPF's *defined* edges (the kernel/RFC-9669 conventions that C leaves
undefined) are honored: unsigned ``DIV`` by zero yields ``0``; ``MOD`` by
zero leaves the destination unchanged; shift counts are masked to the operand
width. A packet load whose ``offset + size`` exceeds the packet length takes
the **defined drop edge** — ``r0`` is cleared and the program halts (the
classic socket filter's "drop the packet" return), kept distinct from the
typed ``unsupported`` abort. Behavior is a ``Trace`` of post-step
``{"pc", "r0".."r10", "halted"}`` states. Pure and deterministic; ``pc`` is an
instruction index (``LDDW`` occupies two slots).

Interpreter version (the shared deliverable's contract — AGENTS.md §3): a
versioned bump is required for any additive semantics change so dependent
pairs re-validate their square.
- ``0.3`` — added the legacy ``ABS``/``IND`` packet loads (``LD|ABS|{B,H,W}``
  and ``LD|IND|{B,H,W}``): big-endian reads from a packet array into ``r0``,
  with an out-of-bounds access taking the defined drop edge (``r0``=0, halt).
- ``0.2`` — added byte-swap (``BPF_END``: ``le``/``be`` on ALU,
  ``bswap`` on ALU64) over a fixed **little-endian host** model (RFC 9669
  §"Byte swap instructions").
- ``0.1`` — ALU/JMP/load-store core (initial vertical slice).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace

INTERP_VERSION = "0.3"  # AGENTS.md §3: bumped when ABS/IND packet loads were added.

MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1
NREG = 11
STACK_TOP = 512


def _u64(v: int) -> int:
    return v & MASK64


def _sext(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    if v >> (bits - 1):
        v -= 1 << bits
    return v


@dataclass
class BpfProgram:
    """A loaded eBPF program: a list of 64-bit instruction words (``pc`` indexes
    this list), an initial data memory (byte address -> byte), the initial frame
    pointer ``r10``, and the packet the legacy ``ABS``/``IND`` loads read from
    (``pkt``: byte index -> byte; ``pkt_len`` is its length, the bounds the drop
    edge is checked against)."""

    insns: list[int] = field(default_factory=list)
    mem: dict[int, int] = field(default_factory=dict)
    stack_top: int = STACK_TOP
    entry: int = 0
    pkt: dict[int, int] = field(default_factory=dict)
    pkt_len: int = 0

    def load(self, addr: int, nbytes: int) -> int:
        value = 0
        for i in range(nbytes):
            value |= self.mem.get(_u64(addr + i), 0) << (8 * i)
        return value

    def store(self, addr: int, nbytes: int, value: int) -> None:
        for i in range(nbytes):
            self.mem[_u64(addr + i)] = (value >> (8 * i)) & 0xFF

    def pkt_load_be(self, addr: int, nbytes: int) -> int:
        """Read ``nbytes`` from the packet at ``addr`` in **big-endian**
        (network) order — the classic socket-filter convention. ``addr`` is an
        unsigned 64-bit index; the caller has already checked bounds
        (``pkt_in_bounds``)."""
        value = 0
        for i in range(nbytes):
            value = (value << 8) | (self.pkt.get(addr + i, 0) & 0xFF)
        return value

    def pkt_in_bounds(self, addr: int, nbytes: int) -> bool:
        """``addr < pkt_len and addr + nbytes <= pkt_len`` over the unsigned
        64-bit ``addr`` — the exact two-conjunct form the bv64 translation
        mirrors (a wrapped negative offset is a huge ``addr`` the first conjunct
        rejects)."""
        return addr < self.pkt_len and addr + nbytes <= self.pkt_len


def program_from_words(words: list[int], mem: dict[int, int] | None = None,
                       stack_top: int = STACK_TOP,
                       pkt: list[int] | dict[int, int] | None = None) -> BpfProgram:
    pkt_bytes = list(pkt) if pkt is not None else []
    pkt_map = {i: (b & 0xFF) for i, b in enumerate(pkt_bytes)}
    return BpfProgram(insns=list(words), mem=dict(mem or {}), stack_top=stack_top,
                      pkt=pkt_map, pkt_len=len(pkt_bytes))


def _decode(insn: int) -> tuple[int, int, int, int, int]:
    code = insn & 0xFF
    dst = (insn >> 8) & 0x0F
    src = (insn >> 12) & 0x0F
    off = _sext((insn >> 16) & 0xFFFF, 16)
    imm = _sext((insn >> 32) & 0xFFFFFFFF, 32)
    return code, dst, src, off, imm


def _alu(op: int, dst_full: int, d: int, x: int, w: int) -> int:
    """One ALU op at width ``w`` over masked operands; result fills the 64-bit
    register (32-bit ops zero-extend, the kernel convention)."""
    m = (1 << w) - 1
    sh = x & (w - 1)
    if op == 0x0:                       # ADD
        return (d + x) & m
    if op == 0x1:                       # SUB
        return (d - x) & m
    if op == 0x2:                       # MUL
        return (d * x) & m
    if op == 0x3:                       # DIV (unsigned); /0 -> 0
        return 0 if x == 0 else (d // x) & m
    if op == 0x4:                       # OR
        return (d | x) & m
    if op == 0x5:                       # AND
        return (d & x) & m
    if op == 0x6:                       # LSH
        return (d << sh) & m
    if op == 0x7:                       # RSH (logical)
        return (d >> sh) & m
    if op == 0x8:                       # NEG
        return (-d) & m
    if op == 0x9:                       # MOD (unsigned); %0 -> dst unchanged
        return dst_full if x == 0 else (d % x) & m
    if op == 0xA:                       # XOR
        return (d ^ x) & m
    if op == 0xB:                       # MOV
        return x & m
    if op == 0xC:                       # ARSH (arithmetic)
        return (_sext(d, w) >> sh) & m
    raise Unsupported("ebpf", f"alu.op=0x{op:x}")


def byteswap(value: int, width: int) -> int:
    """Reverse the low ``width`` bits' bytes, zero-extended into 64 bits.

    The byte-swap source of truth (mirrored by the translator). ``width`` is
    16, 32, or 64. Operates on a fixed little-endian host model: ``be``/``bswap``
    reorder the low ``width//8`` bytes; ``le`` (the no-reorder twin) is just the
    width truncation ``value & ((1 << width) - 1)``.
    """
    nbytes = width // 8
    out = 0
    for i in range(nbytes):
        byte = (value >> (8 * i)) & 0xFF
        out |= byte << (8 * (nbytes - 1 - i))
    return out


def _end(src_x: bool, cls: int, dst: int, width: int) -> int:
    """One ``BPF_END`` (byte-swap) op -> the new 64-bit destination value.

    ALU class: ``src_x`` selects direction — ``to_le`` (no reorder on a LE host)
    vs ``to_be`` (byteswap). ALU64 class: unconditional ``bswap`` (``src_x``
    must be 0, RFC 9669). All results zero-extend into the 64-bit register.
    """
    if width not in (16, 32, 64):
        raise Unsupported("ebpf", f"end.width={width}")
    if cls == 0x07:                         # ALU64: unconditional bswap
        if src_x:
            raise Unsupported("ebpf", "end.alu64.src_x")
        return byteswap(dst, width)
    if src_x:                               # ALU to_be: byteswap
        return byteswap(dst, width)
    return dst & ((1 << width) - 1)         # ALU to_le: truncate (LE host)


def _jump_taken(op: int, a: int, b: int, w: int) -> bool:
    sa, sb = _sext(a, w), _sext(b, w)
    table = {
        0x1: a == b, 0x5: a != b,
        0x2: a > b, 0x3: a >= b, 0xA: a < b, 0xB: a <= b,
        0x6: sa > sb, 0x7: sa >= sb, 0xC: sa < sb, 0xD: sa <= sb,
        0x4: (a & b) != 0,
    }
    if op not in table:
        raise Unsupported("ebpf", f"jmp.op=0x{op:x}")
    return table[op]


_LDST_SIZE = {0x00: 4, 0x08: 2, 0x10: 1, 0x18: 8}
# Legacy packet-load sizes (LD class, ABS/IND modes): W/H/B only (no double).
_PKT_SIZE = {0x00: 4, 0x08: 2, 0x10: 1}
_LD_ABS = 0x20  # code & 0xE0: absolute offset = imm
_LD_IND = 0x40  # code & 0xE0: indirect offset = regs[src] + imm


def _execute(insns: list[int], pc: int, regs: list[int], prog: BpfProgram) -> tuple[int, bool]:
    code, dst, src, off, imm = _decode(insns[pc])
    cls = code & 0x07
    op = (code >> 4) & 0x0F
    use_x = bool(code & 0x08)
    nxt = pc + 1

    if cls in (0x04, 0x07):                          # ALU (32) / ALU64
        if op == 0xD:                                # BPF_END (byte-swap)
            regs[dst] = _end(use_x, cls, regs[dst], imm)
            return nxt, False
        w = 64 if cls == 0x07 else 32
        m = (1 << w) - 1
        x = (regs[src] & m) if use_x else (_u64(imm) & m)
        regs[dst] = _alu(op, regs[dst], regs[dst] & m, x, w)
        return nxt, False

    if cls in (0x05, 0x06):                          # JMP / JMP32
        if cls == 0x05 and op == 0x0:                # JA
            return pc + 1 + off, False
        if cls == 0x05 and op == 0x9:                # EXIT
            return nxt, True
        if op == 0x8:                                # CALL
            raise Unsupported("ebpf", "call")
        w = 64 if cls == 0x05 else 32
        m = (1 << w) - 1
        a = regs[dst] & m
        b = (regs[src] & m) if use_x else (_u64(imm) & m)
        return (pc + 1 + off if _jump_taken(op, a, b, w) else nxt), False

    if cls == 0x00:                                  # LD: LDDW / packet loads
        if code == 0x18:                             # LDDW (64-bit immediate)
            low = imm & MASK32
            high = (insns[pc + 1] >> 32) & MASK32 if pc + 1 < len(insns) else 0
            regs[dst] = (low | (high << 32)) & MASK64
            return pc + 2, False
        mode = code & 0xE0
        sz = _PKT_SIZE.get(code & 0x18)
        if mode in (_LD_ABS, _LD_IND) and sz is not None:   # legacy packet load -> r0
            # ABS: addr = imm; IND: addr = imm + regs[src]. The address is 64-bit
            # register arithmetic (``imm`` already sign-extended by _decode), so
            # it wraps mod 2**64 exactly as the bv64 translation does; a negative
            # source offset wraps to a huge value the unsigned bound rejects.
            addr = (imm + (regs[src] if mode == _LD_IND else 0)) & MASK64
            if not prog.pkt_in_bounds(addr, sz):            # defined drop edge
                regs[0] = 0
                return nxt, True
            regs[0] = prog.pkt_load_be(addr, sz)
            return nxt, False
        raise Unsupported("ebpf", f"ld.code=0x{code:02x}")

    if cls in (0x01, 0x02, 0x03):                    # LDX / ST / STX (MEM mode)
        sz = _LDST_SIZE.get(code & 0x18)
        if (code & 0xE0) != 0x60 or sz is None:
            raise Unsupported("ebpf", f"ldst.code=0x{code:02x}")
        if cls == 0x01:                              # LDX: dst = *(sz*)(src+off)
            regs[dst] = prog.load(_u64(regs[src] + off), sz)
        elif cls == 0x03:                            # STX: *(sz*)(dst+off) = src
            prog.store(_u64(regs[dst] + off), sz, regs[src])
        else:                                        # ST: *(sz*)(dst+off) = imm
            prog.store(_u64(regs[dst] + off), sz, _u64(imm))
        return nxt, False

    raise Unsupported("ebpf", f"class={cls}")


def _state(pc: int, regs: list[int], halted: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"pc": pc, "halted": halted}
    for r in range(NREG):
        s[f"r{r}"] = regs[r]
    return s


def run(
    prog: BpfProgram,
    binding: dict[str, Any] | None = None,
    max_steps: int = 100_000,
    **_kw: Any,
) -> Trace:
    """Run ``prog`` to a halt (``EXIT``, off-the-end, or ``max_steps``).

    ``binding`` may set ``pc``, initial ``regs`` (``{index: value}``), a
    starting ``mem`` (byte map), and the ``pkt`` the legacy packet loads read
    (a byte list, or a ``{index: byte}`` map with an explicit ``pkt_len``).
    Returns the post-step trace.
    """
    regs = [0] * NREG
    regs[10] = prog.stack_top
    pc = prog.entry
    if binding:
        pc = binding.get("pc", pc)
        for r, v in binding.get("regs", {}).items():
            regs[int(r)] = _u64(int(v))
        if "mem" in binding or "pkt" in binding:
            mem = binding.get("mem", prog.mem)
            if "pkt" in binding:
                src = binding["pkt"]
                if isinstance(src, dict):
                    pkt = {int(k): int(v) & 0xFF for k, v in src.items()}
                    pkt_len = int(binding.get("pkt_len", (max(pkt) + 1) if pkt else 0))
                else:
                    pkt = {i: (b & 0xFF) for i, b in enumerate(src)}
                    pkt_len = len(list(src))
            else:
                pkt, pkt_len = prog.pkt, prog.pkt_len
            prog = BpfProgram(prog.insns, dict(mem), prog.stack_top, prog.entry,
                              dict(pkt), pkt_len)

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (0 <= pc < len(prog.insns)):
            trace.append(_state(pc, regs, True))      # ran off the end -> halt
            break
        pc, halt = _execute(prog.insns, pc, regs, prog)
        steps += 1
        trace.append(_state(pc, regs, halt))
        if halt:
            break
    return trace
