"""CBMC as an independent C-level checker (SOLVERS.md §7; ROUTES.md §3).

CBMC consumes ANSI C directly and bounded-model-checks the reachability of an
assertion failure. It is the independent C oracle the ``c-riscv`` differential
(``gurdy.pairs.c_riscv.differential``) uses to re-establish the opaque compile
head's fidelity per run: a property decided on the C *source* by CBMC is
cross-checked against the same property decided on the lowered RISC-V program
(through the long route / the shared interpreter). Agreement lifts the
``reproducible`` compile hop to ``checked`` for that run; a disagreement that
is not a documented C-undefined-but-RISC-V-defined behavior localizes a fault
to the compile hop.

Located via ``$CBMC`` or PATH and gated on the pinned dev image (DOCKER.md).
The verdict and property-class parsers are pure and unit-tested; the runner is
injectable so the differential is exercised without the binary present.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

from ..core.solver import Verdict

# CBMC models the LP64 data model with ``--64`` so ``long`` is 64-bit, matching
# the rv64 register the long route checks ``reg_eq`` against.
DEFAULT_ARGS = ("--64",)

# The C-undefined behaviors RISC-V nonetheless *defines* (languages/riscv
# brief): signed overflow wraps, shift amounts mask, INT_MIN/-1 and div/rem by
# zero have defined results. CBMC reports these as these property classes.
DOCUMENTED_UB = frozenset({"overflow", "division-by-zero", "undefined-shift"})

# CBMC's UB checks, enabling exactly the classes above.
UB_CHECK_ARGS = ("--signed-overflow-check", "--div-by-zero-check",
                 "--undefined-shift-check")

_PROP = re.compile(r"^\[(?P<id>[\w.\-]+)\]\s.*:\s+(?P<status>SUCCESS|FAILURE|UNKNOWN)\s*$")


class CbmcUnavailable(RuntimeError):
    """Raised when ``cbmc`` cannot be located."""


def find_cbmc() -> str | None:
    return os.environ.get("CBMC") or shutil.which("cbmc")


def parse_verdict(output: str) -> Verdict:
    """``VERIFICATION FAILED`` (an assertion failure is reachable) -> REACHABLE;
    ``VERIFICATION SUCCESSFUL`` (all assertions hold) -> UNREACHABLE; else
    UNKNOWN. The mapping mirrors the BTOR2 ``bad``-reachability convention so a
    CBMC verdict is directly comparable to the bridged/long-route one."""
    for line in output.splitlines():
        tok = line.strip()
        if tok == "VERIFICATION FAILED":
            return Verdict.REACHABLE
        if tok == "VERIFICATION SUCCESSFUL":
            return Verdict.UNREACHABLE
    return Verdict.UNKNOWN


def failed_property_classes(output: str) -> set[str]:
    """The CBMC property classes that FAILED, e.g. ``{"overflow",
    "undefined-shift", "assertion"}``. The class is the middle component of a
    property id like ``main.overflow.1`` / ``main.division-by-zero.2``."""
    classes: set[str] = set()
    for line in output.splitlines():
        m = _PROP.match(line.strip())
        if m and m.group("status") == "FAILURE":
            parts = m.group("id").split(".")
            if len(parts) >= 3:
                classes.add(".".join(parts[1:-1]))
    return classes


class CbmcChecker:
    id = "cbmc"
    lineage = ("cprover",)  # independence accounting (solvers/brief.py)

    def __init__(self, binary: str | None = None, args: tuple[str, ...] = DEFAULT_ARGS) -> None:
        self.binary = binary or find_cbmc()
        self.args = args

    def available(self) -> bool:
        return bool(self.binary) and (
            os.path.exists(self.binary) or shutil.which(self.binary) is not None
        )

    def run(self, c_source: str, extra_args: tuple[str, ...] = ()) -> str:
        """Run cbmc on ``c_source`` and return its combined output."""
        if not self.available():
            raise CbmcUnavailable("cbmc not found (set $CBMC)")
        with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as f:
            f.write(c_source)
            path = f.name
        try:
            proc = subprocess.run([self.binary, *self.args, *extra_args, path],
                                  capture_output=True, text=True, timeout=300)
        finally:
            os.unlink(path)
        return proc.stdout + "\n" + proc.stderr

    def decide(self, c_source: str, extra_args: tuple[str, ...] = ()) -> Verdict:
        return parse_verdict(self.run(c_source, extra_args))
