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

    def test_corpus_has_thirtyone_tasks(self):
        h = _load_harness()
        assert len(h.CORPUS) == 31

    def test_corpus_task_ids(self):
        h = _load_harness()
        ids = [t.task_id for t in h.CORPUS]
        # P6/P7 tasks
        assert "seed/r0_add1_exit" in ids
        assert "seed/exit_only_exit_reached" in ids
        assert "seed/r0_xor_self_exit_r0_eq_0" in ids
        assert "seed/r0_xor_self_exit_r0_eq_1_unreachable" in ids
        assert "seed/r0_add1_add1_exit" in ids
        # P8 JMP tasks
        assert "seed/ja_self_loop_unreachable" in ids
        assert "seed/add_jeq_skip_exit_r0_eq_2" in ids
        assert "seed/jeq_taken_skip_add_r0_eq_0" in ids
        # P9 multi-register ALU tasks
        assert "seed/r1_add1_r0_add_r1_exit_r0_eq_1" in ids
        assert "seed/r2_mul_r3_exit_r2_eq_6" in ids
        assert "seed/r0_sub_self_exit_r0_eq_1_unreachable" in ids
        # P10 DIV/OR/AND/MOD K tasks
        assert "seed/r0_div8_exit_r0_eq_3" in ids
        assert "seed/r0_or_0x80_exit_r0_eq_128" in ids
        assert "seed/r0_or_0x80_exit_r0_eq_0_unreachable" in ids
        assert "seed/r0_and_0xf_exit_r0_eq_15" in ids
        assert "seed/r0_mod3_exit_r0_eq_2" in ids
        # P11 LSH/RSH/ARSH K tasks
        assert "seed/r0_lsh2_exit_r0_eq_4" in ids
        assert "seed/r0_lsh2_exit_r0_eq_3_unreachable" in ids
        assert "seed/r0_rsh1_exit_r0_eq_4" in ids
        assert "seed/r0_arsh1_exit_r0_eq_1" in ids
        assert "seed/r0_arsh1_exit_r0_eq_neg1" in ids
        # P12 NEG/MOV tasks
        assert "seed/r0_neg_exit_r0_eq_0" in ids
        assert "seed/r0_neg_exit_r0_eq_1" in ids
        assert "seed/r0_mov_k42_exit_r0_eq_42" in ids
        assert "seed/r0_mov_k42_exit_r0_eq_41_unreachable" in ids
        assert "seed/r0_mov_x_r1_exit_r0_eq_7" in ids
        # P13 multi-instruction programs
        assert "seed/mov5_neg_exit_r0_eq_neg5" in ids
        assert "seed/mov5_neg_exit_r0_eq_5_unreachable" in ids
        assert "seed/mov42_movx_jeq_exit_r0_eq_42" in ids
        assert "seed/mov42_movx_jeq_exit_r0_eq_0_unreachable" in ids
        assert "seed/mov1_jne_mov99_exit_r0_eq_99" in ids

    def test_run_corpus_returns_zero(self):
        import contextlib
        import io

        h = _load_harness()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = h.run_corpus()
        assert rc == 0

    def test_all_corpus_tasks_pass_or_skip(self):
        import contextlib
        import io

        h = _load_harness()
        for task in h.CORPUS:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                status = h.run_task(task)
            assert status in ("PASS", "SKIP"), f"{task.task_id}: {status}"


# ---------------------------------------------------------------------------
# P7 corpus tasks — direct check() tests
# ---------------------------------------------------------------------------

# r0 ^= r0  (ALU64 XOR X, dst=r0, src=r0)
# EXIT
_XOR_SELF_EXIT = bytes([
    0xaf, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])

# r0 += 1; r0 += 1; EXIT
_DOUBLE_ADD_EXIT = bytes([
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])


class TestP7Corpus:
    def test_exit_only_exit_reached_reachable(self):
        result = check(_spec("exit_reached", max_insns=2), _EXIT_ONLY)
        assert result.verdict == "reachable"

    def test_xor_self_r0_eq_0_reachable(self):
        """r0 ^= r0 always gives r0=0; property r0==0 must fire."""
        result = check(_spec("r0 == 0", max_insns=4), _XOR_SELF_EXIT)
        assert result.verdict == "reachable"

    def test_xor_self_r0_eq_1_unreachable(self):
        """r0 ^= r0 always gives r0=0; r0==1 can never fire."""
        result = check(_spec("r0 == 1", max_insns=4), _XOR_SELF_EXIT)
        assert result.verdict == "unreachable"

    def test_double_add_r0_eq_2_reachable(self):
        """r0 += 1; r0 += 1; EXIT: witness initial r0=0 → r0=2 at halt."""
        result = check(_spec("r0 == 2", max_insns=6), _DOUBLE_ADD_EXIT)
        assert result.verdict == "reachable"

    def test_double_add_r0_eq_0_unreachable(self):
        """After two add-1 ops, r0 == initial+2; r0==0 requires initial==−2
        (2^64−2). Verify this is found reachable (unsigned wrap-around)."""
        result = check(_spec("r0 == 0", max_insns=6), _DOUBLE_ADD_EXIT)
        # 2^64 - 2 + 2 = 0 (mod 2^64); the solver finds this witness.
        assert result.verdict == "reachable"

    def test_xor_self_then_add_r0_eq_1_reachable(self):
        """r0 ^= r0; r0 += 1; EXIT: r0 starts at 0, becomes 1.
        Property r0==1 fires at halt."""
        xor_add_exit = bytes([
            0xaf, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 ^= r0
            0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1
            0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
        ])
        result = check(_spec("r0 == 1", max_insns=6), xor_add_exit)
        assert result.verdict == "reachable"


# ---------------------------------------------------------------------------
# P8 corpus tasks — JMP dispatch layer
# ---------------------------------------------------------------------------

# JA -1: self-loop (off=-1 → target = insn_idx)
_JA_SELF = bytes([0x05, 0x00, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00])

# r0 += 1; JEQ r0, 99, +1; EXIT
_ADD_JEQ_SKIP = bytes([
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
    0x15, 0x00, 0x01, 0x00, 0x63, 0x00, 0x00, 0x00,
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])

# JEQ r0, 0, +1; r0 += 1; EXIT
_JEQ_TAKEN = bytes([
    0x15, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])


class TestP8Corpus:
    def test_ja_self_loop_exit_unreachable(self):
        """JA -1 loops forever; EXIT is never reached within bound."""
        result = check(_spec("exit_reached", max_insns=4), _JA_SELF)
        assert result.verdict == "unreachable"

    def test_ja_self_loop_false_unreachable(self):
        """Sanity: false property also unreachable for self-loop."""
        result = check(_spec("false", max_insns=4), _JA_SELF)
        assert result.verdict == "unreachable"

    def test_jeq_not_taken_r0_eq_2_reachable(self):
        """r0 += 1; JEQ r0, 99, +1; EXIT.
        Witness: initial r0=1 → r0=2, JEQ not taken, EXIT with r0=2."""
        result = check(_spec("r0 == 2", max_insns=6), _ADD_JEQ_SKIP)
        assert result.verdict == "reachable"

    def test_jeq_not_taken_r0_eq_99_unreachable(self):
        """r0 += 1; JEQ r0, 99, +1; EXIT.
        r0==99 at EXIT requires initial r0=98 → JEQ taken (r0=99==99) → OOB
        loop, never halts via EXIT. So r0==99 at EXIT is unreachable."""
        result = check(_spec("r0 == 99", max_insns=6), _ADD_JEQ_SKIP)
        assert result.verdict == "unreachable"

    def test_jeq_taken_skip_add_r0_eq_0_reachable(self):
        """JEQ r0, 0, +1; r0 += 1; EXIT.
        Witness: initial r0=0 → JEQ taken, add skipped, EXIT with r0=0."""
        result = check(_spec("r0 == 0", max_insns=6), _JEQ_TAKEN)
        assert result.verdict == "reachable"

    def test_jeq_not_taken_fallthrough_r0_eq_2_reachable(self):
        """JEQ r0, 0, +1; r0 += 1; EXIT.
        Witness: initial r0=1 → JEQ not taken (1≠0), r0+=1=2, EXIT with r0=2."""
        result = check(_spec("r0 == 2", max_insns=6), _JEQ_TAKEN)
        assert result.verdict == "reachable"


# ---------------------------------------------------------------------------
# P9 corpus tasks — multi-register ALU64_X
# ---------------------------------------------------------------------------

# r1 += 1 (ADD K dst=r1); r0 += r1 (ADD X dst=r0 src=r1); EXIT
_R1_ADD1_R0_ADD_R1 = bytes([
    0x07, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r1 += 1
    0x0f, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 += r1
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r2 *= r3 (MUL X dst=r2 src=r3); EXIT
_R2_MUL_R3 = bytes([
    0x2f, 0x32, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r2 *= r3
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 -= r0 (SUB X self-zeroes); EXIT
_R0_SUB_SELF = bytes([
    0x1f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 -= r0
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP9Corpus:
    def test_multi_reg_add_chain_r0_eq_1_reachable(self):
        """r1 += 1; r0 += r1; EXIT. Witness: r0=0, r1=0 → r1=1, r0=1."""
        result = check(_spec("r0 == 1", max_insns=6), _R1_ADD1_R0_ADD_R1)
        assert result.verdict == "reachable"

    def test_multi_reg_add_chain_r1_eq_1_reachable(self):
        """r1 == 1 at halt: r1 was set to 1 by the first ADD K."""
        result = check(_spec("r1 == 1", max_insns=6), _R1_ADD1_R0_ADD_R1)
        assert result.verdict == "reachable"

    def test_mul_x_r2_eq_6_reachable(self):
        """r2 *= r3; EXIT. Solver picks r2=2, r3=3 → r2=6."""
        result = check(_spec("r2 == 6", max_insns=4), _R2_MUL_R3)
        assert result.verdict == "reachable"

    def test_mul_x_r2_eq_0_reachable(self):
        """r2 *= r3; EXIT. Witness: r2=0 → r2*r3=0 for any r3."""
        result = check(_spec("r2 == 0", max_insns=4), _R2_MUL_R3)
        assert result.verdict == "reachable"

    def test_sub_self_r0_eq_0_reachable(self):
        """r0 -= r0 always gives 0; r0==0 fires for any initial r0."""
        result = check(_spec("r0 == 0", max_insns=4), _R0_SUB_SELF)
        assert result.verdict == "reachable"

    def test_sub_self_r0_eq_1_unreachable(self):
        """r0 -= r0 always gives 0; r0==1 can never hold at halt."""
        result = check(_spec("r0 == 1", max_insns=4), _R0_SUB_SELF)
        assert result.verdict == "unreachable"


# ---------------------------------------------------------------------------
# P10 corpus tasks — DIV/OR/AND/MOD K immediate opcodes
# ---------------------------------------------------------------------------

# r0 /= 8  (DIV K, opcode=0x37, imm=8); EXIT
_R0_DIV8 = bytes([
    0x37, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00,  # r0 /= 8  (DIV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 |= 0x80  (OR K, opcode=0x47, imm=128); EXIT
_R0_OR_0X80 = bytes([
    0x47, 0x00, 0x00, 0x00, 0x80, 0x00, 0x00, 0x00,  # r0 |= 0x80  (OR K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 &= 0xf  (AND K, opcode=0x57, imm=15); EXIT
_R0_AND_0XF = bytes([
    0x57, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,  # r0 &= 0xf  (AND K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 %= 3  (MOD K, opcode=0x97, imm=3); EXIT
_R0_MOD3 = bytes([
    0x97, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r0 %= 3  (MOD K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP10Corpus:
    def test_div_k_r0_eq_3_reachable(self):
        """r0 /= 8; EXIT. Solver finds r0=24 → 24//8=3."""
        result = check(_spec("r0 == 3", max_insns=4), _R0_DIV8)
        assert result.verdict == "reachable"

    def test_div_k_r0_eq_0_reachable(self):
        """r0 /= 8; EXIT. Witness: initial r0=0 → 0//8=0."""
        result = check(_spec("r0 == 0", max_insns=4), _R0_DIV8)
        assert result.verdict == "reachable"

    def test_or_k_r0_eq_128_reachable(self):
        """r0 |= 0x80; EXIT. Witness: initial r0=0 → 0|0x80=128."""
        result = check(_spec("r0 == 128", max_insns=4), _R0_OR_0X80)
        assert result.verdict == "reachable"

    def test_or_k_r0_eq_0_unreachable(self):
        """r0 |= 0x80 always sets bit 7; result ≥ 128, so r0==0 is unreachable."""
        result = check(_spec("r0 == 0", max_insns=4), _R0_OR_0X80)
        assert result.verdict == "unreachable"

    def test_and_k_r0_eq_15_reachable(self):
        """r0 &= 0xf; EXIT. Witness: initial r0=15 → 15&0xf=15."""
        result = check(_spec("r0 == 15", max_insns=4), _R0_AND_0XF)
        assert result.verdict == "reachable"

    def test_and_k_r0_eq_16_unreachable(self):
        """r0 &= 0xf: result is at most 0xf=15; r0==16 can never fire."""
        result = check(_spec("r0 == 16", max_insns=4), _R0_AND_0XF)
        assert result.verdict == "unreachable"

    def test_mod_k_r0_eq_2_reachable(self):
        """r0 %= 3; EXIT. Witness: initial r0=2 → 2%3=2."""
        result = check(_spec("r0 == 2", max_insns=4), _R0_MOD3)
        assert result.verdict == "reachable"

    def test_mod_k_r0_eq_3_unreachable(self):
        """r0 %= 3: result ∈ {0,1,2}; r0==3 can never hold at halt."""
        result = check(_spec("r0 == 3", max_insns=4), _R0_MOD3)
        assert result.verdict == "unreachable"


# ---------------------------------------------------------------------------
# P11 corpus tasks — LSH/RSH/ARSH K shift opcodes
# ---------------------------------------------------------------------------

# r0 <<= 2  (LSH K, opcode=0x67, imm=2); EXIT
_R0_LSH2 = bytes([
    0x67, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,  # r0 <<= 2  (LSH K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 >>= 1  (RSH K, opcode=0x77, imm=1); EXIT
_R0_RSH1 = bytes([
    0x77, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 >>= 1  (RSH K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 s>>= 1  (ARSH K, opcode=0xc7, imm=1); EXIT
_R0_ARSH1 = bytes([
    0xc7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 s>>= 1  (ARSH K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP11Corpus:
    def test_lsh_k_r0_eq_4_reachable(self):
        """r0 <<= 2; EXIT. Solver finds initial r0=1 → 1<<2=4."""
        result = check(_spec("r0 == 4", max_insns=4), _R0_LSH2)
        assert result.verdict == "reachable"

    def test_lsh_k_r0_eq_3_unreachable(self):
        """r0 <<= 2 zeros bits 0–1; result is always divisible by 4, so r0==3 unreachable."""
        result = check(_spec("r0 == 3", max_insns=4), _R0_LSH2)
        assert result.verdict == "unreachable"

    def test_lsh_k_r0_eq_0_reachable(self):
        """r0 <<= 2; EXIT. Witness: initial r0=0 → 0<<2=0."""
        result = check(_spec("r0 == 0", max_insns=4), _R0_LSH2)
        assert result.verdict == "reachable"

    def test_rsh_k_r0_eq_4_reachable(self):
        """r0 >>= 1; EXIT. Solver finds initial r0=8 → 8>>1=4."""
        result = check(_spec("r0 == 4", max_insns=4), _R0_RSH1)
        assert result.verdict == "reachable"

    def test_arsh_k_r0_eq_1_reachable(self):
        """r0 s>>= 1; EXIT. Witness: initial r0=2 → 2 s>>1=1."""
        result = check(_spec("r0 == 1", max_insns=4), _R0_ARSH1)
        assert result.verdict == "reachable"

    def test_arsh_k_sign_extension_neg1_reachable(self):
        """r0 s>>= 1; EXIT. ARSH of -1 stays -1 (sign bit replicated).
        Witness: initial r0=0xFFFFFFFFFFFFFFFF → ARSH 1 → 0xFFFFFFFFFFFFFFFF."""
        result = check(_spec("r0 == 0xffffffffffffffff", max_insns=4), _R0_ARSH1)
        assert result.verdict == "reachable"


# ---------------------------------------------------------------------------
# P12 corpus tasks — NEG and MOV opcodes
# ---------------------------------------------------------------------------

# r0 = -r0  (NEG K, opcode=0x87); EXIT
_R0_NEG = bytes([
    0x87, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = -r0  (NEG)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 42  (MOV K, opcode=0xb7, imm=42); EXIT
_R0_MOV_K42 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0 = 42  (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = r1  (MOV X, opcode=0xbf, dst=r0, src=r1); EXIT
_R0_MOV_X_R1 = bytes([
    0xbf, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = r1  (MOV X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP12Corpus:
    def test_neg_r0_eq_0_reachable(self):
        """r0 = -r0; EXIT. Witness: initial r0=0 → neg(0)=0."""
        result = check(_spec("r0 == 0", max_insns=4), _R0_NEG)
        assert result.verdict == "reachable"

    def test_neg_r0_eq_1_reachable(self):
        """r0 = -r0; EXIT. Witness: initial r0=0xFFFFFFFFFFFFFFFF → neg(-1)=1."""
        result = check(_spec("r0 == 1", max_insns=4), _R0_NEG)
        assert result.verdict == "reachable"

    def test_neg_r0_eq_5_reachable(self):
        """r0 = -r0; EXIT. Witness: solver finds initial r0 such that -r0==5,
        i.e. r0=2^64-5=0xFFFFFFFFFFFFFFFB."""
        result = check(_spec("r0 == 5", max_insns=4), _R0_NEG)
        assert result.verdict == "reachable"

    def test_mov_k_r0_eq_42_reachable(self):
        """r0 = 42; EXIT. MOV K always sets r0=42; property fires for any initial r0."""
        result = check(_spec("r0 == 42", max_insns=4), _R0_MOV_K42)
        assert result.verdict == "reachable"

    def test_mov_k_r0_eq_41_unreachable(self):
        """r0 = 42; EXIT. MOV K pins r0 to exactly 42; r0==41 can never hold."""
        result = check(_spec("r0 == 41", max_insns=4), _R0_MOV_K42)
        assert result.verdict == "unreachable"

    def test_mov_x_r0_eq_7_reachable(self):
        """r0 = r1; EXIT. Witness: initial r1=7 → r0=7 at halt."""
        result = check(_spec("r0 == 7", max_insns=4), _R0_MOV_X_R1)
        assert result.verdict == "reachable"


# ---------------------------------------------------------------------------
# P13 corpus tasks — multi-instruction programs (NEG/MOV + branches)
# ---------------------------------------------------------------------------

# r0=5; r0=-r0; EXIT  (MOV K + NEG → deterministic -5)
_MOV5_NEG = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0x87, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = -r0  (NEG)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0=42; r1=r0; JEQ r1,42,+1; r0=0; EXIT  (JEQ always taken)
_MOV42_MOVX_JEQ_MOV0 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0 = 42
    0xbf, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r1 = r0
    0x15, 0x01, 0x01, 0x00, 0x2a, 0x00, 0x00, 0x00,  # JEQ r1, 42, +1
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0  (skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0=1; JNE r0,1,+1; r0=99; EXIT  (JNE not taken, falls through)
_MOV1_JNE_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1
    0x55, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JNE r0, 1, +1
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP13Corpus:
    def test_mov5_neg_r0_eq_neg5_reachable(self):
        """r0=5; r0=-r0; EXIT. MOV K+NEG is deterministic: r0=0xFFFFFFFFFFFFFFFB."""
        result = check(_spec("r0 == 0xfffffffffffffffb", max_insns=6), _MOV5_NEG)
        assert result.verdict == "reachable"

    def test_mov5_neg_r0_eq_5_unreachable(self):
        """r0=5; r0=-r0; EXIT. neg(-5)≠5 in uint64, so r0==5 is unreachable."""
        result = check(_spec("r0 == 5", max_insns=6), _MOV5_NEG)
        assert result.verdict == "unreachable"

    def test_mov42_movx_jeq_r0_eq_42_reachable(self):
        """r0=42; r1=r0; JEQ r1,42,+1; r0=0; EXIT.
        JEQ always taken (r1==42), so MOV K r0=0 is skipped; r0 stays 42."""
        result = check(_spec("r0 == 42", max_insns=10), _MOV42_MOVX_JEQ_MOV0)
        assert result.verdict == "reachable"

    def test_mov42_movx_jeq_r0_eq_0_unreachable(self):
        """Same program: r0==0 unreachable because the zeroing insn is always skipped."""
        result = check(_spec("r0 == 0", max_insns=10), _MOV42_MOVX_JEQ_MOV0)
        assert result.verdict == "unreachable"

    def test_mov1_jne_not_taken_r0_eq_99_reachable(self):
        """r0=1; JNE r0,1,+1; r0=99; EXIT.
        JNE not taken (r0==1), falls through to MOV K r0=99."""
        result = check(_spec("r0 == 99", max_insns=8), _MOV1_JNE_MOV99)
        assert result.verdict == "reachable"
