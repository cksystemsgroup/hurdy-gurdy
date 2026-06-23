"""The shared Sail (RISC-V model) interpreter — an *independent* RISC-V
executor that runs each instruction by concretely evaluating its Sail-derived
``Expr`` trees (``rv64``), rather than the hand-written Python ops of
``languages/riscv/interp.py``. That independence is what makes the
Sail-mediated route a real cross-check of the direct one.

A "Sail program" is ``{"words":[...], "entry":int, "init_regs":{i:v},
"property":{...}}``. Scope is the RV64IMC slice (``rv64.decode`` + the
``compressed`` decompressor): the ALU and M core, control flow, the
C-compressed encodings, and loads/stores, plus ECALL/EBREAK (halt);
out-of-scope opcodes hard-abort. Behavior is the same
``{"pc","x1".."x31","halted"}`` trace shape as the RISC-V interpreter, so the
commuting-square oracle compares them directly.

The interpreter is model-agnostic (``languages/sail`` brief): a "Sail object"
that carries ``{"isa": "aarch64", ...}`` dispatches to the *additive* AArch64
executor (``aarch64.run_aarch64`` — the ALU family ``ADD``/``SUB`` immediate +
``MOVZ``, the flag-setting ``SUBS``/``CMP`` **and** ``ADDS``/``CMN``, the
conditional ``B.cond`` **and** unconditional ``B``/``BL`` control flow, and the
first memory access — the 64-bit unsigned-offset ``LDR``/``STR``) for the
``aarch64-sail`` route; without that key the RISC-V path below runs exactly as
before, so every existing RISC-V caller is untouched.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace
from .expr import evaluate
from .rv64 import MASK64, decode, instruction_stream, operands

NREG = 32


def _state(pc: int, regs: list[int], halted: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"pc": pc, "halted": halted}
    for r in range(1, NREG):
        s[f"x{r}"] = regs[r]
    return s


def _is_ecall(instr: int) -> bool:
    return (instr & 0x7F) == 0x73 and ((instr >> 12) & 0x7) == 0 and (instr >> 20) in (0, 1)


def _resolve(d, regs: list[int], addr: int) -> dict[str, int]:
    return {vn: (regs[v] if k == "reg" else v) & MASK64
            for vn, (k, v) in operands(d, addr).items()}


def _load(mem: dict[int, int], addr: int, n: int) -> int:
    return sum(mem.get((addr + i) & MASK64, 0) << (8 * i) for i in range(n))


def _store(mem: dict[int, int], addr: int, n: int, val: int) -> None:
    for i in range(n):
        mem[(addr + i) & MASK64] = (val >> (8 * i)) & 0xFF


def run(program: dict[str, Any], binding: dict[str, Any] | None = None,
        max_steps: int = 100_000, **_kw: Any) -> Trace:
    # Additive AArch64 arm (aarch64-sail): a Sail object tagged isa=aarch64 runs
    # the A64 executor; the RISC-V path is the untouched default (no isa key).
    if program.get("isa") == "aarch64":
        from .aarch64 import run_aarch64
        return run_aarch64(program, binding, max_steps=max_steps)
    words = program["words"]
    entry = program.get("entry", 0)
    regs = [0] * NREG
    init = (binding or {}).get("regs", program.get("init_regs", {}))
    for r, v in init.items():
        regs[int(r)] = int(v) & MASK64
    regs[0] = 0
    pc = (binding or {}).get("pc", entry)
    mem_src = (binding or {}).get("mem", program.get("mem", {}))
    mem = {int(k) & MASK64: int(v) & 0xFF for k, v in mem_src.items()}

    # PC-keyed fetch over the (addr, instr, length) stream, so compressed
    # (2-byte) and base (4-byte) instructions interleave at their true PCs.
    fetch = {addr: (instr, length) for addr, instr, length in
             instruction_stream({"words": words, "lengths": program.get("lengths"),
                                  "entry": entry})}

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if pc not in fetch:
            trace.append(_state(pc, regs, True))
            break
        instr, length = fetch[pc]
        steps += 1
        if _is_ecall(instr):
            trace.append(_state((pc + length) & MASK64, regs, True))
            break
        d = decode(instr)
        if d is None:
            raise Unsupported("sail", f"opcode=0x{instr & 0x7F:02x}")
        env = _resolve(d, regs, pc)

        if d.kind == "alu":
            if d.rd != 0:
                regs[d.rd] = evaluate(d.execute, env) & MASK64
            pc = (pc + length) & MASK64
        elif d.kind == "branch":
            pc = (pc + d.offset if evaluate(d.cond, env) else pc + length) & MASK64
        elif d.kind == "jal":
            if d.rd != 0:
                regs[d.rd] = (pc + length) & MASK64
            pc = (pc + d.offset) & MASK64
        elif d.kind == "jalr":
            link, tgt = (pc + length) & MASK64, evaluate(d.target, env) & MASK64
            if d.rd != 0:
                regs[d.rd] = link
            pc = tgt
        elif d.kind == "load":
            raw = _load(mem, evaluate(d.addr, env) & MASK64, d.nbytes)
            bits = d.nbytes * 8
            val = (raw - (1 << bits) if d.signed and raw >> (bits - 1) else raw) & MASK64
            if d.rd != 0:
                regs[d.rd] = val
            pc = (pc + length) & MASK64
        elif d.kind == "store":
            _store(mem, evaluate(d.addr, env) & MASK64, d.nbytes, regs[d.b_reg])
            pc = (pc + length) & MASK64
        else:  # fence
            pc = (pc + length) & MASK64
        regs[0] = 0
        trace.append(_state(pc, regs, False))
    return trace
