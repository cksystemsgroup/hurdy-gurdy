"""Invariant lift: parse a Spacer SMT-LIB invariant and label its variables.

Adapted from gurdy/pairs/riscv_btor2/lift/invariant.py (v2-bootstrap).
AArch64 differences: ABI register names and extra sp/nzcv tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping


_REG_TOKEN = re.compile(r"\breg_x(\d{1,2})\b")
_PC_TOKEN = re.compile(r"\bpc\b")
_MEM_TOKEN = re.compile(r"\bmem\b")
_SP_TOKEN = re.compile(r"\bsp\b")
_NZCV_TOKEN = re.compile(r"\bnzcv\b")


# AArch64 procedure call standard (AAPCS64) register aliases.
_ABI = {
    0: "x0 (arg/result 1)", 1: "x1 (arg/result 2)", 2: "x2 (arg/result 3)",
    3: "x3 (arg/result 4)", 4: "x4 (arg/result 5)", 5: "x5 (arg/result 6)",
    6: "x6 (arg/result 7)", 7: "x7 (arg/result 8)",
    8: "x8 (indirect result / IP0 scratch)", 9: "x9 (caller-saved)",
    10: "x10 (caller-saved)", 11: "x11 (caller-saved)", 12: "x12 (caller-saved)",
    13: "x13 (caller-saved)", 14: "x14 (caller-saved)", 15: "x15 (caller-saved)",
    16: "x16 (IP0, intra-procedure scratch)", 17: "x17 (IP1, intra-procedure scratch)",
    18: "x18 (platform register)", 19: "x19 (callee-saved)",
    20: "x20 (callee-saved)", 21: "x21 (callee-saved)", 22: "x22 (callee-saved)",
    23: "x23 (callee-saved)", 24: "x24 (callee-saved)", 25: "x25 (callee-saved)",
    26: "x26 (callee-saved)", 27: "x27 (callee-saved)", 28: "x28 (callee-saved)",
    29: "x29 (fp, frame pointer)", 30: "x30 (lr, link register)",
}


@dataclass
class LiftedInvariant:
    raw: str
    glossary: Mapping[str, str] = field(default_factory=dict)


def lift_invariant(raw: str) -> LiftedInvariant:
    glossary: dict[str, str] = {}
    for m in _REG_TOKEN.finditer(raw):
        n = int(m.group(1))
        if 0 <= n <= 30:
            glossary[m.group(0)] = _ABI[n]
    if _PC_TOKEN.search(raw):
        glossary["pc"] = "program counter"
    if _MEM_TOKEN.search(raw):
        glossary["mem"] = "byte-addressable memory state"
    if _SP_TOKEN.search(raw):
        glossary["sp"] = "stack pointer"
    if _NZCV_TOKEN.search(raw):
        glossary["nzcv"] = "condition flags (N, Z, C, V)"
    return LiftedInvariant(raw=raw, glossary=glossary)


__all__ = ["LiftedInvariant", "lift_invariant"]
