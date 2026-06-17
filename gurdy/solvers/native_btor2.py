"""A native BTOR2 model checker as a BTOR2 solver backend (SOLVERS.md: the
BTOR2 solver inventory — ``pono`` is pinned in the dev image; ``BtorMC`` / AVR
are future layers).

This is the *native* side of the native-vs-bridged cross-check (SOLVERS.md §7):
the engine decides a BTOR2 reachability question directly, and its verdict must
match the one obtained by bridging the same system to SMT-LIB and deciding with
z3 (``btor2-smtlib.reach``). The binary is located via ``$NATIVE_BTOR2`` /
``$PONO`` / ``$BTORMC`` or PATH and is gated on the pinned dev image
(DOCKER.md); the verdict parser is pure and unit-tested.
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


def find_native_checker() -> str | None:
    return (os.environ.get("NATIVE_BTOR2") or os.environ.get("PONO")
            or os.environ.get("BTORMC") or shutil.which("pono") or shutil.which("btormc"))


def parse_verdict(output: str) -> Verdict:
    """Parse a native checker's output: a ``sat`` line (a reached-bad witness)
    means reachable, an ``unsat`` line means unreachable (within the bound),
    else unknown. Both ``pono`` and ``btormc`` emit these tokens."""
    for line in output.splitlines():
        tok = line.strip().lower()
        if tok == "sat" or tok.startswith("sat "):
            return Verdict.REACHABLE
        if tok == "unsat" or tok.startswith("unsat "):
            return Verdict.UNREACHABLE
    return Verdict.UNKNOWN


def _command(binary: str, k: int, path: str) -> list[str]:
    name = os.path.basename(binary).lower()
    if "pono" in name:                      # pono: BMC to bound k
        return [binary, "-e", "bmc", "-k", str(k), path]
    return [binary, "-kmax", str(k), path]  # btormc


class NativeBtor2Checker:
    id = "native-btor2"

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or find_native_checker()

    def available(self) -> bool:
        return bool(self.binary) and (
            os.path.exists(self.binary) or shutil.which(self.binary) is not None
        )

    def decide(self, system: Any, k: int) -> Verdict:
        if not self.available():
            raise NativeUnavailable("no native BTOR2 checker found (set $PONO or $BTORMC)")
        text = system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
        with tempfile.NamedTemporaryFile("w", suffix=".btor2", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            proc = subprocess.run(_command(self.binary, k, path),
                                  capture_output=True, text=True, timeout=300)
        finally:
            os.unlink(path)
        return parse_verdict(proc.stdout + "\n" + proc.stderr)
