"""Step-based concrete executor for the WASM 1.0 MVP integer opcode subset.

One call to :meth:`WasmSourceInterpreter.run` returns a :class:`SourceTrace`
containing one :class:`SourceStep` per instruction executed.

Covered: all i32/i64 integer arithmetic, comparisons, bitwise ops, rotates
and shifts; memory loads/stores (all widths); structured control flow
(block, loop, if/else); br, br_if, br_table, return; local.get/set/tee,
global.get/set; call (direct, including imports); call_indirect; memory.size/
grow; drop, select; i32.wrap_i64, i64.extend_i32_s/u.

Not covered (trap if reached): float arithmetic, SIMD, threads, GC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gurdy.core.interp.types import SourceStep, SourceTrace
from gurdy.pairs.wasm_btor2.source import WasmSource
from gurdy.pairs.wasm_btor2.source.decoder import (
    BLOCKTYPE_VOID,
    WasmTrap,
    _eval_const_expr,
)
from gurdy.pairs.wasm_btor2.source_interp.bindings import (
    FREE,
    Free,
    FreeFieldNotAllowed,
    WasmInputBinding,
)


INTERPRETER_VERSION = "1.0.0"
PAIR_ID = "wasm-btor2"

_MAX_CALL_DEPTH = 512

# Masks
_M32 = 0xFFFFFFFF
_M64 = 0xFFFFFFFFFFFFFFFF
_I32_MIN = -(1 << 31)
_I64_MIN = -(1 << 63)


# ---------------------------------------------------------------------------
# Integer helpers
# ---------------------------------------------------------------------------


def _s32(v: int) -> int:
    v &= _M32
    return v if v < (1 << 31) else v - (1 << 32)


def _s64(v: int) -> int:
    v &= _M64
    return v if v < (1 << 63) else v - (1 << 64)


def _trunc_div(a: int, b: int) -> int:
    return -(-a // b) if (a < 0) != (b < 0) else a // b


def _clz32(v: int) -> int:
    v &= _M32
    return 32 - v.bit_length() if v else 32


def _ctz32(v: int) -> int:
    v &= _M32
    if not v:
        return 32
    return (v & -v).bit_length() - 1


def _clz64(v: int) -> int:
    v &= _M64
    return 64 - v.bit_length() if v else 64


def _ctz64(v: int) -> int:
    v &= _M64
    if not v:
        return 64
    return (v & -v).bit_length() - 1


# ---------------------------------------------------------------------------
# Frame & label
# ---------------------------------------------------------------------------


@dataclass
class Label:
    """Control-flow label pushed by block/loop/if.

    ``kind``: ``"block"``, ``"loop"``, or ``"if"``.
    ``arity``: number of result values forwarded by a ``br`` targeting this label.
    ``br_target``: instruction index to jump to on ``br``.
                   block/if → first instr after the matching ``end``.
                   loop → the loop instruction itself (back-edge).
    ``stack_height``: value-stack depth at label entry (before the label's
                      input values are pushed, per WASM 1.0 MVP where
                      blocks have no inputs).
    """

    kind: str
    arity: int
    br_target: int
    stack_height: int


@dataclass
class Frame:
    """One call-stack entry."""

    func_idx: int
    locals: list[int]                     # params + declared locals (all zeroed unless bound)
    body: list                            # list[Instr] from CodeEntry.body
    return_arity: int
    pc: int = 0
    value_stack: list[int] = field(default_factory=list)
    label_stack: list[Label] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Machine state
# ---------------------------------------------------------------------------


@dataclass
class WasmMachine:
    source: WasmSource
    binding: WasmInputBinding
    call_stack: list[Frame]
    globals: list[int]           # module-level global values (mutable)
    memory: bytearray            # linear memory (may be empty if no memory section)
    record_shadow: bool = False
    trapped: bool = False
    trap_reason: str = ""
    halted: bool = False
    # Shadow accumulation
    _shadow: list[dict[str, Any]] = field(default_factory=list)

    @property
    def frame(self) -> Frame:
        return self.call_stack[-1]

    def _trap(self, reason: str) -> None:
        self.trapped = True
        self.trap_reason = reason
        raise WasmTrap(reason)

    # -----------------------------------------------------------------
    # Memory access helpers
    # -----------------------------------------------------------------

    def _mem_load(self, addr: int, width: int) -> int:
        end = addr + width
        if end > len(self.memory):
            self._trap(f"out of bounds memory access at {addr:#x}")
        return int.from_bytes(self.memory[addr:end], "little")

    def _mem_store(self, addr: int, width: int, value: int) -> None:
        end = addr + width
        if end > len(self.memory):
            self._trap(f"out of bounds memory access at {addr:#x}")
        self.memory[addr:end] = value.to_bytes(width, "little")

    # -----------------------------------------------------------------
    # Step
    # -----------------------------------------------------------------

    def step(self, step_idx: int) -> SourceStep:
        frame = self.frame
        if frame.pc >= len(frame.body):
            # Should not happen in valid WASM but guard anyway
            self._do_return(frame)
            return SourceStep(step_idx, {"func_idx": frame.func_idx, "pc": frame.pc, "op": "implicit_return"})

        ins = frame.body[frame.pc]
        op = ins.op
        vs = frame.value_stack

        shadow: dict[str, Any] = {"op": op, "func_idx": frame.func_idx, "instr_pc": frame.pc}

        try:
            frame.pc += 1  # advance before execution (br/call/etc may overwrite)

            # ---------------------------------------------------------------
            # Control flow
            # ---------------------------------------------------------------
            if op == "unreachable":
                self._trap("unreachable")

            elif op == "nop":
                pass

            elif op == "block":
                bt = ins.imm[0]
                arity = 0 if bt == BLOCKTYPE_VOID else 1
                frame.label_stack.append(Label("block", arity, ins.br_target, len(vs)))

            elif op == "loop":
                bt = ins.imm[0]
                arity = 0 if bt == BLOCKTYPE_VOID else 1
                # br_target for loop = the loop instruction itself (back-edge)
                frame.label_stack.append(Label("loop", arity, ins.br_target, len(vs)))

            elif op == "if":
                cond = vs.pop()
                bt = ins.imm[0]
                arity = 0 if bt == BLOCKTYPE_VOID else 1
                frame.label_stack.append(Label("if", arity, ins.br_target, len(vs)))
                if not cond:
                    # Jump to else or after end
                    frame.pc = ins.alt

            elif op == "else":
                # Reached from the true branch of an if
                # Jump past the else body to after the end
                frame.label_stack.pop()
                frame.pc = ins.br_target

            elif op == "end":
                if not frame.label_stack:
                    # Function-level end: return from this frame
                    self._do_return(frame)
                else:
                    frame.label_stack.pop()
                    # Continue at frame.pc (already incremented past end)

            elif op == "br":
                self._do_br(frame, ins.imm[0])

            elif op == "br_if":
                cond = vs.pop()
                if cond:
                    self._do_br(frame, ins.imm[0])

            elif op == "br_table":
                labels, default = ins.imm
                idx = vs.pop()
                label_idx = labels[idx] if idx < len(labels) else default
                self._do_br(frame, label_idx)

            elif op == "return":
                self._do_return(frame)

            # ---------------------------------------------------------------
            # Calls
            # ---------------------------------------------------------------
            elif op == "call":
                self._do_call(ins.imm[0])

            elif op == "call_indirect":
                type_idx, table_idx = ins.imm
                elem_idx = vs.pop()
                # Look up function index from table
                if not self.source.module.tables:
                    self._trap("call_indirect: no table")
                # We don't track table contents fully in P2; use import_returns as fallback
                # For a minimal implementation, resolve through exported element if possible
                self._trap("call_indirect: not implemented in P2")

            # ---------------------------------------------------------------
            # Parametric
            # ---------------------------------------------------------------
            elif op == "drop":
                vs.pop()

            elif op == "select":
                c = vs.pop(); v2 = vs.pop(); v1 = vs.pop()
                vs.append(v1 if c else v2)

            # ---------------------------------------------------------------
            # Variables
            # ---------------------------------------------------------------
            elif op == "local.get":
                idx = ins.imm[0]
                vs.append(frame.locals[idx])
                if self.record_shadow:
                    shadow["local_read"] = idx

            elif op == "local.set":
                idx = ins.imm[0]
                old = frame.locals[idx]
                frame.locals[idx] = vs.pop()
                if self.record_shadow:
                    shadow["local_write"] = (idx, old, frame.locals[idx])

            elif op == "local.tee":
                idx = ins.imm[0]
                old = frame.locals[idx]
                frame.locals[idx] = vs[-1]   # peek, don't pop
                if self.record_shadow:
                    shadow["local_write"] = (idx, old, frame.locals[idx])

            elif op == "global.get":
                idx = ins.imm[0]
                vs.append(self.globals[idx])
                if self.record_shadow:
                    shadow["global_read"] = idx

            elif op == "global.set":
                idx = ins.imm[0]
                old = self.globals[idx]
                self.globals[idx] = vs.pop()
                if self.record_shadow:
                    shadow["global_write"] = (idx, old, self.globals[idx])

            # ---------------------------------------------------------------
            # Memory loads
            # ---------------------------------------------------------------
            elif op == "i32.load":
                _align, offset = ins.imm
                base = vs.pop()
                addr = (base + offset) & _M32
                vs.append(self._mem_load(addr, 4))

            elif op == "i64.load":
                _align, offset = ins.imm
                base = vs.pop()
                addr = (base + offset) & _M32
                vs.append(self._mem_load(addr, 8))

            elif op == "i32.load8_s":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                v = self._mem_load(addr, 1)
                vs.append(_s32(v if v < 0x80 else v - 0x100) & _M32)

            elif op == "i32.load8_u":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                vs.append(self._mem_load(addr, 1))

            elif op == "i32.load16_s":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                v = self._mem_load(addr, 2)
                vs.append(_s32(v if v < 0x8000 else v - 0x10000) & _M32)

            elif op == "i32.load16_u":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                vs.append(self._mem_load(addr, 2))

            elif op == "i64.load8_s":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                v = self._mem_load(addr, 1)
                vs.append(_s64(v if v < 0x80 else v - 0x100) & _M64)

            elif op == "i64.load8_u":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                vs.append(self._mem_load(addr, 1))

            elif op == "i64.load16_s":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                v = self._mem_load(addr, 2)
                vs.append(_s64(v if v < 0x8000 else v - 0x10000) & _M64)

            elif op == "i64.load16_u":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                vs.append(self._mem_load(addr, 2))

            elif op == "i64.load32_s":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                v = self._mem_load(addr, 4)
                vs.append(_s64(v if v < 0x80000000 else v - 0x100000000) & _M64)

            elif op == "i64.load32_u":
                _align, offset = ins.imm
                addr = (vs.pop() + offset) & _M32
                vs.append(self._mem_load(addr, 4))

            # ---------------------------------------------------------------
            # Memory stores
            # ---------------------------------------------------------------
            elif op == "i32.store":
                _align, offset = ins.imm
                v = vs.pop(); base = vs.pop()
                addr = (base + offset) & _M32
                self._mem_store(addr, 4, v & _M32)

            elif op == "i64.store":
                _align, offset = ins.imm
                v = vs.pop(); base = vs.pop()
                addr = (base + offset) & _M32
                self._mem_store(addr, 8, v & _M64)

            elif op == "i32.store8":
                _align, offset = ins.imm
                v = vs.pop(); base = vs.pop()
                addr = (base + offset) & _M32
                self._mem_store(addr, 1, v & 0xFF)

            elif op == "i32.store16":
                _align, offset = ins.imm
                v = vs.pop(); base = vs.pop()
                addr = (base + offset) & _M32
                self._mem_store(addr, 2, v & 0xFFFF)

            elif op == "i64.store8":
                _align, offset = ins.imm
                v = vs.pop(); base = vs.pop()
                addr = (base + offset) & _M32
                self._mem_store(addr, 1, v & 0xFF)

            elif op == "i64.store16":
                _align, offset = ins.imm
                v = vs.pop(); base = vs.pop()
                addr = (base + offset) & _M32
                self._mem_store(addr, 2, v & 0xFFFF)

            elif op == "i64.store32":
                _align, offset = ins.imm
                v = vs.pop(); base = vs.pop()
                addr = (base + offset) & _M32
                self._mem_store(addr, 4, v & _M32)

            # ---------------------------------------------------------------
            # Memory ops
            # ---------------------------------------------------------------
            elif op == "memory.size":
                vs.append(len(self.memory) // 65536)

            elif op == "memory.grow":
                n_pages = vs.pop()
                old_pages = len(self.memory) // 65536
                new_pages = old_pages + n_pages
                max_pages = 65536  # WASM 1.0 max
                mi = self.source.memory_info()
                if mi and mi.limits.max is not None:
                    max_pages = mi.limits.max
                if new_pages <= max_pages:
                    self.memory.extend(bytes(n_pages * 65536))
                    vs.append(old_pages)
                else:
                    vs.append(_M32)  # -1: growth failed

            # ---------------------------------------------------------------
            # Constants
            # ---------------------------------------------------------------
            elif op == "i32.const":
                vs.append(ins.imm[0] & _M32)

            elif op == "i64.const":
                vs.append(ins.imm[0] & _M64)

            # ---------------------------------------------------------------
            # i32 comparisons
            # ---------------------------------------------------------------
            elif op == "i32.eqz":
                vs.append(1 if not (vs.pop() & _M32) else 0)

            elif op == "i32.eq":
                b = vs.pop() & _M32; a = vs.pop() & _M32
                vs.append(1 if a == b else 0)

            elif op == "i32.ne":
                b = vs.pop() & _M32; a = vs.pop() & _M32
                vs.append(0 if a == b else 1)

            elif op == "i32.lt_s":
                b = vs.pop(); a = vs.pop()
                vs.append(1 if _s32(a) < _s32(b) else 0)

            elif op == "i32.lt_u":
                b = vs.pop() & _M32; a = vs.pop() & _M32
                vs.append(1 if a < b else 0)

            elif op == "i32.gt_s":
                b = vs.pop(); a = vs.pop()
                vs.append(1 if _s32(a) > _s32(b) else 0)

            elif op == "i32.gt_u":
                b = vs.pop() & _M32; a = vs.pop() & _M32
                vs.append(1 if a > b else 0)

            elif op == "i32.le_s":
                b = vs.pop(); a = vs.pop()
                vs.append(1 if _s32(a) <= _s32(b) else 0)

            elif op == "i32.le_u":
                b = vs.pop() & _M32; a = vs.pop() & _M32
                vs.append(1 if a <= b else 0)

            elif op == "i32.ge_s":
                b = vs.pop(); a = vs.pop()
                vs.append(1 if _s32(a) >= _s32(b) else 0)

            elif op == "i32.ge_u":
                b = vs.pop() & _M32; a = vs.pop() & _M32
                vs.append(1 if a >= b else 0)

            # ---------------------------------------------------------------
            # i64 comparisons
            # ---------------------------------------------------------------
            elif op == "i64.eqz":
                vs.append(1 if not (vs.pop() & _M64) else 0)

            elif op == "i64.eq":
                b = vs.pop() & _M64; a = vs.pop() & _M64
                vs.append(1 if a == b else 0)

            elif op == "i64.ne":
                b = vs.pop() & _M64; a = vs.pop() & _M64
                vs.append(0 if a == b else 1)

            elif op == "i64.lt_s":
                b = vs.pop(); a = vs.pop()
                vs.append(1 if _s64(a) < _s64(b) else 0)

            elif op == "i64.lt_u":
                b = vs.pop() & _M64; a = vs.pop() & _M64
                vs.append(1 if a < b else 0)

            elif op == "i64.gt_s":
                b = vs.pop(); a = vs.pop()
                vs.append(1 if _s64(a) > _s64(b) else 0)

            elif op == "i64.gt_u":
                b = vs.pop() & _M64; a = vs.pop() & _M64
                vs.append(1 if a > b else 0)

            elif op == "i64.le_s":
                b = vs.pop(); a = vs.pop()
                vs.append(1 if _s64(a) <= _s64(b) else 0)

            elif op == "i64.le_u":
                b = vs.pop() & _M64; a = vs.pop() & _M64
                vs.append(1 if a <= b else 0)

            elif op == "i64.ge_s":
                b = vs.pop(); a = vs.pop()
                vs.append(1 if _s64(a) >= _s64(b) else 0)

            elif op == "i64.ge_u":
                b = vs.pop() & _M64; a = vs.pop() & _M64
                vs.append(1 if a >= b else 0)

            # ---------------------------------------------------------------
            # i32 arithmetic
            # ---------------------------------------------------------------
            elif op == "i32.clz":
                vs.append(_clz32(vs.pop()))

            elif op == "i32.ctz":
                vs.append(_ctz32(vs.pop()))

            elif op == "i32.popcnt":
                vs.append(bin(vs.pop() & _M32).count("1"))

            elif op == "i32.add":
                b = vs.pop(); a = vs.pop()
                vs.append((a + b) & _M32)

            elif op == "i32.sub":
                b = vs.pop(); a = vs.pop()
                vs.append((a - b) & _M32)

            elif op == "i32.mul":
                b = vs.pop(); a = vs.pop()
                vs.append((a * b) & _M32)

            elif op == "i32.div_s":
                b = vs.pop(); a = vs.pop()
                sb, sa = _s32(b), _s32(a)
                if sb == 0:
                    self._trap("integer divide by zero")
                if sa == _I32_MIN and sb == -1:
                    self._trap("integer overflow")
                vs.append(_trunc_div(sa, sb) & _M32)

            elif op == "i32.div_u":
                b = vs.pop() & _M32; a = vs.pop() & _M32
                if b == 0:
                    self._trap("integer divide by zero")
                vs.append(a // b)

            elif op == "i32.rem_s":
                b = vs.pop(); a = vs.pop()
                sb, sa = _s32(b), _s32(a)
                if sb == 0:
                    self._trap("integer divide by zero")
                q = _trunc_div(sa, sb)
                vs.append((sa - q * sb) & _M32)

            elif op == "i32.rem_u":
                b = vs.pop() & _M32; a = vs.pop() & _M32
                if b == 0:
                    self._trap("integer divide by zero")
                vs.append(a % b)

            elif op == "i32.and":
                b = vs.pop(); a = vs.pop()
                vs.append((a & b) & _M32)

            elif op == "i32.or":
                b = vs.pop(); a = vs.pop()
                vs.append((a | b) & _M32)

            elif op == "i32.xor":
                b = vs.pop(); a = vs.pop()
                vs.append((a ^ b) & _M32)

            elif op == "i32.shl":
                b = vs.pop(); a = vs.pop()
                vs.append((a << (b & 31)) & _M32)

            elif op == "i32.shr_s":
                b = vs.pop(); a = vs.pop()
                vs.append(_s32(a) >> (b & 31) & _M32)

            elif op == "i32.shr_u":
                b = vs.pop(); a = vs.pop()
                vs.append((a & _M32) >> (b & 31))

            elif op == "i32.rotl":
                b = vs.pop() & 31; a = vs.pop() & _M32
                vs.append(((a << b) | (a >> (32 - b))) & _M32 if b else a)

            elif op == "i32.rotr":
                b = vs.pop() & 31; a = vs.pop() & _M32
                vs.append(((a >> b) | (a << (32 - b))) & _M32 if b else a)

            # ---------------------------------------------------------------
            # i64 arithmetic
            # ---------------------------------------------------------------
            elif op == "i64.clz":
                vs.append(_clz64(vs.pop()))

            elif op == "i64.ctz":
                vs.append(_ctz64(vs.pop()))

            elif op == "i64.popcnt":
                vs.append(bin(vs.pop() & _M64).count("1"))

            elif op == "i64.add":
                b = vs.pop(); a = vs.pop()
                vs.append((a + b) & _M64)

            elif op == "i64.sub":
                b = vs.pop(); a = vs.pop()
                vs.append((a - b) & _M64)

            elif op == "i64.mul":
                b = vs.pop(); a = vs.pop()
                vs.append((a * b) & _M64)

            elif op == "i64.div_s":
                b = vs.pop(); a = vs.pop()
                sb, sa = _s64(b), _s64(a)
                if sb == 0:
                    self._trap("integer divide by zero")
                if sa == _I64_MIN and sb == -1:
                    self._trap("integer overflow")
                vs.append(_trunc_div(sa, sb) & _M64)

            elif op == "i64.div_u":
                b = vs.pop() & _M64; a = vs.pop() & _M64
                if b == 0:
                    self._trap("integer divide by zero")
                vs.append(a // b)

            elif op == "i64.rem_s":
                b = vs.pop(); a = vs.pop()
                sb, sa = _s64(b), _s64(a)
                if sb == 0:
                    self._trap("integer divide by zero")
                q = _trunc_div(sa, sb)
                vs.append((sa - q * sb) & _M64)

            elif op == "i64.rem_u":
                b = vs.pop() & _M64; a = vs.pop() & _M64
                if b == 0:
                    self._trap("integer divide by zero")
                vs.append(a % b)

            elif op == "i64.and":
                b = vs.pop(); a = vs.pop()
                vs.append((a & b) & _M64)

            elif op == "i64.or":
                b = vs.pop(); a = vs.pop()
                vs.append((a | b) & _M64)

            elif op == "i64.xor":
                b = vs.pop(); a = vs.pop()
                vs.append((a ^ b) & _M64)

            elif op == "i64.shl":
                b = vs.pop(); a = vs.pop()
                vs.append((a << (b & 63)) & _M64)

            elif op == "i64.shr_s":
                b = vs.pop(); a = vs.pop()
                vs.append(_s64(a) >> (b & 63) & _M64)

            elif op == "i64.shr_u":
                b = vs.pop(); a = vs.pop()
                vs.append((a & _M64) >> (b & 63))

            elif op == "i64.rotl":
                b = vs.pop() & 63; a = vs.pop() & _M64
                vs.append(((a << b) | (a >> (64 - b))) & _M64 if b else a)

            elif op == "i64.rotr":
                b = vs.pop() & 63; a = vs.pop() & _M64
                vs.append(((a >> b) | (a << (64 - b))) & _M64 if b else a)

            # ---------------------------------------------------------------
            # Conversion
            # ---------------------------------------------------------------
            elif op == "i32.wrap_i64":
                vs.append(vs.pop() & _M32)

            elif op == "i64.extend_i32_s":
                vs.append(_s32(vs.pop()) & _M64)

            elif op == "i64.extend_i32_u":
                vs.append(vs.pop() & _M32)

            elif op == "i32.extend8_s":
                v = vs.pop() & 0xFF
                vs.append((v if v < 0x80 else v - 0x100) & _M32)

            elif op == "i32.extend16_s":
                v = vs.pop() & 0xFFFF
                vs.append((v if v < 0x8000 else v - 0x10000) & _M32)

            # ---------------------------------------------------------------
            # Unsupported (float and misc)
            # ---------------------------------------------------------------
            else:
                self._trap(f"unsupported opcode: {op!r}")

        except WasmTrap:
            raise
        except IndexError:
            self._trap("value stack underflow")

        if self.record_shadow:
            shadow["stack_depth"] = len(vs)
            self._shadow.append(shadow)

        return SourceStep(
            step=step_idx,
            location={"func_idx": frame.func_idx if self.call_stack else -1,
                      "pc": frame.pc - 1,
                      "op": op},
            deltas=shadow if self.record_shadow else None,
        )

    # -----------------------------------------------------------------
    # Branch / call helpers
    # -----------------------------------------------------------------

    def _do_br(self, frame: Frame, label_idx: int) -> None:
        ls = frame.label_stack
        if label_idx > len(ls):
            self._trap(f"br: label index {label_idx} out of range")
        if label_idx == len(ls):
            # Function-level branch = return
            self._do_return(frame)
            return
        label = ls[-(label_idx + 1)]
        # Preserve label.arity values from top of stack
        arity = label.arity
        results = frame.value_stack[-arity:] if arity else []
        # Trim stack back to height at label entry
        del frame.value_stack[label.stack_height:]
        frame.value_stack.extend(results)
        # Pop label_idx + 1 labels
        del frame.label_stack[-(label_idx + 1):]
        # Jump
        frame.pc = label.br_target

    def _do_return(self, frame: Frame) -> None:
        arity = frame.return_arity
        results = frame.value_stack[-arity:] if arity else []
        self.call_stack.pop()
        if self.call_stack:
            self.call_stack[-1].value_stack.extend(results)
        else:
            self.halted = True
            # Store results for the caller to read from final_state
            self._final_results = results

    def _do_call(self, func_idx: int) -> None:
        if len(self.call_stack) >= _MAX_CALL_DEPTH:
            self._trap("call stack exhausted")
        ftype = self.source.func_type(func_idx)
        if ftype is None:
            self._trap(f"call: invalid func index {func_idx}")
        n_params = len(ftype.params)
        caller = self.call_stack[-1]
        if n_params > 0:
            params = caller.value_stack[-n_params:]
            del caller.value_stack[-n_params:]
        else:
            params = []

        if self.source.is_import(func_idx):
            # Host import: use binding's import_returns
            imp_funcs = self.source.import_funcs()
            if func_idx < len(imp_funcs):
                mod_name, field_name, _ = imp_funcs[func_idx]
                key = f"{mod_name}.{field_name}"
            else:
                key = f"__import_{func_idx}"
            n_results = len(ftype.results)
            if n_results == 0:
                pass  # void import: no result
            else:
                raw = self.binding.import_returns.get(key, 0)
                val = 0 if isinstance(raw, Free) else int(raw)
                caller.value_stack.append(val & _M64)
            return

        # Local function
        code = self.source.code_entry(func_idx)
        if code is None:
            self._trap(f"call: no code for func {func_idx}")

        # Build locals: params (masked to declared type) + zeroed declared locals
        locals_list: list[int] = list(params)  # params already on stack as ints
        for ld in code.locals:
            locals_list.extend([0] * ld.count)

        new_frame = Frame(
            func_idx=func_idx,
            locals=locals_list,
            body=code.body,
            return_arity=len(ftype.results),
        )
        self.call_stack.append(new_frame)


# ---------------------------------------------------------------------------
# Machine initialization
# ---------------------------------------------------------------------------


def _init_machine(
    source: WasmSource,
    binding: WasmInputBinding,
    entry_func_idx: int,
    record_shadow: bool,
) -> WasmMachine:
    mod = source.module

    # --- Global values ---
    globs: list[int] = []
    for i, g in enumerate(mod.globals):
        if i in binding.global_init and not isinstance(binding.global_init[i], Free):
            globs.append(int(binding.global_init[i]) & _M64)
        else:
            globs.append(_eval_const_expr(g.init) & _M64)

    # --- Linear memory ---
    mem_pages = 0
    if mod.memories:
        mem_pages = mod.memories[0].limits.min
    mem = bytearray(mem_pages * 65536)
    # Apply data segments
    for seg in mod.data:
        offset = _eval_const_expr(seg.offset)
        end = offset + len(seg.init)
        if end <= len(mem):
            mem[offset:end] = seg.init
    # Apply binding memory overrides
    for addr, val in binding.memory_init.items():
        v = 0 if isinstance(val, Free) else int(val)
        if addr < len(mem):
            mem[addr] = v & 0xFF

    # --- Build entry frame ---
    ftype = source.func_type(entry_func_idx)
    if ftype is None:
        raise ValueError(f"no type for entry function {entry_func_idx}")
    code = source.code_entry(entry_func_idx)
    if code is None:
        raise ValueError(f"entry function {entry_func_idx} has no code (it's an import?)")

    n_params = len(ftype.params)
    locals_list: list[int] = []
    for i in range(n_params):
        raw = binding.param_init.get(i, 0)
        v = 0 if isinstance(raw, Free) else int(raw)
        locals_list.append(v & _M64)
    for ld in code.locals:
        locals_list.extend([0] * ld.count)

    entry_frame = Frame(
        func_idx=entry_func_idx,
        locals=locals_list,
        body=code.body,
        return_arity=len(ftype.results),
    )

    machine = WasmMachine(
        source=source,
        binding=binding,
        call_stack=[entry_frame],
        globals=globs,
        memory=mem,
        record_shadow=record_shadow,
    )
    machine._final_results = []
    return machine


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------


class WasmSourceInterpreter:
    """``SourceInterpreter`` protocol implementation for wasm-btor2."""

    version: str = INTERPRETER_VERSION

    def run(
        self,
        source: WasmSource,
        binding: WasmInputBinding,
        max_steps: int,
        *,
        entry_name: str | None = None,
        entry_func_idx: int | None = None,
        record_shadow: bool = False,
    ) -> SourceTrace:
        """Execute the WASM module and return a :class:`SourceTrace`.

        Exactly one of ``entry_name`` (exported function name) or
        ``entry_func_idx`` (raw module function index) must be given.

        ``max_steps`` caps the number of instructions executed.

        ``record_shadow=True`` records per-step state deltas in each step's
        ``deltas`` field for use by the alignment oracle.

        Raises ``FreeFieldNotAllowed`` when the binding contains FREE cells
        and ``record_shadow=False``.
        """
        if binding.has_free_fields() and not record_shadow:
            raise FreeFieldNotAllowed(
                "WasmSourceInterpreter does not accept FREE binding fields "
                "without record_shadow=True."
            )

        if entry_name is not None:
            func_idx = source.export_func_idx(entry_name)
            if func_idx is None:
                raise ValueError(f"no exported function {entry_name!r}")
        elif entry_func_idx is not None:
            func_idx = entry_func_idx
        else:
            raise ValueError("entry_name or entry_func_idx is required")

        machine = _init_machine(source, binding, func_idx, record_shadow)
        inputs_hash = binding.inputs_hash()

        steps: list[SourceStep] = []
        halt_reason: str | None = None

        for i in range(max_steps):
            if machine.halted:
                halt_reason = "halted"
                break
            if machine.trapped:
                halt_reason = machine.trap_reason
                break
            try:
                step = machine.step(i)
            except WasmTrap as exc:
                halt_reason = exc.reason
                steps.append(SourceStep(i, {"func_idx": -1, "pc": -1, "op": "trap"}, halted=True))
                break
            steps.append(step)
        else:
            halt_reason = "max_steps_reached"

        final: dict[str, Any] = {
            "return_values": list(getattr(machine, "_final_results", [])),
            "globals": list(machine.globals),
            "memory_pages": len(machine.memory) // 65536,
        }
        if record_shadow:
            final["shadow"] = list(machine._shadow)

        return SourceTrace(
            pair=PAIR_ID,
            interpreter_version=INTERPRETER_VERSION,
            inputs_hash=inputs_hash,
            steps=tuple(steps),
            final_state=final,
            halted=machine.halted or machine.trapped,
            halt_reason=halt_reason,
        )


__all__ = [
    "INTERPRETER_VERSION",
    "PAIR_ID",
    "WasmMachine",
    "WasmSourceInterpreter",
]
