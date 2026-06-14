"""btor2_smtlib — bridge hop  btor2 -> smt-lib.

Here ``btor2`` sits on a *source* edge, but no Sail-grade oracle exists for
it; trust is **differential** via decide-both-ways (native BTOR2 vs the
bridged SMT-LIB must agree). A transparent, schema-auditable unroll.
"""

from __future__ import annotations

from typing import Any

from gurdy.core.hop import Hop as HopEdge, Tier, register
from gurdy.hops.base import Hop, NotYetImplemented, TranslateResult, LiftResult

register(HopEdge("btor2_smtlib", "bridge", "btor2", "smt-lib", Tier.transparent))


class Btor2Smtlib(Hop):
    id = "btor2_smtlib"
    kind = "bridge"
    in_lang = "btor2"
    out_lang = "smt-lib"

    def translate(self, source: Any, question: dict, *, path: str = "own") -> TranslateResult:
        # TODO(agent): deterministic unroll of a BTOR2 transition system to
        # SMT-LIB (QF_BV + arrays). Schema-auditable => transparent.
        raise NotYetImplemented("btor2_smtlib.translate [TODO(agent)]")

    def lift(self, artifact: Any, raw_solver_result: Any) -> LiftResult:
        raise NotYetImplemented("btor2_smtlib.lift [TODO(agent)]")


HOP = Btor2Smtlib()
