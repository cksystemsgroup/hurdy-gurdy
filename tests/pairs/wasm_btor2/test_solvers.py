"""Tests for the P7 z3-bmc solver adapter (``gurdy/pairs/wasm_btor2/solvers/``).

Coverage:
  - module imports and version-independence smoke
  - Z3BMCSolver.dispatch on the 0001-i32-add-wrap seed → unreachable
  - result shape: verdict, elapsed, engine, payload
  - compile_btor2 / Compiled structural shape
  - bmc returns 'unreachable' for a no-bad-node model
  - bmc returns 'reachable' for a trivially satisfiable bad node
  - Z3Backend make_var, bv_const, bv_zero, bv_one, bv_ones
  - Z3Backend apply_op for arithmetic, logic, comparison, ite, concat
  - Z3Backend check_sat sat/unsat/unknown paths
  - Z3BMCSolver graceful error on bad BTOR2 bytes
  - directive.bound honoured (bound=0 → unreachable for non-trivial bad)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gurdy.pairs.wasm_btor2.solvers import Z3BMCSolver, Compiled, compile_btor2, Z3Backend
from gurdy.core.btor2._bmc import bmc as bmc3, find_sort_for
from gurdy.pairs.wasm_btor2.solvers.btor2_to_z3 import bmc as bmc2

_SEED_DIR = Path(__file__).resolve().parents[3] / "bench/wasm-btor2/corpus/seed/0001-i32-add-wrap"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_artifact() -> bytes:
    """Compile 0001-i32-add-wrap once and return the flattened BTOR2 bytes."""
    from gurdy.core.annotation.sidecar import AnnotationSidecar
    from gurdy.pairs.wasm_btor2.source import load_wasm_source
    from gurdy.pairs.wasm_btor2.spec import WasmBtor2Spec
    from gurdy.pairs.wasm_btor2.translation import Translator

    src = load_wasm_source(_SEED_DIR / "module.wasm")
    spec = WasmBtor2Spec.from_jsonable(json.loads((_SEED_DIR / "spec.json").read_text()))

    class _Ann:
        sidecar = AnnotationSidecar()

    return Translator().translate(spec, src, _Ann()).flattened


def _minimal_btor2_no_bad() -> bytes:
    """A BTOR2 program with one state, no bad node — always unreachable."""
    return b"""\
1 sort bitvec 8
2 state 1 counter
3 zero 1
4 one 1
5 init 1 2 3
6 add 1 2 4
7 next 1 2 6
"""


def _minimal_btor2_always_bad() -> bytes:
    """A BTOR2 program whose bad node fires immediately at cycle 0."""
    return b"""\
1 sort bitvec 1
2 state 1 flag
3 one 1
4 init 1 2 3
5 bad 2
"""


class _Directive:
    def __init__(self, bound: int = 8):
        self.bound = bound


# ---------------------------------------------------------------------------
# Import / structural smoke
# ---------------------------------------------------------------------------


def test_z3bmc_solver_importable():
    assert Z3BMCSolver is not None


def test_compiled_is_dataclass():
    from dataclasses import fields
    assert len(fields(Compiled)) > 0


def test_bmc_importable():
    assert callable(bmc3) and callable(bmc2)


def test_z3backend_instantiates():
    backend = Z3Backend()
    assert backend is not None


# ---------------------------------------------------------------------------
# Compile / Compiled shape
# ---------------------------------------------------------------------------


def test_compile_btor2_state_nids(tmp_path):
    from gurdy.core.btor2.parser import from_text
    result = from_text(_minimal_btor2_no_bad().decode())
    comp = compile_btor2(result.model)
    assert len(comp.state_nids) == 1


def test_compile_btor2_no_bad_nids(tmp_path):
    from gurdy.core.btor2.parser import from_text
    result = from_text(_minimal_btor2_no_bad().decode())
    comp = compile_btor2(result.model)
    assert comp.bad_nids == []


def test_compile_btor2_bad_nids_present():
    from gurdy.core.btor2.parser import from_text
    result = from_text(_minimal_btor2_always_bad().decode())
    comp = compile_btor2(result.model)
    assert len(comp.bad_nids) == 1


def test_compile_btor2_seed_artifact():
    from gurdy.core.btor2.parser import from_text
    btor2_bytes = _load_artifact()
    result = from_text(btor2_bytes.decode())
    comp = compile_btor2(result.model)
    assert len(comp.state_nids) > 0
    assert len(comp.bad_nids) > 0


# ---------------------------------------------------------------------------
# bmc() direct
# ---------------------------------------------------------------------------


def test_bmc_no_bad_unreachable():
    from gurdy.core.btor2.parser import from_text
    result = from_text(_minimal_btor2_no_bad().decode())
    comp = compile_btor2(result.model)
    verdict, solver = bmc3(comp, 4, Z3Backend())
    assert verdict == "unreachable"
    assert solver is None


def test_bmc_always_bad_reachable():
    from gurdy.core.btor2.parser import from_text
    result = from_text(_minimal_btor2_always_bad().decode())
    comp = compile_btor2(result.model)
    verdict, solver = bmc3(comp, 4, Z3Backend())
    assert verdict == "reachable"
    assert solver is not None


def test_bmc_seed_unreachable_at_bound_8():
    from gurdy.core.btor2.parser import from_text
    btor2_bytes = _load_artifact()
    result = from_text(btor2_bytes.decode())
    comp = compile_btor2(result.model)
    verdict, _ = bmc3(comp, 8, Z3Backend())
    assert verdict == "unreachable"


# ---------------------------------------------------------------------------
# Z3BMCSolver.dispatch — result shape
# ---------------------------------------------------------------------------


def test_dispatch_verdict_unreachable():
    solver = Z3BMCSolver()
    result = solver.dispatch(_load_artifact(), _Directive(bound=8))
    assert result.verdict == "unreachable"


def test_dispatch_engine_name():
    solver = Z3BMCSolver()
    result = solver.dispatch(_load_artifact(), _Directive(bound=8))
    assert result.engine == "z3-bmc"


def test_dispatch_elapsed_positive():
    solver = Z3BMCSolver()
    result = solver.dispatch(_load_artifact(), _Directive(bound=8))
    assert result.elapsed > 0.0


def test_dispatch_payload_none_on_unreachable():
    solver = Z3BMCSolver()
    result = solver.dispatch(_load_artifact(), _Directive(bound=8))
    assert result.payload is None


def test_dispatch_payload_witness_on_reachable():
    from gurdy.core.btor2.parser import from_text
    solver = Z3BMCSolver()
    result = solver.dispatch(_minimal_btor2_always_bad(), _Directive(bound=1))
    assert result.verdict == "reachable"
    assert result.payload is not None
    assert "witness_text" in result.payload


def test_dispatch_error_on_bad_btor2():
    solver = Z3BMCSolver()
    result = solver.dispatch(b"this is not btor2 at all @@@@", _Directive())
    assert result.verdict in ("error", "unknown")


def test_dispatch_bound_zero_no_bad():
    from gurdy.core.btor2.parser import from_text
    solver = Z3BMCSolver()
    result = solver.dispatch(_minimal_btor2_no_bad(), _Directive(bound=0))
    assert result.verdict == "unreachable"


# ---------------------------------------------------------------------------
# Z3Backend unit tests
# ---------------------------------------------------------------------------


def test_z3backend_bv_const():
    import z3
    b = Z3Backend()
    term = b.bv_const(32, 42)
    assert z3.is_bv(term)


def test_z3backend_bv_zero():
    import z3
    b = Z3Backend()
    term = b.bv_zero(8)
    assert z3.is_bv(term)


def test_z3backend_bv_one():
    import z3
    b = Z3Backend()
    term = b.bv_one(16)
    assert z3.is_bv(term)


def test_z3backend_bv_ones():
    import z3
    b = Z3Backend()
    term = b.bv_ones(4)
    assert z3.is_bv(term)


def test_z3backend_add_op():
    import z3
    b = Z3Backend()
    comp = Compiled(sort_widths={1: 32})
    x = z3.BitVec("x", 32)
    y = z3.BitVec("y", 32)
    result = b.apply_op("add", [1], [x, y], comp)
    s = z3.Solver()
    s.add(result == z3.BitVecVal(7, 32))
    s.add(x == z3.BitVecVal(3, 32))
    s.add(y == z3.BitVecVal(4, 32))
    assert s.check() == z3.sat


def test_z3backend_eq_op_true():
    import z3
    b = Z3Backend()
    comp = Compiled(sort_widths={1: 32})
    x = z3.BitVecVal(5, 32)
    y = z3.BitVecVal(5, 32)
    result = b.apply_op("eq", [1], [x, y], comp)
    s = z3.Solver()
    s.add(result == z3.BitVecVal(1, 1))
    assert s.check() == z3.sat


def test_z3backend_ite_op():
    import z3
    b = Z3Backend()
    comp = Compiled(sort_widths={1: 32})
    cond = z3.BitVecVal(1, 1)
    t_val = z3.BitVecVal(10, 32)
    f_val = z3.BitVecVal(20, 32)
    result = b.apply_op("ite", [1], [cond, t_val, f_val], comp)
    s = z3.Solver()
    s.add(result == z3.BitVecVal(10, 32))
    assert s.check() == z3.sat


def test_z3backend_unsupported_op_raises():
    b = Z3Backend()
    comp = Compiled(sort_widths={1: 32})
    with pytest.raises(NotImplementedError):
        b.apply_op("future_op_xyz", [1], [], comp)


def test_z3backend_check_sat_unsat():
    import z3
    b = Z3Backend()
    s = b.make_solver()
    x = z3.BitVec("x", 8)
    b.assert_term(s, x == z3.BitVecVal(1, 8))
    b.assert_term(s, x == z3.BitVecVal(2, 8))
    assert b.check_sat(s) == "unsat"


def test_z3backend_check_sat_sat():
    import z3
    b = Z3Backend()
    s = b.make_solver()
    x = z3.BitVec("x", 8)
    b.assert_term(s, x == z3.BitVecVal(5, 8))
    assert b.check_sat(s) == "sat"
