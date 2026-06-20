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


def find_btormc() -> str | None:
    """``btormc`` specifically — the engine whose witness is in the btor2 ``.wit``
    format the shared parser expects (pono's witness is a different format), so
    witness *generation* targets btormc even when ``find_native_checker`` would
    pick pono first for a plain verdict."""
    if os.environ.get("BTORMC"):
        return os.environ["BTORMC"]
    cand = find_native_checker()
    if cand and "btormc" in os.path.basename(cand).lower():
        return cand
    return shutil.which("btormc")


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
    # btormc: --trace-gen-full forces the full state trace into the .wit. Its
    # default only prints inputs (and some builds default it on, others off), so
    # a no-input system can yield a witness with no state lines — a build-
    # dependent gap that silently breaks replay (caught running in-image).
    return [binary, "-kmax", str(k), "--trace-gen-full", path]


class NativeBtor2Checker:
    id = "native-btor2"

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or find_native_checker()

    def available(self) -> bool:
        return bool(self.binary) and (
            os.path.exists(self.binary) or shutil.which(self.binary) is not None
        )

    def _run(self, system: Any, k: int, binary: str | None = None) -> str:
        binary = binary or self.binary
        if not binary or not (os.path.exists(binary) or shutil.which(binary) is not None):
            raise NativeUnavailable("no native BTOR2 checker found (set $PONO or $BTORMC)")
        text = system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
        with tempfile.NamedTemporaryFile("w", suffix=".btor2", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            proc = subprocess.run(_command(binary, k, path),
                                  capture_output=True, text=True, timeout=300)
        finally:
            os.unlink(path)
        return proc.stdout + "\n" + proc.stderr

    def decide(self, system: Any, k: int) -> Verdict:
        return parse_verdict(self._run(system, k))

    def decide_witness(self, system: Any, k: int) -> tuple[Verdict, str | None]:
        """Decide with **btormc** and return the raw btor2 ``.wit`` on
        ``reachable`` (with ``--trace-gen-full`` so the full state trace is
        always present), so a caller can replay it through the shared interpreter
        (``languages/btor2.check_witness``; SOLVERS.md §4). btormc is required
        here regardless of which engine ``decide`` uses: it is the producer of
        the btor2 ``.wit`` format the parser expects (pono's witness differs)."""
        btormc = find_btormc()
        if not btormc:
            raise NativeUnavailable("btormc required for a btor2 .wit witness")
        out = self._run(system, k, binary=btormc)
        verdict = parse_verdict(out)
        return verdict, (out if verdict is Verdict.REACHABLE else None)
