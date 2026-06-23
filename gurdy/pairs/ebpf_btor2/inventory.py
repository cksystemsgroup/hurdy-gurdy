"""The construct-coverage inventory for ebpf-btor2 (BENCHMARKS.md §2).

One minimal probe per in-scope eBPF construct (the spec-derived denominator
the agent does not choose): the ALU op space in both classes (ALU64 / ALU32)
and both operand sources (imm / reg), the byte-swap (``BPF_END``) forms
(``le``/``be``/``bswap`` at 16/32/64), the conditional jumps in both classes,
the unconditional / exit jumps, the load-store core, the legacy
``ABS``/``IND`` packet loads (``B``/``H``/``W``), and the ``CALL`` (helper-call)
instruction. ``coverage()`` measures how many translate without an
``Unsupported`` abort.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from ...languages.ebpf import asm
from ...languages.ebpf.interp import program_from_words
from .translate import translate


def _p(*words: int) -> dict:
    return {"prog": program_from_words([*words, asm.exit_()]), "init_regs": {}}


_ALU_OPS = {
    0x0: "ADD", 0x1: "SUB", 0x2: "MUL", 0x3: "DIV", 0x4: "OR", 0x5: "AND",
    0x6: "LSH", 0x7: "RSH", 0x9: "MOD", 0xA: "XOR", 0xB: "MOV", 0xC: "ARSH",
}
_JMP_OPS = {
    0x1: "JEQ", 0x2: "JGT", 0x3: "JGE", 0x4: "JSET", 0x5: "JNE",
    0x6: "JSGT", 0x7: "JSGE", 0xA: "JLT", 0xB: "JLE", 0xC: "JSLT", 0xD: "JSLE",
}

ALU_PROBES: dict[str, dict] = {}
for _op, _name in _ALU_OPS.items():
    ALU_PROBES[f"{_name}64_K"] = _p(asm.alu64_imm(_op, 1, 1))
    ALU_PROBES[f"{_name}64_X"] = _p(asm.alu64_reg(_op, 1, 2))
    ALU_PROBES[f"{_name}32_K"] = _p(asm.alu32_imm(_op, 1, 1))
    ALU_PROBES[f"{_name}32_X"] = _p(asm.alu32_reg(_op, 1, 2))
ALU_PROBES["NEG64"] = _p(asm.alu64_imm(0x8, 1, 0))
ALU_PROBES["NEG32"] = _p(asm.alu32_imm(0x8, 1, 0))

# byte-swap (BPF_END): le/be on ALU, unconditional bswap on ALU64, at 16/32/64.
END_PROBES: dict[str, dict] = {}
for _w in (16, 32, 64):
    END_PROBES[f"LE{_w}"] = _p(asm.end_le(1, _w))
    END_PROBES[f"BE{_w}"] = _p(asm.end_be(1, _w))
    END_PROBES[f"BSWAP{_w}"] = _p(asm.bswap(1, _w))

JMP_PROBES: dict[str, dict] = {}
for _op, _name in _JMP_OPS.items():
    JMP_PROBES[f"{_name}_K"] = _p(asm.jmp_imm(_op, 1, 1, 1))
    JMP_PROBES[f"{_name}_X"] = _p(asm.jmp_reg(_op, 1, 2, 1))
    JMP_PROBES[f"{_name}32_K"] = _p(asm.jmp32_imm(_op, 1, 1, 1))
    JMP_PROBES[f"{_name}32_X"] = _p(asm.jmp32_reg(_op, 1, 2, 1))
JMP_PROBES["JA"] = _p(asm.ja(1))
JMP_PROBES["EXIT"] = _p()

MEM_PROBES: dict[str, dict] = {
    "LDDW": _p(*asm.lddw(1, 0x1_0000_0001)),
    "LDXW": _p(asm.ldx(4, 1, 2, 0)), "LDXH": _p(asm.ldx(2, 1, 2, 0)),
    "LDXB": _p(asm.ldx(1, 1, 2, 0)), "LDXDW": _p(asm.ldx(8, 1, 2, 0)),
    "STXW": _p(asm.stx(4, 1, 2, 0)), "STXH": _p(asm.stx(2, 1, 2, 0)),
    "STXB": _p(asm.stx(1, 1, 2, 0)), "STXDW": _p(asm.stx(8, 1, 2, 0)),
    "STW": _p(asm.st(4, 1, 5, 0)), "STH": _p(asm.st(2, 1, 5, 0)),
    "STB": _p(asm.st(1, 1, 5, 0)), "STDW": _p(asm.st(8, 1, 5, 0)),
}

# legacy packet loads (LD class): ABS (offset = imm) and IND (offset = src+imm),
# big-endian read of B/H/W into r0.
PKT_PROBES: dict[str, dict] = {
    "LDABSW": _p(asm.ld_abs(4, 0)), "LDABSH": _p(asm.ld_abs(2, 0)),
    "LDABSB": _p(asm.ld_abs(1, 0)),
    "LDINDW": _p(asm.ld_ind(4, 2, 0)), "LDINDH": _p(asm.ld_ind(2, 2, 0)),
    "LDINDB": _p(asm.ld_ind(1, 2, 0)),
}

# CALL (helper call): modeled uniformly for every helper id (r0 + clobbered
# r1..r5 -> fresh inputs; r6..r10 preserved). Probe a known and an arbitrary id
# to assert no id is rejected (the model is helper-id-independent).
CALL_PROBES: dict[str, dict] = {
    "CALL_KNOWN": _p(asm.call(1)),         # a "known" helper id
    "CALL_OTHER": _p(asm.call(0xABCD)),    # an arbitrary id -> still covered
}

ALL_PROBES: dict[str, dict] = {
    **ALU_PROBES, **END_PROBES, **JMP_PROBES, **MEM_PROBES, **PKT_PROBES,
    **CALL_PROBES,
}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
