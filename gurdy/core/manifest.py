"""Registration manifests — the typed holes humans author in ``registry/``.

A manifest is the *contract* an autonomous agent codes against and the gate
checks against. The fields ``projection`` and ``fidelity.target`` are
pinned here and are read-only to the agent (the gate byte-checks them).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from gurdy.core.report import Fidelity

REGISTRY_DIR = Path(__file__).resolve().parents[2] / "registry"


@dataclass(frozen=True)
class Endpoint:
    id: str
    edge_role: str          # source | representation | reasoning


@dataclass(frozen=True)
class MachineTool:
    realization: str        # e.g. "sail-riscv@btor2-machine"
    use: tuple[str, ...]    # subset of {"alt_path", "cross_check"}
    construction: str       # "forbidden" keeps the pair independent


@dataclass(frozen=True)
class Manifest:
    id: str
    kind: str               # compile | reasoning | bridge
    in_lang: Endpoint
    out_lang: Endpoint
    projection: dict
    fidelity_target: Fidelity
    merge_branch: str
    oracle_access: str      # differential_only | held_out_behavioral | guided
    dev_oracle: str | None
    source_group: str | None       # the semantics/<group> dir (resolved)
    source_model: str | None        # the registered model id the pair references
    solvers: tuple[str, ...]
    machine_tool: MachineTool | None
    playbook: str
    raw: dict = field(default_factory=dict, repr=False)


def _endpoint(d: dict) -> Endpoint:
    return Endpoint(id=d["id"], edge_role=d["edge_role"])


def load(path: Path) -> Manifest:
    data = yaml.safe_load(path.read_text())
    fid = data["fidelity"]
    mt = data.get("machine_tool")
    return Manifest(
        id=data["id"],
        kind=data["kind"],
        in_lang=_endpoint(data["in_lang"]),
        out_lang=_endpoint(data["out_lang"]),
        projection=data["projection"],
        fidelity_target=Fidelity.parse(str(fid["target"])),
        merge_branch=fid.get("merge_branch", "main"),
        oracle_access=data.get("oracle_access", "differential_only"),
        dev_oracle=data.get("dev_oracle"),
        # a pair references a model by id; its group dir defaults to that id
        # (the model registration is the authority when group != id).
        source_group=(data.get("source_semantics") or {}).get("group")
        or (data.get("source_semantics") or {}).get("model"),
        source_model=(data.get("source_semantics") or {}).get("model"),
        solvers=tuple((data.get("reasoning") or {}).get("solvers", ())),
        machine_tool=(
            MachineTool(
                realization=mt["realization"],
                use=tuple(mt.get("use", ())),
                construction=mt.get("construction", "forbidden"),
            )
            if mt
            else None
        ),
        playbook=(data.get("agent") or {}).get("playbook", ""),
        raw=data,
    )


def load_all(registry_dir: Path = REGISTRY_DIR) -> list[Manifest]:
    return [load(p) for p in sorted(registry_dir.glob("*.yaml"))]
