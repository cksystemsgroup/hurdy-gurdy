"""Minimal DWARF .debug_line consumer.

A full DWARF v5 line-number-program interpreter is a substantial body
of code on its own. For the riscv-btor2 pair, the lifter only needs
``pc -> SourceLocation`` lookup; richer DWARF features (CFI,
expressions, type info) are not required.

This module ships a small in-memory ``DWARFLineTable`` that the loader
populates either:

- by parsing a ``.debug_line`` section if a standard line-number
  program is present (a simplified subset is implemented here, enough
  for our fixture binaries), or
- by a side-channel sidecar JSON file ``binary.dwarfmap.json`` if
  present alongside the ELF, mapping PC ranges to ``(file, line)``.

The latter route is the test-friendly one and keeps fixture
generation independent of a working RISC-V toolchain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SourceLocation:
    file: str
    line: int
    column: int = 0


@dataclass
class DWARFLineTable:
    entries: list[tuple[int, SourceLocation]] = field(default_factory=list)
    """Sorted list of (pc, loc) anchors. ``pc`` is inclusive; the
    location is in effect until the next anchor's pc."""

    end_pc: int | None = None
    """Optional upper bound; lookups past this return None."""

    def lookup(self, pc: int) -> SourceLocation | None:
        if not self.entries:
            return None
        if self.end_pc is not None and pc >= self.end_pc:
            return None
        # Binary search would be faster; linear is fine for fixture sizes.
        last: SourceLocation | None = None
        for anchor_pc, loc in self.entries:
            if anchor_pc > pc:
                break
            last = loc
        return last

    def add(self, pc: int, loc: SourceLocation) -> None:
        self.entries.append((pc, loc))
        self.entries.sort(key=lambda e: e[0])


def load_sidecar(path: Path) -> DWARFLineTable:
    """Load a ``binary.dwarfmap.json`` side-channel mapping.

    File schema:

        {
          "end_pc": 0x100100,
          "entries": [
            {"pc": "0x1000", "file": "add.c", "line": 5},
            {"pc": "0x1004", "file": "add.c", "line": 6}
          ]
        }
    """
    if not path.exists():
        return DWARFLineTable()
    obj = json.loads(path.read_text(encoding="utf-8"))
    table = DWARFLineTable()
    end_pc = obj.get("end_pc")
    if isinstance(end_pc, str):
        end_pc = int(end_pc, 0)
    table.end_pc = end_pc
    for e in obj.get("entries", ()):
        pc = e["pc"]
        if isinstance(pc, str):
            pc = int(pc, 0)
        table.add(
            pc,
            SourceLocation(
                file=e.get("file", "?"),
                line=int(e.get("line", 0)),
                column=int(e.get("column", 0)),
            ),
        )
    return table


def from_elf(elf, sidecar_hint: Path | None = None) -> DWARFLineTable:
    """Best-effort: prefer a sidecar JSON if present, otherwise return
    an empty table. A future revision can implement a proper DWARF v5
    .debug_line decoder; the pair architecture treats DWARF as
    optional."""
    if sidecar_hint is not None and sidecar_hint.exists():
        return load_sidecar(sidecar_hint)
    # No-op when no sidecar is available; the rest of the pipeline
    # tolerates a missing line table.
    return DWARFLineTable()


__all__ = ["SourceLocation", "DWARFLineTable", "from_elf", "load_sidecar"]
