"""A native BTOR2 model checker as a BTOR2 solver backend (SOLVERS.md: the
BTOR2 solver inventory — ``pono`` is pinned in the dev image; ``btormc`` is
host-wired and drives witness generation and bounded exhaustion; AVR is a
named future layer).

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

    def _run_full(self, system: Any, k: int,
                  binary: str | None = None) -> tuple[str, str, int]:
        import hashlib

        from ..core import costs

        binary = binary or self.binary
        if not binary or not (os.path.exists(binary) or shutil.which(binary) is not None):
            raise NativeUnavailable("no native BTOR2 checker found (set $PONO or $BTORMC)")
        text = system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
        with tempfile.NamedTemporaryFile("w", suffix=".btor2", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            with costs.timed("decide",
                             hashlib.sha256(text.encode("utf-8")).hexdigest(),
                             engine=os.path.basename(binary),
                             language="btor2", k=k, size=len(text)):
                proc = subprocess.run(_command(binary, k, path),
                                      capture_output=True, text=True, timeout=300)
        finally:
            os.unlink(path)
        return proc.stdout, proc.stderr, proc.returncode

    def _run(self, system: Any, k: int, binary: str | None = None) -> str:
        out, err, _ = self._run_full(system, k, binary)
        return out + "\n" + err

    def decide(self, system: Any, k: int) -> Verdict:
        return parse_verdict(self._run(system, k))

    # A trivially reachable system (bad on constant one, hit at step 0): a
    # sane btormc must answer ``sat`` on it. Used as the negative control
    # for the exhaustion signal below — the checker-adapter rule of
    # SOLVERS.md §5 ("an adapter without a negative control is itself
    # unchecked"), applied to the one signal that is *silence*.
    _CANARY = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"
    _canary_ok: dict[str, bool] = {}   # per-binary, per-process

    def _exhaustion_trustworthy(self, btormc: str) -> bool:
        """The exhaustion signal is empty output — indistinguishable from a
        broken binary that silently exits 0. Before trusting it, require the
        same binary to answer ``sat`` on the trivially reachable canary."""
        ok = self._canary_ok.get(btormc)
        if ok is None:
            out, err, _rc = self._run_full(self._CANARY, 0, binary=btormc)
            ok = parse_verdict(out + "\n" + err) is Verdict.REACHABLE
            self._canary_ok[btormc] = ok
        return ok

    def decide_bounded(self, system: Any, k: int) -> Verdict:
        """Decide with **btormc**, reading a clean ``-kmax`` exhaustion as
        \"unreachable within the bound\" — the same bounded claim the SMT
        bridge's ``unsat`` makes. btormc prints ``sat`` plus a witness on a
        counterexample and nothing at all when the bound is exhausted, so a
        clean empty run (exit 0, empty stdout AND stderr) is the exhaustion
        signal; anything else that is not a ``sat``/``unsat`` token stays
        UNKNOWN (a parse error must never read as unreachable). Because the
        exhaustion signal is silence, it is only trusted from a binary that
        first passes the reachable canary (negative control)."""
        btormc = find_btormc()
        if not btormc:
            raise NativeUnavailable("btormc required for a bounded verdict")
        out, err, rc = self._run_full(system, k, binary=btormc)
        verdict = parse_verdict(out + "\n" + err)
        if verdict is Verdict.UNKNOWN and rc == 0 \
                and not out.strip() and not err.strip() \
                and self._exhaustion_trustworthy(btormc):
            return Verdict.UNREACHABLE
        return verdict

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
