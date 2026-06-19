"""CLI-driven SMT ``SolverBackend``s that share one ``sat``/``unsat``/``unknown``
parser (SOLVERS.md §3): **boolector**, **cvc5**, **yices2**.

Each is a thin adapter — locate the pinned binary, run it on the SMT artifact,
normalize the verdict — reimplementing nothing (SOLVERS.md §3 "thin adapters").
They exist for **independence** (SOLVERS.md §5-6): deciding the same query with
several different codebases is what raises a verdict to `checked`, and a
*disagreement* localizes a translator-or-solver bug (§7).

Independence note: boolector and bitwuzla share lineage (bitwuzla is boolector's
successor), so the strongest independent pairing is z3 vs either of them; cvc5
and yices2 are fully independent of all three.

Only the verdict is normalized here (models are not parsed — the reachable
carry-back uses z3's model, ``solvers/z3_smt.py``); these backends serve the
corroboration of `unsat`/`unreachable`. Binaries are located via an env var or
PATH and gated on presence (DOCKER.md); the parser is pure and unit-tested.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any

from ..core.solver import Result, Verdict


class SolverUnavailable(RuntimeError):
    """Raised when a CLI SMT solver's binary cannot be located."""


def parse_verdict(output: str) -> Verdict:
    """Normalize a solver's stdout: a ``sat`` / ``unsat`` / ``unknown`` line.
    Shared by every SMT-LIB CLI solver (they all print these tokens)."""
    for line in output.splitlines():
        tok = line.strip().lower()
        if tok == "unsat":
            return Verdict.UNREACHABLE
        if tok == "sat":
            return Verdict.REACHABLE
        if tok == "unknown":
            return Verdict.UNKNOWN
    return Verdict.UNKNOWN


class SmtCliBackend:
    """Base adapter: subclasses set ``id``, ``env_var`` and candidate
    ``binaries``. ``decide`` runs the binary on the artifact and parses the
    verdict; the subprocess timeout enforces the resource limit."""

    id: str = "?"
    env_var: str = ""
    binaries: tuple[str, ...] = ()

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or self._find()

    def _find(self) -> str | None:
        if self.env_var and os.environ.get(self.env_var):
            return os.environ[self.env_var]
        for name in self.binaries:
            p = shutil.which(name)
            if p:
                return p
        return None

    def available(self) -> bool:
        return bool(self.binary) and (
            os.path.exists(self.binary) or shutil.which(self.binary) is not None
        )

    def version(self) -> str:
        try:
            out = subprocess.run([self.binary, "--version"], capture_output=True,
                                 text=True, timeout=30)
            lines = (out.stdout or out.stderr).strip().splitlines()
            return lines[0] if lines else "?"
        except Exception:  # pragma: no cover - env guard
            return "?"

    def decide(self, artifact: bytes, directive: dict[str, Any] | None = None) -> Result:
        if not self.available():
            raise SolverUnavailable(f"{self.id} not found (set ${self.env_var})")
        text = artifact.decode("utf-8") if isinstance(artifact, (bytes, bytearray)) else str(artifact)
        with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            proc = subprocess.run([self.binary, path], capture_output=True,
                                  text=True, timeout=300)
        finally:
            os.unlink(path)
        prov: dict[str, Any] = {"solver": self.id, "version": self.version(),
                                "directive": dict(directive or {})}
        return Result(parse_verdict(proc.stdout + "\n" + proc.stderr), provenance=prov)


class BoolectorSmtBackend(SmtCliBackend):
    id = "boolector"
    env_var = "BOOLECTOR"
    binaries = ("boolector",)


class Cvc5SmtBackend(SmtCliBackend):
    id = "cvc5"
    env_var = "CVC5"
    binaries = ("cvc5",)


class Yices2SmtBackend(SmtCliBackend):
    id = "yices2"
    env_var = "YICES2"
    binaries = ("yices-smt2", "yices2")
