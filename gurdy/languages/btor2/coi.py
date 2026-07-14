"""Cone-of-influence analysis and the reduction advisor for the BTOR2 hub
(languages/btor2; the abstraction dial of ROUTES.md §6's tradeoff report).

**Cone of influence.** The states a question can possibly depend on: start
from the supports of the ``bad`` conditions under question *and of every
``constraint``* (a constraint restricts which runs are valid, so a state
feeding one can change reachability — excluding constraints here would
make the free set unsound), then close backwards through the ``next`` and
``init`` functions. States outside the cone are the **free havoc set**:
rewriting their ``next`` to a fresh input (the ``btor2-havoc`` pair)
cannot change the question's signal on any run — an over-approximation
with zero precision loss for this question. That claim is executable and
is locked by a test, not just asserted (``tests/test_reduction_advisor``).

**The ladder.** States inside the cone, ranked by distance from the
question (0 = in a ``bad``/``constraint`` support; ``d+1`` = first reached
through the ``next``/``init`` support of a distance-``d`` state), are the
CEGAR dial: a player abstracting aggressively havocs a prefix of the
ladder — farthest first — and a spurious counterexample demands
un-havocking from the end of that prefix.

**Interval seeds.** Observed per-state ``[min, max]`` over deterministic
plus seeded-random runs — *candidates* for ``btor2-interval``'s declared
ranges, in exactly that brief's falsifiable-claim design: a seed is not an
invariant, the lax square is what corroborates or refutes it.

Everything here is **advisory and read-only**: pure syntactic analysis
plus shared-interpreter runs; no solver, no registration, no choice. The
output is plain data the player may pass to ``translate(params)``
unchanged — or ignore.
"""

from __future__ import annotations

from typing import Any, Iterable

from .eval import interpret
from .model import Bitvec, System, from_text

_STOP_OPS = {"state", "input"}  # support-walk leaves; states re-enter by level


def _as_system(system: Any) -> System:
    if isinstance(system, System):
        return system
    text = system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
    return from_text(text)


def _label(node) -> str:
    return node.symbol or f"n{node.id}"


def _next_and_init(sys: System) -> dict[int, list[int]]:
    """Per state id, the value roots its evolution reads: the ``next``
    function and the ``init`` value (both, when present)."""
    roots: dict[int, list[int]] = {}
    for n in sys.nodes.values():
        if n.op in ("next", "init") and len(n.refs) >= 2:
            roots.setdefault(n.refs[0], []).append(n.refs[1])
    return roots


def _state_support(sys: System, root_ids: Iterable[int]) -> set[int]:
    """The state ids in the combinational support of the given value roots
    (DFS through node refs, stopping at states and inputs)."""
    seen: set[int] = set()
    states: set[int] = set()
    stack = [r for r in root_ids if r in sys.nodes]
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        node = sys.nodes[nid]
        if node.op == "state":
            states.add(nid)
            continue
        if node.op in _STOP_OPS:
            continue
        stack.extend(r for r in node.refs if r in sys.nodes)
    return states


def cone_of_influence(system: Any, bads: list[int] | None = None) -> dict[int, int]:
    """``{state id -> distance}`` for every state the question depends on.

    ``bads`` selects bad node ids (default: all). Every ``constraint``'s
    support is always a root: constraints gate which runs are valid, so
    they are part of any question's cone.
    """
    sys = _as_system(system)
    chosen = [n for n in sys.bads() if bads is None or n.id in bads]
    roots = [n.refs[0] for n in chosen] + [n.refs[0] for n in sys.constraints()]
    evolution = _next_and_init(sys)

    dist: dict[int, int] = {}
    frontier = _state_support(sys, roots)
    level = 0
    while frontier:
        for sid in frontier:
            dist.setdefault(sid, level)
        next_roots = [r for sid in frontier for r in evolution.get(sid, [])]
        frontier = _state_support(sys, next_roots) - set(dist)
        level += 1
    return dist


def suggest_reduction(system: Any, bads: list[int] | None = None, *,
                      k: int = 8, samples: int = 4,
                      seed: int = 0xC0FFEE) -> dict[str, Any]:
    """The advisory reduction report for a question on ``system``:
    the cone with distances, the free havoc set (bit-vector states only —
    the havoc pair types array states ``unsupported``), the refinement
    ladder (farthest first), and interval seeds from observed runs.
    Deterministic for fixed arguments; advisory only — the parameters are
    the player's to pass on, amend, or ignore."""
    import random as _random

    sys = _as_system(system)
    dist = cone_of_influence(sys, bads)
    bv = {n.id: _label(n) for n in sys.states()
          if isinstance(sys.sorts.get(n.sort), Bitvec)}
    arrays = {n.id: _label(n) for n in sys.states() if n.id not in bv}

    cone = {bv.get(sid, arrays.get(sid, f"n{sid}")): d
            for sid, d in dist.items()}
    free_bv = sorted(lbl for sid, lbl in bv.items() if sid not in dist)
    free_arrays = sorted(lbl for sid, lbl in arrays.items() if sid not in dist)
    ladder = [lbl for _d, lbl in
              sorted(((d, bv[sid]) for sid, d in dist.items() if sid in bv),
                     key=lambda t: (-t[0], t[1]))]

    # Observed bounds: the deterministic run plus seeded-random input runs
    # (constraint truncation applies, so bounds are over valid prefixes).
    inputs = [n for n in sys.nodes.values() if n.op == "input"]
    rng = _random.Random(seed)
    bindings: list[dict[str, Any]] = [{"steps": k + 1}]
    for _ in range(samples if inputs else 0):
        bindings.append({"steps": k + 1, "inputs": {
            c: {n.id: rng.getrandbits(sys.sorts[n.sort].width) for n in inputs}
            for c in range(k + 1)}})
    lo: dict[str, int] = {}
    hi: dict[str, int] = {}
    for binding in bindings:
        for row in interpret(sys, binding):
            for lbl in bv.values():
                if lbl in row:
                    v = int(row[lbl])
                    lo[lbl] = v if lbl not in lo else min(lo[lbl], v)
                    hi[lbl] = v if lbl not in hi else max(hi[lbl], v)
    seeds = {lbl: [lo[lbl], hi[lbl]] for lbl in sorted(lo)}

    return {
        "cone": dict(sorted(cone.items())),
        "free_havoc": free_bv,
        "free_array_states": free_arrays,
        "refinement_ladder": ladder,
        "interval_seeds": seeds,
        "note": ("advisory only: free_havoc states cannot change the "
                 "question's signal (zero-precision-loss havoc set); the "
                 "ladder lists cone states farthest-from-the-question "
                 "first; interval seeds are observed bounds, candidates "
                 "the lax square corroborates or refutes — the player "
                 "passes parameters on, amends them, or ignores them"),
    }
