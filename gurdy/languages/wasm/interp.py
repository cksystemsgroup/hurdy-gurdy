"""A deterministic WebAssembly interpreter (the shared Wasm source interpreter).

Scope (MVP, thin-first — ``languages/wasm`` brief): a single straight-line
i32 function body over the **integer-stack core** — ``i32.const`` (push an
immediate), ``local.get`` (push a local), and ``i32.add`` (the headline
construct: pop two, push their 32-bit sum). This mirrors the official Wasm
small-step operational semantics for these three reduction rules over a typed
value stack with locals; ``i32.add`` is modular 2^32 addition, as the spec
defines (`iadd_32`). Every other instruction hard-aborts with ``Unsupported``
(BENCHMARKS.md §3) — there is no silent drop.

A *behavior* is a ``Trace`` of **post-step** states (ARCHITECTURE.md §5). The
observable state after each instruction is::

    {"pc": <next instruction index>,
     "halted": <ran off the end of the body>,
     "stack": (<bottom>, ..., <top>),   # the i32 value stack, as a tuple
     "sp": <stack depth>,
     "locals": (<l0>, <l1>, ...)}       # the i32 locals

Pure and deterministic; ``pc`` indexes the instruction list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace

MASK32 = (1 << 32) - 1

# The in-scope opcodes. The mnemonics double as the binary-opcode documentation
# below, but the interpreter consumes the structured ``Instr``, not raw bytes.
OP_I32_CONST = "i32.const"   # binary 0x41
OP_LOCAL_GET = "local.get"   # binary 0x20
OP_I32_ADD = "i32.add"       # binary 0x6a

_IN_SCOPE = frozenset({OP_I32_CONST, OP_LOCAL_GET, OP_I32_ADD})


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

        Each ``i32.const`` / ``local.get`` pushes one; ``i32.add`` pops two and
        pushes one (net -1). The running maximum over the straight-line body is
        the depth the BTOR2 lowering must allocate state for."""
        depth = 0
        peak = 0
        for ins in self.body:
            if ins.op in (OP_I32_CONST, OP_LOCAL_GET):
                depth += 1
            elif ins.op == OP_I32_ADD:
                depth = max(depth - 1, 0)
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
    if op == OP_I32_ADD:
        if len(stack) < 2:
            raise Unsupported("wasm", "i32.add", "stack underflow")
        b = stack.pop()
        a = stack.pop()
        stack.append(_u32(a + b))
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
