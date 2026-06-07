"""Source-level facts lifted from an ebpf-btor2 solver witness."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EbpfWitness:
    """Concrete eBPF facts recovered from a ``reachable`` solver verdict.

    ``initial_regs`` maps register index (r0–r9) to its concrete value at
    BMC cycle 0 — the inputs that drive the program to the bad state.
    ``halted_step`` is the cycle at which the ``halted`` state first
    becomes set (the BPF_EXIT_INSN), or ``None`` if it never does within
    the unrolled bound. ``reachable`` records whether the verdict carried
    a witness at all; for ``unreachable`` / ``unknown`` verdicts the
    witness is empty.
    """

    reachable: bool
    initial_regs: dict[int, int] = field(default_factory=dict)
    halted_step: int | None = None

    def to_jsonable(self) -> dict:
        return {
            "reachable": self.reachable,
            "initial_regs": {str(k): v for k, v in sorted(self.initial_regs.items())},
            "halted_step": self.halted_step,
        }


__all__ = ["EbpfWitness"]
