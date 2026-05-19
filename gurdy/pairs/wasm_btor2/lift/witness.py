"""WasmWitness: source-level counterexample extracted from a solver witness."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WasmWitness:
    """Concrete parameter assignments and trap location from a reachable verdict.

    ``params`` maps param index k → unsigned i32 value (range 0..2^32-1).
    ``trap_step`` is the first BMC cycle at which the trap flag fires;
    ``None`` when the trap node was not visible in the witness.
    ``n_params`` records how many parameters were detected from the
    BTOR2 symbol table.
    """

    params: dict[int, int] = field(default_factory=dict)
    trap_step: int | None = None
    n_params: int = 0

    def as_signed(self, k: int) -> int:
        """Return params[k] interpreted as a signed 32-bit integer."""
        v = self.params.get(k, 0) & 0xFFFFFFFF
        return v if v < (1 << 31) else v - (1 << 32)


__all__ = ["WasmWitness"]
