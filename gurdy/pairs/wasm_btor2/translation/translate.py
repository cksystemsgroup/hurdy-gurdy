"""Top-level WASM → BTOR2 translator.

Assembles the layered artifact by calling per-layer emitters in
dependency order, splits the resulting model on ``:layer:NAME:begin``/
``:end`` comment markers, and returns a ``CompiledArtifact``.

``TRANSLATOR_VERSION`` tracks incompatible changes; bump on any schema
change that would invalidate cached artifacts.
"""

from __future__ import annotations

import hashlib

from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.pairs.wasm_btor2.btor2.nodes import Comment, Model
from gurdy.pairs.wasm_btor2.btor2.printer import to_text
from gurdy.pairs.wasm_btor2.source import WasmSource
from gurdy.pairs.wasm_btor2.spec import WasmBtor2Spec
from gurdy.pairs.wasm_btor2.translation.builder import Builder
from gurdy.pairs.wasm_btor2.translation.layers import (
    LAYER_NAMES,
    EmitContext,
    emit_bad,
    emit_binding,
    emit_constraint,
    emit_dispatch,
    emit_header,
    emit_init,
    emit_library,
    emit_machine,
)


TRANSLATOR_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"


class Translator:
    """The pair's Translator implementation for wasm-btor2."""

    def translate(
        self,
        spec: WasmBtor2Spec,
        source: WasmSource,
        annotation_emitter,
    ) -> CompiledArtifact:
        builder = Builder()
        ctx = EmitContext(spec=spec, source=source, builder=builder)

        emit_header(ctx)
        emit_machine(ctx)
        emit_library(ctx)
        emit_dispatch(ctx)
        emit_init(ctx)
        emit_constraint(ctx)
        emit_bad(ctx)
        emit_binding(ctx)

        layers = _split_layers(builder.model)
        flattened = to_text(builder.model).encode("utf-8")

        return CompiledArtifact(
            pair=spec.pair,
            layers=layers,
            annotation=annotation_emitter.sidecar,
            flattened=flattened,
            schema_version=SCHEMA_VERSION,
            spec_hash=spec.spec_hash(),
        )


def _split_layers(model: Model) -> dict[str, Layer]:
    """Walk model entries and split into named layers on marker comments."""
    layers: dict[str, list] = {n: [] for n in LAYER_NAMES}
    current: str | None = None
    for entry in model.entries:
        if isinstance(entry, Comment) and entry.text.startswith(":layer:"):
            payload = entry.text[len(":layer:"):]
            if payload.endswith(":begin"):
                current = payload[: -len(":begin")]
            elif payload.endswith(":end"):
                current = None
            continue
        if current is not None:
            layers[current].append(entry)
    out: dict[str, Layer] = {}
    for name, entries in layers.items():
        local = Model(entries=entries)
        body = to_text(local).encode("utf-8")
        out[name] = Layer(
            name=name,
            body=body,
            content_hash=hashlib.sha256(body).hexdigest(),
        )
    return out


# Module-level callable for the registry.
translate = Translator()

__all__ = ["Translator", "translate", "TRANSLATOR_VERSION", "SCHEMA_VERSION"]
