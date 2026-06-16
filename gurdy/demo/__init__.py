"""A trivial registered pair that exercises the MVP-1 rig end-to-end
(FRAMEWORK.md §6 acceptance).

This is **not** one of the real registered pairs (those are built by per-pair
agents against PAIRING.md). It is a one-construct demo whose only purpose is
to show the framework's three capabilities compose: ``compile`` (T) ->
``decide`` (z3) -> carry-back + ``align`` (the square), deterministically.

Demo languages:
  - ``demo-nat``  : a program is an int n in [0, 255]; its meaning is the value
                    n. Source interpreter -> a one-step trace ``[{"x": n}]``.
  - ``demo-smt``  : SMT-LIB (a reasoning target). Target interpreter realizes a
                    solver model into a trace ``[{"x": model["x"]}]``.

Pair ``demo-nat-smt``: translate n to an SMT-LIB script asserting ``x == n``
over an 8-bit vector. ``decide`` returns sat with model ``x = n``; carry-back
maps the model back to the source observable; the square commutes under
``π = {x}``.
"""

from __future__ import annotations

from typing import Any

from ..core.registry import Language, Pair, register_language, register_pair
from ..core.types import Projection, Trace

MASK = 0xFF


def _nat_source_interpreter(n: int, *_args: Any, **_kw: Any) -> Trace:
    return [{"x": n & MASK}]


def _smt_target_interpreter(model: dict[str, Any], *_args: Any, **_kw: Any) -> Trace:
    return [{"x": int(model.get("x", 0)) & MASK}]


def _translate(n: int) -> bytes:
    v = n & MASK
    script = (
        "(set-logic QF_BV)\n"
        "(declare-const x (_ BitVec 8))\n"
        f"(assert (= x (_ bv{v} 8)))\n"
        "(check-sat)\n"
    )
    return script.encode("utf-8")


def _carry_back(target_trace: Trace) -> Trace:
    # The demo target observable is already the source observable, so L is a
    # re-projection onto {x}.
    return [{"x": int(s["x"]) & MASK} for s in target_trace]


def register() -> None:
    register_language(Language("demo-nat", source_interpreter=_nat_source_interpreter))
    register_language(Language("demo-smt", target_interpreter=_smt_target_interpreter))
    register_pair(
        Pair(
            id="demo-nat-smt",
            source="demo-nat",
            target="demo-smt",
            translator=_translate,
            target_to_source=_carry_back,
            projection=Projection(("x",)),
            fidelity="checked",
            translator_version="1",
        )
    )


register()
