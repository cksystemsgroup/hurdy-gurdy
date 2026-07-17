"""Bitwuzla as an SMT ``SolverBackend`` (SOLVERS.md §3; the second, independent
SMT engine after z3).

Independence is the whole point (SOLVERS.md §5): deciding the same SMT artifact
with a *different codebase* than z3 is what raises an `unsat`/`unreachable`
answer from `reproducible` (one solver) to `checked` (≥2 independent solvers
agree, SOLVERS.md §6). Bitwuzla is a bit-vector/array SMT solver — the natural
QF_ABV peer of z3 here. A thin adapter: run the pinned binary, normalize the
``sat``/``unsat``/``unknown`` verdict into a framework ``Result``. The binary is
located via ``$BITWUZLA`` or PATH and is gated on its presence (DOCKER.md);
the verdict parser is pure and unit-tested.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any

from ..core.solver import Result, Verdict


class BitwuzlaUnavailable(RuntimeError):
    """Raised when the bitwuzla binary cannot be located."""


def find_bitwuzla() -> str | None:
    return os.environ.get("BITWUZLA") or shutil.which("bitwuzla")


def parse_verdict(output: str) -> Verdict:
    """Bitwuzla prints ``sat`` / ``unsat`` / ``unknown`` on its own line."""
    for line in output.splitlines():
        tok = line.strip().lower()
        if tok == "unsat":
            return Verdict.UNREACHABLE
        if tok == "sat":
            return Verdict.REACHABLE
        if tok == "unknown":
            return Verdict.UNKNOWN
    return Verdict.UNKNOWN


class BitwuzlaSmtBackend:
    id = "bitwuzla"

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or find_bitwuzla()

    def available(self) -> bool:
        return bool(self.binary) and (
            os.path.exists(self.binary) or shutil.which(self.binary) is not None
        )

    def version(self) -> str:
        try:
            out = subprocess.run([self.binary, "--version"], capture_output=True,
                                 text=True, timeout=30)
            return out.stdout.strip().splitlines()[0] if out.stdout.strip() else "?"
        except Exception:  # pragma: no cover - env guard
            return "?"

    def decide(self, artifact: bytes, directive: dict[str, Any] | None = None) -> Result:
        if not self.available():
            raise BitwuzlaUnavailable("bitwuzla not found (set $BITWUZLA)")
        text = artifact.decode("utf-8") if isinstance(artifact, (bytes, bytearray)) else str(artifact)
        with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False) as f:
            f.write(text)
            path = f.name
        cmd = [self.binary]
        if directive and "timeout_ms" in directive:
            cmd += ["-t", str(int(directive["timeout_ms"]))]
        cmd.append(path)
        try:
            import hashlib

            from ..core import ledger

            with ledger.timed("decide",
                             hashlib.sha256(text.encode("utf-8")).hexdigest(),
                             engine=self.id, language="smtlib",
                             size=len(text)) as extra:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                verdict = parse_verdict(proc.stdout + "\n" + proc.stderr)
                extra["verdict"] = verdict.value
        finally:
            os.unlink(path)
        prov: dict[str, Any] = {"solver": self.id, "version": self.version(),
                                "directive": dict(directive or {})}
        return Result(verdict, provenance=prov)
