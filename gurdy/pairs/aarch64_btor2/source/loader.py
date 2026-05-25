"""SourceLoader implementation for the aarch64-btor2 pair.

Adapted from gurdy/pairs/riscv_btor2/source/loader.py (v2-bootstrap).
DWARF line-table support deferred to P3+.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gurdy.pairs.aarch64_btor2.source.elf import AArch64Binary, EM_AARCH64, FunctionRange


@dataclass
class AArch64Source:
    """The pair's Source type — what the translator consumes."""

    binary: AArch64Binary

    @property
    def is_aarch64(self) -> bool:
        return self.binary.is_aarch64

    def function(self, name: str) -> FunctionRange | None:
        return self.binary.function(name)

    def functions(self) -> list[FunctionRange]:
        return self.binary.functions()


def load_aarch64_binary(payload: bytes | str | Path | None) -> AArch64Source:
    """Implements ``SourceLoader``."""
    if payload is None:
        raise ValueError("aarch64-btor2 loader: payload is required")
    if isinstance(payload, (str, Path)):
        binary = AArch64Binary.from_path(payload)
    elif isinstance(payload, (bytes, bytearray)):
        binary = AArch64Binary.from_bytes(bytes(payload))
    else:
        raise ValueError(
            f"aarch64-btor2 loader: unsupported payload type {type(payload)!r}"
        )
    if not binary.is_aarch64:
        raise ValueError(
            f"aarch64-btor2 loader: e_machine={binary.machine} is not "
            f"EM_AARCH64 ({EM_AARCH64})"
        )
    return AArch64Source(binary=binary)


__all__ = ["AArch64Source", "load_aarch64_binary"]
