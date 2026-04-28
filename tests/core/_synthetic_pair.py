"""A minimal synthetic pair used to exercise the framework's tool surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gurdy.core.annotation.sidecar import AnnotationEmitter
from gurdy.core.annotation.types import Role
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.pair import (
    CompiledArtifact,
    Layer,
    LayerSpec,
    Pair,
    register_pair,
)
from gurdy.core.spec.base import BaseSpec


PAIR_ID = "synthetic-test"
SCHEMA_VERSION = "0.0.1"


@dataclass(frozen=True)
class SyntheticSpec(BaseSpec):
    pair = PAIR_ID
    name: str = ""
    width: int = 32

    def to_jsonable(self) -> dict[str, Any]:
        d = super().to_jsonable()
        return d

    @classmethod
    def from_jsonable(cls, obj):
        fields = obj["fields"]
        return cls(name=fields["name"], width=int(fields["width"]))


def _loader(payload):
    if isinstance(payload, Path):
        return payload.read_bytes()
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if payload is None:
        return b""
    return bytes(payload)


def _validate(spec, source):
    return ()


class _Translator:
    def translate(
        self, spec: SyntheticSpec, source: bytes, em: AnnotationEmitter
    ) -> CompiledArtifact:
        body = f"name={spec.name};width={spec.width};src={len(source)}".encode()
        layer = Layer(name="body", body=body, content_hash="dummy")
        em.emit("body", 1, Role.STATE, source_mapping={"name": spec.name})
        em.emit("body", 2, Role.CONSTRAINT)
        return CompiledArtifact(
            pair=PAIR_ID,
            layers={"body": layer},
            annotation=em.sidecar,
            flattened=body,
            schema_version=SCHEMA_VERSION,
            spec_hash=spec.spec_hash(),
        )


class _Lifter:
    def lift(self, artifact: CompiledArtifact, raw: RawSolverResult):
        return {
            "pair": artifact.pair,
            "verdict": raw.verdict,
            "engine": raw.engine,
            "echo": (raw.payload or b"").decode("utf-8")
            if isinstance(raw.payload, (bytes, bytearray))
            else raw.payload,
        }


class _Solver:
    name = "echo"

    def dispatch(self, artifact_bytes, directive):
        return RawSolverResult(
            verdict="proved",
            elapsed=0.0,
            engine=self.name,
            payload=artifact_bytes,
        )


_LAYERS = (LayerSpec(name="body", stability="universal"),)


def install(schema_path: Path) -> Pair:
    p = Pair(
        identifier=PAIR_ID,
        schema_version=SCHEMA_VERSION,
        source_loader=_loader,
        spec_class=SyntheticSpec,
        spec_validator=_validate,
        layer_specs=_LAYERS,
        translator=_Translator(),
        lifter=_Lifter(),
        solvers={"echo": _Solver},
        schema_path=schema_path,
    )
    register_pair(p)
    return p
