"""Smoke test for bench/riscv-btor2/oracle_chain.py.

The chain oracle runs the full ``C -> RV64 ELF -> BTOR2`` chain from
``task.c`` (not the committed ``source.elf``) and reports verdict +
alignment agreement per task. Docker-guarded — hop 1 needs the pinned
image. Capped to the two reference tasks (one unreachable, one reachable
+ aligned) to stay fast and RAM-safe.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from gurdy.hops.c_riscv import toolchain_available

REPO = Path(__file__).resolve().parents[2]
ORACLE = REPO / "bench" / "riscv-btor2" / "oracle_chain.py"

pytestmark = pytest.mark.skipif(
    not toolchain_available(),
    reason="pinned bench Docker image not available (chain hop 1 needs it)",
)


def _run() -> dict:
    # One --task substring that matches both 0100 and 0101: "010".
    res = subprocess.run(
        [sys.executable, str(ORACLE), "--json", "--task", "010", "--max-tasks", "2"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert res.returncode == 0, (
        f"oracle exited {res.returncode}\n"
        f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
    return json.loads(res.stdout)


def test_chain_oracle_no_failures_on_reference_tasks():
    payload = _run()
    assert payload["failures"] == 0, payload
    rows = {r["task"]: r for r in payload["rows"]}
    # 0100 (unreachable) and 0101 (reachable) are the two "010" tasks
    # under --max-tasks 2.
    assert "0100-c-add-trap-correct" in rows
    r0100 = rows["0100-c-add-trap-correct"]
    assert r0100["status"] == "PASS"
    assert r0100["got_verdict"] == "unreachable"
    assert r0100["verdict_ok"] is True


def test_chain_oracle_reachable_task_aligns_and_maps_source():
    payload = _run()
    rows = {r["task"]: r for r in payload["rows"]}
    assert "0101-c-add-trap-bug" in rows
    r0101 = rows["0101-c-add-trap-bug"]
    assert r0101["status"] == "PASS"
    assert r0101["got_verdict"] == "reachable"
    assert r0101["align_kind"] == "ok"
    assert r0101["steps_checked"] > 0
    # The witness grounds back in C source lines via the transitive map.
    assert r0101["c_lines"] > 0
