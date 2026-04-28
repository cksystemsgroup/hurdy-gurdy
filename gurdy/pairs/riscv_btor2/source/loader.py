"""SourceLoader implementation for the riscv-btor2 pair."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gurdy.pairs.riscv_btor2.source.dwarf import DWARFLineTable, from_elf
from gurdy.pairs.riscv_btor2.source.elf import EM_RISCV, RISCVBinary


@dataclass
class RISCVSource:
    """The pair's Source type — what the translator consumes.

    Wraps a ``RISCVBinary`` and a ``DWARFLineTable`` (which may be
    empty when no debug info is available).
    """

    binary: RISCVBinary
    line_table: DWARFLineTable

    @property
    def is_riscv(self) -> bool:
        return self.binary.is_riscv

    def function(self, name: str):
        return self.binary.function(name)

    def functions(self):
        return self.binary.functions()


def load_riscv_binary(payload: bytes | str | Path | None) -> RISCVSource:
    """Implements ``SourceLoader``."""

    if payload is None:
        raise ValueError("riscv-btor2 loader: payload is required")
    if isinstance(payload, (str, Path)):
        path = Path(payload)
        binary = RISCVBinary.from_path(path)
        sidecar = path.with_suffix(path.suffix + ".dwarfmap.json")
        line_table = from_elf(binary.elf, sidecar)
    elif isinstance(payload, (bytes, bytearray)):
        binary = RISCVBinary.from_bytes(bytes(payload))
        line_table = from_elf(binary.elf, None)
    else:
        raise ValueError(
            f"riscv-btor2 loader: unsupported payload type {type(payload)!r}"
        )

    if not binary.is_riscv:
        raise ValueError(
            f"riscv-btor2 loader: e_machine={binary.machine} is not "
            f"EM_RISCV ({EM_RISCV})"
        )

    return RISCVSource(binary=binary, line_table=line_table)


__all__ = ["RISCVSource", "load_riscv_binary"]
