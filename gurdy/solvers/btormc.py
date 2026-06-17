"""A native BTOR2 model checker (``btormc``) as a BTOR2 solver backend
(SOLVERS.md: BtorMC / Pono / AVR).

This is the *native* side of the native-vs-bridged cross-check (SOLVERS.md §7):
``btormc`` decides a BTOR2 reachability question directly, and its verdict must
match the one obtained by bridging the same system to SMT-LIB and deciding with
z3 (``btor2-smtlib.reach``). The binary is located via ``$BTORMC`` or PATH and
is gated on the pinned dev image (DOCKER.md); the verdict parser is pure and
unit-tested.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any

from ..core.solver import Verdict


class NativeUnavailable(RuntimeError):
    """Raised when a native BTOR2 model checker cannot be located."""


def find_btormc() -> str | None:
    return os.environ.get("BTORMC") or shutil.which("btormc")


def parse_verdict(output: str) -> Verdict:
    """Parse ``btormc`` output: a ``sat`` witness means a bad is reachable; an
    ``unsat`` line means it is not (within the bound); else unknown."""
    for line in output.splitlines():
        tok = line.strip().lower()
        if tok == "sat" or tok.startswith("sat "):
            return Verdict.REACHABLE
        if tok == "unsat" or tok.startswith("unsat "):
            return Verdict.UNREACHABLE
    return Verdict.UNKNOWN


class Btor2McBackend:
    id = "btormc"

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or find_btormc()

    def available(self) -> bool:
        return bool(self.binary) and (
            os.path.exists(self.binary) or shutil.which(self.binary) is not None
        )

    def decide(self, system: Any, k: int) -> Verdict:
        if not self.available():
            raise NativeUnavailable("btormc not found (set $BTORMC)")
        text = system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
        with tempfile.NamedTemporaryFile("w", suffix=".btor2", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            proc = subprocess.run(
                [self.binary, "-kmax", str(k), path],
                capture_output=True, text=True, timeout=300,
            )
        finally:
            os.unlink(path)
        return parse_verdict(proc.stdout + "\n" + proc.stderr)
