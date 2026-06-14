"""Orchestrator: watch the registry + groups, plan the agents to spawn.

Two agent types, two epistemologies:

  - machine-build (referential): WITH Sail access; mirrors Sail into the
    btor2-machine and proves equivalence. Spawned when a group's
    btor2-machine realization is PENDING.
  - pair-build (independent, differential_only): sandboxed from Sail AND the
    machine model during construction; builds against dev_oracle. Spawned for
    each registered hop lacking a merged implementation.

The skeleton *plans* (prints the spawn list); actually launching agents and
creating ``pairs/<id>`` branches is ``TODO(orchestrator)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from gurdy.core.manifest import load_all

ROOT = Path(__file__).resolve().parents[1]
SEMANTICS = ROOT / "semantics"


@dataclass
class Spawn:
    agent_type: str          # "machine-build" | "pair-build"
    target: str              # group or hop id
    branch: str
    sail_access: bool
    playbook: str
    note: str = ""


def plan() -> list[Spawn]:
    spawns: list[Spawn] = []

    # machine-build agents for groups whose btor2-machine is not yet GREEN
    for group_yaml in sorted(SEMANTICS.glob("*/GROUP.yaml")):
        data = yaml.safe_load(group_yaml.read_text())
        machine = (data.get("realizations") or {}).get("btor2-machine")
        if machine and machine.get("equivalence") != "GREEN":
            group = group_yaml.parent.name
            spawns.append(
                Spawn(
                    agent_type="machine-build",
                    target=group,
                    branch=f"machine/{group}",
                    sail_access=True,
                    playbook="agents/playbook/BUILD_machine_from_sail.md",
                    note=f"realization {group}@btor2-machine is {machine.get('equivalence')}",
                )
            )

    # pair-build agents for each registered hop (sandboxed from Sail)
    for m in load_all():
        spawns.append(
            Spawn(
                agent_type="pair-build",
                target=m.id,
                branch=f"pairs/{m.id}",
                sail_access=False,
                playbook=m.playbook,
                note=f"oracle_access={m.oracle_access}, dev_oracle={m.dev_oracle}, "
                f"target={m.fidelity_target.label}"
                + (", machine_tool=construction-forbidden" if m.machine_tool else ""),
            )
        )
    return spawns
