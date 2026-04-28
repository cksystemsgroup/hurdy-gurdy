"""Minimal ELF parser for RV64 binaries.

We avoid third-party dependencies (e.g. pyelftools) by reading the
fixed-layout fields directly. The supported subset is what the
``riscv-btor2`` pair actually needs:

- ELF64 little-endian, e_machine == EM_RISCV (243).
- PT_LOAD segments to materialize instruction bytes.
- Symbol table (``.symtab`` / ``.dynsym``) for function symbol lookup.
- Section table to map section name to offset/size.

Anything fancier (relocations, GOT/PLT, dynamic linking) is irrelevant
for verification of statically-loaded ELFs and out of scope.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# Constants
ELFCLASS64 = 2
ELFDATA2LSB = 1
EM_RISCV = 243
PT_LOAD = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_DYNSYM = 11
STT_FUNC = 2
STB_LOCAL = 0
STB_GLOBAL = 1
STB_WEAK = 2


class ELFParseError(ValueError):
    pass


@dataclass(frozen=True)
class ELFHeader:
    elf_class: int
    data: int
    machine: int
    entry: int
    phoff: int
    shoff: int
    phentsize: int
    phnum: int
    shentsize: int
    shnum: int
    shstrndx: int


@dataclass(frozen=True)
class ProgramHeader:
    type: int
    flags: int
    offset: int
    vaddr: int
    paddr: int
    filesz: int
    memsz: int
    align: int


@dataclass(frozen=True)
class SectionHeader:
    name_offset: int
    type: int
    flags: int
    addr: int
    offset: int
    size: int
    link: int
    info: int
    addralign: int
    entsize: int
    name: str = ""


@dataclass(frozen=True)
class Symbol:
    name: str
    addr: int
    size: int
    type: int
    bind: int
    section_index: int


@dataclass(frozen=True)
class LoadSegment:
    vaddr: int
    bytes_: bytes
    flags: int

    def end(self) -> int:
        return self.vaddr + len(self.bytes_)


@dataclass(frozen=True)
class FunctionRange:
    name: str
    start: int
    end: int  # exclusive

    def contains(self, pc: int) -> bool:
        return self.start <= pc < self.end


@dataclass
class ELF:
    header: ELFHeader
    program_headers: list[ProgramHeader]
    sections: list[SectionHeader]
    symbols: list[Symbol]
    raw: bytes
    section_data: dict[str, bytes] = field(default_factory=dict)

    # ---- public surface ----

    def load_segments(self) -> list[LoadSegment]:
        out: list[LoadSegment] = []
        for ph in self.program_headers:
            if ph.type != PT_LOAD:
                continue
            data = self.raw[ph.offset : ph.offset + ph.filesz]
            # Pad with zeros up to memsz, mirroring loader behaviour.
            if ph.memsz > ph.filesz:
                data = data + b"\x00" * (ph.memsz - ph.filesz)
            out.append(LoadSegment(vaddr=ph.vaddr, bytes_=data, flags=ph.flags))
        return out

    def loadable_byte_map(self) -> dict[int, int]:
        """Return ``{addr: byte}`` for every byte covered by PT_LOAD."""
        m: dict[int, int] = {}
        for seg in self.load_segments():
            for i, b in enumerate(seg.bytes_):
                m[seg.vaddr + i] = b
        return m

    def functions(self) -> list[FunctionRange]:
        out: list[FunctionRange] = []
        for s in self.symbols:
            if s.type != STT_FUNC:
                continue
            if s.size <= 0:
                continue
            out.append(FunctionRange(name=s.name, start=s.addr, end=s.addr + s.size))
        out.sort(key=lambda f: f.start)
        return out

    def function_by_name(self, name: str) -> FunctionRange | None:
        for f in self.functions():
            if f.name == name:
                return f
        return None

    def function_at(self, pc: int) -> FunctionRange | None:
        for f in self.functions():
            if f.contains(pc):
                return f
        return None

    def read_bytes(self, addr: int, length: int) -> bytes:
        m = self.loadable_byte_map()
        out = bytearray(length)
        for i in range(length):
            b = m.get(addr + i)
            if b is None:
                return bytes(out[:i])
            out[i] = b
        return bytes(out)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


_EHDR64 = struct.Struct("<16sHHIQQQIHHHHHH")
# e_ident[16], e_type, e_machine, e_version, e_entry, e_phoff, e_shoff,
# e_flags, e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx
_PHDR64 = struct.Struct("<IIQQQQQQ")
# p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align
_SHDR64 = struct.Struct("<IIQQQQIIQQ")
# sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size,
# sh_link, sh_info, sh_addralign, sh_entsize
_SYM64 = struct.Struct("<IBBHQQ")
# st_name, st_info, st_other, st_shndx, st_value, st_size


def _read_cstr(buf: bytes, offset: int) -> str:
    end = buf.find(b"\x00", offset)
    if end == -1:
        end = len(buf)
    return buf[offset:end].decode("utf-8", "replace")


def parse_elf(data: bytes) -> ELF:
    if len(data) < 0x40 or data[:4] != b"\x7fELF":
        raise ELFParseError("not an ELF file (missing magic)")
    if data[4] != ELFCLASS64:
        raise ELFParseError(f"not ELF64 (e_ident[EI_CLASS]={data[4]})")
    if data[5] != ELFDATA2LSB:
        raise ELFParseError("not little-endian ELF")

    e_ident, e_type, e_machine, _e_version, e_entry, e_phoff, e_shoff, \
        _e_flags, _ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, \
        e_shstrndx = _EHDR64.unpack_from(data, 0)
    header = ELFHeader(
        elf_class=ELFCLASS64,
        data=ELFDATA2LSB,
        machine=e_machine,
        entry=e_entry,
        phoff=e_phoff,
        shoff=e_shoff,
        phentsize=e_phentsize,
        phnum=e_phnum,
        shentsize=e_shentsize,
        shnum=e_shnum,
        shstrndx=e_shstrndx,
    )

    # Program headers
    program_headers: list[ProgramHeader] = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = (
            _PHDR64.unpack_from(data, off)
        )
        program_headers.append(
            ProgramHeader(
                type=p_type,
                flags=p_flags,
                offset=p_offset,
                vaddr=p_vaddr,
                paddr=p_paddr,
                filesz=p_filesz,
                memsz=p_memsz,
                align=p_align,
            )
        )

    # Section headers (without names yet)
    raw_sections: list[SectionHeader] = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_info, sh_addralign, sh_entsize = (
            _SHDR64.unpack_from(data, off)
        )
        raw_sections.append(
            SectionHeader(
                name_offset=sh_name,
                type=sh_type,
                flags=sh_flags,
                addr=sh_addr,
                offset=sh_offset,
                size=sh_size,
                link=sh_link,
                info=sh_info,
                addralign=sh_addralign,
                entsize=sh_entsize,
            )
        )

    # Resolve section names
    sections: list[SectionHeader] = []
    if e_shstrndx and e_shstrndx < len(raw_sections):
        shstrtab = raw_sections[e_shstrndx]
        strtab_bytes = data[shstrtab.offset : shstrtab.offset + shstrtab.size]
        for s in raw_sections:
            sections.append(
                SectionHeader(
                    name_offset=s.name_offset,
                    type=s.type,
                    flags=s.flags,
                    addr=s.addr,
                    offset=s.offset,
                    size=s.size,
                    link=s.link,
                    info=s.info,
                    addralign=s.addralign,
                    entsize=s.entsize,
                    name=_read_cstr(strtab_bytes, s.name_offset),
                )
            )
    else:
        sections = raw_sections

    # Section data dictionary by name
    section_data: dict[str, bytes] = {}
    for s in sections:
        if s.size > 0:
            section_data[s.name] = data[s.offset : s.offset + s.size]

    # Symbol table
    symbols: list[Symbol] = []
    for s in sections:
        if s.type not in (SHT_SYMTAB, SHT_DYNSYM):
            continue
        if s.link >= len(sections):
            continue
        strtab_section = sections[s.link]
        strtab = data[strtab_section.offset : strtab_section.offset + strtab_section.size]
        body = data[s.offset : s.offset + s.size]
        n = s.size // _SYM64.size if _SYM64.size else 0
        for i in range(n):
            st_name, st_info, _st_other, st_shndx, st_value, st_size = (
                _SYM64.unpack_from(body, i * _SYM64.size)
            )
            sym_type = st_info & 0xF
            sym_bind = st_info >> 4
            symbols.append(
                Symbol(
                    name=_read_cstr(strtab, st_name),
                    addr=st_value,
                    size=st_size,
                    type=sym_type,
                    bind=sym_bind,
                    section_index=st_shndx,
                )
            )

    return ELF(
        header=header,
        program_headers=program_headers,
        sections=sections,
        symbols=symbols,
        raw=data,
        section_data=section_data,
    )


# ---------------------------------------------------------------------------
# Public RISCVBinary wrapper
# ---------------------------------------------------------------------------


@dataclass
class RISCVBinary:
    path: Path
    elf: ELF

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | str | None = None) -> "RISCVBinary":
        return cls(path=Path(path) if path else Path("<bytes>"), elf=parse_elf(data))

    @classmethod
    def from_path(cls, path: Path | str) -> "RISCVBinary":
        p = Path(path)
        return cls(path=p, elf=parse_elf(p.read_bytes()))

    @property
    def machine(self) -> int:
        return self.elf.header.machine

    @property
    def entry(self) -> int:
        return self.elf.header.entry

    @property
    def is_riscv(self) -> bool:
        return self.machine == EM_RISCV

    def functions(self) -> list[FunctionRange]:
        return self.elf.functions()

    def function(self, name: str) -> FunctionRange | None:
        return self.elf.function_by_name(name)

    def read_bytes(self, addr: int, length: int) -> bytes:
        return self.elf.read_bytes(addr, length)

    def loadable_byte_map(self) -> dict[int, int]:
        return self.elf.loadable_byte_map()

    def instruction_words(self, fn: FunctionRange) -> Iterator[tuple[int, int, int]]:
        """Yield (pc, raw_word, length) over a function.

        ``length`` is 2 for an RVC-shaped instruction (low two bits != 11),
        4 for a standard instruction. Variable-length scanning for
        instructions wider than 32 bits is left to the decoder.
        """
        m = self.loadable_byte_map()
        pc = fn.start
        while pc < fn.end:
            b0 = m.get(pc)
            b1 = m.get(pc + 1)
            if b0 is None or b1 is None:
                break
            half = b0 | (b1 << 8)
            if (half & 0x3) != 0x3:
                yield pc, half, 2
                pc += 2
                continue
            b2 = m.get(pc + 2, 0)
            b3 = m.get(pc + 3, 0)
            full = half | (b2 << 16) | (b3 << 24)
            yield pc, full, 4
            pc += 4


__all__ = [
    "EM_RISCV",
    "ELF",
    "ELFHeader",
    "ELFParseError",
    "FunctionRange",
    "LoadSegment",
    "ProgramHeader",
    "RISCVBinary",
    "SectionHeader",
    "Symbol",
    "parse_elf",
]
