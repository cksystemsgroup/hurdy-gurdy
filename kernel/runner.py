"""Sandboxed deterministic execution (KERNEL.md §9).

Every registered artifact is a pure CLI — bytes in, bytes out — run in
its own process with an empty environment, a temporary working
directory, and a wall-clock cap. Determinism is not declared but
measured: ``run_twice`` runs the same invocation twice and byte-compares
stdout. Budgets ride in the returned record so every caller can put
them in provenance.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

#: Environment for sandboxed runs: interpreter location only, no user env.
_ENV_KEYS = ("PATH", "HOME")


@dataclass(frozen=True)
class RunResult:
    out: bytes
    err: bytes
    rc: int | None          # None when the wall was hit
    wall_s: float
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.rc == 0 and not self.timed_out


def _env() -> dict[str, str]:
    return {k: os.environ[k] for k in _ENV_KEYS if k in os.environ}


def run(argv: list[str], *, stdin: bytes = b"", wall_s: float = 60.0,
        cwd: str | None = None) -> RunResult:
    """Run ``argv`` sandboxed; a hit wall is a result, never an exception."""
    start = time.monotonic()
    with tempfile.TemporaryDirectory() as scratch:
        try:
            proc = subprocess.run(
                argv, input=stdin, capture_output=True, timeout=wall_s,
                cwd=cwd or scratch, env=_env())
            return RunResult(proc.stdout, proc.stderr, proc.returncode,
                             time.monotonic() - start, False)
        except subprocess.TimeoutExpired as exc:
            return RunResult(exc.stdout or b"", exc.stderr or b"", None,
                             time.monotonic() - start, True)


def run_py(script: str, args: list[str], **kw) -> RunResult:
    """Run a registered Python executable under the kernel's interpreter."""
    return run([sys.executable, script, *args], **kw)


def run_twice(script: str, args: list[str], **kw) -> tuple[RunResult, bool]:
    """The determinism measurement: same invocation twice, stdout
    byte-compared. Returns (first result, identical). A timed-out run is
    never called deterministic."""
    first = run_py(script, args, **kw)
    if first.timed_out:
        return first, False
    second = run_py(script, args, **kw)
    return first, (not second.timed_out and first.out == second.out
                   and first.rc == second.rc)
