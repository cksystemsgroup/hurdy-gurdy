"""Tests for bench/aarch64-btor2/harness.py — run_task + list_tasks."""

from __future__ import annotations

import pathlib
import sys

import pytest

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

# harness.py lives in bench/aarch64-btor2/, not on sys.path by default
_REPO = pathlib.Path(__file__).resolve().parents[4]
_HARNESS_DIR = _REPO / "bench" / "aarch64-btor2"
sys.path.insert(0, str(_HARNESS_DIR))

# Another pair's bench may have cached a different "harness" module first; drop
# it so this resolves to aarch64's from the freshly-inserted path[0].
sys.modules.pop("harness", None)
import harness as _harness  # noqa: E402
from harness import TaskResult, list_tasks, run_task  # noqa: E402

_SEED_DIR = _HARNESS_DIR / "corpus" / "seed"
_TASK_0001 = _SEED_DIR / "0001-c-loopsum-o0"

_ALL_SEED_IDS = [
    "0001-c-loopsum-o0",
    "0002-c-loopsum-o1",
    "0003-c-loopsum-o2",
    "0004-c-loopsum-o3",
    "0005-c-int-overflow",
    "0006-c-udiv-by-zero",
    "0007-c-int-min-div-neg-one",
    "0008-c-shift-amount-mask",
    "0009-c-signed-vs-unsigned-shift-right",
    "0010-c-byte-load-signedness",
    "0011-c-mul32-truncation",
    "0012-aarch64-monotonic-x5-spacer",
    "0013-aarch64-bounded-counter-spacer",
]

_Z3_AVAILABLE = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["find_spec"]).find_spec("z3") is None,
    reason="z3 not installed",
)


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------


def test_list_tasks_returns_paths():
    tasks = list_tasks()
    assert isinstance(tasks, list)
    assert all(isinstance(p, pathlib.Path) for p in tasks)


def test_list_tasks_includes_0001():
    ids = [p.name for p in list_tasks()]
    assert "0001-c-loopsum-o0" in ids, f"0001 not found in {ids}"


def test_list_tasks_sorted():
    tasks = list_tasks()
    assert tasks == sorted(tasks)


def test_list_tasks_includes_scaffolds():
    """Scaffolds 0002/0003/0004 appear even without compiled source.elf."""
    ids = {p.name for p in list_tasks()}
    for scaffold in ("0002-c-loopsum-o1", "0003-c-loopsum-o2", "0004-c-loopsum-o3"):
        assert scaffold in ids, f"{scaffold} missing from list_tasks"


def test_list_tasks_includes_all_seeds():
    """All seeds (0001–0013) appear in list_tasks()."""
    ids = {p.name for p in list_tasks()}
    missing = [s for s in _ALL_SEED_IDS if s not in ids]
    assert not missing, f"seeds missing from list_tasks: {missing}"


# ---------------------------------------------------------------------------
# task.toml parse validation (offline — no solver, no ELF required)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed_id", _ALL_SEED_IDS)
def test_task_toml_parses(seed_id: str) -> None:
    """task.toml is valid TOML and carries the required fields."""
    toml_path = _SEED_DIR / seed_id / "task.toml"
    assert toml_path.exists(), f"task.toml missing for {seed_id}"
    data = tomllib.loads(toml_path.read_text())

    # [task] section
    assert data["task"]["id"] == seed_id, (
        f"[task].id mismatch: expected {seed_id!r}, got {data['task']['id']!r}"
    )

    # [expected] section — C tasks: reachable/unreachable; asm/spacer tasks: proved
    verdict = data["expected"]["verdict"]
    assert verdict in ("reachable", "unreachable", "proved"), (
        f"[expected].verdict must be reachable/unreachable/proved, got {verdict!r}"
    )

    # [c] section — only present for C-compiled tasks, not assembly tasks
    if "c" in data:
        bound = data["c"]["bound"]
        assert isinstance(bound, int) and bound > 0, (
            f"[c].bound must be a positive int, got {bound!r}"
        )
        gcc = data["c"]["gcc_version"]
        assert gcc, "[c].gcc_version must be non-empty"


# ---------------------------------------------------------------------------
# run_task: structural / offline checks (no solver)
# ---------------------------------------------------------------------------


def test_task_result_is_frozen_dataclass():
    tr = TaskResult(
        task_id="x",
        verdict="unreachable",
        expected_verdict="unreachable",
        match=True,
        elapsed=0.1,
        engine="z3-bmc",
    )
    with pytest.raises(Exception):
        tr.verdict = "reachable"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# run_task: full solve on 0001 (z3-bmc required)
# ---------------------------------------------------------------------------


@_Z3_AVAILABLE
def test_run_task_0001_unreachable():
    """0001-c-loopsum-o0 translates and z3-bmc returns unreachable."""
    result = run_task(_TASK_0001)
    assert result.task_id == "0001-c-loopsum-o0"
    assert result.verdict != "error", f"solver error: {result.reason}"
    assert result.verdict == "unreachable", f"expected unreachable, got {result.verdict!r}"
    assert result.expected_verdict == "unreachable"
    assert result.match is True
    assert result.elapsed >= 0.0
    assert result.engine == "z3-bmc"


@_Z3_AVAILABLE
def test_run_task_engine_override():
    """Passing engine=z3-bmc explicitly gives the same verdict as default."""
    default_result = run_task(_TASK_0001)
    override_result = run_task(_TASK_0001, engine="z3-bmc")
    assert default_result.verdict == override_result.verdict


@_Z3_AVAILABLE
def test_run_task_timeout_override_propagates():
    """timeout override is accepted without error (solver respects it)."""
    result = run_task(_TASK_0001, timeout=120.0)
    assert result.verdict != "error", f"solver error after timeout override: {result.reason}"


@_Z3_AVAILABLE
def test_run_task_result_fields_populated():
    """All TaskResult fields are populated after a successful run."""
    result = run_task(_TASK_0001)
    assert result.task_id
    assert result.verdict in ("reachable", "unreachable", "unknown", "error")
    assert result.engine
    assert isinstance(result.elapsed, float)
