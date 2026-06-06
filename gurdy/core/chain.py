"""Generic chain runner: execute a route's hops in sequence.

A chain runs an instance through several edges of the language graph (see
:mod:`gurdy.core.route`), threading each hop's output into the next and
collecting per-hop provenance. The runner is deliberately mechanical: it
sequences hops, validates connectivity, and accumulates provenance. It holds
**no domain knowledge** — each hop's actual work (and any question synthesis a
reasoning hop needs) is supplied by the caller as the step's ``run`` callable.
That keeps the "no reasoning in core" line: the runner orchestrates, the chain
supplies meaning (``DESIGN_generalized_pairs.md`` §11.3; ``DESIGN_pair_taxonomy.md``
§11, Stage 3).

The runner does not assume a uniform per-hop signature: Stage 1 deliberately
left compile hops and reasoning pairs with different translate shapes, so a
``ChainStep`` adapts each hop behind a uniform ``run(prev) -> StepOutcome``.

RAM discipline (standing constraint): :meth:`Chain.run` processes one instance
straight through and returns; callers must not fan a whole corpus through it
concurrently.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StepOutcome:
    """What one hop produced: its ``output`` (threaded to the next hop) and a
    jsonable ``provenance`` record for this hop."""

    output: Any
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChainStep:
    """One hop in a chain: its identity, its endpoint languages, and the
    callable that runs it.

    ``run`` receives the previous hop's output — or the chain's initial input
    for the first step — and returns a :class:`StepOutcome`.
    """

    hop: str
    in_lang: str
    out_lang: str
    run: Callable[[Any], StepOutcome]


@dataclass(frozen=True)
class ChainExecution:
    """The record of a chain run: the hop ids and languages traversed, each
    hop's output in order, and the threaded per-hop provenance."""

    hops: tuple[str, ...]
    languages: tuple[str, ...]
    outputs: tuple[Any, ...]
    provenance: tuple[dict[str, Any], ...]

    @property
    def final(self) -> Any:
        """The last hop's output (the chain's result)."""
        return self.outputs[-1]


class ChainConnectivityError(ValueError):
    """A chain's steps do not form a connected path (a hop's ``out_lang`` does
    not match the next hop's ``in_lang``)."""


class Chain:
    """An ordered sequence of :class:`ChainStep` forming a connected route."""

    def __init__(self, steps: Iterable[ChainStep]):
        steps = tuple(steps)
        if not steps:
            raise ValueError("a chain needs at least one step")
        for a, b in zip(steps, steps[1:]):
            if a.out_lang != b.in_lang:
                raise ChainConnectivityError(
                    f"hop {a.hop!r} outputs {a.out_lang!r} but the next hop "
                    f"{b.hop!r} expects {b.in_lang!r}"
                )
        self._steps = steps

    @property
    def hops(self) -> tuple[str, ...]:
        return tuple(s.hop for s in self._steps)

    @property
    def in_lang(self) -> str:
        return self._steps[0].in_lang

    @property
    def out_lang(self) -> str:
        return self._steps[-1].out_lang

    @property
    def languages(self) -> tuple[str, ...]:
        return (self._steps[0].in_lang,) + tuple(s.out_lang for s in self._steps)

    def run(self, initial: Any) -> ChainExecution:
        """Execute the chain on ``initial``, threading each hop's output into
        the next and collecting provenance."""
        outputs: list[Any] = []
        provenance: list[dict[str, Any]] = []
        carry = initial
        for step in self._steps:
            outcome = step.run(carry)
            outputs.append(outcome.output)
            provenance.append(dict(outcome.provenance))
            carry = outcome.output
        return ChainExecution(
            hops=self.hops,
            languages=self.languages,
            outputs=tuple(outputs),
            provenance=tuple(provenance),
        )

    @classmethod
    def for_route(
        cls, route: Any, runners: dict[str, Callable[[Any], StepOutcome]]
    ) -> "Chain":
        """Build a chain from a :class:`gurdy.core.route.Route` by binding each
        hop id to a ``run`` callable from ``runners`` (a mapping ``hop id ->
        callable``). The endpoint languages are read from the registered hops,
        so connectivity is anchored to the graph the route came from."""
        from gurdy.core.hop import get_hop

        steps = []
        for hop_id in route.hops:
            hop = get_hop(hop_id)
            steps.append(
                ChainStep(
                    hop=hop_id,
                    in_lang=hop.in_lang,
                    out_lang=hop.out_lang,
                    run=runners[hop_id],
                )
            )
        return cls(steps)


@dataclass(frozen=True)
class DiffResult:
    """Outcome of a chain-level determinism check: whether two runs on the same
    input agreed at every hop, and if not, the index of the first hop that
    diverged."""

    deterministic: bool
    first_divergence: int | None
    hops: tuple[str, ...]


def recompile_and_diff(
    chain: "Chain",
    initial: Any,
    *,
    key: Callable[[Any], Any] | None = None,
) -> DiffResult:
    """Run ``chain`` twice on ``initial`` and compare each hop, returning the
    first hop index whose two runs differ (or ``None`` if identical throughout)
    — the chain-level "determinism composes" check (``DESIGN_pair_taxonomy.md``
    §7), the generalization of a pair's recompile-and-diff.

    By default each hop's *provenance* record is compared: it carries the hop's
    content hashes (e.g. ``elf_sha256`` / ``spec_hash``), so it is the canonical
    determinism signal. Pass ``key(output) -> comparable`` to compare hop
    outputs directly instead (e.g. raw bytes)."""
    a = chain.run(initial)
    b = chain.run(initial)
    for i in range(len(a.hops)):
        if key is not None:
            same = key(a.outputs[i]) == key(b.outputs[i])
        else:
            same = a.provenance[i] == b.provenance[i]
        if not same:
            return DiffResult(deterministic=False, first_divergence=i, hops=a.hops)
    return DiffResult(deterministic=True, first_divergence=None, hops=a.hops)


__all__ = [
    "StepOutcome",
    "ChainStep",
    "ChainExecution",
    "Chain",
    "ChainConnectivityError",
    "DiffResult",
    "recompile_and_diff",
]
