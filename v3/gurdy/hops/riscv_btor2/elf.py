"""A minimal ELF64 little-endian loader — just enough to read an rv64 program's
loadable code and entry point. Independent of Sail / the machine model (the
pair is differential-only): this is the agent's own front end.
"""

from __future__ import annotations

from dataclasses import dataclass


def _u(b: bytes, off: int, n: int) -> int:
    return int.from_bytes(b[off:off + n], "little")


@dataclass
class Loaded:
    entry: int
    mem: dict[int, int]            # byte address -> byte value (loaded segments)

    def word(self, addr: int) -> int | None:
        """Little-endian 32-bit fetch; None if any byte is unmapped."""
        out = 0
        for i in range(4):
            b = self.mem.get(addr + i)
            if b is None:
                return None
            out |= b << (8 * i)
        return out


def load(data: bytes) -> Loaded:
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    if data[4] != 2 or data[5] != 1:
        raise ValueError("expected little-endian ELF64")
    entry = _u(data, 24, 8)
    e_phoff = _u(data, 32, 8)
    e_phentsize = _u(data, 54, 2)
    e_phnum = _u(data, 56, 2)
    mem: dict[int, int] = {}
    for i in range(e_phnum):
        ph = e_phoff + i * e_phentsize
        if _u(data, ph + 0, 4) != 1:          # PT_LOAD only
            continue
        p_offset = _u(data, ph + 8, 8)
        p_vaddr = _u(data, ph + 16, 8)
        p_filesz = _u(data, ph + 32, 8)
        for j in range(p_filesz):
            mem[p_vaddr + j] = data[p_offset + j]
    return Loaded(entry=entry, mem=mem)
