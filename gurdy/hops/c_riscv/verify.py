"""Independent C-source verification via CBMC — the chain's ``checked``-tier
cross-check.

Hop 1 (``compile_c``) is trust tier ``reproducible``: the same C produces
the same ELF, but nothing *checks* that the ELF (hence the chain's verdict)
faithfully reflects the C. This module adds the independent check that
raises hop 1 toward ``checked``: it runs CBMC on the **same C source**, in
the **same pinned image** (so the check is reproducible too), and yields a
trap-reachability verdict in the corpus vocabulary.

In commuting-square terms it is a *second path* from C to a verdict:

        C  ──gcc──▶ RV64 ELF ──pair──▶ BTOR2 ──solver──▶ verdict   (the chain)
        │                                                  ▲
        └────────────────── CBMC ──────────────────────────┘        (this hop)

The two paths should agree — **except** where C-level UB and RV64-defined
behavior genuinely differ (signed overflow, div-by-zero sentinels, …). CBMC
reasons over C's standard semantics (and flags UB), while the chain reasons
over the RV64 lowering that *defines* those cases. So a disagreement is only
a fault when the task is **not** lowering-sensitive; on a lowering-sensitive
task it is the documented semantic gap, and actively demonstrates the chain
reasoning about something a C-level verifier cannot. ``classify_differential``
encodes exactly that rule.

This is the reproducible, chain-integrated sibling of the bench scripts
``condition_d_reference.py`` (verdict vs *expected*, local CBMC) and
``baselines/cbmc.py`` (Pareto baseline): here CBMC is pinned by image digest
and compared against the *chain's own* verdict.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass

from gurdy.hops.c_riscv.compile import ToolchainUnavailable, toolchain_available
from gurdy.hops.c_riscv.toolchain import ToolchainPin, default_pin

_CBMC = "cbmc"
_VERIFY_TIMEOUT_S = 120

# Markers framing the per-run output so version and verdict are separable
# from a single container invocation.
_VER_MARK = "##CBMC_VERSION##"
_RUN_MARK = "##CBMC_RUN##"


class CbmcVerifyError(RuntimeError):
    """CBMC could not be run or produced no parseable verdict."""


# ---------------------------------------------------------------------------
# Bare-metal C -> CBMC dialect rewrite
#
# Ported from bench/riscv-btor2/corpus/_emit_cbmc.py so the hop is
# self-contained (no dependency on bench scripts). The corpus uses bare-metal
# idioms CBMC can't drive: `void _start(void)`, `if (cond) trap();`, an
# `ebreak` halt, and a `noreturn` extern `trap`. We rewrite the trap-call
# into a `__CPROVER_assert(!(cond), ...)` so CBMC checks the same
# trap-reachability property the chain's synthesized spec targets.
# ---------------------------------------------------------------------------

_RULES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"^extern void trap\([^)]*\)[^;]*;\s*$", re.MULTILINE), ""),
    (
        re.compile(r"^void trap\(void\)\s*\{[^}]*\}\s*$", re.MULTILINE | re.DOTALL),
        "",
    ),
    (re.compile(r"void _start\(void\)"), "int main(void)"),
    (
        re.compile(r"if\s*\(([^()]+)\)\s*trap\(\)\s*;"),
        r'__CPROVER_assert(!(\1), "trap reachable");',
    ),
    (re.compile(r"__asm__\s+volatile\s*\([^)]*\)\s*;"), ""),
    (re.compile(r"__builtin_unreachable\(\)\s*;"), ""),
)


def to_cbmc_dialect(c_source: str) -> str:
    """Rewrite a bare-metal corpus C source into the CBMC dialect.

    Mirrors ``_emit_cbmc.py::rewrite``: drops the ``trap`` decl/def, renames
    ``_start`` to ``main``, turns ``if (cond) trap();`` into a
    ``__CPROVER_assert(!(cond), "trap reachable")``, and strips inline asm.
    """
    out = c_source
    for pat, repl in _RULES:
        out = pat.sub(repl, out)
    return re.sub(r"\n{3,}", "\n\n", out)


# ---------------------------------------------------------------------------
# Result + verdict parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CbmcProvenance:
    """Everything needed to re-derive the CBMC verdict."""

    image: str
    digest: str
    tool: str
    tool_version: str
    unwind: int
    source_sha256: str

    def to_jsonable(self) -> dict:
        return {
            "image": self.image,
            "digest": self.digest,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "unwind": self.unwind,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True)
class CbmcResult:
    """A CBMC trap-reachability verdict on a C source.

    ``verdict`` is in the corpus vocabulary: ``reachable`` (assertion
    violated), ``unreachable`` (verification successful), or ``unknown``
    (inconclusive / bounded-only / unparseable).
    """

    verdict: str
    notes: str
    provenance: CbmcProvenance
    raw_excerpt: str


def _unwind_for(bound: int) -> int:
    """Per-loop unroll depth from a task's BMC bound. Mirrors
    ``condition_d_reference``: a generous multiple of the bound so loops that
    aren't tightly bounded don't trip CBMC's unwinding-assertion warning;
    capped at 256."""
    return min(max(int(bound), 30), 256)


def parse_cbmc_verdict(text: str) -> tuple[str, str]:
    """Map CBMC textual output to ``(verdict, notes)`` in corpus vocabulary.

    Scans from the end for the headline line (a multi-property run can print
    several). ``FAILED`` wins over ``SUCCESSFUL`` — any violated property
    means the trap-reachability assertion's negation does not hold for all
    paths, which in the corpus's single-bad-clause framing is ``reachable``.
    """
    for line in reversed(text.splitlines()):
        s = line.strip()
        if s == "VERIFICATION FAILED":
            return ("reachable", "VERIFICATION FAILED")
        if s == "VERIFICATION SUCCESSFUL":
            return ("unreachable", "VERIFICATION SUCCESSFUL")
        if s.startswith("VERIFICATION INCONCLUSIVE"):
            return ("unknown", "VERIFICATION INCONCLUSIVE")
    if "PARSING ERROR" in text:
        return ("unknown", "PARSING ERROR")
    return ("unknown", "no verdict line in output")


def cbmc_verify(
    c_source: bytes | str,
    *,
    bound: int = 20,
    pin: ToolchainPin | None = None,
    timeout: int = _VERIFY_TIMEOUT_S,
) -> CbmcResult:
    """Run CBMC on ``c_source`` in the pinned image; return a
    :class:`CbmcResult`.

    The source is rewritten to the CBMC dialect, then verified with
    ``cbmc <file> --unwind <n>`` where ``n`` derives from ``bound``. CBMC's
    default check set (fixed by the pinned image) flags C-level UB — which is
    precisely what surfaces the lowering gap on UB tasks. Raises
    ``ToolchainUnavailable`` if the pinned image is absent, ``CbmcVerifyError``
    on a run failure.
    """
    pin = pin or default_pin()
    if not toolchain_available(pin):
        raise ToolchainUnavailable(
            f"pinned toolchain {pin.ref} not available (CBMC verify needs it)"
        )
    src = c_source.encode() if isinstance(c_source, str) else bytes(c_source)
    dialect = to_cbmc_dialect(src.decode("utf-8", errors="replace")).encode()
    unwind = _unwind_for(bound)

    # Source on stdin; version + verdict on stdout, framed by markers, in one
    # container run. CBMC exits non-zero on FAILED, so we don't gate on it.
    # The markers are single-quoted: a word starting with '#' is a comment
    # in POSIX sh, so an unquoted `echo ##MARK##` would print nothing.
    script = (
        f"cat > /tmp/t.c; echo '{_VER_MARK}'; {_CBMC} --version; "
        f"echo '{_RUN_MARK}'; {_CBMC} /tmp/t.c --unwind {unwind} 2>&1"
    )
    cmd = ["docker", "run", "--rm", "-i", pin.ref, "sh", "-c", script]
    try:
        proc = subprocess.run(
            cmd, input=dialect, capture_output=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise CbmcVerifyError(f"cbmc timed out after {timeout}s") from exc

    out = proc.stdout.decode("utf-8", errors="replace")
    if _RUN_MARK not in out:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise CbmcVerifyError(
            f"cbmc produced no run output (exit {proc.returncode}); "
            f"stderr:\n{stderr[-1000:]}"
        )
    ver_part, run_part = out.split(_RUN_MARK, 1)
    tool_version = ver_part.split(_VER_MARK, 1)[-1].strip().splitlines()
    version = tool_version[0].strip() if tool_version else "unknown"
    verdict, notes = parse_cbmc_verdict(run_part)

    return CbmcResult(
        verdict=verdict,
        notes=notes,
        provenance=CbmcProvenance(
            image=pin.image,
            digest=pin.digest,
            tool=_CBMC,
            tool_version=version,
            unwind=unwind,
            source_sha256=hashlib.sha256(src).hexdigest(),
        ),
        raw_excerpt=run_part.strip()[:4096],
    )


# ---------------------------------------------------------------------------
# Differential classification (pure)
# ---------------------------------------------------------------------------


def classify_differential(
    chain_verdict: str, cbmc_verdict: str, *, lowering_sensitive: bool
) -> str:
    """Classify a chain-vs-CBMC verdict pair.

    Returns one of:

    - ``"agree"`` — both verdicts definite and equal (independent
      corroboration of the chain).
    - ``"expected-divergence"`` — definite but unequal, on a
      ``lowering_sensitive`` task: the documented C-UB vs RV64-defined gap
      (CBMC flags UB; the chain reasons over the RV64 lowering). Not a fault.
    - ``"fault"`` — definite but unequal, on a task that is **not**
      lowering-sensitive: a real disagreement, localized to hop 1 (the
      gcc/UB hop — hop 2 is independently checked by alignment).
    - ``"inconclusive"`` — either side is not a definite reachable/
      unreachable (e.g. CBMC ``unknown`` / chain ``unknown``); nothing to
      score.
    """
    definite = {"reachable", "unreachable"}
    if chain_verdict not in definite or cbmc_verdict not in definite:
        return "inconclusive"
    if chain_verdict == cbmc_verdict:
        return "agree"
    return "expected-divergence" if lowering_sensitive else "fault"


__all__ = [
    "CbmcProvenance",
    "CbmcResult",
    "CbmcVerifyError",
    "cbmc_verify",
    "classify_differential",
    "parse_cbmc_verdict",
    "to_cbmc_dialect",
]
