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

    def test_corpus_has_hundredsixtyone_tasks(self):
        h = _load_harness()
        assert len(h.CORPUS) == 161

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
        # P15 signed vs unsigned boundary
        assert "seed/neg1_jlt1_mov100_exit_r0_eq_100" in ids
        assert "seed/neg1_jslt1_mov100_exit_r0_eq_100_unreachable" in ids
        assert "seed/neg1_jgt0_mov0_exit_r0_eq_0_unreachable" in ids
        assert "seed/neg1_jsgt0_mov0_exit_r0_eq_0" in ids
        # P16 JLE/JSLE/JSGE signed vs unsigned boundary
        assert "seed/neg1_jle0_mov50_exit_r0_eq_50" in ids
        assert "seed/neg1_jsle0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jle_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jsle_neg2_mov50_exit_r0_eq_50" in ids
        assert "seed/neg1_jsge0_mov0_exit_r0_eq_0" in ids
        assert "seed/neg1_jsge_neg2_mov0_exit_r0_eq_0_unreachable" in ids
        # P17 JGE unsigned corpus
        assert "seed/neg1_jge0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/zero_jge1_mov50_exit_r0_eq_50" in ids
        assert "seed/neg1_jge_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg2_jge_neg1_mov50_exit_r0_eq_50" in ids
        # P18 JNE corpus
        assert "seed/five_jne5_mov99_exit_r0_eq_99" in ids
        assert "seed/five_jne6_mov99_exit_r0_eq_99_unreachable" in ids
        assert "seed/zero_jne0_mov99_exit_r0_eq_99" in ids
        assert "seed/neg1_jne0_mov99_exit_r0_eq_99_unreachable" in ids
        # P19 JSET corpus
        assert "seed/ten_jset2_mov99_exit_r0_eq_99_unreachable" in ids
        assert "seed/ten_jset5_mov99_exit_r0_eq_99" in ids
        assert "seed/ff_jset0f_mov99_exit_r0_eq_99_unreachable" in ids
        assert "seed/f0_jset0f_mov99_exit_r0_eq_99" in ids
        # P20 JGT boundary corpus
        assert "seed/five_jgt5_mov50_exit_r0_eq_50" in ids
        assert "seed/six_jgt5_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jgt_neg2_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg2_jgt_neg1_mov50_exit_r0_eq_50" in ids
        # P21 JLT boundary corpus
        assert "seed/five_jlt5_mov50_exit_r0_eq_50" in ids
        assert "seed/four_jlt5_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg2_jlt_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jlt_neg2_mov50_exit_r0_eq_50" in ids
        # P22 JSLT signed boundary corpus
        assert "seed/neg1_jslt_neg1_mov50_exit_r0_eq_50" in ids
        assert "seed/neg2_jslt_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jslt0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jslt_neg2_mov50_exit_r0_eq_50" in ids
        # P23 JSGT signed boundary corpus
        assert "seed/neg1_jsgt_neg1_mov50_exit_r0_eq_50" in ids
        assert "seed/neg1_jsgt_neg2_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/zero_jsgt_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg2_jsgt_neg1_mov50_exit_r0_eq_50" in ids
        # P24 JSLE signed boundary corpus
        assert "seed/neg1_jsle_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg2_jsle_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/zero_jsle0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/zero_jsle_neg1_mov50_exit_r0_eq_50" in ids
        # P25 JSGE signed boundary corpus
        assert "seed/neg1_jsge_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg2_jsge_neg1_mov50_exit_r0_eq_50" in ids
        assert "seed/zero_jsge0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/zero_jsge1_mov50_exit_r0_eq_50" in ids
        # P26 JLE unsigned boundary corpus
        assert "seed/zero_jle0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/one_jle0_mov50_exit_r0_eq_50" in ids
        assert "seed/neg2_jle_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jle_neg2_mov50_exit_r0_eq_50" in ids
        # P27 JGT unsigned boundary corpus
        assert "seed/zero_jgt0_mov50_exit_r0_eq_50" in ids
        assert "seed/one_jgt0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jgt_neg1_mov50_exit_r0_eq_50" in ids
        assert "seed/zero_jgt_neg1_mov50_exit_r0_eq_50" in ids
        # P28 JLT unsigned boundary corpus
        assert "seed/zero_jlt0_mov50_exit_r0_eq_50" in ids
        assert "seed/one_jlt2_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jlt_neg1_mov50_exit_r0_eq_50" in ids
        assert "seed/neg1_jlt0_mov50_exit_r0_eq_50" in ids
        # P29 JGE unsigned boundary corpus
        assert "seed/zero_jge0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/one_jge0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jge_neg2_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/zero_jge_neg1_mov50_exit_r0_eq_50" in ids
        # P30 JEQ boundary corpus
        assert "seed/zero_jeq0_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/one_jeq0_mov50_exit_r0_eq_50" in ids
        assert "seed/neg1_jeq_neg1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/neg1_jeq0_mov50_exit_r0_eq_50" in ids
        # P31 JNE additional boundary corpus
        assert "seed/one_jne1_mov99_exit_r0_eq_99" in ids
        assert "seed/zero_jne1_mov99_exit_r0_eq_99_unreachable" in ids
        assert "seed/neg1_jne_neg1_mov99_exit_r0_eq_99" in ids
        assert "seed/neg1_jne1_mov99_exit_r0_eq_99_unreachable" in ids
        # P32 JSET additional boundary corpus
        assert "seed/one_jset1_mov99_exit_r0_eq_99_unreachable" in ids
        assert "seed/one_jset2_mov99_exit_r0_eq_99" in ids
        assert "seed/neg1_jset_neg1_mov99_exit_r0_eq_99_unreachable" in ids
        assert "seed/zero_jset1_mov99_exit_r0_eq_99" in ids
        # P33 JA forward-skip and chain corpus
        assert "seed/mov1_ja1_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/mov1_ja0_mov50_exit_r0_eq_50" in ids
        assert "seed/mov1_ja2_mov50_exit_r0_eq_50_unreachable" in ids
        assert "seed/mov1_ja_chain_mov50_exit_r0_eq_50_unreachable" in ids
        # P34 ALU64 K arithmetic boundary corpus
        assert "seed/neg1_add1_exit_r0_eq_0" in ids
        assert "seed/five_sub3_exit_r0_eq_2" in ids
        assert "seed/zero_sub1_exit_r0_eq_neg1" in ids
        assert "seed/twentyone_mul2_exit_r0_eq_42" in ids
        # P35 ALU32 K zero-extension and overflow corpus
        assert "seed/neg1_mov32_5_exit_r0_eq_5" in ids
        assert "seed/neg1_mov32_5_exit_r0_eq_neg1_unreachable" in ids
        assert "seed/mov32_neg1_add32_1_exit_r0_eq_0" in ids
        assert "seed/neg1_add32_0_exit_r0_eq_4294967295" in ids
        # P36 ALU32 K subtraction and multiplication corpus
        assert "seed/five_sub32_3_exit_r0_eq_2" in ids
        assert "seed/zero32_sub32_1_exit_r0_eq_4294967295" in ids
        assert "seed/twentyone_mul32_2_exit_r0_eq_42" in ids
        assert "seed/neg1_mov32_21_mul32_2_exit_r0_eq_42" in ids
        # P37 ALU32/ALU64 K division and modulo corpus
        assert "seed/fortytwo_div32_6_exit_r0_eq_7" in ids
        assert "seed/thirtytwo_div32_4_exit_r0_eq_8" in ids
        assert "seed/fortytwo_div64_6_exit_r0_eq_7" in ids
        assert "seed/fortytwo_mod32_5_exit_r0_eq_2" in ids
        # P38 MOD64 K and bitwise ALU corpus
        assert "seed/fortytwo_mod64_5_exit_r0_eq_2" in ids
        assert "seed/fifteen_or64_48_exit_r0_eq_63" in ids
        assert "seed/twofiftyfive_and64_15_exit_r0_eq_15" in ids
        assert "seed/onesixtyfive_xor64_90_exit_r0_eq_255" in ids
        # P39 bitwise ALU32 and LSH64 K corpus
        assert "seed/fifteen_or32_48_exit_r0_eq_63" in ids
        assert "seed/twofiftyfive_and32_15_exit_r0_eq_15" in ids
        assert "seed/onesixtyfive_xor32_90_exit_r0_eq_255" in ids
        assert "seed/one_lsh64_4_exit_r0_eq_16" in ids
        # P40 RSH64 K, ARSH64 K, LSH32 K, RSH32 K corpus
        assert "seed/sixtyfour_rsh64_3_exit_r0_eq_8" in ids
        assert "seed/neg16_arsh64_2_exit_r0_eq_neg4" in ids
        assert "seed/one_lsh32_3_exit_r0_eq_8" in ids
        assert "seed/onetwentyeight_rsh32_3_exit_r0_eq_16" in ids
        # P41 ARSH32 K and register-source (X) ALU corpus
        assert "seed/neg128_arsh32_2_exit_r0_eq_4294967264" in ids
        assert "seed/fortytwo_div64x_r1_6_exit_r0_eq_7" in ids
        assert "seed/fortytwo_mod64x_r1_5_exit_r0_eq_2" in ids
        assert "seed/ninetynine_mov64x_r1_42_exit_r0_eq_42" in ids
        # P42 register-source (X) bitwise and ARSH64 corpus
        assert "seed/fifteen_or64x_r1_48_exit_r0_eq_63" in ids
        assert "seed/twofiftyfive_and64x_r1_15_exit_r0_eq_15" in ids
        assert "seed/onesixtyfive_xor64x_r1_90_exit_r0_eq_255" in ids
        assert "seed/neg16_arsh64x_r1_2_exit_r0_eq_neg4" in ids
        # P43 register-source (X) shift corpus
        assert "seed/one_lsh64x_r1_4_exit_r0_eq_16" in ids
        assert "seed/sixtyfour_rsh64x_r1_3_exit_r0_eq_8" in ids
        assert "seed/one_lsh32x_r1_3_exit_r0_eq_8" in ids
        assert "seed/onetwentyeight_rsh32x_r1_3_exit_r0_eq_16" in ids
        # P44 ARSH32 X and JMP X (JEQ, JNE, JGT) corpus
        assert "seed/neg128_arsh32x_r1_2_exit_r0_eq_4294967264" in ids
        assert "seed/r0_42_r1_42_jeqx_taken_exit_r0_eq_42" in ids
        assert "seed/r0_10_r1_20_jnex_taken_exit_r0_eq_10" in ids
        assert "seed/r0_20_r1_10_jgtx_taken_exit_r0_eq_20" in ids
        # P45 JMP X (JGE, JSGT, JSGE, JLT) corpus
        assert "seed/r0_20_r1_20_jgex_taken_exit_r0_eq_20" in ids
        assert "seed/r0_5_r1_3_jsgtx_taken_exit_r0_eq_5" in ids
        assert "seed/r0_neg1_r1_neg1_jsgex_taken_exit_r0_eq_neg1" in ids
        assert "seed/r0_10_r1_20_jltx_taken_exit_r0_eq_10" in ids

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


# ---------------------------------------------------------------------------
# P14 corpus tasks — AND-conjunction property grammar
# ---------------------------------------------------------------------------

# r0=5; r1=7; EXIT  (two MOV K, deterministic independent registers)
_R0_5_R1_7 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0xb7, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00,  # r1 = 7    (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP14Corpus:
    def test_and_both_reachable(self):
        """r0=5; r1=7; EXIT. AND of two exact values both hold at halt."""
        result = check(_spec("r0 == 5 AND r1 == 7", max_insns=6), _R0_5_R1_7)
        assert result.verdict == "reachable"

    def test_and_second_conjunct_wrong_unreachable(self):
        """r0=5; r1=7; EXIT. r1 is always 7; AND with r1==99 never holds."""
        result = check(_spec("r0 == 5 AND r1 == 99", max_insns=6), _R0_5_R1_7)
        assert result.verdict == "unreachable"

    def test_and_exit_reached_with_reg_reachable(self):
        """r0=5; r1=7; EXIT. exit_reached AND r0==5 both hold at the halt point."""
        result = check(_spec("exit_reached AND r0 == 5", max_insns=6), _R0_5_R1_7)
        assert result.verdict == "reachable"

    def test_and_first_conjunct_wrong_unreachable(self):
        """r0=5; r1=7; EXIT. r0 is always 5; AND with r0==0 never holds."""
        result = check(_spec("r0 == 0 AND r1 == 7", max_insns=6), _R0_5_R1_7)
        assert result.verdict == "unreachable"


# ---------------------------------------------------------------------------
# P15 corpus tasks — JLT/JSLT/JGT/JSGT signed vs unsigned boundary
# ---------------------------------------------------------------------------
# All programs set r0 = 0xFFFFFFFFFFFFFFFF (= -1 signed, = UINT64_MAX unsigned)
# via MOV K imm=-1, then branch on a comparison that flips depending on
# whether the opcode treats the value as signed or unsigned.

# r0 = -1 (MOV K); JLT r0, 1, +1; r0 = 100; EXIT
_NEG1_JLT1_MOV100 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JLT r0, 1, +1  (unsigned, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00,  # r0 = 100 (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1 (MOV K); JSLT r0, 1, +1; r0 = 100; EXIT
_NEG1_JSLT1_MOV100 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JSLT r0, 1, +1 (signed, taken)
    0xb7, 0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00,  # r0 = 100 (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1 (MOV K); JGT r0, 0, +1; r0 = 0; EXIT
_NEG1_JGT0_MOV0 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGT r0, 0, +1  (unsigned, taken)
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1 (MOV K); JSGT r0, 0, +1; r0 = 0; EXIT
_NEG1_JSGT0_MOV0 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0x65, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSGT r0, 0, +1 (signed, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP15Corpus:
    def test_jlt_unsigned_not_taken_r0_eq_100_reachable(self):
        """r0=-1; JLT r0,1 unsigned: 0xFFFF...>=1, not taken → r0=100 executes."""
        result = check(_spec("r0 == 100", max_insns=8), _NEG1_JLT1_MOV100)
        assert result.verdict == "reachable"

    def test_jslt_signed_taken_r0_eq_100_unreachable(self):
        """r0=-1; JSLT r0,1 signed: -1<1, taken → r0=100 skipped → unreachable."""
        result = check(_spec("r0 == 100", max_insns=8), _NEG1_JSLT1_MOV100)
        assert result.verdict == "unreachable"

    def test_jgt_unsigned_taken_r0_eq_0_unreachable(self):
        """r0=-1; JGT r0,0 unsigned: 0xFFFF...>0, taken → r0=0 skipped → unreachable."""
        result = check(_spec("r0 == 0", max_insns=8), _NEG1_JGT0_MOV0)
        assert result.verdict == "unreachable"

    def test_jsgt_signed_not_taken_r0_eq_0_reachable(self):
        """r0=-1; JSGT r0,0 signed: -1 not > 0, not taken → r0=0 executes → reachable."""
        result = check(_spec("r0 == 0", max_insns=8), _NEG1_JSGT0_MOV0)
        assert result.verdict == "reachable"


# ---------------------------------------------------------------------------
# P16 corpus tasks — JLE/JSLE/JSGE signed vs unsigned boundary
# ---------------------------------------------------------------------------
# JLE (0xb5): unsigned ≤. JSLE (0xd5): signed ≤. JSGE (0x75): signed ≥.
# Key contrast: r0 = 0xFFFFFFFFFFFFFFFF is UINT64_MAX unsigned but -1 signed.

# r0 = -1 (MOV K); JLE r0, 0, +1; r0 = 50; EXIT
_NEG1_JLE0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLE r0, 0, +1  (unsigned, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50  (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1 (MOV K); JSLE r0, 0, +1; r0 = 50; EXIT
_NEG1_JSLE0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSLE r0, 0, +1 (signed, taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50  (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1 (MOV K); JLE r0, -1, +1; r0 = 50; EXIT
_NEG1_JLE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JLE r0, -1, +1 (unsigned: equal, taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50  (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1 (MOV K); JSLE r0, -2, +1; r0 = 50; EXIT
_NEG1_JSLE_NEG2_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JSLE r0, -2, +1 (signed, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50  (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1 (MOV K); JSGE r0, 0, +1; r0 = 0; EXIT
_NEG1_JSGE0_MOV0 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0x75, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSGE r0, 0, +1  (signed, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1 (MOV K); JSGE r0, -2, +1; r0 = 0; EXIT
_NEG1_JSGE_NEG2_MOV0 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV K)
    0x75, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JSGE r0, -2, +1 (signed, taken)
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP16Corpus:
    def test_jle_unsigned_not_taken_r0_eq_50_reachable(self):
        """r0=-1; JLE r0,0 unsigned: UINT64_MAX>0, not taken → r0=50 executes."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JLE0_MOV50)
        assert result.verdict == "reachable"

    def test_jsle_signed_taken_r0_eq_50_unreachable(self):
        """r0=-1; JSLE r0,0 signed: -1<=0, taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JSLE0_MOV50)
        assert result.verdict == "unreachable"

    def test_jle_unsigned_taken_equal_r0_eq_50_unreachable(self):
        """r0=-1; JLE r0,-1 unsigned: UINT64_MAX<=UINT64_MAX (equal), taken → r0=50 skipped."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JLE_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jsle_signed_not_taken_r0_eq_50_reachable(self):
        """r0=-1; JSLE r0,-2 signed: -1<=-2? No, not taken → r0=50 executes."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JSLE_NEG2_MOV50)
        assert result.verdict == "reachable"

    def test_jsge_signed_not_taken_r0_eq_0_reachable(self):
        """r0=-1; JSGE r0,0 signed: -1>=0? No, not taken → r0=0 executes."""
        result = check(_spec("r0 == 0", max_insns=8), _NEG1_JSGE0_MOV0)
        assert result.verdict == "reachable"

    def test_jsge_signed_taken_r0_eq_0_unreachable(self):
        """r0=-1; JSGE r0,-2 signed: -1>=-2, taken → r0=0 skipped → unreachable."""
        result = check(_spec("r0 == 0", max_insns=8), _NEG1_JSGE_NEG2_MOV0)
        assert result.verdict == "unreachable"


# P17 corpus tasks — JGE unsigned, contrasting with JSGE signed (P16).
# JGE K opcode = JMP(0x05) | JGE(0x30) | K(0x00) = 0x35.

_NEG1_JGE0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x35, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGE r0, 0, +1 (unsigned, taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JGE1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x35, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JGE r0, 1, +1 (unsigned, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JGE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x35, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGE r0, -1, +1 (unsigned: equal, taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG2_JGE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0x35, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGE r0, -1, +1 (unsigned, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP17Corpus:
    def test_jge_unsigned_taken_r0_eq_50_unreachable(self):
        """r0=-1; JGE r0,0 unsigned: UINT64_MAX>=0, taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JGE0_MOV50)
        assert result.verdict == "unreachable"

    def test_jge_unsigned_not_taken_r0_eq_50_reachable(self):
        """r0=0; JGE r0,1 unsigned: 0>=1? No, not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JGE1_MOV50)
        assert result.verdict == "reachable"

    def test_jge_unsigned_taken_equal_r0_eq_50_unreachable(self):
        """r0=-1; JGE r0,-1 unsigned: UINT64_MAX>=UINT64_MAX (equal), taken → r0=50 skipped."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JGE_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jge_unsigned_not_taken_below_r0_eq_50_reachable(self):
        """r0=-2; JGE r0,-1 unsigned: UINT64_MAX-1>=UINT64_MAX? No, not taken → r0=50 executes."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG2_JGE_NEG1_MOV50)
        assert result.verdict == "reachable"


# P18 corpus tasks — JNE (not-equal). JNE K opcode = 0x55. No signed/unsigned distinction.

_FIVE_JNE5_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JNE r0, 5, +1 (not taken: 5==5)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_FIVE_JNE6_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x06, 0x00, 0x00, 0x00,  # JNE r0, 6, +1 (taken: 5!=6)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JNE0_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JNE r0, 0, +1 (not taken: 0==0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JNE0_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JNE r0, 0, +1 (taken: UINT64_MAX!=0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP18Corpus:
    def test_jne_not_taken_equal_r0_eq_99_reachable(self):
        """r0=5; JNE r0,5: 5!=5? No, not taken → r0=99 executes → reachable."""
        result = check(_spec("r0 == 99", max_insns=8), _FIVE_JNE5_MOV99)
        assert result.verdict == "reachable"

    def test_jne_taken_unequal_r0_eq_99_unreachable(self):
        """r0=5; JNE r0,6: 5!=6? Yes, taken → r0=99 skipped → unreachable."""
        result = check(_spec("r0 == 99", max_insns=8), _FIVE_JNE6_MOV99)
        assert result.verdict == "unreachable"

    def test_jne_not_taken_zero_r0_eq_99_reachable(self):
        """r0=0; JNE r0,0: 0!=0? No, not taken → r0=99 executes → reachable."""
        result = check(_spec("r0 == 99", max_insns=8), _ZERO_JNE0_MOV99)
        assert result.verdict == "reachable"

    def test_jne_taken_uint64max_r0_eq_99_unreachable(self):
        """r0=-1; JNE r0,0: UINT64_MAX!=0? Yes, taken → r0=99 skipped → unreachable."""
        result = check(_spec("r0 == 99", max_insns=8), _NEG1_JNE0_MOV99)
        assert result.verdict == "unreachable"


# P19 corpus tasks — JSET (bitwise AND test). JSET K opcode = 0x45.
# Taken when (dst & src) != 0.

_TEN_JSET2_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x0a, 0x00, 0x00, 0x00,  # r0 = 10   (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00,  # JSET r0, 2, +1 (taken: 10&2=2)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_TEN_JSET5_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x0a, 0x00, 0x00, 0x00,  # r0 = 10   (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JSET r0, 5, +1 (not taken: 10&5=0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_FF_JSET0F_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00,  # r0 = 0xFF (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x0f, 0x00, 0x00, 0x00,  # JSET r0, 0x0F, +1 (taken: overlap)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_F0_JSET0F_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xf0, 0x00, 0x00, 0x00,  # r0 = 0xF0 (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x0f, 0x00, 0x00, 0x00,  # JSET r0, 0x0F, +1 (not taken: disjoint)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP19Corpus:
    def test_jset_taken_overlapping_bits_unreachable(self):
        """r0=0b1010; JSET r0,0b0010: bits overlap → taken → r0=99 skipped → unreachable."""
        result = check(_spec("r0 == 99", max_insns=8), _TEN_JSET2_MOV99)
        assert result.verdict == "unreachable"

    def test_jset_not_taken_disjoint_bits_reachable(self):
        """r0=0b1010; JSET r0,0b0101: no overlap → not taken → r0=99 executes → reachable."""
        result = check(_spec("r0 == 99", max_insns=8), _TEN_JSET5_MOV99)
        assert result.verdict == "reachable"

    def test_jset_taken_high_nibble_overlap_unreachable(self):
        """r0=0xFF; JSET r0,0x0F: low nibble overlaps → taken → r0=99 skipped → unreachable."""
        result = check(_spec("r0 == 99", max_insns=8), _FF_JSET0F_MOV99)
        assert result.verdict == "unreachable"

    def test_jset_not_taken_nibble_disjoint_reachable(self):
        """r0=0xF0; JSET r0,0x0F: high/low nibble disjoint → not taken → r0=99 executes."""
        result = check(_spec("r0 == 99", max_insns=8), _F0_JSET0F_MOV99)
        assert result.verdict == "reachable"


# P20 corpus tasks — JGT boundary cases. JGT K opcode = 0x25 (strict unsigned >).

_FIVE_JGT5_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JGT r0, 5, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_SIX_JGT5_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x00,  # r0 = 6    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JGT r0, 5, +1 (taken: 6>5)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JGT_NEG2_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x25, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JGT r0, -2, +1 (taken: UINT64_MAX > UINT64_MAX-1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG2_JGT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0x25, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGT r0, -1, +1 (not taken: UINT64_MAX-1 < UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP20Corpus:
    def test_jgt_not_taken_equal_reachable(self):
        """r0=5; JGT r0,5: strict >, 5>5 is false → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _FIVE_JGT5_MOV50)
        assert result.verdict == "reachable"

    def test_jgt_taken_strictly_greater_unreachable(self):
        """r0=6; JGT r0,5: 6>5 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _SIX_JGT5_MOV50)
        assert result.verdict == "unreachable"

    def test_jgt_taken_uint64max_wrap_unreachable(self):
        """r0=-1; JGT r0,-2 unsigned: UINT64_MAX > UINT64_MAX-1 → taken → r0=50 skipped."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JGT_NEG2_MOV50)
        assert result.verdict == "unreachable"

    def test_jgt_not_taken_below_uint64max_reachable(self):
        """r0=-2; JGT r0,-1 unsigned: UINT64_MAX-1 > UINT64_MAX? No → not taken → r0=50 executes."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG2_JGT_NEG1_MOV50)
        assert result.verdict == "reachable"


# P21 corpus tasks — JLT boundary cases. JLT K opcode = 0xA5 (strict unsigned <).

_FIVE_JLT5_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JLT r0, 5, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_FOUR_JLT5_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00,  # r0 = 4    (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JLT r0, 5, +1 (taken: 4<5)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG2_JLT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JLT r0, -1, +1 (taken: UINT64_MAX-1 < UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JLT_NEG2_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JLT r0, -2, +1 (not taken: UINT64_MAX > UINT64_MAX-1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP21Corpus:
    def test_jlt_not_taken_equal_reachable(self):
        """r0=5; JLT r0,5: strict <, 5<5 is false → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _FIVE_JLT5_MOV50)
        assert result.verdict == "reachable"

    def test_jlt_taken_strictly_less_unreachable(self):
        """r0=4; JLT r0,5: 4<5 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _FOUR_JLT5_MOV50)
        assert result.verdict == "unreachable"

    def test_jlt_taken_uint64max_minus1_unreachable(self):
        """r0=-2; JLT r0,-1 unsigned: UINT64_MAX-1 < UINT64_MAX → taken → r0=50 skipped."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG2_JLT_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jlt_not_taken_uint64max_reachable(self):
        """r0=-1; JLT r0,-2 unsigned: UINT64_MAX < UINT64_MAX-1? No → not taken → r0=50 executes."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JLT_NEG2_MOV50)
        assert result.verdict == "reachable"


# P22 corpus tasks — JSLT signed boundary cases. JSLT K opcode = 0xC5.

_NEG1_JSLT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLT r0, -1, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG2_JSLT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLT r0, -1, +1 (taken: -2 < -1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JSLT0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSLT r0, 0, +1 (taken: -1 < 0 signed)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JSLT_NEG2_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JSLT r0, -2, +1 (not taken: -1 > -2)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP22Corpus:
    def test_jslt_not_taken_equal_reachable(self):
        """r0=-1; JSLT r0,-1 signed: -1<-1? No (equal) → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JSLT_NEG1_MOV50)
        assert result.verdict == "reachable"

    def test_jslt_taken_neg2_lt_neg1_unreachable(self):
        """r0=-2; JSLT r0,-1 signed: -2<-1 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG2_JSLT_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jslt_taken_neg1_lt_zero_unreachable(self):
        """r0=-1; JSLT r0,0 signed: -1<0 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JSLT0_MOV50)
        assert result.verdict == "unreachable"

    def test_jslt_not_taken_neg1_gt_neg2_reachable(self):
        """r0=-1; JSLT r0,-2 signed: -1<-2? No (-1>-2) → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JSLT_NEG2_MOV50)
        assert result.verdict == "reachable"


# P23 corpus tasks — JSGT signed boundary cases. JSGT K opcode = 0x65.

_NEG1_JSGT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x65, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGT r0, -1, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JSGT_NEG2_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x65, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JSGT r0, -2, +1 (taken: -1 > -2)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JSGT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x65, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGT r0, -1, +1 (taken: 0 > -1 signed)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG2_JSGT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0x65, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGT r0, -1, +1 (not taken: -2 < -1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP23Corpus:
    def test_jsgt_not_taken_equal_reachable(self):
        """r0=-1; JSGT r0,-1 signed: -1>-1? No (equal) → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JSGT_NEG1_MOV50)
        assert result.verdict == "reachable"

    def test_jsgt_taken_neg1_gt_neg2_unreachable(self):
        """r0=-1; JSGT r0,-2 signed: -1>-2 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JSGT_NEG2_MOV50)
        assert result.verdict == "unreachable"

    def test_jsgt_taken_zero_gt_neg1_unreachable(self):
        """r0=0; JSGT r0,-1 signed: 0>-1 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JSGT_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jsgt_not_taken_neg2_lt_neg1_reachable(self):
        """r0=-2; JSGT r0,-1 signed: -2>-1? No → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG2_JSGT_NEG1_MOV50)
        assert result.verdict == "reachable"


# P24 corpus tasks — JSLE signed boundary cases. JSLE K opcode = 0xD5.
# P16 already has JSLE r0,0 (taken) and JSLE r0,-2 (not taken);
# P24 adds equal, strictly-less, zero-zero, and zero-gt-neg1 cases.

_NEG1_JSLE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLE r0, -1, +1 (taken: -1<=-1 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG2_JSLE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLE r0, -1, +1 (taken: -2<=-1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JSLE0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSLE r0, 0, +1 (taken: 0<=0 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JSLE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLE r0, -1, +1 (not taken: 0 > -1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP24Corpus:
    def test_jsle_taken_equal_unreachable(self):
        """r0=-1; JSLE r0,-1 signed: -1<=-1 (equal) → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JSLE_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jsle_taken_neg2_le_neg1_unreachable(self):
        """r0=-2; JSLE r0,-1 signed: -2<=-1 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG2_JSLE_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jsle_taken_zero_equal_unreachable(self):
        """r0=0; JSLE r0,0 signed: 0<=0 (equal) → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JSLE0_MOV50)
        assert result.verdict == "unreachable"

    def test_jsle_not_taken_zero_gt_neg1_reachable(self):
        """r0=0; JSLE r0,-1 signed: 0<=-1? No (0>-1) → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JSLE_NEG1_MOV50)
        assert result.verdict == "reachable"


# P25 corpus tasks — JSGE signed boundary cases. JSGE K opcode = 0x75.
# P16 already has JSGE r0,0 (not taken: -1>=0? No) and basic JSGE cases;
# P25 adds equal (neg-neg), strictly-less, zero-zero, and zero-lt-1 cases.

_NEG1_JSGE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x75, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGE r0, -1, +1 (taken: -1>=-1 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG2_JSGE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0x75, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGE r0, -1, +1 (not taken: -2 < -1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JSGE0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x75, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSGE r0, 0, +1 (taken: 0>=0 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JSGE1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x75, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JSGE r0, 1, +1 (not taken: 0 < 1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP25Corpus:
    def test_jsge_taken_equal_unreachable(self):
        """r0=-1; JSGE r0,-1 signed: -1>=-1 (equal) → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JSGE_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jsge_not_taken_neg2_lt_neg1_reachable(self):
        """r0=-2; JSGE r0,-1 signed: -2>=-1? No (-2<-1) → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG2_JSGE_NEG1_MOV50)
        assert result.verdict == "reachable"

    def test_jsge_taken_zero_equal_unreachable(self):
        """r0=0; JSGE r0,0 signed: 0>=0 (equal) → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JSGE0_MOV50)
        assert result.verdict == "unreachable"

    def test_jsge_not_taken_zero_lt_1_reachable(self):
        """r0=0; JSGE r0,1 signed: 0>=1? No (0<1) → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JSGE1_MOV50)
        assert result.verdict == "reachable"


# P26 corpus tasks — JLE unsigned boundary cases. JLE K opcode = 0xB5.
# P16 already has JLE r0,0 (UINT64_MAX <= 0? No) and JLE r0,-1 (equal, taken);
# P26 adds zero-zero equal, one-gt-zero not-taken, high-unsigned-taken, and
# high-unsigned-not-taken cases.

_ZERO_JLE0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLE r0, 0, +1 (taken: 0<=0 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ONE_JLE0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLE r0, 0, +1 (not taken: 1 > 0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG2_JLE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JLE r0, -1, +1 (taken: UINT64_MAX-1<=UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JLE_NEG2_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JLE r0, -2, +1 (not taken: UINT64_MAX>UINT64_MAX-1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP26Corpus:
    def test_jle_taken_zero_equal_unreachable(self):
        """r0=0; JLE r0,0 unsigned: 0<=0 (equal) → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JLE0_MOV50)
        assert result.verdict == "unreachable"

    def test_jle_not_taken_one_gt_zero_reachable(self):
        """r0=1; JLE r0,0 unsigned: 1<=0? No → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ONE_JLE0_MOV50)
        assert result.verdict == "reachable"

    def test_jle_taken_uint64max_minus1_le_uint64max_unreachable(self):
        """r0=-2 (UINT64_MAX-1); JLE r0,-1 (UINT64_MAX): UINT64_MAX-1<=UINT64_MAX → taken → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG2_JLE_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jle_not_taken_uint64max_gt_uint64max_minus1_reachable(self):
        """r0=-1 (UINT64_MAX); JLE r0,-2 (UINT64_MAX-1): UINT64_MAX<=UINT64_MAX-1? No → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JLE_NEG2_MOV50)
        assert result.verdict == "reachable"


# P27 corpus tasks — JGT unsigned boundary cases. JGT K opcode = 0x25.
# P15 added UINT64_MAX > 0 (taken); P20 added equal-at-5, strictly-greater-at-6,
# and high-unsigned pair. P27 adds zero-boundary equal (not taken), one-gt-zero
# (taken), UINT64_MAX equal (not taken), and unsigned sign-crossing (0 > UINT64_MAX?
# No — contrast with JSGT 0 > -1? Yes from P23).

_ZERO_JGT0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGT r0, 0, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ONE_JGT0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGT r0, 0, +1 (taken: 1 > 0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JGT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x25, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGT r0, -1, +1 (not taken: UINT64_MAX==UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JGT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGT r0, -1, +1 (not taken: 0 < UINT64_MAX unsigned)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP27Corpus:
    def test_jgt_not_taken_zero_equal_reachable(self):
        """r0=0; JGT r0,0 unsigned: 0>0? No (strict) → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JGT0_MOV50)
        assert result.verdict == "reachable"

    def test_jgt_taken_one_gt_zero_unreachable(self):
        """r0=1; JGT r0,0 unsigned: 1>0 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ONE_JGT0_MOV50)
        assert result.verdict == "unreachable"

    def test_jgt_not_taken_uint64max_equal_reachable(self):
        """r0=-1 (UINT64_MAX); JGT r0,-1 (UINT64_MAX): UINT64_MAX>UINT64_MAX? No → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JGT_NEG1_MOV50)
        assert result.verdict == "reachable"

    def test_jgt_not_taken_zero_vs_uint64max_reachable(self):
        """r0=0; JGT r0,-1 (UINT64_MAX): 0>UINT64_MAX unsigned? No → reachable (contrast JSGT 0>-1 signed: yes)."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JGT_NEG1_MOV50)
        assert result.verdict == "reachable"


# P28 corpus tasks — JLT unsigned boundary cases. JLT K opcode = 0xA5.
# P15 had UINT64_MAX < 1 (not taken); P21 added equal-at-5, strictly-less-at-4,
# and high-unsigned pair. P28 adds zero-boundary equal (not taken), one-lt-two
# (taken), UINT64_MAX equal (not taken), and unsigned sign-crossing (UINT64_MAX < 0?
# No — complement of JGT P27; contrast with JSLT UINT64_MAX < 0 signed? Yes).

_ZERO_JLT0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLT r0, 0, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ONE_JLT2_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00,  # JLT r0, 2, +1 (taken: 1 < 2)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JLT_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JLT r0, -1, +1 (not taken: UINT64_MAX==UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JLT0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLT r0, 0, +1 (not taken: UINT64_MAX > 0 unsigned)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP28Corpus:
    def test_jlt_not_taken_zero_equal_reachable(self):
        """r0=0; JLT r0,0 unsigned: 0<0? No (strict) → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JLT0_MOV50)
        assert result.verdict == "reachable"

    def test_jlt_taken_one_lt_two_unreachable(self):
        """r0=1; JLT r0,2 unsigned: 1<2 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ONE_JLT2_MOV50)
        assert result.verdict == "unreachable"

    def test_jlt_not_taken_uint64max_equal_reachable(self):
        """r0=-1 (UINT64_MAX); JLT r0,-1 (UINT64_MAX): UINT64_MAX<UINT64_MAX? No → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JLT_NEG1_MOV50)
        assert result.verdict == "reachable"

    def test_jlt_not_taken_uint64max_vs_zero_reachable(self):
        """r0=-1 (UINT64_MAX); JLT r0,0: UINT64_MAX<0 unsigned? No → reachable (contrast JSLT -1<0 signed: yes)."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JLT0_MOV50)
        assert result.verdict == "reachable"


# P29 corpus tasks — JGE unsigned boundary cases. JGE K opcode = 0x35.
# P17 added UINT64_MAX>=0 (taken), 0>=1 (not taken), UINT64_MAX>=UINT64_MAX equal
# (taken), UINT64_MAX-1>=UINT64_MAX (not taken). P29 adds zero-zero equal (taken),
# one-GE-zero (taken), UINT64_MAX>=UINT64_MAX-1 strictly-greater (taken), and the
# unsigned sign-crossing complement (0>=UINT64_MAX? No — contrast P17's UINT64_MAX>=0
# taken; contrast with JSGE 0>=-1 signed: yes from P25).

_ZERO_JGE0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x35, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGE r0, 0, +1 (taken: 0>=0 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ONE_JGE0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x35, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGE r0, 0, +1 (taken: 1>=0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JGE_NEG2_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x35, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JGE r0, -2, +1 (taken: UINT64_MAX>=UINT64_MAX-1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JGE_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x35, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGE r0, -1, +1 (not taken: 0 < UINT64_MAX unsigned)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP29Corpus:
    def test_jge_taken_zero_equal_unreachable(self):
        """r0=0; JGE r0,0 unsigned: 0>=0 (equal) → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JGE0_MOV50)
        assert result.verdict == "unreachable"

    def test_jge_taken_one_ge_zero_unreachable(self):
        """r0=1; JGE r0,0 unsigned: 1>=0 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ONE_JGE0_MOV50)
        assert result.verdict == "unreachable"

    def test_jge_taken_uint64max_ge_uint64max_minus1_unreachable(self):
        """r0=-1 (UINT64_MAX); JGE r0,-2 (UINT64_MAX-1): UINT64_MAX>=UINT64_MAX-1 → taken → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JGE_NEG2_MOV50)
        assert result.verdict == "unreachable"

    def test_jge_not_taken_zero_vs_uint64max_reachable(self):
        """r0=0; JGE r0,-1 (UINT64_MAX): 0>=UINT64_MAX unsigned? No → reachable (contrast JSGE 0>=-1 signed: yes)."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JGE_NEG1_MOV50)
        assert result.verdict == "reachable"


# P30 corpus tasks — JEQ boundary cases. JEQ K opcode = 0x15.
# P8 had complex JEQ programs; P30 adds clean boundary cases with the standard
# MOV K + JEQ + MOV K + EXIT structure. JEQ has no signed/unsigned distinction.

_ZERO_JEQ0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x15, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JEQ r0, 0, +1 (taken: 0==0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ONE_JEQ0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x15, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JEQ r0, 0, +1 (not taken: 1!=0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JEQ_NEG1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x15, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JEQ r0, -1, +1 (taken: UINT64_MAX==UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JEQ0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x15, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JEQ r0, 0, +1 (not taken: UINT64_MAX!=0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP30Corpus:
    def test_jeq_taken_zero_equal_unreachable(self):
        """r0=0; JEQ r0,0: 0==0 → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ZERO_JEQ0_MOV50)
        assert result.verdict == "unreachable"

    def test_jeq_not_taken_one_ne_zero_reachable(self):
        """r0=1; JEQ r0,0: 1==0? No → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _ONE_JEQ0_MOV50)
        assert result.verdict == "reachable"

    def test_jeq_taken_uint64max_equal_unreachable(self):
        """r0=-1 (UINT64_MAX); JEQ r0,-1: UINT64_MAX==UINT64_MAX → taken → r0=50 skipped → unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JEQ_NEG1_MOV50)
        assert result.verdict == "unreachable"

    def test_jeq_not_taken_uint64max_ne_zero_reachable(self):
        """r0=-1 (UINT64_MAX); JEQ r0,0: UINT64_MAX==0? No → not taken → r0=50 executes → reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _NEG1_JEQ0_MOV50)
        assert result.verdict == "reachable"


# P31 corpus tasks — JNE additional boundary cases. JNE K opcode = 0x55.
# P18 had: 5!=5 (not taken), 5!=6 (taken), 0!=0 (not taken), UINT64_MAX!=0 (taken).
# P31 adds: 1!=1 (not taken), 0!=1 (taken), UINT64_MAX!=UINT64_MAX (not taken),
# UINT64_MAX!=1 (taken). No signed/unsigned distinction.

_ONE_JNE1_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JNE r0, 1, +1 (not taken: 1==1)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JNE1_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JNE r0, 1, +1 (taken: 0!=1)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JNE_NEG1_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x55, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JNE r0, -1, +1 (not taken: UINT64_MAX==UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JNE1_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JNE r0, 1, +1 (taken: UINT64_MAX!=1)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP31Corpus:
    def test_jne_not_taken_one_equal_reachable(self):
        """r0=1; JNE r0,1: 1!=1? No → not taken → r0=99 executes → reachable."""
        result = check(_spec("r0 == 99", max_insns=8), _ONE_JNE1_MOV99)
        assert result.verdict == "reachable"

    def test_jne_taken_zero_ne_one_unreachable(self):
        """r0=0; JNE r0,1: 0!=1 → taken → r0=99 skipped → unreachable."""
        result = check(_spec("r0 == 99", max_insns=8), _ZERO_JNE1_MOV99)
        assert result.verdict == "unreachable"

    def test_jne_not_taken_uint64max_equal_reachable(self):
        """r0=-1 (UINT64_MAX); JNE r0,-1: UINT64_MAX!=UINT64_MAX? No → not taken → r0=99 executes → reachable."""
        result = check(_spec("r0 == 99", max_insns=8), _NEG1_JNE_NEG1_MOV99)
        assert result.verdict == "reachable"

    def test_jne_taken_uint64max_ne_one_unreachable(self):
        """r0=-1 (UINT64_MAX); JNE r0,1: UINT64_MAX!=1 → taken → r0=99 skipped → unreachable."""
        result = check(_spec("r0 == 99", max_insns=8), _NEG1_JNE1_MOV99)
        assert result.verdict == "unreachable"


# P32 corpus tasks — JSET additional boundary cases. JSET K opcode = 0x45.
# P19 had: 0b1010&0b0010 (taken), 0b1010&0b0101 (not taken), 0xFF&0x0F (taken),
# 0xF0&0x0F (not taken). P32 adds: single-bit match, adjacent-bit miss,
# UINT64_MAX self-AND, zero-operand miss.

_ONE_JSET1_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JSET r0, 1, +1 (taken: 1&1=1)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ONE_JSET2_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00,  # JSET r0, 2, +1 (not taken: 1&2=0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_NEG1_JSET_NEG1_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x45, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSET r0, -1, +1 (taken: UINT64_MAX&UINT64_MAX!=0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_ZERO_JSET1_MOV99 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JSET r0, 1, +1 (not taken: 0&1=0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


class TestP32Corpus:
    def test_jset_taken_single_bit_match_unreachable(self):
        """r0=1; JSET r0,1: 0b01&0b01=1≠0 → taken → r0=99 skipped → unreachable."""
        result = check(_spec("r0 == 99", max_insns=8), _ONE_JSET1_MOV99)
        assert result.verdict == "unreachable"

    def test_jset_not_taken_adjacent_bit_miss_reachable(self):
        """r0=1; JSET r0,2: 0b01&0b10=0 → not taken → r0=99 executes → reachable."""
        result = check(_spec("r0 == 99", max_insns=8), _ONE_JSET2_MOV99)
        assert result.verdict == "reachable"

    def test_jset_taken_uint64max_self_and_unreachable(self):
        """r0=-1 (UINT64_MAX); JSET r0,-1: UINT64_MAX&UINT64_MAX≠0 → taken → unreachable."""
        result = check(_spec("r0 == 99", max_insns=8), _NEG1_JSET_NEG1_MOV99)
        assert result.verdict == "unreachable"

    def test_jset_not_taken_zero_operand_reachable(self):
        """r0=0; JSET r0,1: 0&1=0 → not taken → r0=99 executes → reachable."""
        result = check(_spec("r0 == 99", max_insns=8), _ZERO_JSET1_MOV99)
        assert result.verdict == "reachable"


# P33 corpus tasks — JA forward-skip and chained-jump cases. JA opcode = 0x05.
# P8 had JA -1 self-loop (EXIT unreachable). P33 adds forward skips and chains.
# JA target = current_insn_index + 1 + offset (16-bit signed LE in bytes 2-3).

_MOV1_JA1_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x05, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JA +1 (skip next insn)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=1)
])

_MOV1_JA0_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # JA +0 (no-op: falls through)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, executed)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=50)
])

_MOV1_JA2_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x05, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,  # JA +2 (skip next 2 insns)
    0xb7, 0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00,  # r0 = 100  (MOV K, skipped)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=1)
])

_MOV1_JA_CHAIN_MOV50 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x05, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JA +1 (skip insn 2, land on insn 3)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped by first JA)
    0x05, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JA +1 (skip insn 4, land on insn 5)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped by second JA)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=1)
])


class TestP33Corpus:
    def test_ja_skip1_unreachable(self):
        """r0=1; JA +1 skips r0=50; EXIT with r0=1 → r0==50 unreachable."""
        result = check(_spec("r0 == 50", max_insns=8), _MOV1_JA1_MOV50)
        assert result.verdict == "unreachable"

    def test_ja_nop_reachable(self):
        """r0=1; JA +0 is no-op; r0=50 executes → r0==50 reachable."""
        result = check(_spec("r0 == 50", max_insns=8), _MOV1_JA0_MOV50)
        assert result.verdict == "reachable"

    def test_ja_skip2_unreachable(self):
        """r0=1; JA +2 skips r0=100 and r0=50; EXIT with r0=1 → r0==50 unreachable."""
        result = check(_spec("r0 == 50", max_insns=10), _MOV1_JA2_MOV50)
        assert result.verdict == "unreachable"

    def test_ja_chain2_unreachable(self):
        """r0=1; two-hop JA chain skips r0=50 and r0=99; EXIT with r0=1 → r0==50 unreachable."""
        result = check(_spec("r0 == 50", max_insns=12), _MOV1_JA_CHAIN_MOV50)
        assert result.verdict == "unreachable"


# P34 corpus tasks — ALU64 K arithmetic boundary cases.
# Adds SUB64 K and MUL64 K (only X variants existed), ADD64 overflow, SUB64 underflow.
# ALU64 K opcodes: ADD=0x07, SUB=0x17, MUL=0x27 (BPF_ALU64|op|BPF_K).

_NEG1_ADD1 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K = UINT64_MAX)
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1   (ADD64 K, wraps to 0)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

_FIVE_SUB3 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0x17, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r0 -= 3   (SUB64 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=2)
])

_ZERO_SUB1 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x17, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 -= 1   (SUB64 K, underflows to UINT64_MAX)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=-1)
])

_TWENTYONE_MUL2 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x15, 0x00, 0x00, 0x00,  # r0 = 21   (MOV K)
    0x27, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,  # r0 *= 2   (MUL64 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=42)
])

_NEG1_MOV32_K5 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV64 K = UINT64_MAX)
    0xb4, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0_32 = 5 (MOV32 K, zeroes upper)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=5)
])

_MOV32_NEG1_ADD32_K1 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0_32 = 0xFFFFFFFF (MOV32 K -1)
    0x04, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0_32 += 1 (ADD32 K, wraps to 0)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=0)
])

_NEG1_ADD32_K0 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV64 K = UINT64_MAX)
    0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0_32 += 0 (ADD32 K, zeroes upper)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=4294967295)
])


class TestP34Corpus:
    def test_add64_overflow_wrap_reachable(self):
        """r0=-1 (UINT64_MAX); r0+=1 → ADD64 overflow wraps to 0 → r0==0 reachable."""
        result = check(_spec("r0 == 0", max_insns=4), _NEG1_ADD1)
        assert result.verdict == "reachable"

    def test_sub64_basic_reachable(self):
        """r0=5; r0-=3 → r0==2 reachable (first SUB64 K corpus task)."""
        result = check(_spec("r0 == 2", max_insns=4), _FIVE_SUB3)
        assert result.verdict == "reachable"

    def test_sub64_underflow_reachable(self):
        """r0=0; r0-=1 → SUB64 underflow wraps to UINT64_MAX (== -1 signed) → r0==-1 reachable."""
        result = check(_spec("r0 == -1", max_insns=4), _ZERO_SUB1)
        assert result.verdict == "reachable"

    def test_mul64_basic_reachable(self):
        """r0=21; r0*=2 → r0==42 reachable (first MUL64 K corpus task)."""
        result = check(_spec("r0 == 42", max_insns=4), _TWENTYONE_MUL2)
        assert result.verdict == "reachable"


class TestP35Corpus:
    def test_mov32_zeroes_upper_reachable(self):
        """r0=-1; MOV32 K 5 → upper 32 bits cleared → r0==5 reachable."""
        result = check(_spec("r0 == 5", max_insns=4), _NEG1_MOV32_K5)
        assert result.verdict == "reachable"

    def test_mov32_zeroes_upper_neg1_unreachable(self):
        """r0=-1; MOV32 K 5 clears upper bits → r0==-1 unreachable (r0 is now 5)."""
        result = check(_spec("r0 == -1", max_insns=4), _NEG1_MOV32_K5)
        assert result.verdict == "unreachable"

    def test_add32_overflow_wraps_reachable(self):
        """r0_32=0xFFFFFFFF; ADD32 K 1 wraps to 0, zero-extended → r0==0 reachable."""
        result = check(_spec("r0 == 0", max_insns=4), _MOV32_NEG1_ADD32_K1)
        assert result.verdict == "reachable"

    def test_add32_zeroes_upper_reachable(self):
        """r0=UINT64_MAX; ADD32 K 0 zeroes upper 32 bits → r0==4294967295 reachable."""
        result = check(_spec("r0 == 4294967295", max_insns=4), _NEG1_ADD32_K0)
        assert result.verdict == "reachable"


_FIVE_SUB32_K3 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV64 K)
    0x14, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r0_32 -= 3 (SUB32 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=2)
])

_ZERO32_SUB32_K1 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0_32 = 0 (MOV32 K 0)
    0x14, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0_32 -= 1 (SUB32 K, wraps to 0xFFFFFFFF)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=4294967295)
])

_TWENTYONE_MUL32_K2 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x15, 0x00, 0x00, 0x00,  # r0_32 = 21 (MOV32 K)
    0x24, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,  # r0_32 *= 2 (MUL32 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=42)
])

_NEG1_MOV32_21_MUL32_K2 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV64 K = UINT64_MAX)
    0xb4, 0x00, 0x00, 0x00, 0x15, 0x00, 0x00, 0x00,  # r0_32 = 21 (MOV32 K, zeroes upper)
    0x24, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,  # r0_32 *= 2 (MUL32 K, result=42)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=42)
])


class TestP36Corpus:
    def test_sub32_basic_reachable(self):
        """r0=5; SUB32 K 3 → 5-3=2, zero-extended → r0==2 reachable."""
        result = check(_spec("r0 == 2", max_insns=4), _FIVE_SUB32_K3)
        assert result.verdict == "reachable"

    def test_sub32_underflow_reachable(self):
        """r0_32=0; SUB32 K 1 underflows → 0xFFFFFFFF, zero-extended → r0==4294967295 reachable."""
        result = check(_spec("r0 == 4294967295", max_insns=4), _ZERO32_SUB32_K1)
        assert result.verdict == "reachable"

    def test_mul32_basic_reachable(self):
        """r0_32=21; MUL32 K 2 → 42, zero-extended → r0==42 reachable."""
        result = check(_spec("r0 == 42", max_insns=4), _TWENTYONE_MUL32_K2)
        assert result.verdict == "reachable"

    def test_mul32_upper_clear_reachable(self):
        """r0=UINT64_MAX; MOV32 K 21 clears upper; MUL32 K 2 → 42 → r0==42 reachable."""
        result = check(_spec("r0 == 42", max_insns=5), _NEG1_MOV32_21_MUL32_K2)
        assert result.verdict == "reachable"


_FORTYTWO_DIV32_K6 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0_32 = 42 (MOV32 K)
    0x34, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x00,  # r0_32 ÷= 6 (DIV32 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=7)
])

_THIRTYTWO_DIV32_K4 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x20, 0x00, 0x00, 0x00,  # r0_32 = 32 (MOV32 K)
    0x34, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00,  # r0_32 ÷= 4 (DIV32 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=8)
])

_FORTYTWO_DIV64_K6 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0 = 42   (MOV64 K)
    0x37, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x00,  # r0 ÷= 6   (DIV64 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=7)
])

_FORTYTWO_MOD32_K5 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0_32 = 42 (MOV32 K)
    0x94, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0_32 %= 5 (MOD32 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=2)
])


class TestP37Corpus:
    def test_div32_basic_reachable(self):
        """r0_32=42; DIV32 K 6 → 42/6=7, zero-extended → r0==7 reachable."""
        result = check(_spec("r0 == 7", max_insns=4), _FORTYTWO_DIV32_K6)
        assert result.verdict == "reachable"

    def test_div32_power_of_two_reachable(self):
        """r0_32=32; DIV32 K 4 (power-of-two) → 32/4=8, zero-extended → r0==8 reachable."""
        result = check(_spec("r0 == 8", max_insns=4), _THIRTYTWO_DIV32_K4)
        assert result.verdict == "reachable"

    def test_div64_basic_reachable(self):
        """r0=42; DIV64 K 6 → 42/6=7 → r0==7 reachable (64-bit division)."""
        result = check(_spec("r0 == 7", max_insns=4), _FORTYTWO_DIV64_K6)
        assert result.verdict == "reachable"

    def test_mod32_basic_reachable(self):
        """r0_32=42; MOD32 K 5 → 42%5=2, zero-extended → r0==2 reachable."""
        result = check(_spec("r0 == 2", max_insns=4), _FORTYTWO_MOD32_K5)
        assert result.verdict == "reachable"


_FORTYTWO_MOD64_K5 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0 = 42  (MOV64 K)
    0x97, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 %= 5  (MOD64 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=2)
])

_FIFTEEN_OR64_K48 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,  # r0 = 15  (MOV64 K, 0x0f)
    0x47, 0x00, 0x00, 0x00, 0x30, 0x00, 0x00, 0x00,  # r0 |= 48 (OR64 K, 0x30)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=63)
])

_TWOFIFTYFIVE_AND64_K15 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00,  # r0 = 255 (MOV64 K, 0xff)
    0x57, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,  # r0 &= 15 (AND64 K, 0x0f)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=15)
])

_ONESIXTYFIVE_XOR64_K90 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xa5, 0x00, 0x00, 0x00,  # r0 = 165 (MOV64 K, 0xa5)
    0xa7, 0x00, 0x00, 0x00, 0x5a, 0x00, 0x00, 0x00,  # r0 ^= 90 (XOR64 K, 0x5a)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=255)
])


class TestP38Corpus:
    def test_mod64_basic_reachable(self):
        """r0=42; MOD64 K 5 → 42%5=2 → r0==2 reachable (64-bit modulo)."""
        result = check(_spec("r0 == 2", max_insns=4), _FORTYTWO_MOD64_K5)
        assert result.verdict == "reachable"

    def test_or64_mask_reachable(self):
        """r0=15 (0x0f); OR64 K 48 (0x30) → 0x0f|0x30=0x3f=63 → r0==63 reachable."""
        result = check(_spec("r0 == 63", max_insns=4), _FIFTEEN_OR64_K48)
        assert result.verdict == "reachable"

    def test_and64_clear_upper_reachable(self):
        """r0=255 (0xff); AND64 K 15 (0x0f) → 0xff&0x0f=15 → r0==15 reachable."""
        result = check(_spec("r0 == 15", max_insns=4), _TWOFIFTYFIVE_AND64_K15)
        assert result.verdict == "reachable"

    def test_xor64_complement_reachable(self):
        """r0=165 (0xa5); XOR64 K 90 (0x5a) → 0xa5^0x5a=0xff=255 → r0==255 reachable."""
        result = check(_spec("r0 == 255", max_insns=4), _ONESIXTYFIVE_XOR64_K90)
        assert result.verdict == "reachable"


_FIFTEEN_OR32_K48 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,  # r0_32 = 15  (MOV32 K, 0x0f)
    0x44, 0x00, 0x00, 0x00, 0x30, 0x00, 0x00, 0x00,  # r0_32 |= 48 (OR32 K, 0x30)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=63)
])

_TWOFIFTYFIVE_AND32_K15 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00,  # r0_32 = 255 (MOV32 K, 0xff)
    0x54, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,  # r0_32 &= 15 (AND32 K, 0x0f)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=15)
])

_ONESIXTYFIVE_XOR32_K90 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0xa5, 0x00, 0x00, 0x00,  # r0_32 = 165 (MOV32 K, 0xa5)
    0xa4, 0x00, 0x00, 0x00, 0x5a, 0x00, 0x00, 0x00,  # r0_32 ^= 90 (XOR32 K, 0x5a)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=255)
])

_ONE_LSH64_K4 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1   (MOV64 K)
    0x67, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00,  # r0 <<= 4 (LSH64 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=16)
])


class TestP39Corpus:
    def test_or32_mask_reachable(self):
        """r0_32=15 (0x0f); OR32 K 48 (0x30) → 0x0f|0x30=63, zero-extended → r0==63 reachable."""
        result = check(_spec("r0 == 63", max_insns=4), _FIFTEEN_OR32_K48)
        assert result.verdict == "reachable"

    def test_and32_clear_reachable(self):
        """r0_32=255 (0xff); AND32 K 15 (0x0f) → 0xff&0x0f=15, zero-extended → r0==15 reachable."""
        result = check(_spec("r0 == 15", max_insns=4), _TWOFIFTYFIVE_AND32_K15)
        assert result.verdict == "reachable"

    def test_xor32_complement_reachable(self):
        """r0_32=165 (0xa5); XOR32 K 90 (0x5a) → 0xa5^0x5a=255, zero-extended → r0==255 reachable."""
        result = check(_spec("r0 == 255", max_insns=4), _ONESIXTYFIVE_XOR32_K90)
        assert result.verdict == "reachable"

    def test_lsh64_basic_reachable(self):
        """r0=1; LSH64 K 4 → 1<<4=16 → r0==16 reachable."""
        result = check(_spec("r0 == 16", max_insns=4), _ONE_LSH64_K4)
        assert result.verdict == "reachable"


_SIXTYFOUR_RSH64_K3 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00,  # r0 = 64  (MOV64 K)
    0x77, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r0 >>= 3 (RSH64 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=8)
])

_NEG16_ARSH64_K2 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xf0, 0xff, 0xff, 0xff,  # r0 = -16 (MOV64 K, sign-extended)
    0xc7, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,  # r0 >>= 2 (ARSH64 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=-4)
])

_ONE_LSH32_K3 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0_32 = 1   (MOV32 K)
    0x64, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r0_32 <<= 3 (LSH32 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=8)
])

_ONETWENTYEIGHT_RSH32_K3 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x80, 0x00, 0x00, 0x00,  # r0_32 = 128 (MOV32 K)
    0x74, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r0_32 >>= 3 (RSH32 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=16)
])


class TestP40Corpus:
    def test_rsh64_basic_reachable(self):
        """r0=64; RSH64 K 3 → 64>>3=8 (logical) → r0==8 reachable."""
        result = check(_spec("r0 == 8", max_insns=4), _SIXTYFOUR_RSH64_K3)
        assert result.verdict == "reachable"

    def test_arsh64_sign_preserved_reachable(self):
        """r0=-16; ARSH64 K 2 → -16>>2=-4 (arithmetic, sign-preserved) → r0==-4 reachable."""
        result = check(_spec("r0 == -4", max_insns=4), _NEG16_ARSH64_K2)
        assert result.verdict == "reachable"

    def test_lsh32_basic_reachable(self):
        """r0_32=1; LSH32 K 3 → 1<<3=8, zero-extended → r0==8 reachable."""
        result = check(_spec("r0 == 8", max_insns=4), _ONE_LSH32_K3)
        assert result.verdict == "reachable"

    def test_rsh32_basic_reachable(self):
        """r0_32=128; RSH32 K 3 → 128>>3=16, zero-extended → r0==16 reachable."""
        result = check(_spec("r0 == 16", max_insns=4), _ONETWENTYEIGHT_RSH32_K3)
        assert result.verdict == "reachable"


_NEG128_ARSH32_K2 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x80, 0xff, 0xff, 0xff,  # r0_32 = -128 (MOV32 K, 0xFFFFFF80)
    0xc4, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,  # r0_32 >>= 2  (ARSH32 K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=4294967264)
])

_FORTYTWO_DIV64X_R1_6 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0 = 42  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x06, 0x00, 0x00, 0x00,  # r1 = 6   (MOV64 K)
    0x3f, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 /= r1 (DIV64 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=7)
])

_FORTYTWO_MOD64X_R1_5 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0 = 42  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r1 = 5   (MOV64 K)
    0x9f, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 %= r1 (MOD64 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=2)
])

_NINETYNINE_MOV64X_R1_42 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r1 = 42  (MOV64 K)
    0xbf, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = r1  (MOV64 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=42)
])


class TestP41Corpus:
    def test_arsh32_sign_preserved_reachable(self):
        """r0_32=-128; ARSH32 K 2 → -32 as int32, zero-extended → r0==4294967264 reachable."""
        result = check(_spec("r0 == 4294967264", max_insns=4), _NEG128_ARSH32_K2)
        assert result.verdict == "reachable"

    def test_div64x_basic_reachable(self):
        """r0=42, r1=6; DIV64 X → 42/6=7 → r0==7 reachable."""
        result = check(_spec("r0 == 7", max_insns=5), _FORTYTWO_DIV64X_R1_6)
        assert result.verdict == "reachable"

    def test_mod64x_basic_reachable(self):
        """r0=42, r1=5; MOD64 X → 42%5=2 → r0==2 reachable."""
        result = check(_spec("r0 == 2", max_insns=5), _FORTYTWO_MOD64X_R1_5)
        assert result.verdict == "reachable"

    def test_mov64x_reg_copy_reachable(self):
        """r0=99, r1=42; MOV64 X → r0=r1=42 → r0==42 reachable."""
        result = check(_spec("r0 == 42", max_insns=5), _NINETYNINE_MOV64X_R1_42)
        assert result.verdict == "reachable"


_FIFTEEN_OR64X_R1_48 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,  # r0 = 15  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x30, 0x00, 0x00, 0x00,  # r1 = 48  (MOV64 K)
    0x4f, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 |= r1 (OR64 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=63)
])

_TWOFIFTYFIVE_AND64X_R1_15 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00,  # r0 = 255 (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,  # r1 = 15  (MOV64 K)
    0x5f, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 &= r1 (AND64 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=15)
])

_ONESIXTYFIVE_XOR64X_R1_90 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xa5, 0x00, 0x00, 0x00,  # r0 = 165 (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x5a, 0x00, 0x00, 0x00,  # r1 = 90  (MOV64 K)
    0xaf, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 ^= r1 (XOR64 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=255)
])

_NEG16_ARSH64X_R1_2 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xf0, 0xff, 0xff, 0xff,  # r0 = -16 (MOV64 K, sign-extended)
    0xb7, 0x01, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,  # r1 = 2   (MOV64 K)
    0xcf, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 >>= r1 (ARSH64 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=-4)
])


class TestP42Corpus:
    def test_or64x_mask_reachable(self):
        """r0=15, r1=48; OR64 X → 0x0f|0x30=63 → r0==63 reachable."""
        result = check(_spec("r0 == 63", max_insns=5), _FIFTEEN_OR64X_R1_48)
        assert result.verdict == "reachable"

    def test_and64x_clear_reachable(self):
        """r0=255, r1=15; AND64 X → 0xff&0x0f=15 → r0==15 reachable."""
        result = check(_spec("r0 == 15", max_insns=5), _TWOFIFTYFIVE_AND64X_R1_15)
        assert result.verdict == "reachable"

    def test_xor64x_complement_reachable(self):
        """r0=165, r1=90; XOR64 X → 0xa5^0x5a=255 → r0==255 reachable."""
        result = check(_spec("r0 == 255", max_insns=5), _ONESIXTYFIVE_XOR64X_R1_90)
        assert result.verdict == "reachable"

    def test_arsh64x_sign_preserved_reachable(self):
        """r0=-16, r1=2; ARSH64 X → -16>>2=-4 (arithmetic) → r0==-4 reachable."""
        result = check(_spec("r0 == -4", max_insns=5), _NEG16_ARSH64X_R1_2)
        assert result.verdict == "reachable"


_ONE_LSH64X_R1_4 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1   (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00,  # r1 = 4   (MOV64 K)
    0x6f, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 <<= r1 (LSH64 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=16)
])

_SIXTYFOUR_RSH64X_R1_3 = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00,  # r0 = 64  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r1 = 3   (MOV64 K)
    0x7f, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 >>= r1 (RSH64 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=8)
])

_ONE_LSH32X_R1_3 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0_32 = 1 (MOV32 K)
    0xb7, 0x01, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r1 = 3   (MOV64 K, shift count)
    0x6c, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0_32 <<= r1 (LSH32 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=8)
])

_ONETWENTYEIGHT_RSH32X_R1_3 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x80, 0x00, 0x00, 0x00,  # r0_32 = 128 (MOV32 K)
    0xb7, 0x01, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r1 = 3   (MOV64 K, shift count)
    0x7c, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0_32 >>= r1 (RSH32 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=16)
])


class TestP43Corpus:
    def test_lsh64x_basic_reachable(self):
        """r0=1, r1=4; LSH64 X → 1<<4=16 → r0==16 reachable."""
        result = check(_spec("r0 == 16", max_insns=5), _ONE_LSH64X_R1_4)
        assert result.verdict == "reachable"

    def test_rsh64x_basic_reachable(self):
        """r0=64, r1=3; RSH64 X → 64>>3=8 (logical) → r0==8 reachable."""
        result = check(_spec("r0 == 8", max_insns=5), _SIXTYFOUR_RSH64X_R1_3)
        assert result.verdict == "reachable"

    def test_lsh32x_basic_reachable(self):
        """r0_32=1, r1=3; LSH32 X → 1<<3=8, zero-extended → r0==8 reachable."""
        result = check(_spec("r0 == 8", max_insns=5), _ONE_LSH32X_R1_3)
        assert result.verdict == "reachable"

    def test_rsh32x_basic_reachable(self):
        """r0_32=128, r1=3; RSH32 X → 128>>3=16, zero-extended → r0==16 reachable."""
        result = check(_spec("r0 == 16", max_insns=5), _ONETWENTYEIGHT_RSH32X_R1_3)
        assert result.verdict == "reachable"


_NEG128_ARSH32X_R1_2 = bytes([
    0xb4, 0x00, 0x00, 0x00, 0x80, 0xff, 0xff, 0xff,  # r0_32 = -128 (MOV32 K)
    0xb7, 0x01, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,  # r1 = 2   (MOV64 K, shift count)
    0xcc, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0_32 >>= r1 (ARSH32 X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=4294967264)
])

_R042_R142_JEQX_SKIP = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0 = 42  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r1 = 42  (MOV64 K)
    0x1d, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JEQ X r0,r1,+1 (skip if r0==r1)
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1  (skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=42)
])

_TEN_R120_JNEX_SKIP = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x0a, 0x00, 0x00, 0x00,  # r0 = 10  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x14, 0x00, 0x00, 0x00,  # r1 = 20  (MOV64 K)
    0x5d, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JNE X r0,r1,+1 (skip if r0!=r1)
    0x07, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 += 5  (skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=10)
])

_TWENTY_R110_JGTX_SKIP = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x14, 0x00, 0x00, 0x00,  # r0 = 20  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x0a, 0x00, 0x00, 0x00,  # r1 = 10  (MOV64 K)
    0x2d, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGT X r0,r1,+1 (skip if r0>r1 unsigned)
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1  (skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=20)
])


class TestP44Corpus:
    def test_arsh32x_sign_preserved_reachable(self):
        """r0_32=-128, r1=2; ARSH32 X → -32 int32, zero-extended → r0==4294967264 reachable."""
        result = check(_spec("r0 == 4294967264", max_insns=5), _NEG128_ARSH32X_R1_2)
        assert result.verdict == "reachable"

    def test_jeqx_taken_reachable(self):
        """r0=42, r1=42; JEQ X taken (42==42) skips ADD → r0==42 reachable."""
        result = check(_spec("r0 == 42", max_insns=6), _R042_R142_JEQX_SKIP)
        assert result.verdict == "reachable"

    def test_jnex_taken_reachable(self):
        """r0=10, r1=20; JNE X taken (10!=20) skips ADD → r0==10 reachable."""
        result = check(_spec("r0 == 10", max_insns=6), _TEN_R120_JNEX_SKIP)
        assert result.verdict == "reachable"

    def test_jgtx_taken_reachable(self):
        """r0=20, r1=10; JGT X taken (20>10 unsigned) skips ADD → r0==20 reachable."""
        result = check(_spec("r0 == 20", max_insns=6), _TWENTY_R110_JGTX_SKIP)
        assert result.verdict == "reachable"


_TWENTY_R120_JGEX_SKIP = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x14, 0x00, 0x00, 0x00,  # r0 = 20  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x14, 0x00, 0x00, 0x00,  # r1 = 20  (MOV64 K)
    0x3d, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGE X r0,r1,+1 (skip if r0>=r1 unsigned)
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1  (skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=20)
])

_FIVE_R13_JSGTX_SKIP = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5   (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r1 = 3   (MOV64 K)
    0x6d, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSGT X r0,r1,+1 (skip if r0>r1 signed)
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1  (skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=5)
])

_NEG1_R1NEG1_JSGEX_SKIP = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1  (MOV64 K, sign-extended)
    0xb7, 0x01, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r1 = -1  (MOV64 K, sign-extended)
    0x7d, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSGE X r0,r1,+1 (skip if r0>=r1 signed)
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1  (skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=-1)
])

_TEN_R120_JLTX_SKIP = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x0a, 0x00, 0x00, 0x00,  # r0 = 10  (MOV64 K)
    0xb7, 0x01, 0x00, 0x00, 0x14, 0x00, 0x00, 0x00,  # r1 = 20  (MOV64 K)
    0xad, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLT X r0,r1,+1 (skip if r0<r1 unsigned)
    0x07, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 += 5  (skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT (r0=10)
])


class TestP45Corpus:
    def test_jgex_taken_reachable(self):
        """r0=20, r1=20; JGE X taken (20>=20 unsigned) skips ADD → r0==20 reachable."""
        result = check(_spec("r0 == 20", max_insns=6), _TWENTY_R120_JGEX_SKIP)
        assert result.verdict == "reachable"

    def test_jsgtx_taken_reachable(self):
        """r0=5, r1=3; JSGT X taken (5>3 signed) skips ADD → r0==5 reachable."""
        result = check(_spec("r0 == 5", max_insns=6), _FIVE_R13_JSGTX_SKIP)
        assert result.verdict == "reachable"

    def test_jsgex_taken_reachable(self):
        """r0=-1, r1=-1; JSGE X taken (-1>=-1 signed) skips ADD → r0==-1 reachable."""
        result = check(_spec("r0 == -1", max_insns=6), _NEG1_R1NEG1_JSGEX_SKIP)
        assert result.verdict == "reachable"

    def test_jltx_taken_reachable(self):
        """r0=10, r1=20; JLT X taken (10<20 unsigned) skips ADD → r0==10 reachable."""
        result = check(_spec("r0 == 10", max_insns=6), _TEN_R120_JLTX_SKIP)
        assert result.verdict == "reachable"
