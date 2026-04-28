"""Cross-layer name resolution and flattening.

Each pair carries its own surface syntax for cross-layer references.
The framework knows how to:

- Slice a layer's bytes into a sequence of *records*. Each record has
  a stable per-layer numeric id (``nid``) and may export symbolic
  names or import symbolic names from other layers.
- Renumber nids globally, rewrite import references to point at the
  exporter's renumbered id, and concatenate the renumbered records
  into a single byte stream.

The pair supplies:

- ``parser``: layer name + bytes -> list of ``LayerRecord``.
- ``printer``: ``LayerRecord`` after renumbering -> bytes.

This keeps BTOR2 syntax out of ``gurdy/core/`` while letting the linker
do the ID-rewriting bookkeeping that's pair-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping

from gurdy.core.layers.declaration import LayerOrder, order_layers
from gurdy.core.pair import LayerSpec


@dataclass
class LayerRecord:
    """A single record within a layer.

    ``nid`` is the per-layer id as the producer wrote it. The linker
    rewrites ``nid`` and the imports/exports below; the printer should
    rebuild surface syntax from these fields.

    ``raw`` is opaque pair-specific structure (e.g. operator, args)
    that the printer turns back into bytes; the linker doesn't read it.
    """

    nid: int
    raw: object
    refs: tuple[int, ...] = ()
    """Other ``nid``s in this same layer that this record references.
    The linker rewrites these to the new global ids."""

    exports: tuple[str, ...] = ()
    """Symbolic names this record exposes to other layers."""

    imports: tuple[str, ...] = ()
    """Symbolic names this record needs from other layers. After
    linking, these become ``ref`` entries pointing at the resolved
    exporter's globally-renumbered id."""

    comment: str = ""


@dataclass(frozen=True)
class LinkInput:
    """One layer's contribution to the linker."""

    name: str
    bytes_: bytes


@dataclass(frozen=True)
class LinkResult:
    flattened: bytes
    nid_map: Mapping[str, Mapping[int, int]]
    """For every layer, maps original nid -> globally-renumbered nid.
    Useful for translating annotations after linking."""


LayerParser = Callable[[str, bytes], list[LayerRecord]]
LayerPrinter = Callable[[LayerRecord], bytes]


@dataclass
class LinkerSyntax:
    """Pair-supplied surface syntax helpers."""

    parser: LayerParser
    printer: LayerPrinter
    record_separator: bytes = b"\n"


class LinkError(ValueError):
    pass


def link(
    layer_specs: Iterable[LayerSpec],
    inputs: Iterable[LinkInput],
    syntax: LinkerSyntax,
) -> LinkResult:
    """Renumber, resolve names, and flatten layers.

    The flattening order is the topological order of ``layer_specs``,
    filtered to layers actually present in ``inputs``.
    """

    spec_list = tuple(layer_specs)
    order = order_layers(spec_list)
    inputs_by_name = {i.name: i for i in inputs}
    return _flatten(order, spec_list, inputs_by_name, syntax)


def _flatten(
    order: LayerOrder,
    spec_list: tuple[LayerSpec, ...],
    inputs_by_name: Mapping[str, LinkInput],
    syntax: LinkerSyntax,
) -> LinkResult:
    next_global_nid = 1
    nid_map: dict[str, dict[int, int]] = {}
    exports: dict[str, int] = {}  # symbolic name -> global nid
    flat_records: list[bytes] = []

    for layer_name in order.order:
        if layer_name not in inputs_by_name:
            continue
        records = syntax.parser(layer_name, inputs_by_name[layer_name].bytes_)
        local_map: dict[int, int] = {}
        for r in records:
            local_map[r.nid] = next_global_nid
            next_global_nid += 1
        nid_map[layer_name] = local_map

        for r in records:
            new_refs = tuple(local_map[ref] for ref in r.refs)
            for sym in r.imports:
                if sym not in exports:
                    raise LinkError(
                        f"layer {layer_name!r} record nid={r.nid} imports "
                        f"{sym!r} which has not been exported by any prior layer"
                    )
                new_refs = new_refs + (exports[sym],)
            new_record = LayerRecord(
                nid=local_map[r.nid],
                raw=r.raw,
                refs=new_refs,
                exports=r.exports,
                imports=(),
                comment=r.comment,
            )
            for sym in r.exports:
                if sym in exports:
                    raise LinkError(
                        f"symbolic export {sym!r} declared twice "
                        f"(was nid={exports[sym]}, now nid={new_record.nid})"
                    )
                exports[sym] = new_record.nid
            flat_records.append(syntax.printer(new_record))

    flattened = syntax.record_separator.join(flat_records)
    if flat_records:
        flattened += syntax.record_separator
    return LinkResult(flattened=flattened, nid_map=nid_map)


__all__ = [
    "LayerRecord",
    "LinkInput",
    "LinkResult",
    "LinkerSyntax",
    "LinkError",
    "link",
]
