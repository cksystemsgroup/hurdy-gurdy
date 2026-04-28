"""LayerSpec declarations and dependency resolution.

A pair declares its layer set as a tuple of ``LayerSpec`` records.
The framework's job is to:

- check the declared dependencies form a DAG
- topologically order layers so that, when flattening, every layer's
  dependencies precede it.

The actual cross-layer name resolution happens in ``linker.py``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable, Sequence

# Re-export so callers can import from one place.
from gurdy.core.pair import LayerSpec  # noqa: F401  (re-export)


@dataclass(frozen=True)
class LayerOrder:
    """Result of ``order_layers``."""

    order: tuple[str, ...]


class LayerDependencyError(ValueError):
    """Raised when layer dependencies are malformed."""


def order_layers(layers: Sequence[LayerSpec]) -> LayerOrder:
    """Topologically order the declared layers.

    Raises ``LayerDependencyError`` on duplicate names, undeclared
    dependencies, or cycles. The order is deterministic: among
    independent layers, the declaration order wins.
    """

    by_name: dict[str, LayerSpec] = {}
    for spec in layers:
        if spec.name in by_name:
            raise LayerDependencyError(f"duplicate layer name: {spec.name!r}")
        by_name[spec.name] = spec

    in_degree: dict[str, int] = {n: 0 for n in by_name}
    succ: dict[str, list[str]] = {n: [] for n in by_name}
    declaration_index = {n: i for i, n in enumerate(by_name)}

    for spec in layers:
        for dep in spec.depends_on:
            if dep not in by_name:
                raise LayerDependencyError(
                    f"layer {spec.name!r} depends on undeclared layer {dep!r}"
                )
            succ[dep].append(spec.name)
            in_degree[spec.name] += 1

    # Kahn's algorithm with declaration-order tiebreaking.
    ready: deque[str] = deque(
        sorted((n for n, d in in_degree.items() if d == 0), key=declaration_index.get)
    )
    order: list[str] = []
    while ready:
        n = ready.popleft()
        order.append(n)
        for s in succ[n]:
            in_degree[s] -= 1
            if in_degree[s] == 0:
                # Insert preserving declaration order among ready set.
                _insert_sorted(ready, s, declaration_index)

    if len(order) != len(by_name):
        unresolved = [n for n, d in in_degree.items() if d > 0]
        raise LayerDependencyError(
            f"cycle in layer dependencies, unresolved: {sorted(unresolved)!r}"
        )

    return LayerOrder(order=tuple(order))


def _insert_sorted(d: deque, name: str, idx: dict[str, int]) -> None:
    target = idx[name]
    for i, existing in enumerate(d):
        if idx[existing] > target:
            d.insert(i, name)
            return
    d.append(name)


def required_dependencies(
    layers: Iterable[LayerSpec], target: str
) -> tuple[str, ...]:
    """Transitive dependency closure of ``target`` (excluding itself)."""

    by_name: dict[str, LayerSpec] = {s.name: s for s in layers}
    if target not in by_name:
        raise LayerDependencyError(f"unknown layer {target!r}")
    seen: set[str] = set()
    out: list[str] = []
    stack: list[str] = list(by_name[target].depends_on)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
        if n not in by_name:
            raise LayerDependencyError(f"unknown layer {n!r} required by {target!r}")
        stack.extend(by_name[n].depends_on)
    return tuple(out)


__all__ = ["LayerSpec", "LayerOrder", "LayerDependencyError", "order_layers", "required_dependencies"]
