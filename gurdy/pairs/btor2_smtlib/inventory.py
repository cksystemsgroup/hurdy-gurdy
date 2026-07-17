"""Construct-coverage inventory for btor2-smtlib (BENCHMARKS.md §2, §5).

The denominator is BTOR2's spec-enumerable set of sorts, leaves, directives, and
operators — the inventory the agent does **not** choose; it is the format
definition, mirrored by ``languages/btor2/model.py``. A construct is *covered*
iff a minimal system exercising it bridges to SMT-LIB without an ``Unsupported``
abort. A finite reasoning bridge must cover 100% of this set (BENCHMARKS.md §5
floor: it is small and spec-enumerable), so any gap is a real, itemized hole.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from .translate import translate

_W8 = "1 sort bitvec 8"  # id 1: an 8-bit sort, reused across the templates below


def _probe(*lines: str) -> dict:
    return {"system": "\n".join(lines) + "\n", "k": 1}


def _bin(op: str) -> dict:  # binary bit-vector op, 8-bit operands and result
    return _probe(_W8, "2 input 1", "3 input 1", f"4 {op} 1 2 3")


def _un(op: str) -> dict:  # unary bit-vector op
    return _probe(_W8, "2 input 1", f"3 {op} 1 2")


def _red(op: str) -> dict:  # reduction op: 8-bit operand -> 1-bit result
    return _probe(_W8, "2 sort bitvec 1", "3 input 1", f"4 {op} 2 3")


def _cmp(op: str) -> dict:  # comparison: 8-bit operands -> 1-bit result
    return _probe(_W8, "2 sort bitvec 1", "3 input 1", "4 input 1", f"5 {op} 2 3 4")


def _logic(op: str) -> dict:  # 1-bit logical connective
    return _probe("1 sort bitvec 1", "2 input 1", "3 input 1", f"4 {op} 1 2 3")


ALL_PROBES: dict[str, dict] = {
    # sorts
    "bitvec": _probe(_W8, "2 input 1"),
    "array": _probe(_W8, "2 sort array 1 1", "3 state 2 mem"),
    # constant leaves
    "zero": _probe(_W8, "2 zero 1"),
    "one": _probe(_W8, "2 one 1"),
    "ones": _probe(_W8, "2 ones 1"),
    "const": _probe(_W8, "2 const 1 10101010"),
    "constd": _probe(_W8, "2 constd 1 42"),
    "consth": _probe(_W8, "2 consth 1 ff"),
    # non-constant leaves
    "input": _probe(_W8, "2 input 1"),
    "state": _probe(_W8, "2 state 1 s"),
    # directives
    "init": _probe(_W8, "2 state 1 s", "3 zero 1", "4 init 1 2 3"),
    "next": _probe(_W8, "2 state 1 s", "3 one 1", "4 add 1 2 3", "5 next 1 2 4"),
    "bad": _probe("1 sort bitvec 1", "2 input 1", "3 bad 2"),
    "constraint": _probe("1 sort bitvec 1", "2 input 1", "3 constraint 2"),
    "output": _probe(_W8, "2 input 1", "3 output 2"),
    # the signed-operand form: -n cites the bitwise NOT of node n, in
    # operand and directive positions alike (surfaced by HWMCC ingestion)
    "negated-ref": _probe("1 sort bitvec 1", "2 one 1", "3 state 1 s",
                          "4 init 1 3 -2", "5 next 1 3 -3", "6 bad -3"),
    # unary
    "not": _un("not"), "neg": _un("neg"), "inc": _un("inc"), "dec": _un("dec"),
    "redor": _red("redor"), "redand": _red("redand"), "redxor": _red("redxor"),
    # binary arithmetic / logic / shifts
    "and": _bin("and"), "or": _bin("or"), "xor": _bin("xor"),
    "nand": _bin("nand"), "nor": _bin("nor"),
    "add": _bin("add"), "sub": _bin("sub"), "mul": _bin("mul"),
    "udiv": _bin("udiv"), "urem": _bin("urem"),
    "sdiv": _bin("sdiv"), "srem": _bin("srem"),
    "sll": _bin("sll"), "srl": _bin("srl"), "sra": _bin("sra"),
    # concat widens, so the result needs its own (16-bit) sort
    "concat": _probe(_W8, "2 sort bitvec 16", "3 input 1", "4 input 1", "5 concat 2 3 4"),
    # comparisons
    "eq": _cmp("eq"), "neq": _cmp("neq"),
    "ult": _cmp("ult"), "ulte": _cmp("ulte"), "ugt": _cmp("ugt"), "ugte": _cmp("ugte"),
    "slt": _cmp("slt"), "slte": _cmp("slte"), "sgt": _cmp("sgt"), "sgte": _cmp("sgte"),
    # logical connectives
    "implies": _logic("implies"), "iff": _logic("iff"),
    # structural
    "ite": _probe(_W8, "2 sort bitvec 1", "3 input 2", "4 input 1", "5 input 1",
                  "6 ite 1 3 4 5"),
    "slice": _probe(_W8, "2 sort bitvec 4", "3 input 1", "4 slice 2 3 3 0"),
    "sext": _probe(_W8, "2 sort bitvec 16", "3 input 1", "4 sext 2 3 8"),
    "uext": _probe(_W8, "2 sort bitvec 16", "3 input 1", "4 uext 2 3 8"),
    # arrays
    "read": _probe(_W8, "2 sort array 1 1", "3 state 2 mem", "4 input 1", "5 read 1 3 4"),
    "write": _probe(_W8, "2 sort array 1 1", "3 state 2 mem", "4 input 1", "5 input 1",
                    "6 write 2 3 4 5"),
}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
