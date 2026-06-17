"""The shared Sail (RISC-V model) interpreter — an *independent* RISC-V
executor that runs each instruction by concretely evaluating its Sail-derived
``Expr`` trees (``rv64``), rather than the hand-written Python ops of
``languages/riscv/interp.py``. That independence is what makes the
Sail-mediated route a real cross-check of the direct one.

A "Sail program" is ``{"words":[...], "entry":int, "init_regs":{i:v},
"property":{...}}``. Scope is the ALU + control-flow slice (``rv64.decode``)
plus ECALL/EBREAK (halt); loads/stores and other opcodes hard-abort. Behavior
is the same ``{"pc","x1".."x31","halted"}`` trace shape as the RISC-V
interpreter, so the commuting-square oracle compares them directly.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace
from .expr import evaluate
from .rv64 import MASK64, decode, operands

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


def run(program: dict[str, Any], binding: dict[str, Any] | None = None,
        max_steps: int = 100_000, **_kw: Any) -> Trace:
    words = program["words"]
    entry = program.get("entry", 0)
    regs = [0] * NREG
    init = (binding or {}).get("regs", program.get("init_regs", {}))
    for r, v in init.items():
        regs[int(r)] = int(v) & MASK64
    regs[0] = 0
    pc = (binding or {}).get("pc", entry)

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        idx = (pc - entry) // 4
        if not (0 <= idx < len(words)) or (pc - entry) % 4:
            trace.append(_state(pc, regs, True))
            break
        instr = words[idx]
        steps += 1
        if _is_ecall(instr):
            trace.append(_state((pc + 4) & MASK64, regs, True))
            break
        d = decode(instr)
        if d is None:
            raise Unsupported("sail", f"opcode=0x{instr & 0x7F:02x}")
        env = _resolve(d, regs, pc)

        if d.kind == "alu":
            if d.rd != 0:
                regs[d.rd] = evaluate(d.execute, env) & MASK64
            pc = (pc + 4) & MASK64
        elif d.kind == "branch":
            pc = (pc + d.offset if evaluate(d.cond, env) else pc + 4) & MASK64
        elif d.kind == "jal":
            if d.rd != 0:
                regs[d.rd] = (pc + 4) & MASK64
            pc = (pc + d.offset) & MASK64
        elif d.kind == "jalr":
            link, tgt = (pc + 4) & MASK64, evaluate(d.target, env) & MASK64
            if d.rd != 0:
                regs[d.rd] = link
            pc = tgt
        else:  # fence
            pc = (pc + 4) & MASK64
        regs[0] = 0
        trace.append(_state(pc, regs, False))
    return trace
