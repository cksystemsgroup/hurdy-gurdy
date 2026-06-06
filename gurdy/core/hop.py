"""The ``Hop`` genus and the unified hop/pair registry.

A **hop** is one registered, deterministic edge ``L_in -> L_out`` between two
languages that each carry a formal semantics. It is the genus; the species are
distinguished by what kind of language ``L_out`` is (see
``DESIGN_pair_taxonomy.md``):

- a **compile pair** (:class:`CompileHop`) translates to another
  representation / execution target (RV64 ELF, WASM, ...). It carries no
  lifter and no solvers; its value is a certified new representation.
- a **reasoning pair** (:class:`gurdy.core.pair.Pair`) translates to a
  reasoning language where a solver lives (BTOR2, SMT-LIB, ...). It adds a
  spec vocabulary, a lifter, solvers, and interpreters.

Both live in one registry keyed by identifier, so the set of registered hops
forms the language graph that routing and chains (later stages) walk. This
module owns the registry and the *generic* registration; the reasoning-pair
back-compat surface (``register_pair`` / ``get_pair`` / ``list_pairs``) lives
in :mod:`gurdy.core.pair` and delegates here.

Stage 1 (see ``DESIGN_generalized_pairs.md`` §11) deliberately stops short of
unifying the per-hop *translation callable* signature: a reasoning pair's
``translator.translate(spec, source, emitter)`` and a compile hop's
``compile(source, ...)`` have genuinely different shapes, so each species keeps
its own. The genus captures only what the graph and the trust computation need.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


class Tier(str, Enum):
    """A hop's trust tier (``DESIGN_generalized_pairs.md`` §4).

    The values form the *predictability* axis, orthogonal to the
    compile-vs-reasoning (output-kind) axis. A chain's tier is the meet
    (weakest hop) unless a verifier hop re-establishes it.
    """

    transparent = "transparent"   # schema-predictable, byte-deterministic
    reproducible = "reproducible"  # not predictable, but pinned => identical bytes
    checked = "checked"            # output validated against input on every run
    trusted = "trusted"            # taken on faith; admit only behind a verifier hop

    @property
    def trust_rank(self) -> int:
        """Assurance ranking (higher = more trustworthy); used to compute a
        chain's trust as its weakest (minimum-rank) hop. Rationale: transparent
        is schema-auditable (predict the bytes); checked is independently
        validated against its input on every run; reproducible assures only
        determinism (correctness rests on the pinned tool); trusted assures
        nothing. See ``DESIGN_pair_taxonomy.md`` §8."""
        return _TRUST_RANK[self]

    @property
    def is_deterministic(self) -> bool:
        """Whether the tier guarantees byte-identical output for a fixed input.
        Every tier except ``trusted`` does."""
        return self is not Tier.trusted


# Assurance ranking behind Tier.trust_rank: transparent (schema-auditable) >
# checked (validated every run) > reproducible (deterministic only) > trusted.
_TRUST_RANK: dict["Tier", int] = {
    Tier.transparent: 3,
    Tier.checked: 2,
    Tier.reproducible: 1,
    Tier.trusted: 0,
}


def weakest_tier(tiers: Iterable[Tier]) -> Tier:
    """The least-trustworthy tier among ``tiers`` — the chain-trust meet.

    A chain's declared trust is ``weakest_tier`` of its hops' tiers. A verifier
    that independently corroborates a hop's translation lifts that hop's
    *effective* tier to ``checked`` and recomputes the meet with it overridden
    (the "verifier hop re-establishes trust" rule, ``DESIGN_pair_taxonomy.md``
    §8). Raises ``ValueError`` on an empty iterable."""
    ranked = list(tiers)
    if not ranked:
        raise ValueError("weakest_tier of no tiers")
    return min(ranked, key=lambda t: t.trust_rank)


@dataclass(frozen=True)
class Preservation:
    """A hop's preservation contract — what its translation keeps vs. discards
    (a generalization of the projection's observable set; ``DESIGN_pair_taxonomy.md``
    §8).

    Labels are free-form and pair-local: no shared cross-field ontology is
    imposed (the §10/§15 discipline). The framework only *composes* them — a
    chain's total loss is the union of its hops' ``discards`` ("lossiness
    compounds"). ``keeps`` is reported per hop for inspection but is not
    composed across hops, since that would need the shared vocabulary we avoid.
    """

    keeps: tuple[str, ...] = ()
    discards: tuple[str, ...] = ()
    note: str = ""

    @property
    def specified(self) -> bool:
        return bool(self.keeps or self.discards or self.note)


@dataclass(frozen=True, kw_only=True)
class Hop:
    """The genus: a deterministic translation edge ``in_lang -> out_lang``.

    ``in_lang``/``out_lang`` are language identifiers (bare strings for now; a
    ``Language`` registry validating them lands in Stage 2). They default to
    empty so that minimal/synthetic pairs constructed in tests need not declare
    them; real hops set them so they appear as graph edges.
    """

    identifier: str
    in_lang: str = ""
    out_lang: str = ""
    tier: Tier = Tier.transparent
    preservation: Preservation = field(default_factory=Preservation)

    @property
    def kind(self) -> str:
        """The species discriminator: ``"compile"`` or ``"reasoning"``.

        Overridden by each concrete species; the bare genus is just ``"hop"``.
        """
        return "hop"


@dataclass(frozen=True, kw_only=True)
class CompileHop(Hop):
    """A compile pair: ``L_out`` is a representation, not a reasoning language.

    Carries the hop's translation callable (``compile``) — whose signature is
    hop-specific, by design (see module docstring) — and a pointer to its
    contract document (the opaque-hop analogue of a pair's ``SCHEMA.md``).
    """

    compile: Any                       # the hop's translation callable; signature varies
    contract_path: Path | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return "compile"


_REGISTRY: dict[str, Hop] = {}


def register_hop(hop: Hop) -> None:
    """Add a hop to the singleton registry (idempotent on the same object).

    Generic across species. Re-registering the same identifier with a
    *different* object replaces it (useful for hot-reload); reasoning pairs add
    a schema-version compatibility guard on top of this in
    :func:`gurdy.core.pair.register_pair`.
    """
    existing = _REGISTRY.get(hop.identifier)
    if existing is None or existing is hop:
        _REGISTRY[hop.identifier] = hop
        return
    _REGISTRY[hop.identifier] = hop


def get_hop(identifier: str) -> Hop:
    """Return any registered hop (compile or reasoning) by identifier."""
    try:
        return _REGISTRY[identifier]
    except KeyError as exc:  # pragma: no cover - exercised via tests
        raise KeyError(f"no hop registered with identifier {identifier!r}") from exc


def list_hops(kind: str | None = None) -> tuple[str, ...]:
    """Sorted identifiers of registered hops, optionally filtered by ``kind``
    (``"compile"`` or ``"reasoning"``)."""
    return tuple(
        sorted(
            ident
            for ident, hop in _REGISTRY.items()
            if kind is None or hop.kind == kind
        )
    )


def all_hops() -> tuple[Hop, ...]:
    """All registered hops as objects, sorted by identifier (deterministic).

    The directed multigraph that :func:`gurdy.core.route.routes` walks is read
    from these: each hop is the edge ``in_lang -> out_lang``.
    """
    return tuple(_REGISTRY[ident] for ident in sorted(_REGISTRY))


def unregister_hop(identifier: str) -> None:
    """Test/utility helper. Not part of the user-facing surface."""
    _REGISTRY.pop(identifier, None)


def _clear_registry_for_tests() -> None:
    _REGISTRY.clear()


__all__ = [
    "Tier",
    "weakest_tier",
    "Preservation",
    "Hop",
    "CompileHop",
    "register_hop",
    "get_hop",
    "list_hops",
    "all_hops",
    "unregister_hop",
]
