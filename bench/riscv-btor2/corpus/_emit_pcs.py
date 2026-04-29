"""Emit `pcs.json` next to a task's `source.elf`.

Reads the ELF via the riscv-btor2 pair's own loader (no extra deps),
walks every analyzed function, and writes a JSON file that task
authors look up to find the PCs they want — eliminates the
hand-counting / RVC footgun that hit the seed tasks.

Output schema (stable; consumers may rely on it):

    {
      "entry": <int>,
      "symbols": { "<name>": { "start": <int>, "end": <int> } },
      "instructions": [
        { "pc": <int>, "size": <2|4>, "word": "0x..." }
      ],
      "ebreaks": [ <int>, ... ],     # PCs of every EBREAK / c.ebreak
      "ecalls":  [ <int>, ... ]      # PCs of every ECALL
    }

Usage (driven from corpus/Makefile):
    python _emit_pcs.py <task_dir>/source.elf
writes to <task_dir>/pcs.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from gurdy.pairs.riscv_btor2.source.elf import RISCVBinary


# RISC-V opcodes we identify as exit instructions. Both 32-bit and the
# RVC compressed equivalents.
EBREAK_32 = 0x00100073
ECALL_32 = 0x00000073
RVC_EBREAK = 0x9002  # c.ebreak


def emit_pcs(elf_path: Path) -> dict:
    binary = RISCVBinary.from_path(elf_path)

    symbols: dict[str, dict[str, int]] = {}
    instructions: list[dict] = []
    ebreaks: list[int] = []
    ecalls: list[int] = []

    for fn in binary.functions():
        symbols[fn.name] = {"start": fn.start, "end": fn.end}
        for pc, word, length in binary.instruction_words(fn):
            instructions.append(
                {"pc": pc, "size": length, "word": f"0x{word:0{length * 2}x}"}
            )
            if length == 4 and word == EBREAK_32:
                ebreaks.append(pc)
            elif length == 4 and word == ECALL_32:
                ecalls.append(pc)
            elif length == 2 and (word & 0xFFFF) == RVC_EBREAK:
                ebreaks.append(pc)

    return {
        "entry": binary.entry,
        "symbols": symbols,
        "instructions": instructions,
        "ebreaks": ebreaks,
        "ecalls": ecalls,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <source.elf>", file=sys.stderr)
        return 2
    elf = Path(argv[1])
    out = elf.with_name("pcs.json")
    out.write_text(json.dumps(emit_pcs(elf), indent=2) + "\n")
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
