"""Sealed deterministic execution (KERNEL.md §6, §10).

Every registered implementation is a pure CLI — bytes in, bytes out —
run in its own process with an **emptied environment** and a temporary
working directory, under a wall-clock cap. The emptied environment is
the generation rule made operational: it holds nothing but a *blank*
``PATH`` — blank rather than absent, because with ``PATH`` unset both
libc and Python's ``subprocess`` fall back to the platform's default
search path (``/bin:/usr/bin``), which the kernel's own tests caught
finding ``/usr/bin/python3`` — so an implementation cannot *discover*
an existing tool: the only things that run are the entry's own files,
Python under the kernel's own interpreter and a declared accelerator
directly. (The seal makes reaching for a tool loud, and the registry
makes it visible — every implementation is committed source; neither
is claimed to be a proof: an absolute path is not hidden by anything.)

Determinism is not declared but measured: ``run_twice`` runs the same
invocation twice and byte-compares stdout. Budgets ride in the returned
record so every caller can put them in provenance.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass


#: The seal's environment: a blank ``PATH`` and nothing else. Blank,
#: not absent — an unset ``PATH`` is replaced by the platform default
#: search path by libc and by Python alike.
SEALED_ENV = {"PATH": ""}


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


def run(argv: list[str], *, stdin: bytes = b"", wall_s: float = 60.0,
        cwd: str | None = None) -> RunResult:
    """Run ``argv`` sealed; a hit wall is a result, never an exception."""
    start = time.monotonic()
    with tempfile.TemporaryDirectory() as scratch:
        try:
            proc = subprocess.run(
                argv, input=stdin, capture_output=True, timeout=wall_s,
                cwd=cwd or scratch, env=SEALED_ENV)
            return RunResult(proc.stdout, proc.stderr, proc.returncode,
                             time.monotonic() - start, False)
        except subprocess.TimeoutExpired as exc:
            return RunResult(exc.stdout or b"", exc.stderr or b"", None,
                             time.monotonic() - start, True)


def run_exe(path: str, args: list[str], **kw) -> RunResult:
    """Run a registered executable: ``.py`` under the kernel's own
    interpreter (the reference implementations), anything else directly
    (a built accelerator)."""
    if path.endswith(".py"):
        return run([sys.executable, path, *args], **kw)
    return run([os.path.abspath(path), *args], **kw)


def run_twice(path: str, args: list[str], **kw) -> tuple[RunResult, bool]:
    """The determinism measurement: same invocation twice, stdout
    byte-compared. Returns (first result, identical). A timed-out run is
    never called deterministic."""
    first = run_exe(path, args, **kw)
    if first.timed_out:
        return first, False
    second = run_exe(path, args, **kw)
    return first, (not second.timed_out and first.out == second.out
                   and first.rc == second.rc)
