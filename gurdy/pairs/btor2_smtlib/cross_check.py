"""Multi-path cross-check for a BTOR2 model — the "many paths, one question"
translator-bug detector (``DESIGN_generalized_pairs.md`` §6), made reusable
(Stage 7.F).

Decide the *same* BTOR2 model two independent ways and report whether they agree:

- ``native``  — BTOR2 → z3 directly (``gurdy.core.btor2`` BMC).
- ``bridged`` — BTOR2 → SMT-LIB → z3 (this pair, the BTOR2 ↔ SMT-LIB bridge).

The two paths share only the BTOR2 input and the underlying SMT solver; their
*encoders* are independent. Agreement corroborates both encoders; a disagreement
localizes a translator/encoder bug to the diverging path. Because it operates on
BTOR2 *bytes*, it cross-checks any pair's translator output (riscv, aarch64,
wasm, …) through the shared hub — the populated-hub payoff: the translators
start checking each other.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrossCheck:
    """Result of deciding one BTOR2 model via several independent paths."""

    bound: int
    verdicts: dict[str, str]  # path name -> verdict (reachable/unreachable/unknown/error)
    agree: bool

    @property
    def verdict(self) -> str | None:
        """The single agreed verdict, or ``None`` when the paths disagree."""
        return next(iter(self.verdicts.values())) if self.agree and self.verdicts else None

    def summary(self) -> str:
        body = ", ".join(f"{k}={v}" for k, v in sorted(self.verdicts.items()))
        if self.agree:
            return f"AGREE @bound={self.bound}: {self.verdict}  [{body}]"
        return f"DISAGREE @bound={self.bound}: {body}  -- translator/encoder bug"


def _native_verdict(text: str, bound: int) -> str:
    from gurdy.core.btor2.btor2_to_z3 import bmc, compile_btor2
    from gurdy.core.btor2.parser import from_text

    verdict, _ = bmc(compile_btor2(from_text(text).model), bound)
    return verdict


def _bridged_verdict(text: str, bound: int) -> str:
    from gurdy.core.pair import get_pair, register_pair
    from gurdy.core.tools.compile import compile_spec
    from gurdy.core.tools.dispatch import dispatch
    from gurdy.pairs.btor2_smtlib import PAIR
    from gurdy.pairs.btor2_smtlib.spec import Btor2SmtSpec

    try:  # robust to a cleared registry (e.g. tests/core)
        get_pair(PAIR.identifier)
    except KeyError:
        register_pair(PAIR)
    spec = Btor2SmtSpec(bound=bound)
    return dispatch(compile_spec(spec, text), spec.analysis).verdict


_PATHS = {"native": _native_verdict, "bridged": _bridged_verdict}


def cross_check(
    btor2: bytes | str, *, bound: int, paths: tuple[str, ...] = ("native", "bridged")
) -> CrossCheck:
    """Decide ``btor2`` via each named path at ``bound`` and report agreement."""
    text = btor2.decode("utf-8", "replace") if isinstance(btor2, (bytes, bytearray)) else btor2
    verdicts = {name: _PATHS[name](text, bound) for name in paths}
    agree = len(set(verdicts.values())) <= 1
    return CrossCheck(bound=bound, verdicts=verdicts, agree=agree)


__all__ = ["CrossCheck", "cross_check"]
