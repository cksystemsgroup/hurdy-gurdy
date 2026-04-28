"""Invariant lift: parse a Spacer SMT-LIB invariant and label its variables.

Spacer returns invariants as SMT-LIB strings referencing the
artifact's state variables (e.g. ``reg_x10 < 100``). Lifting these
back to source-level facts means renaming the references through
the annotation: ``reg_x10`` becomes ``a0`` (ABI alias), ``pc``
becomes its source-mapped function/line.

The implementation here is intentionally conservative: it does not
attempt to rewrite SMT-LIB syntax (which would require a full
parser); instead, it scans for known state-name tokens and produces
a structured glossary the LLM can read alongside the raw invariant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping


_REG_TOKEN = re.compile(r"\breg_x(\d{1,2})\b")
_PC_TOKEN = re.compile(r"\bpc\b")
_MEM_TOKEN = re.compile(r"\bmem\b")


_ABI = {
    0: "zero", 1: "ra", 2: "sp", 3: "gp", 4: "tp", 5: "t0", 6: "t1", 7: "t2",
    8: "s0", 9: "s1", 10: "a0", 11: "a1", 12: "a2", 13: "a3", 14: "a4",
    15: "a5", 16: "a6", 17: "a7", 18: "s2", 19: "s3", 20: "s4", 21: "s5",
    22: "s6", 23: "s7", 24: "s8", 25: "s9", 26: "s10", 27: "s11",
    28: "t3", 29: "t4", 30: "t5", 31: "t6",
}


@dataclass
class LiftedInvariant:
    raw: str
    glossary: Mapping[str, str] = field(default_factory=dict)


def lift_invariant(raw: str) -> LiftedInvariant:
    glossary: dict[str, str] = {}
    for m in _REG_TOKEN.finditer(raw):
        n = int(m.group(1))
        if 0 <= n < 32:
            glossary[m.group(0)] = f"x{n} ({_ABI[n]})"
    if _PC_TOKEN.search(raw):
        glossary["pc"] = "program counter"
    if _MEM_TOKEN.search(raw):
        glossary["mem"] = "byte-addressable memory state"
    return LiftedInvariant(raw=raw, glossary=glossary)


__all__ = ["LiftedInvariant", "lift_invariant"]
