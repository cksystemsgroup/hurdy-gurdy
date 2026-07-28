"""Pono's ``msat-ic3ia`` — the one family member the host cannot hold,
played through a pinned Linux container (the registered ``pono-msat``
solver brief's adapter, SOLVERS.md §2.1).

``msat-ic3ia`` is IC3 via Implicit Predicate Abstraction hardwired to
MathSAT's interpolation — the sub-family's reference configuration
(the ``ic3ia`` the exploration iteration played used the weaker
default interpolator). MathSAT ships no macOS-arm64 or Linux-aarch64
build, so the engine runs as pono v2.0.0 (the same ``c81aa36`` pin the
host build uses) rebuilt ``--with-msat --with-msat-ic3ia`` in an
**amd64 Linux image** (``pono-msat:c81aa36``, Dockerfile alongside the
campaign records), executed under emulation. The wall is wall-clock as
always — emulation means the engine gets less work done per wall,
which is honest as long as it is declared, and it is.

Two facts the build surfaced, both load-bearing: ``--with-msat`` alone
is *not* enough — it only adds MathSAT as an SMT backend, while the
engine's source compiles only under ``WITH_MSAT_IC3IA``, which needs
Griggio's standalone ic3ia library built against MathSAT; and the
engine refuses every other backend at run time, so ``--smt-solver
msat`` is passed on every run. A build missing either would answer
``error``/``Unhandled engine`` on *all* input — an engine that
abstains everywhere, which a campaign iteration would have recorded
as a perfectly clean null result. Hence the two-sided fixtures below
and the gate before any pin is spent.

Lineage: ``(pono, smt-switch, mathsat)`` — shares ``pono`` and
``smt-switch`` with the host pono brief, so nothing decided here can
corroborate a pono answer (solvers/brief.independent); the member is
played for coverage of the demanded family, not for the trust axis.

The adapter mirrors ``pono_btor2``: per-property any-bad aggregation
(pono checks one property per run), the BTOR2 witness dumped on ``sat``
for shared-interpreter replay, unbounded runs booked ``k=None``. Each
property run is one ``docker run`` (``--memory`` capped per the RAM
discipline); the wall is enforced host-side and an overrun kills the
named container before ``TimeoutExpired`` propagates.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Any

from ..core.solver import Verdict
from .native_btor2 import parse_verdict
from .pono_btor2 import UNBOUNDED_FRAMES, UNBOUNDED_WALL_S, _count_bads

#: The pinned image: pono c81aa36 rebuilt --with-msat (MathSAT 5.6.11
#: linux-x86_64 — its custom research license is the reason this build
#: cannot ship in the bench image), amd64 under emulation.
PONO_MSAT_IMAGE = "pono-msat:c81aa36"

#: ``--memory`` handed to every container run (the RAM discipline).
PONO_MSAT_MEM = "8g"


class PonoMsatUnavailable(RuntimeError):
    """Raised when docker or the pinned image cannot be located."""


def find_pono_msat() -> str | None:
    """The pinned image name, when docker can run it."""
    docker = shutil.which("docker")
    if not docker:
        return None
    try:
        probe = subprocess.run(
            [docker, "image", "inspect", PONO_MSAT_IMAGE],
            capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    return PONO_MSAT_IMAGE if probe.returncode == 0 else None


class PonoMsatBtor2Checker:
    id = "pono-msat"

    #: Shares pono and smt-switch with the host pono brief — declared
    #: in full, so the two can never corroborate each other.
    lineage = ("pono", "smt-switch", "mathsat")

    def __init__(self, image: str | None = None) -> None:
        self.image = image or PONO_MSAT_IMAGE

    def available(self) -> bool:
        return find_pono_msat() is not None

    def decide(self, system: Any, *, mode: str = "msat-ic3ia",
               k: int = UNBOUNDED_FRAMES) -> tuple[Verdict, str | None]:
        """One containerized mode over **every** ``bad`` property —
        the same any-bad aggregation as the host adapter: ``reachable``
        on the first ``sat`` (with the dumped witness or ``None``),
        ``unreachable`` only when every property answers ``unsat``.
        ``TimeoutExpired`` propagates after the container is killed."""
        if not self.available():
            raise PonoMsatUnavailable(
                f"docker image {self.image} not runnable")
        text = (system.decode("utf-8")
                if isinstance(system, (bytes, bytearray)) else str(system))
        all_unsat = True
        for prop in range(max(1, _count_bads(text))):
            verdict, witness = self._decide_prop(text, mode, k, prop)
            if verdict is Verdict.REACHABLE:
                return verdict, witness
            all_unsat = all_unsat and verdict is Verdict.UNREACHABLE
        return (Verdict.UNREACHABLE if all_unsat
                else Verdict.UNKNOWN), None

    def _decide_prop(self, text: str, mode: str, k: int,
                     prop: int) -> tuple[Verdict, str | None]:
        from ..core import ledger

        work = tempfile.mkdtemp(prefix="pono-msat-")
        path = os.path.join(work, "q.btor2")
        witpath = os.path.join(work, "q.wit")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        name = f"pono-msat-{uuid.uuid4().hex[:12]}"
        # --smt-solver msat is mandatory, not incidental: the engine
        # refuses any other backend ("MsatIC3IA only supports mathsat
        # solver"), and forcing it on every mode — probes included —
        # is what makes the declared (pono, smt-switch, mathsat)
        # lineage true of every verdict this adapter books.
        cmd = ["docker", "run", "--rm", "--name", name,
               "--platform", "linux/amd64", "--memory", PONO_MSAT_MEM,
               "-v", f"{work}:/w", self.image,
               "pono", "-e", mode, "--smt-solver", "msat",
               "-k", str(k), "-p", str(prop),
               "--witness", "--dump-btor2-witness", "/w/q.wit",
               "/w/q.btor2"]
        try:
            with ledger.timed(
                    "decide",
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    engine=f"pono-msat-{mode}", language="btor2",
                    k=None, prop=prop, size=len(text)):
                try:
                    proc = subprocess.run(cmd, capture_output=True,
                                          text=True,
                                          timeout=UNBOUNDED_WALL_S)
                except subprocess.TimeoutExpired:
                    subprocess.run(["docker", "kill", name],
                                   capture_output=True, timeout=60)
                    raise
            verdict = parse_verdict(proc.stdout + "\n" + proc.stderr)
            witness = None
            if verdict is Verdict.REACHABLE and os.path.exists(witpath):
                with open(witpath, encoding="utf-8") as f:
                    witness = f.read()
            return verdict, witness
        finally:
            shutil.rmtree(work, ignore_errors=True)
