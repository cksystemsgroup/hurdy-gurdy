"""Target-to-source interpreter ``L`` for c-riscv: carry a RISC-V behavior
back toward the C source.

Without debug-line info (kept off for reproducible bytes), the carry-back is
function-level: ``c_function_at`` maps a RISC-V pc to the enclosing C function
via the ELF symbol table, so a witness found on the lowered program is legible
("reached in ``f``"). ``lift`` re-projects the RISC-V trace into the pair's
observable shape.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        rec: dict[str, Any] = {"pc": row.get("pc"), "halted": bool(row.get("halted", 0))}
        for i in range(1, 32):
            rec[f"x{i}"] = row.get(f"x{i}")
        out.append(rec)
    return out


def c_function_at(image, pc: int) -> str | None:
    """The C function enclosing ``pc`` (nearest preceding code symbol)."""
    best_name, best_addr = None, -1
    for name, addr in image.symbols.items():
        if name.startswith("$"):
            continue   # ELF mapping symbols ($x...), not functions
        if image.code_lo <= addr <= pc and addr > best_addr:
            best_name, best_addr = name, addr
    return best_name
