"""Sandboxed Sail oracle with agent-blind held-out partitioning.

For ``differential_only`` pairs the agent gets NO Sail access. For
``held_out_behavioral`` the agent may query a *training* partition only,
through this service; the gate validates on the disjoint *held-out*
partition. Instances are partitioned by a keyed hash the agent cannot
compute, so it cannot selectively avoid the validation set.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

HELDOUT_FRACTION = 0.3


@dataclass
class Partitioner:
    """Deterministic, agent-blind train/held-out split. The key stays with the
    gate; the agent never sees it, so it cannot tell an instance's partition."""

    key: bytes

    def is_heldout(self, instance_id: str) -> bool:
        digest = hmac.new(self.key, instance_id.encode(), hashlib.sha256).digest()
        # use the low bits as a uniform fraction
        frac = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        return frac < HELDOUT_FRACTION


class OracleService:
    """Gate-owned black box over the Sail reference. Logs every query; refuses
    held-out queries; exposes only the projection (never Sail source/state)."""

    def __init__(self, partitioner: Partitioner) -> None:
        self._p = partitioner
        self.query_log: list[str] = []

    def query(self, instance_id: str, program: bytes, binding: dict) -> dict:
        if self._p.is_heldout(instance_id):
            raise PermissionError(f"instance {instance_id!r} is held-out; query refused")
        self.query_log.append(instance_id)
        # TODO(gate): call semantics/sail-riscv/realizations/emulator/oracle.run
        raise NotImplementedError("oracle query wiring [TODO]")
