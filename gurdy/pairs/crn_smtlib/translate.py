"""CRN -> SMT-LIB translator ``T``: schema-determined unrolling of the discrete
(Petri-net) semantics to a caller-supplied step bound ``k`` (pairs/crn-smtlib
brief; PAIRING.md §2).

**Covered reaction classes (PAIRING.md §1 "start thin, then widen").** The
in-scope per-reaction shapes are translated end-to-end, sharing one firing
schema:

  * **unimolecular** ``A -> B`` — one unit reactant, one unit product, distinct
    species (molecularity 1);
  * **bimolecular** — reactant molecularity 2 with a single unit product: either
    two distinct unit reactants ``A + B -> C`` or one doubled reactant
    ``2 A -> B``;
  * **catalysis / multi-product** — a single unit reactant with a product of
    molecularity 2: ``A -> 2 B`` (one doubled product) or ``A -> B + C`` (two
    distinct unit products);
  * **synthesis** ``0 -> A`` — empty reactant side: always enabled (the
    enabledness conjunction is empty = ``true``), net stoichiometry ``A: +1``;
  * **degradation** ``A -> 0`` — empty product side: precondition ``xA >= 1``,
    net stoichiometry ``A: -1``;
  * **self-loop** ``A -> A`` — a reaction whose product set intersects its
    reactant set, so a shared species has *net* stoichiometry 0: a valid (if
    no-op-ish) firing whose enabledness precondition (``xA >= 1``) is still
    required.

The network may hold **any number of reactions** (each within an in-scope
per-reaction shape above): **zero** (an empty network — only stuttering is
possible, so the target is reachable iff it equals the initial marking), **one**
(reducing byte-for-byte to the pre-widening single-reaction schema), or **two or
more** (a multi-reaction network whose per-step firing *selects* which one
reaction fires). **Every other construct hard-aborts** with a typed
``Unsupported`` (BENCHMARKS.md §3): per reaction, reactant molecularity ≥ 3
(``crn:trimolecular``), product molecularity ≥ 3 or a molecularity-2 product on
a non-unit reactant side (``crn:catalysis``, e.g. ``2 A -> 2 B``), or a no-op
reaction with both sides empty (``crn:empty-reaction``, ``0 -> 0``).

The emitted ``QF_LIA`` script is determined **byte-for-byte** by
``(network, k, target)`` and the fixed schema below (``predicted`` fidelity):
nothing adaptive, nothing hashed, nothing timestamped. Emission order is fixed —
steps ascending ``0..k``, species in network declaration order, reactions in
network order.

Schema (reactions ``R0..R{N-1}``, reaction ``i`` has reactant multiset ``Rc_i``
-> product multiset ``Pc_i``)
---------------------------------------------------------------------------------
Variables (emitted steps-major, then species in network order, then firing flags
in reaction order):
  * ``x<species>_<t>`` : ``Int``  population of the species after step ``t``,
    for ``t = 0 .. k``;
  * ``f<i>_<t>`` : ``Bool``  did reaction ``i`` fire during step ``t``, for every
    reaction ``i = 0 .. N-1`` and ``t = 0 .. k-1`` (none when ``N = 0``).
Constraints (emitted in this fixed order):
  1. init   ``(= x<s>_0 <init count>)`` for every species ``s``;
  2. domain ``(>= x<s>_t 0)`` for every species ``s`` and ``t = 0 .. k``;
  3. trans  for ``t = 0 .. k-1`` (with ``N = 0`` the firing/mutex parts vanish
            and each species' update is the bare stutter ``(= x<s>_{t+1}
            x<s>_t)`` — the empty ``ite`` chain):
       * **mutual exclusion** (emitted only when ``N >= 2``): at most one reaction
         fires per step, as the pairwise clause
         ``(assert (or (not f<i>_t) (not f<j>_t)))`` for ``0 <= i < j < N`` (in
         lexicographic ``(i, j)`` order), keeping the encoding in plain ``QF_LIA``
         boolean atoms;
       * **enabledness** ``(=> f<i>_t <guard_i>)`` per reaction ``i`` (reaction
         order), ``<guard_i>`` the conjunction of ``(>= x<r>_t Rc_i[r])`` over
         reaction ``i``'s reactants (the bare atom for one reactant, ``(and ...)``
         for two, the literal ``true`` for an empty reactant side);
       * **per species** ``s`` (network order) the guarded update
         ``(assert (= x<s>_{t+1} (ite f0_t <upd_0(s)> (ite f1_t <upd_1(s)>
         ... x<s>_t))))`` — a nested ``ite`` chain in reaction order, each guarded
         by that reaction's flag, applying reaction ``i``'s *net* stoichiometry
         ``Pc_i[s] - Rc_i[s]`` (decrement reactants, increment products, preserve
         spectators / net-zero species), falling through to ``x<s>_t`` when no
         reaction fired. With one reaction the chain is the single
         ``(ite f0_t <upd> x_t)``;
  4. bad    a disjunction over steps ``0..k`` of "the target marking holds here".
The script is ``sat`` iff some firing schedule (selecting at most one reaction
per step) reaches the target within ``k``. For a **single reaction** the mutual-
exclusion clause is absent and the ``ite`` chain is one level deep, so the bytes
reduce **exactly** to the pre-widening single-reaction schema (the byte-exact
tests are unchanged). For unimolecular ``A -> B`` the net update is ``A: -1, B:
+1`` with the single enabledness conjunct ``(>= xA_t 1)``. Synthesis ``0 -> A``
has the literal ``true`` guard; degradation ``A -> 0`` keeps the ``(>= xA_t 1)``
guard with the single net update ``A: -1``; a self-loop ``A -> A`` keeps the
``xA >= 1`` guard with the *net-zero* update (``A`` preserved). An **empty
network** emits no firing flags and a pure stutter ``(= x<s>_{t+1} x<s>_t)`` per
step, so the marking never changes and the target is reachable iff it equals the
initial marking.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...languages.crn.model import Network, Reaction, as_network


def _check_reaction_in_scope(rxn: Reaction) -> None:
    """Restrict a single reaction to the in-scope per-reaction shapes; hard-abort
    everything else with a typed ``Unsupported`` (BENCHMARKS.md §3).

    In scope (each shape may now appear in a network with any number of
    reactions — see :func:`_check_in_scope`):

      * **unimolecular** ``A -> B`` — one unit reactant, one unit product;
      * **bimolecular** — reactant molecularity 2 with a single unit product:
        ``A + B -> C`` (two distinct unit reactants) or ``2 A -> B`` (one doubled
        reactant);
      * **catalysis / multi-product** — reactant molecularity 1 (a single unit
        reactant) with a product of molecularity 2: ``A -> 2 B`` (one doubled
        product) or ``A -> B + C`` (two distinct unit products);
      * **synthesis** ``0 -> A`` — an empty reactant side (always enabled);
      * **degradation** ``A -> 0`` — an empty product side;
      * **self-loop** ``A -> A`` — a product species also among the reactants, so
        the shared species has net stoichiometry 0 (preserved); the enabledness
        precondition ``(>= xA 1)`` is still required.

    Out of scope (each a distinct typed abort): reactant molecularity >= 3
    (``crn:trimolecular``); product molecularity >= 3 or a non-unit reactant
    paired with a non-unit product (e.g. ``2 A -> 2 B``) (``crn:catalysis``); a
    no-op reaction with both sides empty (``crn:empty-reaction``).
    """
    # The degenerate ``0 -> 0`` (both sides empty) has no species effect and is
    # not a reaction class — keep it out of scope (a self-loop ``A -> A`` is
    # *not* this: it has a non-empty reactant side and a real precondition).
    if rxn.reactant_tokens == 0 and rxn.product_tokens == 0:
        raise Unsupported("crn", "empty-reaction", "reaction has neither reactant nor product")
    # Reactant molecularity (total reactant tokens) must be 0 (synthesis, an
    # empty reactant side), 1 (unimolecular) or 2 (bimolecular). The two
    # bimolecular shapes — ``A + B`` (two distinct unit reactants) and ``2 A``
    # (one doubled reactant) — both have ``reactant_tokens == 2``. Molecularity
    # >= 3 is out of scope.
    if rxn.reactant_tokens > 2:
        raise Unsupported(
            "crn", "trimolecular",
            f"reactant multiset {dict(rxn.reactants)} has molecularity "
            f"{rxn.reactant_tokens} > 2",
        )
    # Product side: molecularity 0 (degradation, an empty product side),
    # molecularity 1 (a single unit product, paired with any in-scope reactant
    # side) or molecularity 2 (catalysis / multi-product — ``A -> 2 B`` or
    # ``A -> B + C``), but a molecularity-2 product is admitted only when the
    # reactant side is a single unit reactant (``reactant_tokens == 1``). A
    # doubled-or-multi product on a bimolecular reactant side (e.g. ``2 A -> 2 B``)
    # and any product molecularity >= 3 stay out of scope.
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
    # A self-loop (a product species also among the reactants, e.g. ``A -> A``)
    # is now in scope: its net stoichiometry on the shared species is 0, which
    # the net-stoichiometry update preserves, while its enabledness precondition
    # is still required. No abort.


def _check_in_scope(net: Network) -> tuple[Reaction, ...]:
    """Restrict to in-scope networks and return the reactions (network order).

    A network may now hold **any number** of reactions, each within an in-scope
    per-reaction shape (:func:`_check_reaction_in_scope`): zero reactions (an
    empty network — only stuttering, target reachable iff equal to init), one
    reaction (the pre-widening single-reaction schema, byte-for-byte), or two or
    more (the per-step firing selects which one reaction fires). Each reaction is
    validated independently; an out-of-scope reaction hard-aborts with its typed
    construct (``crn:trimolecular`` / ``crn:catalysis`` / ``crn:empty-reaction``).
    """
    for rxn in net.reactions:
        _check_reaction_in_scope(rxn)
    return net.reactions


def _guard(rxn: Reaction, t: int) -> str:
    """Reaction ``rxn``'s enabledness guard at step ``t``: the conjunction of
    ``(>= x<r>_t Rc[r])`` over its reactants (the bare atom for one reactant,
    ``(and ...)`` for two, the literal ``true`` for an empty reactant side)."""
    enabled = [f"(>= x{r}_{t} {c})" for r, c in rxn.reactants]
    if not enabled:
        return "true"
    if len(enabled) == 1:
        return enabled[0]
    return f"(and {' '.join(enabled)})"


def _update(rxn: Reaction, s: str, t: int) -> str:
    """Reaction ``rxn``'s net-stoichiometry update of species ``s`` at step ``t``:
    ``(- x<s>_t n)`` / ``(+ x<s>_t n)`` for a net loss / gain of ``n``, else the
    bare ``x<s>_t`` (a spectator or net-zero — e.g. self-loop — species)."""
    net_coeff = rxn.product_map.get(s, 0) - rxn.reactant_map.get(s, 0)
    if net_coeff < 0:
        return f"(- x{s}_{t} {-net_coeff})"
    if net_coeff > 0:
        return f"(+ x{s}_{t} {net_coeff})"
    return f"x{s}_{t}"


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

    reactions = _check_in_scope(net)
    n = len(reactions)
    init = net.init_map

    lines = ["(set-logic QF_LIA)"]

    # declarations: populations x<s>_t (t=0..k), firing flags f<i>_t (t=0..k-1,
    # one per reaction). An empty network declares no flags.
    for t in range(k + 1):
        for s in net.species:
            lines.append(f"(declare-fun x{s}_{t} () Int)")
    for t in range(k):
        for i in range(n):
            lines.append(f"(declare-fun f{i}_{t} () Bool)")

    # 1. init
    for s in net.species:
        lines.append(f"(assert (= x{s}_0 {init[s]}))")

    # 2. domain: populations are non-negative
    for t in range(k + 1):
        for s in net.species:
            lines.append(f"(assert (>= x{s}_{t} 0))")

    # 3. transition relation. For an empty network the firing/mutex parts vanish
    # and each species' update is the bare stutter (= x<s>_{t+1} x<s>_t) — only
    # stuttering is possible, so the marking never changes and the target is
    # reachable iff it equals the init marking.
    for t in range(k):
        # mutual exclusion: at most one reaction fires per step. Pairwise clauses
        # keep the encoding in plain QF_LIA boolean atoms. Emitted only when there
        # are >= 2 reactions (with one reaction the single flag is vacuously
        # exclusive, so the clause is absent and the single-reaction bytes are
        # unchanged).
        for i in range(n):
            for j in range(i + 1, n):
                lines.append(f"(assert (or (not f{i}_{t}) (not f{j}_{t})))")
        # enabledness: firing reaction i requires every reactant present in at
        # least its stoichiometric coefficient (one linear conjunct per reactant,
        # in reaction order; the literal ``true`` for an empty reactant side).
        for i, rxn in enumerate(reactions):
            lines.append(f"(assert (=> f{i}_{t} {_guard(rxn, t)}))")
        # per species: a nested ite chain in reaction order, each guarded by that
        # reaction's flag and applying its net stoichiometry, falling through to
        # x<s>_t when no reaction fired. With one reaction this is the single
        # ``(ite f0_t <upd> x_t)`` — the pre-widening bytes.
        for s in net.species:
            upd = f"x{s}_{t}"
            for i in reversed(range(n)):
                upd = f"(ite f{i}_{t} {_update(reactions[i], s, t)} {upd})"
            lines.append(f"(assert (= x{s}_{t + 1} {upd}))")

    # 4. bad: target marking reached at some step 0..k
    disj = []
    for t in range(k + 1):
        atoms = _target_atoms(net, target, t)
        disj.append(atoms[0] if len(atoms) == 1 else f"(and {' '.join(atoms)})")
    lines.append(f"(assert (or {' '.join(disj)}))" if len(disj) > 1 else f"(assert {disj[0]})")

    lines.append("(check-sat)")
    return ("\n".join(lines) + "\n").encode("utf-8")
