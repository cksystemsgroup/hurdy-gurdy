"""EVM -> BTOR2 translator (pairs/evm-btor2 brief).

Emits a BTOR2 transition system modeling the EVM stack machine one opcode per
cycle: state ``pc`` (bv256, a *byte* offset into the bytecode), a bounded
operand stack ``s0..s{N-1}`` (bv256 each), the stack depth ``sp`` (bv256, the
number of live items), and ``halted`` (bv1). The fixed bytecode is lowered to a
PC-keyed ITE dispatch over the per-opcode next-state functions, exactly
mirroring ``languages/evm/interp.py`` so the commuting-square oracle
cross-checks them.

Scope (pure stack/arithmetic slice): the push immediates ``PUSH1`` (0x60) /
``PUSH2`` (0x61) / ``PUSH4`` (0x63), the binary arithmetic ``ADD`` (0x01) /
``MUL`` (0x02) / ``SUB`` (0x03) and the unsigned ``DIV`` (0x04) / ``MOD`` (0x06),
the stack shuffles ``POP`` (0x50) / ``DUP1`` (0x80), and ``STOP`` (0x00) over
256-bit words. ``DIV`` / ``MOD`` lower with an explicit EVM by-zero guard —
``DIV(a,b) = ite(b==0, 0, udiv(a,b))`` and ``MOD(a,b) = ite(b==0, 0, urem(a,b))``
— because the BTOR2 ``udiv`` / ``urem`` carry the *SMT* by-zero convention
(all-ones / dividend), not EVM's ``= 0``. Stack underflow/overflow are EVM
exceptional halts (a defined edge -> ``halted``). Every other opcode hard-aborts
with ``unsupported: evm:<opcode>`` (BENCHMARKS.md §3) — control flow
(``JUMP``/``JUMPI``), the signed ``SDIV``/``SMOD``, memory, and storage are
deliberately deferred. Deterministic in ``(code, init_stack, init_sp)``: the
dispatch is keyed on the byte offsets of the opcodes, the stack-cell update rule
is index-driven, and no iteration or hash order reaches the emitted bytes.

The 256-bit words and the dynamic ``s{sp-1}`` / ``s{sp-2}`` selection are why
this pair needs bv256 in the shared BTOR2 evaluator (``languages/btor2`` brief).
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder
from ...languages.evm import asm
from ...languages.evm.interp import MASK256, STACK_SIZE, WORD


_STACK_OPS = (asm.ADD, asm.MUL, asm.SUB, asm.DIV, asm.MOD, asm.POP, asm.DUP1, asm.STOP)


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
        if op in asm.PUSH_WIDTH:                    # PUSH1 / PUSH2 / PUSH4
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


def translate(program: dict[str, Any]) -> bytes:
    code = program["code"] if isinstance(program, dict) else bytes(program)
    code = bytes(code)
    entry = int(program.get("entry", 0)) if isinstance(program, dict) else 0
    init_stack = program.get("init_stack", {}) if isinstance(program, dict) else {}
    init_sp = int(program.get("init_sp", 0)) if isinstance(program, dict) else 0

    insns = _decode(code)  # also validates: aborts on any unsupported opcode

    b = Builder()
    pc = b.state(WORD, "pc")
    cells = [b.state(WORD, f"s{i}") for i in range(STACK_SIZE)]
    sp = b.state(WORD, "sp")
    halted = b.state(1, "halted")

    # Initial state.
    b.init(pc, b.constd(WORD, entry))
    for i in range(STACK_SIZE):
        b.init(cells[i], b.constd(WORD, int(init_stack.get(i, 0)) & MASK256))
    b.init(sp, b.constd(WORD, init_sp & MASK256))
    b.init(halted, b.zero(1))

    not_halted = b.op1("not", 1, halted)

    next_pc = pc
    next_cells = list(cells)
    next_sp = sp
    next_halted = halted

    def kpc(v: int) -> int:
        return b.constd(WORD, v & MASK256)

    for off, op, imm in insns:
        at = b.op2("eq", 1, pc, b.constd(WORD, off))
        active = b.op2("and", 1, at, not_halted)

        if op == asm.STOP:
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            next_halted = b.ite(1, active, b.one(1), next_halted)
            continue

        if op in asm.PUSH_WIDTH:                    # PUSH1 / PUSH2 / PUSH4
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
            halt_here = b.op2("and", 1, active, overflow)
            next_halted = b.ite(1, halt_here, b.one(1), next_halted)
            continue

        if op in (asm.ADD, asm.MUL, asm.SUB, asm.DIV, asm.MOD):   # binary arithmetic
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
            else:
                kind = {asm.ADD: "add", asm.MUL: "mul", asm.SUB: "sub"}[op]
                total = b.op2(kind, WORD, a, bb)
            for j in range(STACK_SIZE):
                target = b.op2("eq", 1, nxt_idx, b.constd(WORD, j))
                write = b.op2("and", 1, do, target)
                next_cells[j] = b.ite(WORD, write, total, next_cells[j])
            next_sp = b.ite(WORD, do, b.op2("sub", WORD, sp, b.constd(WORD, 1)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, underflow)
            next_halted = b.ite(1, halt_here, b.one(1), next_halted)
            continue

        if op == asm.POP:
            # underflow (sp < 1) -> exceptional halt; else drop top (cell stale).
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 1))
            do = b.op2("and", 1, active, b.op1("not", 1, underflow))
            next_sp = b.ite(WORD, do, b.op2("sub", WORD, sp, b.constd(WORD, 1)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, underflow)
            next_halted = b.ite(1, halt_here, b.one(1), next_halted)
            continue

        if op == asm.DUP1:
            # underflow (sp < 1) or overflow (sp >= STACK_SIZE) -> exceptional
            # halt; else s{sp} := s{sp-1}, sp += 1.
            underflow = b.op2("ult", 1, sp, b.constd(WORD, 1))
            overflow = b.op2("ugte", 1, sp, b.constd(WORD, STACK_SIZE))
            bad = b.op2("or", 1, underflow, overflow)
            do = b.op2("and", 1, active, b.op1("not", 1, bad))
            top_idx = b.op2("sub", WORD, sp, b.constd(WORD, 1))      # sp-1 (top)
            top = _mux_cell(b, cells, top_idx)
            for j in range(STACK_SIZE):
                target = b.op2("eq", 1, sp, b.constd(WORD, j))        # write s{sp}
                write = b.op2("and", 1, do, target)
                next_cells[j] = b.ite(WORD, write, top, next_cells[j])
            next_sp = b.ite(WORD, do, b.op2("add", WORD, sp, b.constd(WORD, 1)), next_sp)
            next_pc = b.ite(WORD, active, kpc(off + 1), next_pc)
            halt_here = b.op2("and", 1, active, bad)
            next_halted = b.ite(1, halt_here, b.one(1), next_halted)
            continue

        raise Unsupported("evm", asm.opcode_name(op))  # pragma: no cover

    # Running off the end of the bytecode is an implicit STOP (EVM semantics):
    # when ``pc`` is past the last byte and not yet halted, halt with pc / sp /
    # stack unchanged — mirroring the interpreter's off-the-end halt row. (Any
    # ``pc`` that is neither a decoded opcode offset nor < len(code) lands here.)
    off_end = b.op2("ugte", 1, pc, b.constd(WORD, len(code)))
    halt_end = b.op2("and", 1, off_end, not_halted)
    next_halted = b.ite(1, halt_end, b.one(1), next_halted)

    b.next(pc, next_pc)
    for i in range(STACK_SIZE):
        b.next(cells[i], next_cells[i])
    b.next(sp, next_sp)
    b.next(halted, next_halted)

    # Optional reachability property -> a `bad` signal, so a downstream
    # reasoning bridge (btor2-smtlib) can decide the question.
    prop = program.get("property") if isinstance(program, dict) else None
    if prop and "stack_eq" in prop:
        depth, val = prop["stack_eq"]   # s{depth} == val
        b.bad(b.op2("eq", 1, cells[int(depth)], b.constd(WORD, int(val) & MASK256)))

    return b.to_text().encode("utf-8")
