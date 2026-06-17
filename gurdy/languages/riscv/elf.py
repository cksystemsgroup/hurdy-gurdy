"""A minimal ELF64 loader for the RISC-V interpreter (languages/riscv brief:
"a program is an ELF image").

Parses a static little-endian RISC-V ELF64, copies its ``PT_LOAD`` segments
into a flat ``RiscvImage`` (BSS zero-filled implicitly by the sparse memory),
and takes the entry point from ``e_entry``. The executable (``PF_X``)
segments bound the code region, so running past the loaded code halts —
matching ``image_from_words``. This is the loader for ``-nostdlib`` /
freestanding binaries (e.g. ``riscv64-unknown-elf-gcc -march=rv64im``); dynamic
linking, relocations, and interpreters are out of scope and not consumed.
"""

from __future__ import annotations

import struct

from ...core.errors import Unsupported
from .interp import MASK64, RiscvImage

_PT_LOAD = 1
_PF_X = 0x1
_EM_RISCV = 243


def load_elf(data: bytes) -> RiscvImage:
    """Load a RISC-V ELF64 image into a ``RiscvImage`` (entry + flat memory)."""
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file (bad magic)")
    ei_class, ei_data = data[4], data[5]
    if ei_class != 2:
        raise Unsupported("riscv-elf", "ELFCLASS32 (only ELF64 is supported)")
    if ei_data != 1:
        raise Unsupported("riscv-elf", "big-endian ELF (only little-endian)")
    e_machine = struct.unpack_from("<H", data, 18)[0]
    if e_machine not in (0, _EM_RISCV):
        raise Unsupported("riscv-elf", f"e_machine={e_machine} (not RISC-V)")

    e_entry, e_phoff = struct.unpack_from("<QQ", data, 24)
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 54)
    if e_phoff == 0 or e_phnum == 0:
        raise Unsupported("riscv-elf", "no program headers (not an executable image)")

    mem: dict[int, int] = {}
    code_lo: int | None = None
    code_hi: int | None = None
    loaded_lo: int | None = None
    loaded_hi: int | None = None

    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_flags, p_offset, p_vaddr, _p_paddr, p_filesz, p_memsz, _p_align = \
            struct.unpack_from("<IIQQQQQQ", data, off)
        if p_type != _PT_LOAD:
            continue
        for k in range(p_filesz):
            mem[(p_vaddr + k) & MASK64] = data[p_offset + k]
        lo, hi = p_vaddr, p_vaddr + p_memsz  # p_memsz >= p_filesz: BSS is implicit 0
        loaded_lo = lo if loaded_lo is None else min(loaded_lo, lo)
        loaded_hi = hi if loaded_hi is None else max(loaded_hi, hi)
        if p_flags & _PF_X:
            code_lo = lo if code_lo is None else min(code_lo, lo)
            code_hi = hi if code_hi is None else max(code_hi, hi)

    if code_lo is None:                 # no PF_X segment: bound by everything loaded
        code_lo, code_hi = loaded_lo, loaded_hi
    if code_lo is None:
        raise Unsupported("riscv-elf", "no loadable segments")

    return RiscvImage(mem=mem, entry=e_entry, code_lo=code_lo, code_hi=code_hi)
