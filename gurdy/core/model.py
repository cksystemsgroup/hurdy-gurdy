"""Model registrations — the formal models humans register in ``registry/models/``.

Symmetric to ``gurdy.core.manifest`` (pairs): a registration is the contract a
*model-build* agent codes against and the *model gate* certifies. The pinned
fields (``id``, ``language``, ``target_capabilities``) are read-only to the
agent. Pairs reference a model by id via ``source_semantics: { model: <id> }``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

MODELS_DIR = Path(__file__).resolve().parents[2] / "registry" / "models"


@dataclass(frozen=True)
class ModelRegistration:
    id: str
    language: str                       # the ISA/language this model gives semantics to
    oracle_kind: str                    # sail | external
    target_capabilities: tuple[str, ...]  # subset of gurdy.core.oracle.ALL_CAPABILITIES
    source: dict                        # { repo, model_source, emulator_release, ... } — pinned
    conformance_suite: str | None       # how the oracle is validated against upstream
    group: str                          # the semantics/<group> dir; defaults to id
    playbook: str
    raw: dict = field(default_factory=dict, repr=False)


def load(path: Path) -> ModelRegistration:
    data = yaml.safe_load(path.read_text())
    return ModelRegistration(
        id=data["id"],
        language=data["language"],
        oracle_kind=(data.get("oracle") or {}).get("kind", "sail"),
        target_capabilities=tuple(data.get("target_capabilities", ())),
        source=data.get("source") or {},
        conformance_suite=data.get("conformance_suite"),
        group=data.get("group", data["id"]),
        playbook=(data.get("agent") or {}).get("playbook", ""),
        raw=data,
    )


def load_all(models_dir: Path = MODELS_DIR) -> list[ModelRegistration]:
    if not models_dir.is_dir():
        return []
    return [load(p) for p in sorted(models_dir.glob("*.yaml"))]
