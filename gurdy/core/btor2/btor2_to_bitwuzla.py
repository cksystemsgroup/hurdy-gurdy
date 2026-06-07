"""Bitwuzla backend for the shared BTOR2 BMC driver.

The structural compile and the BMC unrolling live in ``_bmc``;
this module is a ``Backend`` adapter that translates the BTOR2 op
vocabulary into bitwuzla terms.

Bitwuzla's own Python BTOR2 parser does not handle the model-checking
extensions (``init`` / ``next`` / ``bad`` / ``constraint``), so we
drive the unrolling explicitly via the shared driver.
"""

from __future__ import annotations

from typing import Any

from gurdy.core.btor2._bmc import Backend, Compiled, compile_btor2
from gurdy.core.btor2._bmc import bmc as _bmc

try:
    import bitwuzla as _bw
except ImportError:  # pragma: no cover
    _bw = None  # type: ignore[assignment]


def _require_bw():
    if _bw is None:
        raise ImportError("bitwuzla bindings not installed")
    return _bw


class BitwuzlaBackend:
    """Each backend instance owns a TermManager. The BMC driver creates
    one Backend per dispatch so terms don't leak between sessions."""

    def __init__(self) -> None:
        _require_bw()
        self._tm = _bw.TermManager()
        self._bv1 = self._tm.mk_bv_sort(1)
        self._bv1_one = self._tm.mk_bv_one(self._bv1)
        self._bv1_zero = self._tm.mk_bv_zero(self._bv1)

    @property
    def K(self):
        return _bw.Kind

    def make_var(self, name: str, sort_nid: int, comp: Compiled) -> Any:
        if sort_nid in comp.sort_widths:
            return self._tm.mk_const(self._tm.mk_bv_sort(comp.sort_widths[sort_nid]), name)
        if sort_nid in comp.array_meta:
            idx_s, elt_s = comp.array_meta[sort_nid]
            sort = self._tm.mk_array_sort(
                self._tm.mk_bv_sort(comp.sort_widths[idx_s]),
                self._tm.mk_bv_sort(comp.sort_widths[elt_s]),
            )
            return self._tm.mk_const(sort, name)
        raise ValueError(f"unknown sort nid {sort_nid}")

    def width_of(self, term: Any) -> int:
        return term.sort().bv_size()

    def bv_const(self, width: int, value: int) -> Any:
        return self._tm.mk_bv_value(self._tm.mk_bv_sort(width), value & ((1 << width) - 1))

    def bv_zero(self, width: int) -> Any:
        return self._tm.mk_bv_zero(self._tm.mk_bv_sort(width))

    def bv_one(self, width: int) -> Any:
        return self._tm.mk_bv_one(self._tm.mk_bv_sort(width))

    def bv_ones(self, width: int) -> Any:
        return self._tm.mk_bv_ones(self._tm.mk_bv_sort(width))

    def apply_op(self, op: str, args: list[int], operands: list[Any], comp: Compiled) -> Any:
        K = self.K
        tm = self._tm

        if op == "slice":
            return tm.mk_term(K.BV_EXTRACT, [operands[0]], [args[2], args[3]])
        if op == "sext":
            target_w = comp.sort_widths[args[0]]
            return tm.mk_term(K.BV_SIGN_EXTEND, [operands[0]], [target_w - self.width_of(operands[0])])
        if op == "uext":
            target_w = comp.sort_widths[args[0]]
            return tm.mk_term(K.BV_ZERO_EXTEND, [operands[0]], [target_w - self.width_of(operands[0])])

        # Comparison ops produce Bool in bitwuzla; wrap to bv1 to match BTOR2.
        def b2bv1(b):
            return tm.mk_term(K.ITE, [b, self._bv1_one, self._bv1_zero])

        if op == "add":
            return tm.mk_term(K.BV_ADD, operands)
        if op == "sub":
            return tm.mk_term(K.BV_SUB, operands)
        if op == "mul":
            return tm.mk_term(K.BV_MUL, operands)
        if op == "and":
            return tm.mk_term(K.BV_AND, operands)
        if op == "or":
            return tm.mk_term(K.BV_OR, operands)
        if op == "xor":
            return tm.mk_term(K.BV_XOR, operands)
        if op == "not":
            return tm.mk_term(K.BV_NOT, operands)
        if op == "neg":
            return tm.mk_term(K.BV_NEG, operands)
        if op == "sll":
            return tm.mk_term(K.BV_SHL, operands)
        if op == "srl":
            return tm.mk_term(K.BV_SHR, operands)
        if op == "sra":
            return tm.mk_term(K.BV_ASHR, operands)
        if op == "udiv":
            return tm.mk_term(K.BV_UDIV, operands)
        if op == "urem":
            return tm.mk_term(K.BV_UREM, operands)
        if op == "sdiv":
            return tm.mk_term(K.BV_SDIV, operands)
        if op == "srem":
            return tm.mk_term(K.BV_SREM, operands)
        if op == "eq":
            return b2bv1(tm.mk_term(K.EQUAL, operands))
        if op == "neq":
            return b2bv1(tm.mk_term(K.DISTINCT, operands))
        if op == "slt":
            return b2bv1(tm.mk_term(K.BV_SLT, operands))
        if op == "sgt":
            return b2bv1(tm.mk_term(K.BV_SGT, operands))
        if op == "slte":
            return b2bv1(tm.mk_term(K.BV_SLE, operands))
        if op == "sgte":
            return b2bv1(tm.mk_term(K.BV_SGE, operands))
        if op == "ult":
            return b2bv1(tm.mk_term(K.BV_ULT, operands))
        if op == "ugt":
            return b2bv1(tm.mk_term(K.BV_UGT, operands))
        if op == "ulte":
            return b2bv1(tm.mk_term(K.BV_ULE, operands))
        if op == "ugte":
            return b2bv1(tm.mk_term(K.BV_UGE, operands))
        if op == "ite":
            cond = tm.mk_term(K.EQUAL, [operands[0], self._bv1_one])
            return tm.mk_term(K.ITE, [cond, operands[1], operands[2]])
        if op == "concat":
            return tm.mk_term(K.BV_CONCAT, operands)
        if op == "read":
            return tm.mk_term(K.ARRAY_SELECT, operands)
        if op == "write":
            return tm.mk_term(K.ARRAY_STORE, operands)
        raise NotImplementedError(f"BitwuzlaBackend: unsupported op {op!r}")

    def make_solver(self) -> Any:
        opts = _bw.Options()
        opts.set(_bw.Option.PRODUCE_MODELS, True)
        return _bw.Bitwuzla(self._tm, opts)

    def assert_eq(self, solver: Any, a: Any, b: Any) -> None:
        solver.assert_formula(self._tm.mk_term(self.K.EQUAL, [a, b]))

    def assert_term(self, solver: Any, term: Any) -> None:
        solver.assert_formula(term)

    def make_or(self, terms: list[Any]) -> Any:
        if len(terms) == 1:
            return terms[0]
        return self._tm.mk_term(self.K.OR, terms)

    def make_eq_bv1_one(self, term: Any) -> Any:
        return self._tm.mk_term(self.K.EQUAL, [term, self._bv1_one])

    def check_sat(self, solver: Any) -> str:
        r = solver.check_sat()
        if r == _bw.Result.SAT:
            return "sat"
        if r == _bw.Result.UNSAT:
            return "unsat"
        return "unknown"


def bmc(comp: Compiled, bound: int) -> tuple[str, Any]:
    """Engine-specific entry point used by the wrapper module."""
    _require_bw()
    return _bmc(comp, bound, BitwuzlaBackend())


# Compat alias for the wrapper module that imported under the old name.
compile_to_z3 = compile_btor2


__all__ = ["bmc", "BitwuzlaBackend", "compile_btor2", "compile_to_z3"]
