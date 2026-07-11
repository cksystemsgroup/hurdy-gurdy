"""EVM -> BTOR2 translator (pairs/evm-btor2 brief).

Emits a BTOR2 transition system modeling the EVM stack machine one opcode per
cycle: state ``pc`` (bv256, a *byte* offset into the bytecode), a bounded
operand stack ``s0..s{N-1}`` (bv256 each), the stack depth ``sp`` (bv256, the
number of live items), ``halted`` (bv1), and the **halt-status** ``status``
(bv8, v0.9 — running / success / revert / exceptional). The fixed bytecode is
lowered to a PC-keyed ITE dispatch over the per-opcode next-state functions,
exactly mirroring ``languages/evm/interp.py`` so the commuting-square oracle
cross-checks them.

Scope (pure stack/arithmetic slice): the full push family ``PUSH1`` (0x60) ..
``PUSH32`` (0x7f) and ``PUSH0`` (0x5f, the constant-0 push), the binary
arithmetic ``ADD`` (0x01) / ``MUL`` (0x02) /
``SUB`` (0x03), the unsigned ``DIV`` (0x04) / ``MOD`` (0x06) and the signed
``SDIV`` (0x05) / ``SMOD`` (0x07), the stack shuffles ``POP`` (0x50), the
duplications ``DUP1`` (0x80) .. ``DUP16`` (0x8f), the swaps ``SWAP1`` (0x90) ..
``SWAP16`` (0x9f), ``STOP`` (0x00), and the terminal/halt ops ``RETURN`` (0xf3)
/ ``REVERT`` (0xfd) / ``INVALID`` (0xfe) over 256-bit words. ``DIV`` / ``MOD``
lower with an explicit EVM by-zero guard —
``DIV(a,b) = ite(b==0, 0, udiv(a,b))`` and ``MOD(a,b) = ite(b==0, 0, urem(a,b))``
— because the BTOR2 ``udiv`` / ``urem`` carry the *SMT* by-zero convention
(all-ones / dividend), not EVM's ``= 0``. The signed ``SDIV`` / ``SMOD`` lower
over BTOR2 ``sdiv`` / ``srem`` with explicit guards —
``SDIV(a,b) = ite(b==0, 0, ite(a==INT_MIN ∧ b==-1, INT_MIN, sdiv(a,b)))`` and
``SMOD(a,b) = ite(b==0, 0, srem(a,b))`` (``INT_MIN = 2**255``, ``-1`` = all-ones)
— recovering EVM's by-zero ``= 0`` and the ``INT_MIN / -1`` wrap from BTOR2's SMT
``sdiv`` / ``srem`` conventions. ``DUP{n}`` copies the n-th item from
the top (``s{sp-n}``) onto ``s{sp}``; ``SWAP{n}`` swaps the top ``s{sp-1}`` with
``s{sp-1-n}``, leaving the depth unchanged. The byte-addressed memory ops
``MLOAD`` (0x51) / ``MSTORE`` (0x52) / ``MSTORE8`` (0x53) lower over an
``Array bv256 bv8`` ``mem``; the **persistent storage** ops ``SLOAD`` (0x54) /
``SSTORE`` (0x55) lower over an ``Array bv256 bv256`` ``storage`` — word-keyed
word values, so a single array ``read`` / ``write`` (no byte assembly). The
**control-flow ops** ``JUMP`` (0x56) / ``JUMPI`` (0x57) / ``JUMPDEST`` (0x5b) /
``PC`` (0x58) are the first **non-linear** successors: ``JUMPDEST`` is a no-op
marker, ``PC`` pushes the current instruction's byte offset, and ``JUMP`` /
``JUMPI`` pop a *dynamic* destination off the stack and resolve it against the
**statically-scanned set of ``JUMPDEST`` byte offsets** via an ITE chain —
``next_pc := ite(dest == jd0, jd0, ite(dest == jd1, jd1, …, off+1))`` — with the
``halted`` flag set when ``dest`` matches no ``JUMPDEST`` (the invalid-jump
exceptional halt). ``JUMPI`` additionally gates the jump on ``cond != 0`` (else it
falls through to ``off+1``). ``PUSH0`` pushes the constant 0 (the ``PUSH`` lowering
with the immediate replaced by 0). The **terminal/halt ops** set both ``halted``
and the ``status`` byte: ``RETURN`` pops ``offset`` + ``length`` and halts with
``success``; ``REVERT`` pops ``offset`` + ``length`` and halts with ``revert``;
``INVALID`` halts with ``exceptional`` (no operands). Stack underflow/overflow,
an invalid jump, and ``INVALID`` are EVM exceptional halts (a defined edge ->
``halted``, ``status := exceptional``); ``STOP`` / off-the-end / ``RETURN`` set
``status := success``. Every other opcode hard-aborts with
``unsupported: evm:<opcode>`` (BENCHMARKS.md §3) — ``MSIZE`` / gas / ``CALL`` /
``CREATE`` / ``LOG`` stay deferred. Deterministic in ``(code, init_stack,
init_sp)``: the dispatch is keyed on the byte offsets of the opcodes, the JUMPDEST
set is materialized as a *sorted* list of offsets, the stack-cell update rule is
index-driven, and no iteration or hash order reaches the emitted bytes.

The 256-bit words and the dynamic ``s{sp-1}`` / ``s{sp-2}`` selection are why
this pair needs bv256 in the shared BTOR2 evaluator (``languages/btor2`` brief);
the memory and storage ops additionally use its **array** sort.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder
from ...languages.evm import asm
from ...languages.evm.interp import (
    INT_MIN,
    MASK256,
    MEM_WINDOW,
    STACK_SIZE,
    STATUS_EXCEPTIONAL,
    STATUS_REVERT,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    STATUS_WIDTH,
    STORE_WINDOW,
    WORD,
    jumpdests,
)

BYTE = 8  # the memory element width (a byte); the mem array is ``Array bv256 bv8``.

# The single-byte (no inline immediate) in-scope opcodes the decoder accepts.
# ``DUP1..DUP16`` and ``SWAP1..SWAP16`` come straight from the shared asm maps so
# the decoder and the lowering share one source of truth for the families. The
# byte-addressed memory ops ``MLOAD``/``MSTORE``/``MSTORE8`` and the persistent
# storage ops ``SLOAD``/``SSTORE`` are single-byte too.
_MEM_OPS = frozenset((asm.MLOAD, asm.MSTORE, asm.MSTORE8))
_STORAGE_OPS = frozenset((asm.SLOAD, asm.SSTORE))
# Control flow (the first non-linear successors): JUMP/JUMPI resolve a popped
# byte-offset destination against the static JUMPDEST set; JUMPDEST is a no-op
# marker; PC pushes the current instruction's offset. All single-byte.
_CONTROL_OPS = frozenset((asm.JUMP, asm.JUMPI, asm.PC, asm.JUMPDEST))
# Terminal/halt ops (v0.9): RETURN/REVERT pop offset+length and halt with a
# success/revert status; INVALID halts exceptionally. PUSH0 is the constant-0
# push (no inline immediate, so it is single-byte — not in PUSH_WIDTH). All
# single-byte.
_TERMINAL_OPS = frozenset((asm.RETURN, asm.REVERT, asm.INVALID))
# Bitwise ops (v0.10): the binary bitwise AND/OR/XOR (fold into the binary block)
# and the unary NOT / ISZERO. All single-byte (no inline immediate).
_BITWISE_OPS = frozenset((asm.AND, asm.OR))
_STACK_OPS = frozenset(
    (asm.ADD, asm.MUL, asm.SUB, asm.DIV, asm.MOD, asm.SDIV, asm.SMOD,
     asm.POP, asm.STOP, asm.PUSH0)
    + tuple(asm.DUP_N)
    + tuple(asm.SWAP_N)
) | _MEM_OPS | _STORAGE_OPS | _CONTROL_OPS | _TERMINAL_OPS | _BITWISE_OPS


def _decode(code: bytes) -> list[tuple[int, int, int | None]]:
    """Decode the bytecode into ``(pc, opcode, immediate)`` per instruction.

    ``pc`` is the byte offset; ``immediate`` is the inline big-endian operand for
    a ``PUSH{n}`` (else ``None``). Unsupported opcodes hard-abort here
    (load/translate time)."""
    out: list[tuple[int, int, int | None]] = []
    i = 0
    n = len(code)
    while i < n:
        op = code[i]
        if op in asm.PUSH_WIDTH:                    # PUSH1 .. PUSH32
            w = asm.PUSH_WIDTH[op]
            imm = 0
            for k in range(w):                      # big-endian inline immediate
                imm = (imm << 8) | (code[i + 1 + k] if i + 1 + k < n else 0)
            out.append((i, op, imm))
            i += 1 + w
        elif op in _STACK_OPS:
            out.append((i, op, None))
            i += 1
        else:
            raise Unsupported("evm", asm.opcode_name(op))
    return out


def _mux_cell(b: Builder, cells: list[int], index_node: int) -> int:
    """Select the stack cell whose index equals ``index_node`` (a bv256 node):
    a chain of ITEs ``s{j} if index == j else ...``, defaulting to ``s0``."""
    sel = cells[0]
    for j in range(STACK_SIZE):
        at = b.op2("eq", 1, index_node, b.constd(WORD, j))
        sel = b.ite(WORD, at, cells[j], sel)
    return sel


def _resolve_jumpdest(b: Builder, dest: int, jds: list[int], fall: int) -> tuple[int, int]:
    """Resolve a dynamic jump ``dest`` (a bv256 node, the popped destination) over
    the static set of valid ``JUMPDEST`` byte offsets ``jds`` (a *sorted* list).

    Returns ``(target_pc, is_valid)``:

    - ``target_pc`` = ``ite(dest == jd0, jd0, ite(dest == jd1, jd1, …, fall))`` —
      the byte offset to jump to (``fall`` when no JUMPDEST matches; for an invalid
      jump this is the post-step ``pc`` mirroring the interpreter's ``pc + 1``).
    - ``is_valid`` (bv1) = ``OR over (dest == jd_i)`` — false when ``dest`` is not a
      valid JUMPDEST, used to set the invalid-jump exceptional-halt edge.

    Both chains fold over the *sorted* offsets, so the emitted node order is
    deterministic in the bytecode (no set/hash iteration reaches the bytes)."""
    target = fall
    is_valid = b.zero(1)
    # Fold from the highest offset down so the lowest offset is the outermost ITE
    # (the chain reads `dest == jd0 ? jd0 : …`), matching the natural reading.
    for jd in reversed(jds):
        at = b.op2("eq", 1, dest, b.constd(WORD, jd))
        target = b.ite(WORD, at, b.constd(WORD, jd), target)
    for jd in jds:
        at = b.op2("eq", 1, dest, b.constd(WORD, jd))
        is_valid = b.op2("or", 1, is_valid, at)
    return target, is_valid


def _uses_memory(insns: list[tuple[int, int, int | None]]) -> bool:
    """Whether the program touches the byte-addressed memory (any MLOAD/MSTORE/
    MSTORE8). The ``mem`` array + the ``m{i}`` window states are emitted only
    when it does (mirrors ``ebpf-btor2``'s conditional ``mem`` array)."""
    return any(op in _MEM_OPS for _off, op, _imm in insns)


def _uses_storage(insns: list[tuple[int, int, int | None]]) -> bool:
    """Whether the program touches persistent storage (any SLOAD/SSTORE). The
    ``storage`` array (``Array bv256 bv256``) + the ``s_at_{i}`` window states are
    emitted only when it does, so a non-storage program stays byte-identical."""
    return any(op in _STORAGE_OPS for _off, op, _imm in insns)


def _mem_read_word_be(b: Builder, mem: int, offset: int) -> int:
    """Read the 32-byte **big-endian** word at ``mem[offset .. offset+31]`` -> a
    bv256 node (the byte at ``offset`` is most significant). ``offset`` is a
    bv256 node; the byte read is an array ``read`` at ``offset + i``."""
    word = b.read(BYTE, mem, offset)                       # byte 0 -> top (BE)
    w = BYTE
    for i in range(1, 32):
        a_i = b.op2("add", WORD, offset, b.constd(WORD, i))
        byte = b.read(BYTE, mem, a_i)
        word = b.op2("concat", w + BYTE, word, byte)
        w += BYTE
    return word                                            # already exactly 256 bits


def _mem_write_word_be(b: Builder, mem: int, offset: int, value: int) -> int:
    """Write the 32-byte **big-endian** encoding of the bv256 ``value`` to
    ``mem[offset .. offset+31]`` (most significant byte at ``offset``) -> the new
    array node."""
    cur = mem
    for i in range(32):                                    # byte i: bits [hi..lo]
        hi = 8 * (31 - i) + 7
        lo = 8 * (31 - i)
        byte = b.slice(value, hi, lo)
        a_i = offset if i == 0 else b.op2("add", WORD, offset, b.constd(WORD, i))
        cur = b.write(WORD, BYTE, cur, a_i, byte)
    return cur


def _mem_write_byte(b: Builder, mem: int, offset: int, value: int) -> int:
    """Write the **low byte** of the bv256 ``value`` to ``mem[offset]`` -> the
    new array node (MSTORE8)."""
    return b.write(WORD, BYTE, mem, offset, b.slice(value, 7, 0))


def translate(program: dict[str, Any]) -> bytes:
    code = program["code"] if isinstance(program, dict) else bytes(program)
    code = bytes(code)
    entry = int(program.get("entry", 0)) if isinstance(program, dict) else 0
    init_stack = program.get("init_stack", {}) if isinstance(program, dict) else {}
    init_sp = int(program.get("init_sp", 0)) if isinstance(program, dict) else 0

    insns = _decode(code)  # also validates: aborts on any unsupported opcode
    # The static set of valid JUMPDEST byte offsets (PUSH-immediate-aware), as a
    # *sorted* list so the jump-resolution ITE/OR chains are deterministic — the
    # single source of truth shared with the interpreter (interp.jumpdests).
    jds = sorted(jumpdests(code))

    uses_mem = _uses_memory(insns)
    uses_storage = _uses_storage(insns)

    b = Builder()
    pc = b.state(WORD, "pc")
    cells = [b.state(WORD, f"s{i}") for i in range(STACK_SIZE)]
    sp = b.state(WORD, "sp")
    halted = b.state(1, "halted")
    # Halt-status observable (v0.9): a bv8 ``status`` recording *why* the run
    # halted — running (0) / success (1) / revert (2) / exceptional (3) — emitted
    # in *every* program (every halt carries a why), unlike the conditional mem /
    # storage states. It mirrors the interpreter's ``status`` exactly so the
    # commuting square checks the terminal kind, not just *that* a run halted.
    status = b.state(STATUS_WIDTH, "status")
    # Byte-addressed memory: an ``Array bv256 bv8`` (zero-initialized), plus the
    # fixed observable window ``m0..m{MEM_WINDOW-1}`` (bv8 states mirroring the
    # array's lowest bytes). The shared BTOR2 trace only exposes BIT-VECTOR
    # state, not arrays, so the window states are how the memory observable
    # reaches ``π`` (the source interpreter exposes the same ``m{i}`` bytes).
    mem = b.state_array(WORD, BYTE, "mem") if uses_mem else None
    mwin = [b.state(BYTE, f"m{i}") for i in range(MEM_WINDOW)] if uses_mem else []
    # Persistent storage: an ``Array bv256 bv256`` (zero-initialized) — word-keyed
    # word values, the word-keyed analogue of ``mem`` — plus the fixed observable
    # window ``s_at_0..s_at_{STORE_WINDOW-1}`` (bv256 states mirroring the values at
    # keys 0..STORE_WINDOW-1). Emitted (after the memory states) only when the body
    # uses storage, so non-storage programs stay byte-identical.
    storage = b.state_array(WORD, WORD, "storage") if uses_storage else None
    swin = [b.state(WORD, f"s_at_{i}") for i in range(STORE_WINDOW)] if uses_storage else []

    # Initial state.
    b.init(pc, b.constd(WORD, entry))
    for i in range(STACK_SIZE):
        b.init(cells[i], b.constd(WORD, int(init_stack.get(i, 0)) & MASK256))
    b.init(sp, b.constd(WORD, init_sp & MASK256))
    b.init(halted, b.zero(1))
    b.init(status, b.constd(STATUS_WIDTH, STATUS_RUNNING))   # running (0)
    for i in range(MEM_WINDOW):                # window mirrors the all-zero init mem
        if uses_mem:
            b.init(mwin[i], b.zero(BYTE))
    for i in range(STORE_WINDOW):              # window mirrors the all-zero init storage
        if uses_storage:
            b.init(swin[i], b.zero(WORD))

    not_halted = b.op1("not", 1, halted)

    next_pc = pc
    next_cells = list(cells)
    next_sp = sp
    next_halted = halted
    next_status = status
    next_mem = mem
    next_storage = storage

    def kpc(v: int) -> int:
        return b.constd(WORD, v & MASK256)

    # Halt helper (v0.9): on ``cond`` set ``halted := 1`` and ``status := kind``,
    # folding both into the running ``next_*`` expressions exactly as the existing
    # ``next_halted`` fold does. ``kind`` is one of the STATUS_* constants. This is
    # the single place a halt's *why* is recorded, mirroring the interpreter.
    def halt_with(cond: int, kind: int) -> None:
        nonlocal next_halted, next_status
        next_halted = b.ite(1, cond, b.one(1), next_halted)
        next_status = b.ite(STATUS_WIDTH, cond, b.constd(STATUS_WIDTH, kind), next_status)

    for off, op, imm in insns:
        at = b.op2("eq", 1, pc, b.constd(WORD, off))
        active = b.op2("and", 1, at, not_halted)

        if op == asm.STOP:
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_with(active, STATUS_SUCCESS)       # STOP halts successfully
            continue

        if op == asm.PUSH0:                         # PUSH0: push the constant 0
            # overflow (sp >= STACK_SIZE) -> exceptional halt; else write s{sp} := 0.
            # The PUSH lowering with the immediate fixed to 0 and a 1-byte advance.
            overflow = b.op2("ugte", 1, sp, b.constd(WORD, STACK_SIZE))
            do = b.op2("and", 1, active, b.op1("not", 1, overflow))
            for j in range(STACK_SIZE):
                target = b.op2("eq", 1, sp, b.constd(WORD, j))
                write = b.op2("and", 1, do, target)
                next_cells[j] = b.ite(WORD, write, kpc(0), next_cells[j])
            next_sp = b.ite(WORD, do, b.op2("add", WORD, sp, b.constd(WORD, 1)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_with(b.op2("and", 1, active, overflow), STATUS_EXCEPTIONAL)
            continue

        if op in asm.PUSH_WIDTH:                    # PUSH1 .. PUSH32
            # overflow (sp >= STACK_SIZE) -> exceptional halt; else write s{sp}.
            w = asm.PUSH_WIDTH[op]
            overflow = b.op2("ugte", 1, sp, b.constd(WORD, STACK_SIZE))
            do = b.op2("and", 1, active, b.op1("not", 1, overflow))
            for j in range(STACK_SIZE):
                target = b.op2("eq", 1, sp, b.constd(WORD, j))
                write = b.op2("and", 1, do, target)
                next_cells[j] = b.ite(WORD, write, kpc(imm or 0), next_cells[j])
            next_sp = b.ite(WORD, do, b.op2("add", WORD, sp, b.constd(WORD, 1)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1 + w), next_pc)
            halt_with(b.op2("and", 1, active, overflow), STATUS_EXCEPTIONAL)
            continue

        if op in (asm.ADD, asm.MUL, asm.SUB, asm.DIV, asm.MOD,
                  asm.SDIV, asm.SMOD, asm.AND, asm.OR):      # binary arithmetic / bitwise
            # underflow (sp < 2) -> exceptional halt; else s{sp-2} = s{sp-1} OP s{sp-2}.
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 2))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            top_idx = b.op2("sub", WORD, sp, b.constd(WORD, 1))      # sp-1 (top = a)
            nxt_idx = b.op2("sub", WORD, sp, b.constd(WORD, 2))      # sp-2 (next = b)
            a = _mux_cell(b, cells, top_idx)
            bb = _mux_cell(b, cells, nxt_idx)
            # SUB is a - b (top minus next); ADD/MUL are commutative. BTOR2
            # sub/mul on bv256 already wrap mod 2**256, mirroring the interp.
            # DIV/MOD are unsigned with the EVM by-zero = 0 special case, lowered
            # with an explicit guard ite(b==0, 0, udiv/urem(a,b)) because BTOR2
            # udiv/urem carry the SMT by-zero convention (all-ones / dividend),
            # which is NOT EVM's; mirrors interp.py's `0 if b==0 else a//b|a%b`.
            if op in (asm.DIV, asm.MOD):
                kind = {asm.DIV: "udiv", asm.MOD: "urem"}[op]
                raw = b.op2(kind, WORD, a, bb)
                is_zero = b.op2("eq", 1, bb, b.constd(WORD, 0))
                total = b.ite(WORD, is_zero, b.constd(WORD, 0), raw)
            elif op in (asm.SDIV, asm.SMOD):
                # SIGNED division/modulo over two's-complement bv256. BTOR2
                # sdiv/srem give the TRUNCATING (toward-zero) quotient/remainder
                # (the remainder takes the sign of the dividend), which is what
                # EVM wants — but they carry the SMT by-zero convention (sdiv ->
                # all-ones/1, srem -> dividend), NOT EVM's = 0, and SMT sdiv would
                # trap-or-wrap on INT_MIN/-1. So guard explicitly:
                #   SDIV = ite(b==0, 0, ite(a==INT_MIN & b==-1, INT_MIN, sdiv(a,b)))
                #   SMOD = ite(b==0, 0, srem(a,b))
                # INT_MIN = 2**255 (top bit only); -1 = all-ones. Mirrors interp.py.
                is_zero = b.op2("eq", 1, bb, b.constd(WORD, 0))
                if op == asm.SDIV:
                    raw = b.op2("sdiv", WORD, a, bb)
                    a_is_min = b.op2("eq", 1, a, b.constd(WORD, INT_MIN))
                    b_is_neg1 = b.op2("eq", 1, bb, b.constd(WORD, MASK256))  # -1
                    overflow = b.op2("and", 1, a_is_min, b_is_neg1)
                    guarded = b.ite(WORD, overflow, b.constd(WORD, INT_MIN), raw)
                    total = b.ite(WORD, is_zero, b.constd(WORD, 0), guarded)
                else:                                        # SMOD
                    raw = b.op2("srem", WORD, a, bb)
                    total = b.ite(WORD, is_zero, b.constd(WORD, 0), raw)
            else:
                # ADD/MUL/SUB wrap mod 2**256 natively on bv256; the bitwise
                # AND/OR/XOR (v0.10) are bit-parallel — both fold into one op2.
                kind = {asm.ADD: "add", asm.MUL: "mul", asm.SUB: "sub",
                        asm.AND: "and", asm.OR: "or"}[op]
                total = b.op2(kind, WORD, a, bb)
            for j in range(STACK_SIZE):
                target = b.op2("eq", 1, nxt_idx, b.constd(WORD, j))
                write = b.op2("and", 1, do, target)
                next_cells[j] = b.ite(WORD, write, total, next_cells[j])
            next_sp = b.ite(WORD, do, b.op2("sub", WORD, sp, b.constd(WORD, 1)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, underflow)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op == asm.POP:
            # underflow (sp < 1) -> exceptional halt; else drop top (cell stale).
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 1))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            next_sp = b.ite(WORD, do, b.op2("sub", WORD, sp, b.constd(WORD, 1)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, underflow)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op in asm.DUP_N:                          # DUP1 .. DUP16
            # underflow (sp < n, nothing at depth n) or overflow (sp >= STACK_SIZE)
            # -> exceptional halt; else s{sp} := s{sp-n}, sp += 1. (DUP1 copies the
            # top itself; the only change from DUP1 is the read index sp-n.)
            n = asm.DUP_N[op]
            underflow = b.op2("ult", 1, sp, b.constd(WORD, n))
            overflow = b.op2("ugte", 1, sp, b.constd(WORD, STACK_SIZE))
            bad = b.op2("or", 1, underflow, overflow)
            do = b.op2("and", 1, active, b.op1("not", 1, bad))
            src_idx = b.op2("sub", WORD, sp, b.constd(WORD, n))      # sp-n (n-th item)
            src = _mux_cell(b, cells, src_idx)
            for j in range(STACK_SIZE):
                target = b.op2("eq", 1, sp, b.constd(WORD, j))        # write s{sp}
                write = b.op2("and", 1, do, target)
                next_cells[j] = b.ite(WORD, write, src, next_cells[j])
            next_sp = b.ite(WORD, do, b.op2("add", WORD, sp, b.constd(WORD, 1)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, bad)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op in asm.SWAP_N:                         # SWAP1 .. SWAP16
            # underflow (sp < n+1, no top + (n+1)-th item) -> exceptional halt;
            # else swap s{sp-1} <-> s{sp-1-n}, sp unchanged. Both targets are
            # written by index muxes (eq the swap slot), reading the *current*
            # cells so the swap is simultaneous.
            n = asm.SWAP_N[op]
            underflow = b.op2("ult", 1, sp, b.constd(WORD, n + 1))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            top_idx = b.op2("sub", WORD, sp, b.constd(WORD, 1))      # sp-1 (top)
            deep_idx = b.op2("sub", WORD, sp, b.constd(WORD, n + 1))  # sp-1-n
            top_val = _mux_cell(b, cells, top_idx)
            deep_val = _mux_cell(b, cells, deep_idx)
            for j in range(STACK_SIZE):
                at_top = b.op2("eq", 1, top_idx, b.constd(WORD, j))
                at_deep = b.op2("eq", 1, deep_idx, b.constd(WORD, j))
                w_top = b.op2("and", 1, do, at_top)                   # s{sp-1} := deep
                cell = b.ite(WORD, w_top, deep_val, next_cells[j])
                w_deep = b.op2("and", 1, do, at_deep)                 # s{sp-1-n} := top
                next_cells[j] = b.ite(WORD, w_deep, top_val, cell)
            # sp is unchanged for SWAP; only pc advances and an underflow halts.
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, underflow)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op == asm.MLOAD:                          # MLOAD (byte-addressed)
            # underflow (sp < 1) -> exceptional halt; else off = s{sp-1}, and
            # s{sp-1} := the 32-byte big-endian word at mem[off..off+31] (offset
            # popped, word pushed -> sp unchanged, written at the same slot).
            assert mem is not None
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 1))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            off_idx = b.op2("sub", WORD, sp, b.constd(WORD, 1))     # sp-1 (offset)
            offset = _mux_cell(b, cells, off_idx)
            word = _mem_read_word_be(b, mem, offset)
            for j in range(STACK_SIZE):
                target = b.op2("eq", 1, off_idx, b.constd(WORD, j))  # write s{sp-1}
                write = b.op2("and", 1, do, target)
                next_cells[j] = b.ite(WORD, write, word, next_cells[j])
            # sp unchanged (one popped, one pushed); pc advances; underflow halts.
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, underflow)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op in (asm.MSTORE, asm.MSTORE8):          # MSTORE / MSTORE8
            # underflow (sp < 2) -> exceptional halt; else off = s{sp-1}, value =
            # s{sp-2}; write the word (MSTORE: 32-byte big-endian) or the low byte
            # (MSTORE8) to mem[off], drop both operands (sp -= 2).
            assert mem is not None
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 2))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            off_idx = b.op2("sub", WORD, sp, b.constd(WORD, 1))     # sp-1 (offset)
            val_idx = b.op2("sub", WORD, sp, b.constd(WORD, 2))     # sp-2 (value)
            offset = _mux_cell(b, cells, off_idx)
            value = _mux_cell(b, cells, val_idx)
            if op == asm.MSTORE:
                written = _mem_write_word_be(b, mem, offset, value)
            else:                                                   # MSTORE8
                written = _mem_write_byte(b, mem, offset, value)
            next_mem = b.ite_array(WORD, BYTE, do, written, next_mem)
            next_sp = b.ite(WORD, do, b.op2("sub", WORD, sp, b.constd(WORD, 2)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, underflow)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op == asm.SLOAD:                          # SLOAD (word-keyed storage)
            # underflow (sp < 1) -> exceptional halt; else key = s{sp-1}, and
            # s{sp-1} := storage[key] (a single array read; key popped, value
            # pushed -> sp unchanged, written at the same slot). A never-written
            # key reads the array default 0 (zero-initialized storage).
            assert storage is not None
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 1))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            key_idx = b.op2("sub", WORD, sp, b.constd(WORD, 1))     # sp-1 (key)
            key = _mux_cell(b, cells, key_idx)
            word = b.read(WORD, storage, key)                       # storage[key]
            for j in range(STACK_SIZE):
                target = b.op2("eq", 1, key_idx, b.constd(WORD, j))  # write s{sp-1}
                write = b.op2("and", 1, do, target)
                next_cells[j] = b.ite(WORD, write, word, next_cells[j])
            # sp unchanged (one popped, one pushed); pc advances; underflow halts.
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, underflow)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op == asm.SSTORE:                         # SSTORE (word-keyed storage)
            # underflow (sp < 2) -> exceptional halt; else key = s{sp-1}, value =
            # s{sp-2}; storage[key] := value (a single array write), drop both
            # operands (sp -= 2). The array update is guarded so an inactive /
            # underflow cycle leaves storage unchanged.
            assert storage is not None
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 2))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            key_idx = b.op2("sub", WORD, sp, b.constd(WORD, 1))     # sp-1 (key)
            val_idx = b.op2("sub", WORD, sp, b.constd(WORD, 2))     # sp-2 (value)
            key = _mux_cell(b, cells, key_idx)
            value = _mux_cell(b, cells, val_idx)
            written = b.write(WORD, WORD, storage, key, value)
            next_storage = b.ite_array(WORD, WORD, do, written, next_storage)
            next_sp = b.ite(WORD, do, b.op2("sub", WORD, sp, b.constd(WORD, 2)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, underflow)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op == asm.JUMPDEST:                       # JUMPDEST: a no-op marker
            # No stack / halt effect; pc simply advances. (A JUMP lands here when
            # off is in the static JUMPDEST set, so dispatch continues from off+1.)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            continue

        if op == asm.PC:                             # PC: push this instr's offset
            # overflow (sp >= STACK_SIZE) -> exceptional halt; else s{sp} := off
            # (the byte offset of THIS opcode), sp += 1. Mirrors the PUSH lowering
            # with the immediate replaced by the constant offset.
            overflow = b.op2("ugte", 1, sp, b.constd(WORD, STACK_SIZE))
            do = b.op2("and", 1, active, b.op1("not", 1, overflow))
            for j in range(STACK_SIZE):
                target = b.op2("eq", 1, sp, b.constd(WORD, j))
                write = b.op2("and", 1, do, target)
                next_cells[j] = b.ite(WORD, write, kpc(off), next_cells[j])
            next_sp = b.ite(WORD, do, b.op2("add", WORD, sp, b.constd(WORD, 1)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, overflow)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op == asm.JUMP:                           # JUMP: pop dest, set pc := dest
            # underflow (sp < 1) -> exceptional halt; else dest = s{sp-1}, resolve
            # it against the static JUMPDEST set: a valid target sets pc := dest,
            # an invalid one takes the exceptional-halt edge (pc := off+1, halted).
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 1))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            dest_idx = b.op2("sub", WORD, sp, b.constd(WORD, 1))     # sp-1 (dest)
            dest = _mux_cell(b, cells, dest_idx)
            target, is_valid = _resolve_jumpdest(b, dest, jds, kpc(off + 1))
            # next_pc when active: off+1 on the underflow-halt edge (mirroring the
            # interpreter's pc+1), else the resolved target (off+1 if invalid, which
            # also equals the interpreter's pc on the invalid-halt edge). Inactive
            # cycles leave pc unchanged.
            pc_active = b.ite(WORD, underflow, kpc(off + 1), target)
            next_pc = b.ite(WORD, active, pc_active, next_pc)
            next_sp = b.ite(WORD, do, b.op2("sub", WORD, sp, b.constd(WORD, 1)), next_sp)
            # halt on underflow OR a do-cycle whose dest is not a valid JUMPDEST.
            bad_jump = b.op2("and", 1, do, b.op1("not", 1, is_valid))
            halt_here = b.op2("or", 1, b.op2("and", 1, active, underflow), bad_jump)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op == asm.JUMPI:                          # JUMPI: pop dest, cond; jump iff cond
            # underflow (sp < 2) -> exceptional halt; else dest = s{sp-1}, cond =
            # s{sp-2}. If cond != 0 resolve dest as for JUMP (valid -> jump, invalid
            # -> halt); if cond == 0 fall through to off+1. sp -= 2 either way.
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 2))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            dest_idx = b.op2("sub", WORD, sp, b.constd(WORD, 1))     # sp-1 (dest)
            cond_idx = b.op2("sub", WORD, sp, b.constd(WORD, 2))     # sp-2 (cond)
            dest = _mux_cell(b, cells, dest_idx)
            cond = _mux_cell(b, cells, cond_idx)
            taken = b.op2("neq", 1, cond, b.constd(WORD, 0))         # cond != 0
            target, is_valid = _resolve_jumpdest(b, dest, jds, kpc(off + 1))
            # taken -> resolved target (off+1 if invalid); not taken -> off+1.
            chosen = b.ite(WORD, taken, target, kpc(off + 1))
            # next_pc when active: off+1 on the underflow-halt edge (mirroring the
            # interpreter's pc+1), else the chosen target. Inactive cycles unchanged.
            pc_active = b.ite(WORD, underflow, kpc(off + 1), chosen)
            next_pc = b.ite(WORD, active, pc_active, next_pc)
            next_sp = b.ite(WORD, do, b.op2("sub", WORD, sp, b.constd(WORD, 2)), next_sp)
            # halt on underflow OR a taken do-cycle whose dest is not a valid JUMPDEST.
            taken_bad = b.op2("and", 1, do, b.op2("and", 1, taken, b.op1("not", 1, is_valid)))
            halt_here = b.op2("or", 1, b.op2("and", 1, active, underflow), taken_bad)
            halt_with(halt_here, STATUS_EXCEPTIONAL)
            continue

        if op in (asm.RETURN, asm.REVERT):           # RETURN / REVERT: pop offset, length
            # underflow (sp < 2) -> exceptional halt; else consume offset + length
            # (sp -= 2) and halt with the terminal status (RETURN -> success,
            # REVERT -> revert). The return/revert data range is memory[off..off+len],
            # already observable via the memory window — no new state is needed.
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 2))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            next_sp = b.ite(WORD, do, b.op2("sub", WORD, sp, b.constd(WORD, 2)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            # underflow is the exceptional edge; a clean do-cycle is the terminal halt.
            halt_with(b.op2("and", 1, active, underflow), STATUS_EXCEPTIONAL)
            kind = STATUS_SUCCESS if op == asm.RETURN else STATUS_REVERT
            halt_with(do, kind)
            continue

        if op == asm.INVALID:                        # INVALID: halt exceptionally
            # No operands; pc advances and the run halts with the exceptional status.
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_with(active, STATUS_EXCEPTIONAL)
            continue

        raise Unsupported("evm", asm.opcode_name(op))  # pragma: no cover

    # Running off the end of the bytecode is an implicit STOP (EVM semantics):
    # when ``pc`` is past the last byte and not yet halted, halt with pc / sp /
    # stack unchanged — mirroring the interpreter's off-the-end halt row, a SUCCESS
    # halt. (Any ``pc`` that is neither a decoded opcode offset nor < len(code)
    # lands here.)
    off_end = b.op2("ugte", 1, pc, b.constd(WORD, len(code)))
    halt_end = b.op2("and", 1, off_end, not_halted)
    halt_with(halt_end, STATUS_SUCCESS)

    b.next(pc, next_pc)
    for i in range(STACK_SIZE):
        b.next(cells[i], next_cells[i])
    b.next(sp, next_sp)
    b.next(halted, next_halted)
    b.next(status, next_status)
    if uses_mem:
        assert next_mem is not None
        b.next_array(mem, next_mem)
        # Each window byte tracks the post-step memory array at its fixed address,
        # so the bit-vector trace carries the memory observable into ``π``.
        for i in range(MEM_WINDOW):
            b.next(mwin[i], b.read(BYTE, next_mem, b.constd(WORD, i)))
    if uses_storage:
        assert next_storage is not None
        b.next_array(storage, next_storage)
        # Each window state tracks the post-step storage array at its fixed key,
        # so the bit-vector trace carries the storage observable into ``π``.
        for i in range(STORE_WINDOW):
            b.next(swin[i], b.read(WORD, next_storage, b.constd(WORD, i)))

    # Optional reachability property -> a `bad` signal, so a downstream
    # reasoning bridge (btor2-smtlib) can decide the question.
    prop = program.get("property") if isinstance(program, dict) else None
    if prop and "stack_eq" in prop:
        depth, val = prop["stack_eq"]   # s{depth} == val
        b.bad(b.op2("eq", 1, cells[int(depth)], b.constd(WORD, int(val) & MASK256)))

    return b.to_text().encode("utf-8")
