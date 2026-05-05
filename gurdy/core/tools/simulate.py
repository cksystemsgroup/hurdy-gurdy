"""``simulate(spec, source, binding, max_steps)`` tool.

Runs the pair's source interpreter on a concrete input binding and
returns a ``SourceTrace``. No solver involvement; no search.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gurdy.core.interp.types import InputBinding, SourceTrace
from gurdy.core.pair import get_pair
from gurdy.core.spec.base import BaseSpec


def simulate(
    spec: BaseSpec,
    binding: InputBinding,
    max_steps: int,
    *,
    source_payload: bytes | str | Path | Any | None = None,
) -> SourceTrace:
    """Run the pair's source interpreter on ``binding`` for up to
    ``max_steps`` steps, honouring the spec's entry assumptions.

    ``source_payload`` is the same kind of value ``compile`` accepts.
    If ``None`` the framework infers it from the spec the way
    ``compile_spec`` does.
    """
    pair = get_pair(spec.pair)
    if pair.source_interpreter is None:
        raise ValueError(
            f"pair {spec.pair!r} has no source_interpreter; cannot simulate"
        )
    if source_payload is None:
        source_payload = _infer_source_payload(spec)
    source = pair.source_loader(source_payload)
    return pair.source_interpreter.run(source, binding, max_steps, spec=spec)


def _infer_source_payload(spec: BaseSpec) -> Any:
    for attr in ("source", "source_path", "binary"):
        v = getattr(spec, attr, None)
        if v is None:
            continue
        path = getattr(v, "path", v)
        if isinstance(path, (str, Path)):
            return Path(path)
        return v
    return None


__all__ = ["simulate"]
