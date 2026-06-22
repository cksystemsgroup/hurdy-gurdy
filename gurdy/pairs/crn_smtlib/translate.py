"""CRN -> SMT-LIB translator ``T``: schema-determined unrolling of the discrete
(Petri-net) semantics to a caller-supplied step bound ``k`` (pairs/crn-smtlib
brief; PAIRING.md §2).

**Minimal vertical slice (PAIRING.md §1 "start thin").** Exactly one in-scope
reaction class is translated end-to-end: a single **unimolecular reaction**
``A -> B`` — one reactant consumed with coefficient 1, one product produced with
coefficient 1, the two species distinct. The network must consist of exactly
that one reaction. **Every other construct hard-aborts** with a typed
``Unsupported`` (BENCHMARKS.md §3): bimolecular / non-unit reactants
(``A + B``, ``2 A``), multiple or non-unit products (catalysis, ``A -> 2 B``),
synthesis / degradation (empty side), self-loops (``A -> A``), and any network
with zero or more than one reaction.

The emitted ``QF_LIA`` script is determined **byte-for-byte** by
``(network, k, target)`` and the fixed schema below (``predicted`` fidelity):
nothing adaptive, nothing hashed, nothing timestamped. Emission order is fixed —
steps ascending ``0..k``, species in network declaration order.

Schema (for the one reaction ``R0 : A -> B``)
---------------------------------------------
Variables (emitted steps-major, species in network order):
  * ``x<species>_<t>`` : ``Int``  population of the species after step ``t``,
    for ``t = 0 .. k``;
  * ``f0_<t>`` : ``Bool``  did ``R0`` fire during step ``t``, for ``t = 0 .. k-1``.
Constraints (emitted in this fixed order):
  1. init   ``(= x<s>_0 <init count>)`` for every species ``s``;
  2. domain ``(>= x<s>_t 0)`` for every species ``s`` and ``t = 0 .. k``;
  3. trans  for ``t = 0 .. k-1``: ``f0_t`` requires ``xA_t >= 1`` (enabledness),
            and every species' next value is its ``ite``-guarded update — the
            reactant ``A`` decrements, the product ``B`` increments, every other
            (spectator) species is preserved — when ``f0_t`` holds, else preserved;
  4. bad    a disjunction over steps ``0..k`` of "the target marking holds here".
The script is ``sat`` iff some firing schedule reaches the target within ``k``.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...languages.crn.model import Network, Reaction, as_network


def _check_in_scope(net: Network) -> Reaction:
    """Restrict to the one in-scope reaction class; hard-abort everything else
    with a typed ``Unsupported`` (BENCHMARKS.md §3). Returns the single
    unimolecular reaction ``A -> B``."""
    if len(net.reactions) == 0:
        raise Unsupported("crn", "empty-network", "no reactions to unroll")
    if len(net.reactions) > 1:
        raise Unsupported(
            "crn", "multiple-reactions",
            f"{len(net.reactions)} reactions; the slice handles exactly one",
        )
    rxn = net.reactions[0]

    if rxn.reactant_tokens == 0:
        raise Unsupported("crn", "synthesis", "reaction has no reactant")
    if rxn.product_tokens == 0:
        raise Unsupported("crn", "degradation", "reaction has no product")
    # Unimolecular reactant: exactly one reactant species, coefficient 1.
    if len(rxn.reactants) != 1 or rxn.reactants[0][1] != 1:
        raise Unsupported(
            "crn", "bimolecular",
            f"reactant multiset {dict(rxn.reactants)} is not a single unit reactant",
        )
    # Unit single product: exactly one product species, coefficient 1.
    if len(rxn.products) != 1 or rxn.products[0][1] != 1:
        raise Unsupported(
            "crn", "catalysis",
            f"product multiset {dict(rxn.products)} is not a single unit product",
        )
    reactant = rxn.reactants[0][0]
    product = rxn.products[0][0]
    if reactant == product:
        raise Unsupported("crn", "self-loop", f"reactant and product are both {reactant!r}")
    return rxn


def _target_atoms(net: Network, target: dict[str, int], t: int) -> list[str]:
    """The per-step conjuncts ``(= x<s>_t <count>)`` for the target marking,
    species in network order so the bytes are deterministic."""
    for s in target:
        if s not in net.species:
            raise Unsupported("crn", "target-species", f"target names undeclared species {s!r}")
    return [f"(= x{s}_{t} {int(target[s])})" for s in net.species if s in target]


def translate(program: dict[str, Any]) -> bytes:
    """Unroll a CRN reachability question to ``QF_LIA``.

    ``program`` keys:
      * ``crn``    — the network (``Network`` / text / bytes);
      * ``k``      — the step bound (a caller parameter, not a heuristic);
      * ``target`` — ``{species: count}``: the marking to reach (every named
        species equals that count) at *some* step ``0..k``.
    """
    net = as_network(program["crn"])
    k = int(program["k"])
    if k < 0:
        raise Unsupported("crn", "negative-bound", f"k={k}")
    target = dict(program.get("target") or {})
    if not target:
        raise Unsupported("crn", "no-target", "a reachability target marking is required")

    rxn = _check_in_scope(net)
    reactant = rxn.reactants[0][0]
    product = rxn.products[0][0]
    init = net.init_map

    lines = ["(set-logic QF_LIA)"]

    # declarations: populations x<s>_t (t=0..k), firing flags f0_t (t=0..k-1)
    for t in range(k + 1):
        for s in net.species:
            lines.append(f"(declare-fun x{s}_{t} () Int)")
    for t in range(k):
        lines.append(f"(declare-fun f0_{t} () Bool)")

    # 1. init
    for s in net.species:
        lines.append(f"(assert (= x{s}_0 {init[s]}))")

    # 2. domain: populations are non-negative
    for t in range(k + 1):
        for s in net.species:
            lines.append(f"(assert (>= x{s}_{t} 0))")

    # 3. transition relation
    for t in range(k):
        # enabledness: firing requires the reactant present
        lines.append(f"(assert (=> f0_{t} (>= x{reactant}_{t} 1)))")
        for s in net.species:
            if s == reactant:
                upd = f"(- x{s}_{t} 1)"
            elif s == product:
                upd = f"(+ x{s}_{t} 1)"
            else:  # spectator species are preserved
                upd = f"x{s}_{t}"
            lines.append(f"(assert (= x{s}_{t + 1} (ite f0_{t} {upd} x{s}_{t})))")

    # 4. bad: target marking reached at some step 0..k
    disj = []
    for t in range(k + 1):
        atoms = _target_atoms(net, target, t)
        disj.append(atoms[0] if len(atoms) == 1 else f"(and {' '.join(atoms)})")
    lines.append(f"(assert (or {' '.join(disj)}))" if len(disj) > 1 else f"(assert {disj[0]})")

    lines.append("(check-sat)")
    return ("\n".join(lines) + "\n").encode("utf-8")
