"""A minimal ELF64 loader for the RISC-V interpreter (languages/riscv brief:
"a program is an ELF image").

Parses a static little-endian RISC-V ELF64, copies its ``PT_LOAD`` segments
into a flat ``RiscvImage`` (BSS zero-filled implicitly by the sparse memory),
and takes the entry point from ``e_entry``.

The code region is bounded **symbol/section-aware**: when section headers are
present (the common, non-stripped case) the executable (``SHF_EXECINSTR``)
sections define ``[code_lo, code_hi)`` precisely — so the ELF header bytes that
a linker maps into the same executable *segment* are excluded, and an arbitrary
``riscv64-unknown-elf-gcc`` binary flows through the translator's whole-region
dispatch, not just the interpreter. The symbol table is exposed as
``image.symbols`` and an ``entry_symbol`` may override the entry point. A
stripped image (no section headers) falls back to the ``PF_X`` segment bounds.

This is the loader for ``-nostdlib`` / freestanding binaries; dynamic linking,
relocations, and interpreters are out of scope and not consumed.
"""

from __future__ import annotations

import struct

from ...core.errors import Unsupported
from .interp import MASK64, RiscvImage

_PT_LOAD = 1
_PF_X = 0x1
_EM_RISCV = 243
_SHF_EXECINSTR = 0x4
_SHT_PROGBITS = 1
_SHT_SYMTAB = 2


def _load_segments(data: bytes) -> tuple[dict[int, int], int | None, int | None,
                                         int | None, int | None]:
    """Copy PT_LOAD segments into a flat memory; return (mem, exec lo/hi from
    PF_X segments, loaded lo/hi over all segments)."""
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 54)
    if e_phoff == 0 or e_phnum == 0:
        raise Unsupported("riscv-elf", "no program headers (not an executable image)")

    mem: dict[int, int] = {}
    seg_lo = seg_hi = all_lo = all_hi = None
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_flags, p_offset, p_vaddr, _pa, p_filesz, p_memsz, _al = \
            struct.unpack_from("<IIQQQQQQ", data, off)
        if p_type != _PT_LOAD:
            continue
        for k in range(p_filesz):
            mem[(p_vaddr + k) & MASK64] = data[p_offset + k]
        lo, hi = p_vaddr, p_vaddr + p_memsz   # p_memsz >= p_filesz: BSS implicit 0
        all_lo = lo if all_lo is None else min(all_lo, lo)
        all_hi = hi if all_hi is None else max(all_hi, hi)
        if p_flags & _PF_X:
            seg_lo = lo if seg_lo is None else min(seg_lo, lo)
            seg_hi = hi if seg_hi is None else max(seg_hi, hi)
    return mem, seg_lo, seg_hi, all_lo, all_hi


def _read_sections(data: bytes) -> tuple[int | None, int | None, dict[str, int]]:
    """From the section headers, return (code_lo, code_hi) spanning executable
    PROGBITS sections and the symbol-name -> address map. Returns (None, None,
    {}) for a stripped image."""
    e_shoff = struct.unpack_from("<Q", data, 40)[0]
    e_shentsize, e_shnum = struct.unpack_from("<HH", data, 58)
    if e_shoff == 0 or e_shnum == 0:
        return None, None, {}

    secs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, _info, _al, sh_entsize = \
            struct.unpack_from("<IIQQQQIIQQ", data, off)
        secs.append((sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_entsize))

    code_lo = code_hi = None
    for sh_type, sh_flags, sh_addr, _o, sh_size, _l, _e in secs:
        if sh_type == _SHT_PROGBITS and (sh_flags & _SHF_EXECINSTR) and sh_addr:
            code_lo = sh_addr if code_lo is None else min(code_lo, sh_addr)
            code_hi = sh_addr + sh_size if code_hi is None else max(code_hi, sh_addr + sh_size)

    symbols: dict[str, int] = {}
    for sh_type, _f, _a, sh_offset, sh_size, sh_link, sh_entsize in secs:
        if sh_type != _SHT_SYMTAB or sh_entsize == 0 or sh_link >= len(secs):
            continue
        str_off = secs[sh_link][3]
        for s in range(sh_offset, sh_offset + sh_size, sh_entsize):
            st_name, _info, _other, _shndx, st_value, _size = struct.unpack_from("<IBBHQQ", data, s)
            if st_name == 0:
                continue
            end = data.index(b"\x00", str_off + st_name)
            name = data[str_off + st_name:end].decode("latin-1")
            if name:
                symbols[name] = st_value
    return code_lo, code_hi, symbols


def load_elf(data: bytes, entry_symbol: str | None = None) -> RiscvImage:
    """Load a RISC-V ELF64 image. If ``entry_symbol`` is given, start there
    instead of ``e_entry`` (symbol-aware entry)."""
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file (bad magic)")
    if data[4] != 2:
        raise Unsupported("riscv-elf", "ELFCLASS32 (only ELF64 is supported)")
    if data[5] != 1:
        raise Unsupported("riscv-elf", "big-endian ELF (only little-endian)")
    e_machine = struct.unpack_from("<H", data, 18)[0]
    if e_machine not in (0, _EM_RISCV):
        raise Unsupported("riscv-elf", f"e_machine={e_machine} (not RISC-V)")

    e_entry = struct.unpack_from("<Q", data, 24)[0]
    mem, seg_lo, seg_hi, all_lo, all_hi = _load_segments(data)
    sec_lo, sec_hi, symbols = _read_sections(data)

    # Prefer precise executable-section bounds; fall back to the PF_X segment,
    # then to everything loaded.
    code_lo = sec_lo if sec_lo is not None else (seg_lo if seg_lo is not None else all_lo)
    code_hi = sec_hi if sec_hi is not None else (seg_hi if seg_hi is not None else all_hi)
    if code_lo is None:
        raise Unsupported("riscv-elf", "no loadable code")

    entry = e_entry
    if entry_symbol is not None:
        if entry_symbol not in symbols:
            raise ValueError(f"entry symbol not found: {entry_symbol!r}")
        entry = symbols[entry_symbol]

    return RiscvImage(mem=mem, entry=entry, code_lo=code_lo, code_hi=code_hi, symbols=symbols)
