import shutil
import sys
from dataclasses import dataclass

import pytest

from gurdy.core.dispatch.backend import (
    InProcessSolverBackend,
    SolverBackend,
    SubprocessSolverBackend,
)
from gurdy.core.dispatch.result import VERDICTS, RawSolverResult
from gurdy.core.dispatch.timeout import run_with_timeout


@dataclass
class _Directive:
    timeout: float | None = None


def test_raw_result_unknown_verdict_is_normalized():
    r = RawSolverResult(verdict="bogus", elapsed=0.1, engine="x")
    assert r.verdict == "unknown"
    assert "unknown" in VERDICTS


def test_run_with_timeout_captures_stdout():
    out = run_with_timeout([sys.executable, "-c", "print('hi')"], timeout=10)
    assert out.returncode == 0
    assert b"hi" in out.stdout
    assert not out.timed_out


def test_run_with_timeout_fires_on_long_command():
    out = run_with_timeout(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        timeout=0.2,
    )
    assert out.timed_out
    assert out.returncode == 124


def test_subprocess_solver_reports_missing_binary():
    class S(SubprocessSolverBackend):
        pass

    s = S(name="fake", binary="this-binary-definitely-does-not-exist-xyz123")
    res = s.dispatch(b"", _Directive())
    assert res.verdict == "error"
    assert "not on PATH" in (res.reason or "")


def test_subprocess_solver_runs_real_binary():
    if not shutil.which("cat"):
        pytest.skip("no cat on PATH")

    class CatSolver(SubprocessSolverBackend):
        def build_argv(self, directive):
            return [self.binary]

        def parse_output(self, outcome, directive):
            return RawSolverResult(
                verdict="proved" if outcome.returncode == 0 else "error",
                elapsed=outcome.elapsed,
                engine=self.name,
                payload=outcome.stdout,
            )

    s = CatSolver(name="cat-solver", binary="cat")
    res = s.dispatch(b"hello", _Directive())
    assert res.verdict == "proved"
    assert res.payload == b"hello"


def test_in_process_solver_subclass_protocol():
    class S(InProcessSolverBackend):
        name = "test-inproc"

        def dispatch(self, artifact_bytes, directive):
            return RawSolverResult(
                verdict="reachable", elapsed=0.0, engine=self.name
            )

    assert isinstance(S(), SolverBackend)
    assert S().dispatch(b"", _Directive()).verdict == "reachable"
