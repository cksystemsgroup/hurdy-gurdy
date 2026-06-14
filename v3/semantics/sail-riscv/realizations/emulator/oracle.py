"""The reference realization: the pinned Sail-RISCV executable model.

Uniform interface ``run(program, binding) -> projection`` over the Sail
emulator. This is the *reference* the gate trusts; it is exposed to builder
agents only through the gate's sandboxed oracle service (never directly, for
``differential_only`` pairs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gurdy.hops.base import NotYetImplemented


@dataclass
class Projection:
    """Observable state per step (the pinned pi for rv64)."""

    pc: int = 0
    regs: dict[int, int] = field(default_factory=dict)   # x1..x31
    halted: bool = False


def run(program: bytes, binding: dict, *, max_steps: int) -> list[Projection]:
    # TODO(machine-agent): invoke the pinned Sail emulator (riscv_sim) on
    # (program, binding), extract the per-step projection. Reference only.
    raise NotYetImplemented("sail-riscv emulator oracle [TODO]")
