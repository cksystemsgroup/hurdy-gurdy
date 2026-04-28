"""Wall-clock timeout helper used by subprocess solver wrappers."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SubprocessOutcome:
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed: float
    timed_out: bool


def run_with_timeout(
    argv: list[str],
    stdin: bytes | None = None,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> SubprocessOutcome:
    """Run a subprocess, enforce ``timeout`` (seconds), capture
    stdout+stderr+elapsed, and report whether the timeout fired."""

    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            argv,
            input=stdin,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        elapsed = time.monotonic() - start
        return SubprocessOutcome(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed=elapsed,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        elapsed = time.monotonic() - start
        out = exc.stdout if exc.stdout is not None else b""
        err = exc.stderr if exc.stderr is not None else b""
        return SubprocessOutcome(
            returncode=124,  # GNU timeout convention
            stdout=out if isinstance(out, bytes) else out.encode("utf-8", "replace"),
            stderr=err if isinstance(err, bytes) else err.encode("utf-8", "replace"),
            elapsed=elapsed,
            timed_out=True,
        )


__all__ = ["SubprocessOutcome", "run_with_timeout"]
