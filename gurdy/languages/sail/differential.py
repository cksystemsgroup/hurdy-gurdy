"""Wire the Sail interpreter to the gold oracle ``sail_riscv_sim``.

The Sail-derived semantics (``rv64.EXEC`` etc.) are *meant* to mirror the
official Sail RISC-V model; this closes that loop by letting the shared
differential harness validate the Sail interpreter against the real
``sail_riscv_sim`` emulator on the same ELF — the same oracle the hand-written
RISC-V interpreter is checked against (DOCKER.md). It is the subject side of
``riscv.differential.differential(..., subject=sail_subject)``.

``sail_subject`` loads a RISC-V ELF, projects it into a Sail program (the
decoded instruction stream + data memory the Sail machine consumes), runs the
Sail interpreter, and returns the executed-instruction stream. Pure; the
emulator side is gated on the pinned binary being present.
"""

from __future__ import annotations

from ...core.types import Trace
from ..riscv.differential import executed_stream
from ..riscv.elf import load_elf
from .interp import run as sail_run


def sail_program_from_elf(elf_bytes: bytes) -> tuple[dict, int]:
    """Project a RISC-V ELF into a Sail program ``({words, entry, mem}, entry)``."""
    image = load_elf(elf_bytes)
    lo = image.code_lo
    hi = image.code_hi if image.code_hi is not None else lo
    words = [image.load(addr, 4) for addr in range(lo, hi, 4)]
    prog = {"words": words, "entry": image.entry, "init_regs": {}, "mem": dict(image.mem)}
    return prog, image.entry


def sail_subject(elf_bytes: bytes, max_steps: int = 100_000) -> Trace:
    """Run the Sail interpreter on a RISC-V ELF; return the executed stream."""
    prog, entry = sail_program_from_elf(elf_bytes)
    return executed_stream(sail_run(prog, max_steps=max_steps), entry)
