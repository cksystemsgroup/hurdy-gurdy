"""Top-level translator for the aarch64-btor2 pair.

Adapted from gurdy/pairs/riscv_btor2/translation/translate.py.
"""

from __future__ import annotations

import hashlib

from gurdy.core.annotation.sidecar import AnnotationEmitter
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.pairs.aarch64_btor2.source.loader import AArch64Source
from gurdy.pairs.aarch64_btor2.spec import Aarch64Btor2Spec
from gurdy.pairs.aarch64_btor2.translation.builder import Builder
from gurdy.pairs.aarch64_btor2.translation.layers import (
    LAYER_NAMES,
    EmitContext,
    emit_bad,
    emit_binding,
    emit_constraint,
    emit_dispatch,
    emit_havoc,
    emit_header,
    emit_init,
    emit_library,
    emit_machine,
    emit_volatile,
)
from gurdy.pairs.riscv_btor2.btor2.nodes import Comment, Model
from gurdy.pairs.riscv_btor2.btor2.printer import to_text


SCHEMA_VERSION = "1.0.0"


class Translator:
    """The pair's Translator implementation."""

    def translate(
        self,
        spec: Aarch64Btor2Spec,
        source: AArch64Source,
        annotation_emitter: AnnotationEmitter,
    ) -> CompiledArtifact:
        builder = Builder()
        ctx = EmitContext(
            spec=spec, source=source, builder=builder, annotator=annotation_emitter
        )
        emit_header(ctx)
        emit_machine(ctx)
        emit_library(ctx)
        emit_dispatch(ctx)
        emit_init(ctx)
        emit_constraint(ctx)
        emit_volatile(ctx)
        emit_bad(ctx)
        emit_binding(ctx)
        emit_havoc(ctx)

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


translate = Translator()

__all__ = ["Translator", "translate", "SCHEMA_VERSION"]
