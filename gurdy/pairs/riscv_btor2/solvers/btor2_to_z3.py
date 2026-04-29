"""Z3 backend for the shared BTOR2 BMC driver.

The structural compile and the BMC unrolling live in ``_bmc``;
this module is a ~100-line ``Backend`` adapter that translates
the BTOR2 op vocabulary into z3 expressions.
"""

from __future__ import annotations

from typing import Any

from gurdy.pairs.riscv_btor2.solvers._bmc import Backend, Compiled, compile_btor2
from gurdy.pairs.riscv_btor2.solvers._bmc import bmc as _bmc

try:
    import z3 as _z3
except ImportError:  # pragma: no cover
    _z3 = None  # type: ignore[assignment]


def _require_z3():
    if _z3 is None:
        raise ImportError("z3-solver is not installed")
    return _z3


def _bv_const(width: int, value: int):
    return _z3.BitVecVal(value & ((1 << width) - 1), width)


class Z3Backend:
    def make_var(self, name: str, sort_nid: int, comp: Compiled) -> Any:
        if sort_nid in comp.sort_widths:
            return _z3.BitVec(name, comp.sort_widths[sort_nid])
        if sort_nid in comp.array_meta:
            idx_s, elt_s = comp.array_meta[sort_nid]
            return _z3.Array(
                name,
                _z3.BitVecSort(comp.sort_widths[idx_s]),
                _z3.BitVecSort(comp.sort_widths[elt_s]),
            )
        raise ValueError(f"unknown sort nid {sort_nid}")

    def width_of(self, term: Any) -> int:
        return term.size()

    def bv_const(self, width: int, value: int) -> Any:
        return _bv_const(width, value)

    def bv_zero(self, width: int) -> Any:
        return _bv_const(width, 0)

    def bv_one(self, width: int) -> Any:
        return _bv_const(width, 1)

    def bv_ones(self, width: int) -> Any:
        return _bv_const(width, (1 << width) - 1)

    def apply_op(self, op: str, args: list[int], operands: list[Any], comp: Compiled) -> Any:
        # Mixed-arg ops first.
        if op == "slice":
            return _z3.Extract(args[2], args[3], operands[0])
        if op == "sext":
            target_w = comp.sort_widths[args[0]]
            return _z3.SignExt(target_w - operands[0].size(), operands[0])
        if op == "uext":
            target_w = comp.sort_widths[args[0]]
            return _z3.ZeroExt(target_w - operands[0].size(), operands[0])

        if op == "add":
            return operands[0] + operands[1]
        if op == "sub":
            return operands[0] - operands[1]
        if op == "mul":
            return operands[0] * operands[1]
        if op == "and":
            return operands[0] & operands[1]
        if op == "or":
            return operands[0] | operands[1]
        if op == "xor":
            return operands[0] ^ operands[1]
        if op == "not":
            return ~operands[0]
        if op == "neg":
            return -operands[0]
        if op == "sll":
            return operands[0] << operands[1]
        if op == "srl":
            return _z3.LShR(operands[0], operands[1])
        if op == "sra":
            return operands[0] >> operands[1]
        if op == "udiv":
            return _z3.UDiv(operands[0], operands[1])
        if op == "urem":
            return _z3.URem(operands[0], operands[1])
        if op == "sdiv":
            return operands[0] / operands[1]
        if op == "srem":
            return _z3.SRem(operands[0], operands[1])
        if op == "eq":
            return _z3.If(operands[0] == operands[1], _bv_const(1, 1), _bv_const(1, 0))
        if op == "neq":
            return _z3.If(operands[0] != operands[1], _bv_const(1, 1), _bv_const(1, 0))
        if op == "slt":
            return _z3.If(operands[0] < operands[1], _bv_const(1, 1), _bv_const(1, 0))
        if op == "sgt":
            return _z3.If(operands[0] > operands[1], _bv_const(1, 1), _bv_const(1, 0))
        if op == "slte":
            return _z3.If(operands[0] <= operands[1], _bv_const(1, 1), _bv_const(1, 0))
        if op == "sgte":
            return _z3.If(operands[0] >= operands[1], _bv_const(1, 1), _bv_const(1, 0))
        if op == "ult":
            return _z3.If(_z3.ULT(operands[0], operands[1]), _bv_const(1, 1), _bv_const(1, 0))
        if op == "ugt":
            return _z3.If(_z3.UGT(operands[0], operands[1]), _bv_const(1, 1), _bv_const(1, 0))
        if op == "ulte":
            return _z3.If(_z3.ULE(operands[0], operands[1]), _bv_const(1, 1), _bv_const(1, 0))
        if op == "ugte":
            return _z3.If(_z3.UGE(operands[0], operands[1]), _bv_const(1, 1), _bv_const(1, 0))
        if op == "ite":
            cond = operands[0] == _bv_const(1, 1)
            return _z3.If(cond, operands[1], operands[2])
        if op == "concat":
            return _z3.Concat(operands[0], operands[1])
        if op == "read":
            return _z3.Select(operands[0], operands[1])
        if op == "write":
            return _z3.Update(operands[0], operands[1], operands[2])
        raise NotImplementedError(f"Z3Backend: unsupported op {op!r}")

    def make_solver(self) -> Any:
        return _z3.Solver()

    def assert_eq(self, solver: Any, a: Any, b: Any) -> None:
        solver.add(a == b)

    def assert_term(self, solver: Any, term: Any) -> None:
        solver.add(term)

    def make_or(self, terms: list[Any]) -> Any:
        return _z3.Or(*terms) if len(terms) > 1 else terms[0]

    def make_eq_bv1_one(self, term: Any) -> Any:
        return term == _bv_const(1, 1)

    def check_sat(self, solver: Any) -> str:
        r = solver.check()
        if r == _z3.sat:
            return "sat"
        if r == _z3.unsat:
            return "unsat"
        return "unknown"


def bmc(comp: Compiled, bound: int) -> tuple[str, Any]:
    """Engine-specific entry point used by the wrapper module."""
    _require_z3()
    return _bmc(comp, bound, Z3Backend())


# Backward-compat aliases for callers that still use the old names.
CompiledZ3 = Compiled
compile_to_z3 = compile_btor2


__all__ = ["bmc", "Z3Backend", "Compiled", "compile_btor2", "CompiledZ3", "compile_to_z3"]
