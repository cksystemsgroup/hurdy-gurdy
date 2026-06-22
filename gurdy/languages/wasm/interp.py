"""A deterministic WebAssembly interpreter (the shared Wasm source interpreter).

Scope (MVP, thin-first then widened — ``languages/wasm`` brief): a single
straight-line i32 function body over the **integer-stack core**. The operand
producers ``i32.const`` (push an immediate) and ``local.get`` (push a local);
the conditional ``select`` (pop ``c``, ``v2``, ``v1``; push ``v1`` if ``c ≠ 0``
else ``v2``); the unary comparison ``i32.eqz``; and the **i32 binary-operator
family** — each pops two i32 and pushes one i32:

- arithmetic / bitwise: ``i32.add`` (modular 2³² sum), ``i32.sub``, ``i32.mul``,
  ``i32.and``, ``i32.or``, ``i32.xor`` (each modular / bitwise at width 32);
- shifts: ``i32.shl``, ``i32.shr_u`` (logical), ``i32.shr_s`` (arithmetic) —
  the shift amount is taken **mod 32**, exactly as the Wasm spec masks it;
- comparisons (push the i32 result ``1``/``0``): ``i32.eq``, ``i32.ne``,
  ``i32.lt_s`` / ``i32.lt_u``, ``i32.gt_s`` / ``i32.gt_u``, ``i32.le_s`` /
  ``i32.le_u``, ``i32.ge_s`` / ``i32.ge_u`` — the ``_s`` variants compare the
  operands as two's-complement signed, the ``_u`` variants as unsigned.

This mirrors the official Wasm small-step operational semantics for these
reduction rules over a typed value stack with locals. Every other instruction
hard-aborts with ``Unsupported`` (BENCHMARKS.md §3) — there is no silent drop.
``i32.div_*`` / ``i32.rem_*`` stay out of scope (they need a div-by-zero trap
edge) and keep hard-aborting.

A *behavior* is a ``Trace`` of **post-step** states (ARCHITECTURE.md §5). The
observable state after each instruction is::

    {"pc": <next instruction index>,
     "halted": <ran off the end of the body>,
     "stack": (<bottom>, ..., <top>),   # the i32 value stack, as a tuple
     "sp": <stack depth>,
     "locals": (<l0>, <l1>, ...)}       # the i32 locals

Pure and deterministic; ``pc`` indexes the instruction list.

Interpreter version (the shared deliverable's contract — AGENTS.md §3): a
versioned bump is required for any additive semantics change so dependent
pairs re-validate their square.
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

INTERP_VERSION = "0.3"  # AGENTS.md §3: bumped when the i32 binop family was added.

MASK32 = (1 << 32) - 1
SHIFT_MASK = 31          # Wasm masks the i32 shift amount mod 32.

# The in-scope opcodes. The mnemonics double as the binary-opcode documentation
# below, but the interpreter consumes the structured ``Instr``, not raw bytes.
OP_I32_CONST = "i32.const"   # binary 0x41
OP_LOCAL_GET = "local.get"   # binary 0x20
OP_I32_ADD = "i32.add"       # binary 0x6a
OP_I32_EQZ = "i32.eqz"       # binary 0x45
OP_SELECT = "select"         # binary 0x1b

# The rest of the i32 binary-operator family (each pops two i32, pushes one).
# Arithmetic / bitwise:
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

def _sext32(v: int) -> int:
    """Interpret a u32 ``v`` as a two's-complement signed i32 (for the signed
    comparisons and the arithmetic right shift ``shr_s``)."""
    v &= MASK32
    return v - (1 << 32) if v >> 31 else v


# Pop-two-push-one binary ops keyed by opcode -> a pure (a, b) -> i32 function
# over the *masked* u32 operands, the single source of truth the BTOR2 lowering
# mirrors per construct. The result is reduced mod 2³² by ``_execute``.
I32_BINOPS: dict[str, Any] = {
    OP_I32_ADD: lambda a, b: a + b,
    OP_I32_SUB: lambda a, b: a - b,
    OP_I32_MUL: lambda a, b: a * b,
    OP_I32_AND: lambda a, b: a & b,
    OP_I32_OR: lambda a, b: a | b,
    OP_I32_XOR: lambda a, b: a ^ b,
    OP_I32_SHL: lambda a, b: a << (b & SHIFT_MASK),
    OP_I32_SHR_U: lambda a, b: a >> (b & SHIFT_MASK),
    OP_I32_SHR_S: lambda a, b: _sext32(a) >> (b & SHIFT_MASK),
    OP_I32_EQ: lambda a, b: 1 if a == b else 0,
    OP_I32_NE: lambda a, b: 1 if a != b else 0,
    OP_I32_LT_U: lambda a, b: 1 if a < b else 0,
    OP_I32_GT_U: lambda a, b: 1 if a > b else 0,
    OP_I32_LE_U: lambda a, b: 1 if a <= b else 0,
    OP_I32_GE_U: lambda a, b: 1 if a >= b else 0,
    OP_I32_LT_S: lambda a, b: 1 if _sext32(a) < _sext32(b) else 0,
    OP_I32_GT_S: lambda a, b: 1 if _sext32(a) > _sext32(b) else 0,
    OP_I32_LE_S: lambda a, b: 1 if _sext32(a) <= _sext32(b) else 0,
    OP_I32_GE_S: lambda a, b: 1 if _sext32(a) >= _sext32(b) else 0,
}

_IN_SCOPE = frozenset(
    {OP_I32_CONST, OP_LOCAL_GET, OP_I32_EQZ, OP_SELECT} | set(I32_BINOPS)
)


@dataclass(frozen=True)
class Instr:
    """One Wasm instruction: an opcode and (at most) one immediate operand.

    ``imm`` is the i32 literal for ``i32.const`` or the local index for
    ``local.get``; ``None`` for ``i32.add``.
    """

    op: str
    imm: int | None = None


@dataclass
class WasmModule:
    """A loaded single-function i32 module: the function ``body`` (a list of
    ``Instr``) and the number of i32 locals (``nlocals``). ``pc`` indexes the
    body. Parameters are modeled as the first locals; their initial values come
    from the run binding."""

    body: list[Instr] = field(default_factory=list)
    nlocals: int = 0
    entry: int = 0

    @property
    def max_stack(self) -> int:
        """A static bound on the value-stack depth this body can reach.

        Each ``i32.const`` / ``local.get`` pushes one; every i32 binary op
        (``i32.add`` and the rest of ``I32_BINOPS``) pops two and pushes one
        (net -1); ``i32.eqz`` pops one and pushes one (net 0); ``select`` pops
        three and pushes one (net -2). The running maximum over the
        straight-line body is the depth the BTOR2 lowering must allocate state
        for."""
        depth = 0
        peak = 0
        for ins in self.body:
            if ins.op in (OP_I32_CONST, OP_LOCAL_GET):
                depth += 1
            elif ins.op in I32_BINOPS:
                depth = max(depth - 1, 0)        # net -1 (pop 2, push 1)
            elif ins.op == OP_I32_EQZ:
                depth = max(depth, 0)            # net 0 (pop 1, push 1)
            elif ins.op == OP_SELECT:
                depth = max(depth - 2, 0)
            peak = max(peak, depth)
        return peak


def module(body: list[Instr], nlocals: int = 0) -> WasmModule:
    return WasmModule(body=list(body), nlocals=nlocals)


def _u32(v: int) -> int:
    return v & MASK32


def _execute(ins: Instr, pc: int, stack: list[int], locals_: list[int]) -> int:
    """Apply one in-scope reduction rule, mutating ``stack`` in place; return
    the next ``pc``. Out-of-scope opcodes / malformed stacks hard-abort."""
    op = ins.op
    if op == OP_I32_CONST:
        if ins.imm is None:
            raise Unsupported("wasm", "i32.const", "missing immediate")
        stack.append(_u32(int(ins.imm)))
        return pc + 1
    if op == OP_LOCAL_GET:
        idx = ins.imm
        if idx is None or not (0 <= idx < len(locals_)):
            raise Unsupported("wasm", "local.get", f"index {idx} out of range")
        stack.append(locals_[idx])
        return pc + 1
    if op in I32_BINOPS:
        if len(stack) < 2:
            raise Unsupported("wasm", op, "stack underflow")
        b = stack.pop()
        a = stack.pop()
        # Each rule is a pure (a, b) -> i32 over the u32 operands; the result is
        # reduced mod 2³² (a no-op for the 0/1 comparisons). This single source
        # of truth is mirrored by the BTOR2 lowering per construct.
        stack.append(_u32(I32_BINOPS[op](a, b)))
        return pc + 1
    if op == OP_I32_EQZ:
        if len(stack) < 1:
            raise Unsupported("wasm", "i32.eqz", "stack underflow")
        x = stack.pop()
        stack.append(1 if x == 0 else 0)        # i32 result (Wasm ieqz_32)
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
    value}`` — parameters are the first locals). Returns the post-step trace.
    """
    locals_ = [0] * mod.nlocals
    pc = mod.entry
    if binding:
        pc = binding.get("pc", pc)
        for idx, val in binding.get("locals", {}).items():
            i = int(idx)
            if not (0 <= i < mod.nlocals):
                raise Unsupported("wasm", "local.get", f"binding index {i} out of range")
            locals_[i] = _u32(int(val))

    stack: list[int] = []
    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (0 <= pc < len(mod.body)):
            trace.append(_state(pc, stack, locals_, True))   # off the end -> halt
            break
        pc = _execute(mod.body[pc], pc, stack, locals_)
        steps += 1
        halted = not (0 <= pc < len(mod.body))
        trace.append(_state(pc, stack, locals_, halted))
        if halted:
            break
    return trace
