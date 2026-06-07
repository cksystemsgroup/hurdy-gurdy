"""cvc5 backend for the shared BTOR2 BMC driver.

Mirrors the bitwuzla and z3 backends. cvc5's Python bindings don't
consume BTOR2 natively (the format is a model-checking language;
cvc5 is an SMT solver), so we drive the unrolling explicitly via
the shared ``_bmc`` driver.
"""

from __future__ import annotations

from typing import Any

from gurdy.core.btor2._bmc import Backend, Compiled, compile_btor2
from gurdy.core.btor2._bmc import bmc as _bmc

try:
    import cvc5 as _cvc5
except ImportError:  # pragma: no cover
    _cvc5 = None  # type: ignore[assignment]


def _require_cvc5():
    if _cvc5 is None:
        raise ImportError("cvc5 bindings not installed")
    return _cvc5


class Cvc5Backend:
    def __init__(self) -> None:
        _require_cvc5()
        self._tm = _cvc5.TermManager()
        self._bv1_sort = self._tm.mkBitVectorSort(1)
        self._bv1_one = self._tm.mkBitVector(1, 1)
        self._bv1_zero = self._tm.mkBitVector(1, 0)

    @property
    def K(self):
        return _cvc5.Kind

    def make_var(self, name: str, sort_nid: int, comp: Compiled) -> Any:
        if sort_nid in comp.sort_widths:
            return self._tm.mkConst(
                self._tm.mkBitVectorSort(comp.sort_widths[sort_nid]), name
            )
        if sort_nid in comp.array_meta:
            idx_s, elt_s = comp.array_meta[sort_nid]
            sort = self._tm.mkArraySort(
                self._tm.mkBitVectorSort(comp.sort_widths[idx_s]),
                self._tm.mkBitVectorSort(comp.sort_widths[elt_s]),
            )
            return self._tm.mkConst(sort, name)
        raise ValueError(f"unknown sort nid {sort_nid}")

    def width_of(self, term: Any) -> int:
        return term.getSort().getBitVectorSize()

    def bv_const(self, width: int, value: int) -> Any:
        return self._tm.mkBitVector(width, value & ((1 << width) - 1))

    def bv_zero(self, width: int) -> Any:
        return self._tm.mkBitVector(width, 0)

    def bv_one(self, width: int) -> Any:
        return self._tm.mkBitVector(width, 1)

    def bv_ones(self, width: int) -> Any:
        return self._tm.mkBitVector(width, (1 << width) - 1)

    def apply_op(self, op: str, args: list[int], operands: list[Any], comp: Compiled) -> Any:
        K = self.K
        tm = self._tm

        if op == "slice":
            opd = tm.mkOp(K.BITVECTOR_EXTRACT, args[2], args[3])
            return tm.mkTerm(opd, operands[0])
        if op == "sext":
            target_w = comp.sort_widths[args[0]]
            opd = tm.mkOp(K.BITVECTOR_SIGN_EXTEND, target_w - self.width_of(operands[0]))
            return tm.mkTerm(opd, operands[0])
        if op == "uext":
            target_w = comp.sort_widths[args[0]]
            opd = tm.mkOp(K.BITVECTOR_ZERO_EXTEND, target_w - self.width_of(operands[0]))
            return tm.mkTerm(opd, operands[0])

        # Comparison ops produce Bool; wrap to bv1.
        def b2bv1(b):
            return tm.mkTerm(K.ITE, b, self._bv1_one, self._bv1_zero)

        if op == "add":
            return tm.mkTerm(K.BITVECTOR_ADD, *operands)
        if op == "sub":
            return tm.mkTerm(K.BITVECTOR_SUB, *operands)
        if op == "mul":
            return tm.mkTerm(K.BITVECTOR_MULT, *operands)
        if op == "and":
            return tm.mkTerm(K.BITVECTOR_AND, *operands)
        if op == "or":
            return tm.mkTerm(K.BITVECTOR_OR, *operands)
        if op == "xor":
            return tm.mkTerm(K.BITVECTOR_XOR, *operands)
        if op == "not":
            return tm.mkTerm(K.BITVECTOR_NOT, *operands)
        if op == "neg":
            return tm.mkTerm(K.BITVECTOR_NEG, *operands)
        if op == "sll":
            return tm.mkTerm(K.BITVECTOR_SHL, *operands)
        if op == "srl":
            return tm.mkTerm(K.BITVECTOR_LSHR, *operands)
        if op == "sra":
            return tm.mkTerm(K.BITVECTOR_ASHR, *operands)
        if op == "udiv":
            return tm.mkTerm(K.BITVECTOR_UDIV, *operands)
        if op == "urem":
            return tm.mkTerm(K.BITVECTOR_UREM, *operands)
        if op == "sdiv":
            return tm.mkTerm(K.BITVECTOR_SDIV, *operands)
        if op == "srem":
            return tm.mkTerm(K.BITVECTOR_SREM, *operands)
        if op == "eq":
            return b2bv1(tm.mkTerm(K.EQUAL, *operands))
        if op == "neq":
            return b2bv1(tm.mkTerm(K.DISTINCT, *operands))
        if op == "slt":
            return b2bv1(tm.mkTerm(K.BITVECTOR_SLT, *operands))
        if op == "sgt":
            return b2bv1(tm.mkTerm(K.BITVECTOR_SGT, *operands))
        if op == "slte":
            return b2bv1(tm.mkTerm(K.BITVECTOR_SLE, *operands))
        if op == "sgte":
            return b2bv1(tm.mkTerm(K.BITVECTOR_SGE, *operands))
        if op == "ult":
            return b2bv1(tm.mkTerm(K.BITVECTOR_ULT, *operands))
        if op == "ugt":
            return b2bv1(tm.mkTerm(K.BITVECTOR_UGT, *operands))
        if op == "ulte":
            return b2bv1(tm.mkTerm(K.BITVECTOR_ULE, *operands))
        if op == "ugte":
            return b2bv1(tm.mkTerm(K.BITVECTOR_UGE, *operands))
        if op == "ite":
            cond = tm.mkTerm(K.EQUAL, operands[0], self._bv1_one)
            return tm.mkTerm(K.ITE, cond, operands[1], operands[2])
        if op == "concat":
            return tm.mkTerm(K.BITVECTOR_CONCAT, *operands)
        if op == "read":
            return tm.mkTerm(K.SELECT, *operands)
        if op == "write":
            return tm.mkTerm(K.STORE, *operands)
        raise NotImplementedError(f"Cvc5Backend: unsupported op {op!r}")

    def make_solver(self) -> Any:
        s = _cvc5.Solver(self._tm)
        s.setOption("produce-models", "true")
        return s

    def assert_eq(self, solver: Any, a: Any, b: Any) -> None:
        solver.assertFormula(self._tm.mkTerm(self.K.EQUAL, a, b))

    def assert_term(self, solver: Any, term: Any) -> None:
        solver.assertFormula(term)

    def make_or(self, terms: list[Any]) -> Any:
        if len(terms) == 1:
            return terms[0]
        return self._tm.mkTerm(self.K.OR, *terms)

    def make_eq_bv1_one(self, term: Any) -> Any:
        return self._tm.mkTerm(self.K.EQUAL, term, self._bv1_one)

    def check_sat(self, solver: Any) -> str:
        r = solver.checkSat()
        if r.isSat():
            return "sat"
        if r.isUnsat():
            return "unsat"
        return "unknown"


def bmc(comp: Compiled, bound: int) -> tuple[str, Any]:
    """Engine-specific entry point used by the wrapper module."""
    _require_cvc5()
    return _bmc(comp, bound, Cvc5Backend())


__all__ = ["bmc", "Cvc5Backend", "compile_btor2"]
