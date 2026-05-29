"""Tests for gurdy/pairs/ebpf_btor2/solvers/ (P6)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# bench/ebpf-btor2/ has a hyphen so it is not importable as a package.
# Inject it into sys.path so ``harness`` can be imported by filename.
_BENCH_EBPF = Path(__file__).resolve().parent.parent.parent.parent / "bench" / "ebpf-btor2"
if str(_BENCH_EBPF) not in sys.path:
    sys.path.insert(0, str(_BENCH_EBPF))

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.pairs.ebpf_btor2.spec import (
    AnalysisDirective,
    EbpfBtor2Spec,
    EbpfProgramRef,
    EbpfScope,
    Property,
)
from gurdy.pairs.ebpf_btor2.solvers import Z3BMCSolver, check
from gurdy.pairs.ebpf_btor2.translation import translate


# ---------------------------------------------------------------------------
# Shared bytecode fixtures (same as in test_translation.py)
# ---------------------------------------------------------------------------

# r0 += 1 (ALU64 ADD K dst=r0 imm=1) ; EXIT
_ADD_EXIT = bytes([
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])

# EXIT only
_EXIT_ONLY = bytes([
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])


def _spec(expression: str = "false", max_insns: int = 4) -> EbpfBtor2Spec:
    return EbpfBtor2Spec(
        program=EbpfProgramRef(path="test"),
        scope=EbpfScope(max_insns=max_insns),
        property=Property(expression=expression),
        analysis=AnalysisDirective(engine="z3-bmc"),
    )


# ---------------------------------------------------------------------------
# Z3BMCSolver unit tests
# ---------------------------------------------------------------------------


class TestZ3BMCSolverName:
    def test_default_name(self):
        assert Z3BMCSolver().name == "z3-bmc"


class TestZ3BMCSolverDispatch:
    def test_bad_btor2_returns_error(self):
        solver = Z3BMCSolver()

        class _D:
            bound = 1

        result = solver.dispatch(b"not valid btor2 at all", _D())
        assert result.verdict == "error"
        assert result.engine == "z3-bmc"
        assert result.reason is not None

    def test_false_property_unreachable(self):
        """Property 'false' can never fire → unreachable."""
        spec = _spec("false")
        artifact = translate(spec, _EXIT_ONLY)

        class _D:
            bound = 4

        result = Z3BMCSolver().dispatch(artifact.flattened, _D())
        assert result.verdict == "unreachable"

    def test_r0_eq_1_reachable_after_add(self):
        """r0 += 1; EXIT with property 'r0 == 1' → bad fires → reachable."""
        spec = _spec("r0 == 1")
        artifact = translate(spec, _ADD_EXIT)

        class _D:
            bound = 4

        result = Z3BMCSolver().dispatch(artifact.flattened, _D())
        assert result.verdict == "reachable"

    def test_witness_payload_present_when_reachable(self):
        spec = _spec("r0 == 1")
        artifact = translate(spec, _ADD_EXIT)

        class _D:
            bound = 4

        result = Z3BMCSolver().dispatch(artifact.flattened, _D())
        assert result.verdict == "reachable"
        assert result.payload is not None
        assert "witness_text" in result.payload

    def test_result_is_raw_solver_result(self):
        spec = _spec("false")
        artifact = translate(spec, _EXIT_ONLY)

        class _D:
            bound = 4

        result = Z3BMCSolver().dispatch(artifact.flattened, _D())
        assert isinstance(result, RawSolverResult)
        assert result.engine == "z3-bmc"
        assert result.elapsed >= 0.0


# ---------------------------------------------------------------------------
# check() entry-point tests
# ---------------------------------------------------------------------------


class TestCheck:
    def test_seed_task_reachable(self):
        """Seed corpus task: r0 += 1; EXIT with property r0 == 1 → PASS."""
        spec = _spec("r0 == 1", max_insns=4)
        result = check(spec, _ADD_EXIT)
        assert result.verdict == "reachable"

    def test_false_property_unreachable(self):
        spec = _spec("false", max_insns=4)
        result = check(spec, _EXIT_ONLY)
        assert result.verdict == "unreachable"

    def test_exit_reached_reachable(self):
        """exit_reached fires when halted=1; EXIT-only program always halts."""
        spec = _spec("exit_reached", max_insns=4)
        result = check(spec, _EXIT_ONLY)
        assert result.verdict == "reachable"

    def test_bound_from_spec_analysis(self):
        """Explicit bound in analysis directive is respected."""
        spec = EbpfBtor2Spec(
            program=EbpfProgramRef(path="test"),
            scope=EbpfScope(max_insns=100),
            property=Property(expression="r0 == 1"),
            analysis=AnalysisDirective(engine="z3-bmc", bound=2),
        )
        result = check(spec, _ADD_EXIT)
        assert result.verdict == "reachable"

    def test_bound_falls_back_to_max_insns(self):
        """When analysis.bound is None, scope.max_insns is used."""
        spec = EbpfBtor2Spec(
            program=EbpfProgramRef(path="test"),
            scope=EbpfScope(max_insns=4),
            property=Property(expression="r0 == 1"),
            analysis=AnalysisDirective(engine="z3-bmc"),  # bound=None
        )
        result = check(spec, _ADD_EXIT)
        assert result.verdict == "reachable"

    def test_returns_raw_solver_result(self):
        spec = _spec("false")
        result = check(spec, _EXIT_ONLY)
        assert isinstance(result, RawSolverResult)
        assert result.engine == "z3-bmc"

    def test_ja_exit_reachable(self):
        """JA (unconditional jump) + EXIT: exit_reached fires → reachable."""
        # JA +0 (jump forward 0) then EXIT — same as EXIT but tests JMP path
        ja_exit = bytes([
            0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # JA +0
            0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
        ])
        spec = _spec("exit_reached", max_insns=4)
        result = check(spec, ja_exit)
        assert result.verdict == "reachable"


# ---------------------------------------------------------------------------
# Harness smoke test
# ---------------------------------------------------------------------------


def _load_harness():
    """Load bench/ebpf-btor2/harness.py with a unique module name to avoid
    collisions with bench/riscv-btor2/harness.py in sys.modules."""
    import importlib.util

    _MOD = "ebpf_btor2_harness"
    if _MOD in sys.modules:
        return sys.modules[_MOD]
    spec = importlib.util.spec_from_file_location(_MOD, _BENCH_EBPF / "harness.py")
    h = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses can resolve forward refs via sys.modules.
    sys.modules[_MOD] = h
    spec.loader.exec_module(h)
    return h


class TestHarness:
    def test_seed_task_passes_in_harness(self):
        """run_task on the seed corpus entry should return PASS."""
        import contextlib
        import io

        h = _load_harness()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = h.run_task(h.CORPUS[0])
        assert status == "PASS"
        assert "seed/r0_add1_exit" in buf.getvalue()

    def test_corpus_nonempty(self):
        h = _load_harness()
        assert len(h.CORPUS) >= 1

    def test_run_corpus_returns_zero(self):
        import contextlib
        import io

        h = _load_harness()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = h.run_corpus()
        assert rc == 0
