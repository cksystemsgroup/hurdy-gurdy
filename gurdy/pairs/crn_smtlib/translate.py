"""CRN -> SMT-LIB translator ``T``: schema-determined unrolling of the discrete
(Petri-net) semantics to a caller-supplied step bound ``k`` (pairs/crn-smtlib
brief; PAIRING.md §2).

**Covered reaction classes (PAIRING.md §1 "start thin, then widen").** Three
in-scope reaction classes are translated end-to-end, sharing one firing schema:

  * **unimolecular** ``A -> B`` — one unit reactant, one unit product, distinct
    species (molecularity 1);
  * **bimolecular** — reactant molecularity 2 with a single unit product: either
    two distinct unit reactants ``A + B -> C`` or one doubled reactant
    ``2 A -> B``;
  * **catalysis / multi-product** — a single unit reactant with a product of
    molecularity 2: ``A -> 2 B`` (one doubled product) or ``A -> B + C`` (two
    distinct unit products).

The network must consist of exactly that one reaction. **Every other construct
hard-aborts** with a typed ``Unsupported`` (BENCHMARKS.md §3): reactant
molecularity ≥ 3 (``crn:trimolecular``), product molecularity ≥ 3 or a
molecularity-2 product on a non-unit reactant side (``crn:catalysis``, e.g.
``2 A -> 2 B``), synthesis / degradation (empty side), self-loops (a product
also appears among the reactants), and any network with zero or more than one
reaction.

The emitted ``QF_LIA`` script is determined **byte-for-byte** by
``(network, k, target)`` and the fixed schema below (``predicted`` fidelity):
nothing adaptive, nothing hashed, nothing timestamped. Emission order is fixed —
steps ascending ``0..k``, species in network declaration order.

Schema (one reaction ``R0``, reactant multiset ``Rc`` -> product multiset ``Pc``)
---------------------------------------------------------------------------------
Variables (emitted steps-major, species in network order):
  * ``x<species>_<t>`` : ``Int``  population of the species after step ``t``,
    for ``t = 0 .. k``;
  * ``f0_<t>`` : ``Bool``  did ``R0`` fire during step ``t``, for ``t = 0 .. k-1``.
Constraints (emitted in this fixed order):
  1. init   ``(= x<s>_0 <init count>)`` for every species ``s``;
  2. domain ``(>= x<s>_t 0)`` for every species ``s`` and ``t = 0 .. k``;
  3. trans  for ``t = 0 .. k-1``: ``f0_t`` requires ``(>= x<r>_t Rc[r])`` for
            every reactant species ``r`` (the Petri-net enabledness precondition,
            still **linear** in the marking — one conjunct per reactant in
            network order), and every species' next value is its ``ite``-guarded
            update by the *net* stoichiometry ``Pc[s] - Rc[s]`` (decrement
            reactants, increment products, preserve spectators) when ``f0_t``
            holds, else preserved;
  4. bad    a disjunction over steps ``0..k`` of "the target marking holds here".
The script is ``sat`` iff some firing schedule reaches the target within ``k``.
For unimolecular ``A -> B`` the net update is exactly ``A: -1, B: +1`` and the
single enabledness conjunct ``(>= xA_t 1)`` — the bimolecular schema reduces to
the unimolecular bytes exactly.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...languages.crn.model import Network, Reaction, as_network


def _check_in_scope(net: Network) -> Reaction:
    """Restrict to the in-scope reaction classes; hard-abort everything else with
    a typed ``Unsupported`` (BENCHMARKS.md §3). Returns the single in-scope
    reaction.

    In scope (each a network of exactly one reaction whose product is disjoint
    from its reactants — no self-loop):

      * **unimolecular** ``A -> B`` — one unit reactant, one unit product;
      * **bimolecular** — reactant molecularity 2 with a single unit product:
        ``A + B -> C`` (two distinct unit reactants) or ``2 A -> B`` (one doubled
        reactant);
      * **catalysis / multi-product** — reactant molecularity 1 (a single unit
        reactant) with a product of molecularity 2: ``A -> 2 B`` (one doubled
        product) or ``A -> B + C`` (two distinct unit products).

    Out of scope (each a distinct typed abort): reactant molecularity >= 3
    (``crn:trimolecular``); product molecularity >= 3 or a non-unit reactant
    paired with a non-unit product (e.g. ``2 A -> 2 B``) (``crn:catalysis``);
    synthesis / degradation (an empty side); a self-loop (the product is also a
    reactant); and any network with zero or more than one reaction.
    """
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
    # Reactant molecularity (total reactant tokens) must be 1 (unimolecular) or 2
    # (bimolecular). The two bimolecular shapes — ``A + B`` (two distinct unit
    # reactants) and ``2 A`` (one doubled reactant) — both have
    # ``reactant_tokens == 2``. Molecularity >= 3 is out of scope.
    if rxn.reactant_tokens > 2:
        raise Unsupported(
            "crn", "trimolecular",
            f"reactant multiset {dict(rxn.reactants)} has molecularity "
            f"{rxn.reactant_tokens} > 2",
        )
    # Product side: molecularity 1 (a single unit product, paired with any
    # in-scope reactant side) or molecularity 2 (catalysis / multi-product —
    # ``A -> 2 B`` or ``A -> B + C``), but a molecularity-2 product is admitted
    # only when the reactant side is a single unit reactant (``reactant_tokens
    # == 1``). A doubled-or-multi product on a bimolecular reactant side (e.g.
    # ``2 A -> 2 B``) and any product molecularity >= 3 stay out of scope.
    if rxn.product_tokens > 2:
        raise Unsupported(
            "crn", "catalysis",
            f"product multiset {dict(rxn.products)} has molecularity "
            f"{rxn.product_tokens} > 2",
        )
    if rxn.product_tokens == 2 and rxn.reactant_tokens != 1:
        raise Unsupported(
            "crn", "catalysis",
            f"product multiset {dict(rxn.products)} (molecularity 2) requires a "
            f"single unit reactant, not {dict(rxn.reactants)}",
        )
    # A self-loop — a product species that also appears among the reactants —
    # makes the firing's net effect on that species non-strict and is out of
    # scope, exactly as for the unimolecular ``A -> A`` (generalized to e.g.
    # ``A + B -> A`` and ``A -> A + C``).
    overlap = [s for s, _ in rxn.products if s in rxn.reactant_map]
    if overlap:
        raise Unsupported(
            "crn", "self-loop",
            f"product {overlap[0]!r} is also a reactant",
        )
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
    react_map = rxn.reactant_map  # {species: coefficient} for reactants
    prod_map = rxn.product_map    # {species: coefficient} for products
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
        # enabledness: firing requires every reactant present in at least its
        # stoichiometric coefficient (one linear conjunct per reactant species,
        # in reaction order). For a unimolecular ``A -> B`` this is the single
        # ``(>= xA_t 1)``; for ``2 A`` it is ``(>= xA_t 2)``; for ``A + B`` it is
        # the conjunction of ``(>= xA_t 1)`` and ``(>= xB_t 1)``.
        enabled = [f"(>= x{r}_{t} {c})" for r, c in rxn.reactants]
        guard = enabled[0] if len(enabled) == 1 else f"(and {' '.join(enabled)})"
        lines.append(f"(assert (=> f0_{t} {guard}))")
        for s in net.species:
            # net stoichiometry: product gain minus reactant loss for this species
            net_coeff = prod_map.get(s, 0) - react_map.get(s, 0)
            if net_coeff < 0:
                upd = f"(- x{s}_{t} {-net_coeff})"
            elif net_coeff > 0:
                upd = f"(+ x{s}_{t} {net_coeff})"
            else:  # spectator (or net-zero) species are preserved
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
