"""Emit ``<elf>.dwarfmap.json`` from a built source.elf.

The pair's ELF loader (``gurdy/pairs/riscv_btor2/source/dwarf.py``)
prefers a sidecar JSON over decoding ``.debug_line`` directly. We
generate that sidecar here by running ``riscv64-unknown-elf-objdump
--dwarf=decodedline`` and reshaping its output.

The lifter then populates ``LiftedStep.file`` and ``LiftedStep.line``
for every traced PC, instead of leaving them ``None``.

Usage (driven from corpus/Makefile):
    python _emit_dwarfmap.py <task_dir>/source.elf
writes to <task_dir>/source.elf.dwarfmap.json.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


# objdump --dwarf=decodedline lines look like:
#   source.S                                   6             0x10002       1       x
# Columns are whitespace-separated; the address is the third token from
# the right when a "View" or "Stmt" column is present, but the column
# count is variable. Match the address as the first 0x... after a line
# number.
_LINE_RE = re.compile(
    r"^(?P<file>\S+)\s+(?P<line>\d+|-)\s+(?P<addr>0x[0-9a-fA-F]+)"
)


def parse_decodedline(text: str) -> tuple[list[dict], int | None]:
    entries: list[dict] = []
    end_pc: int | None = None
    in_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Contents of the .debug_line"):
            in_table = True
            continue
        if not in_table or not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        addr = int(m["addr"], 16)
        if m["line"] == "-":
            # Sentinel "end of program at this address" row.
            if end_pc is None or addr > end_pc:
                end_pc = addr
            continue
        entries.append({"pc": hex(addr), "file": m["file"], "line": int(m["line"])})
    return entries, end_pc


def emit(elf_path: Path, objdump: str = "riscv64-unknown-elf-objdump") -> dict:
    out = subprocess.check_output(
        [objdump, "--dwarf=decodedline", str(elf_path)],
        stderr=subprocess.STDOUT,
    ).decode()
    entries, end_pc = parse_decodedline(out)
    payload: dict = {"entries": entries}
    if end_pc is not None:
        payload["end_pc"] = hex(end_pc)
    return payload


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <source.elf>", file=sys.stderr)
        return 2
    elf = Path(argv[1])
    out = elf.with_suffix(elf.suffix + ".dwarfmap.json")
    out.write_text(json.dumps(emit(elf), indent=2) + "\n")
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
