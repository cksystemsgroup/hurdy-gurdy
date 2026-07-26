"""The ``btor2-interval`` translator — interval (range) abstraction over BTOR2.

Input: ``{"system": <BTOR2 text/bytes>, "intervals": {state symbol or id ->
(lo, hi)}}``. For each mapped state of width ``w`` the translator deletes the
state's ``next`` line and appends a fresh ``input`` (symbol ``iv_<label>``)
plus the const/arith nodes computing ``next(s) := lo + urem(iv, hi − lo +
1)`` — a free choice confined to the caller-declared range. Where
``btor2-havoc`` deletes all information about a state's update,
``btor2-interval`` retains the one fact the player asserts: the state stays
in ``[lo, hi]``.

Special cases (the brief's, pairs/btor2-interval/README.md): the full range
``[0, 2^w − 1]`` emits ``next(s) := iv`` directly — havoc's exact rewrite,
bypassing the ``urem`` whose range-size constant would not fit at width
``w`` — and the singleton ``[c, c]`` still emits the uniform shape
(``urem(iv, 1) = 0``, so ``next(s) := c``). The range-size constant
``hi − lo + 1`` is emitted at width ``w``.

The interval map is a **caller parameter**, never a heuristic
(ARCHITECTURE.md §4): which states to confine, and to what ranges, is the
player's refinement decision (``gurdy suggest-reduction`` emits observed
``[min, max]`` seeds as candidates). Entries are resolved deterministically,
processed in ascending state-id order, and fresh ids are assigned
sequentially past the largest existing id, so the output bytes are a pure
function of the input. The empty map is the identity. v0.1 keeps every
source value node (the havoc-style dead-update sweep is a v0.2 candidate)
and emits no ``constraint`` nodes (the brief's v1 design; the
constraint-based variant is a v2 decision, not a silent substitution).

Typed partiality vs caller error: an array-sorted state is
``Unsupported("interval.array-state")`` (no array-valued inputs in the
shared interpreter — havoc's gap) and an in-width wrapped range ``hi < lo``
is ``Unsupported("interval.wraparound")`` (a meaningful construct the v1
does not implement — the brief's coverage target types both at registration
scope). An unknown state name, a non-integer bound, or a bound outside the
state's width is a ``ValueError`` (caller error, not coverage).
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.model import Bitvec, Node, System, from_text

__all__ = ["translate", "interval_plan"]


def _text(system: Any) -> str:
    if isinstance(system, (bytes, bytearray)):
        return system.decode("utf-8")
    return str(system)


def _label(node: Node) -> str:
    return node.symbol or f"n{node.id}"


def _resolve(sys: System, intervals: Any) -> list[tuple[Node, int, int, int]]:
    """Resolve interval entries (state symbols or ids -> (lo, hi)) to
    ``(state, lo, hi, width)``, deduped by state, in ascending state-id
    order. Validation per the brief: bounds are ints with ``0 <= lo <= hi <
    2^w``; ``hi < lo`` inside the width is the typed wraparound gap."""
    by_label = {_label(s): s for s in sys.states()}
    chosen: dict[int, tuple[Node, int, int, int]] = {}
    for entry, bounds in dict(intervals or {}).items():
        if isinstance(entry, int):
            node = sys.nodes.get(entry)
            if node is None or node.op != "state":
                raise ValueError(f"btor2-interval: no state with id {entry}")
        else:
            node = by_label.get(str(entry))
            if node is None:
                raise ValueError(f"btor2-interval: no such state: {entry!r}")
        sort = sys.sorts.get(node.sort)
        if not isinstance(sort, Bitvec):
            raise Unsupported("btor2-interval", "interval.array-state")
        lo, hi = bounds
        if not (isinstance(lo, int) and isinstance(hi, int)):
            raise ValueError(f"btor2-interval: non-integer bounds {bounds!r} "
                             f"for state {_label(node)!r}")
        top = (1 << sort.width) - 1
        if not (0 <= lo <= top and 0 <= hi <= top):
            raise ValueError(
                f"btor2-interval: bounds {bounds!r} outside width "
                f"{sort.width} for state {_label(node)!r}")
        if hi < lo:
            raise Unsupported("btor2-interval", "interval.wraparound")
        chosen[node.id] = (node, lo, hi, sort.width)
    return [chosen[i] for i in sorted(chosen)]


def _max_id(text: str) -> int:
    top = 0
    for line in text.split("\n"):
        toks = line.split()
        if toks and toks[0].isdigit():
            top = max(top, int(toks[0]))
    return top


def interval_plan(program: dict[str, Any]) -> tuple[
        System, str, list[tuple[Node, int, int, tuple[int, ...]]]]:
    """The deterministic rewrite plan: the parsed source system, its text,
    and per mapped state ``(state, lo, hi, fresh ids)`` — ids are ``(input,
    next)`` for the full-range case and ``(input, const_lo, const_range,
    urem, add, next)`` otherwise, assigned sequentially past the largest
    existing id in ascending state-id order. Shared by the translator and
    the witness embedding so the embedding never depends on the (possibly
    mutated) translator output."""
    text = _text(program["system"])
    sys = from_text(text)
    resolved = _resolve(sys, program.get("intervals", {}))
    nxt = _max_id(text) + 1
    plan: list[tuple[Node, int, int, tuple[int, ...]]] = []
    for state, lo, hi, width in resolved:
        n = 2 if (lo, hi) == (0, (1 << width) - 1) else 6
        plan.append((state, lo, hi, tuple(range(nxt, nxt + n))))
        nxt += n
    return sys, text, plan


def translate(program: dict[str, Any]) -> bytes:
    sys, text, plan = interval_plan(program)
    if not plan:  # empty interval map: the identity rewrite
        return text.encode("utf-8")
    mapped = {s.id for s, _, _, _ in plan}
    kept: list[str] = []
    for line in text.split("\n"):
        toks = line.split()
        if (len(toks) >= 4 and toks[1] == "next" and toks[3].isdigit()
                and int(toks[3]) in mapped):
            continue
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    for state, lo, hi, ids in plan:
        sort = state.sort
        if len(ids) == 2:  # full range: havoc's exact rewrite, no urem
            iv, nx = ids
            kept.append(f"{iv} input {sort} iv_{_label(state)}")
            kept.append(f"{nx} next {sort} {state.id} {iv}")
            continue
        iv, c_lo, c_rng, rem, add, nx = ids
        kept.append(f"{iv} input {sort} iv_{_label(state)}")
        kept.append(f"{c_lo} constd {sort} {lo}")
        kept.append(f"{c_rng} constd {sort} {hi - lo + 1}")
        kept.append(f"{rem} urem {sort} {iv} {c_rng}")
        kept.append(f"{add} add {sort} {c_lo} {rem}")
        kept.append(f"{nx} next {sort} {state.id} {add}")
    return ("\n".join(kept) + "\n").encode("utf-8")
