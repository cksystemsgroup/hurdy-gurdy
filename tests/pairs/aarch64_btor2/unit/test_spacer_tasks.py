"""Tests for the aarch64-btor2 spacer corpus tasks (P13).

Covers:
- Structural checks (offline, no z3): required files exist, spec/toml valid.
- Harness integration (z3-required): run_task returns "proved" for both tasks.
- oracle_cross integration (z3-required): inductive profiles produce CROSS-PASS.
- _assemble_asm.py importability.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

_REPO = pathlib.Path(__file__).resolve().parents[4]
_SEED = _REPO / "bench" / "aarch64-btor2" / "corpus" / "seed"
_BENCH = _REPO / "bench" / "aarch64-btor2"
sys.path.insert(0, str(_BENCH))
sys.path.insert(0, str(_REPO))

_TASK_0012 = _SEED / "0012-aarch64-monotonic-x5-spacer"
_TASK_0013 = _SEED / "0013-aarch64-bounded-counter-spacer"

_Z3_AVAILABLE = pytest.mark.skipif(
    importlib.util.find_spec("z3") is None,
    reason="z3 not installed",
)


# ---------------------------------------------------------------------------
# Structural tests — offline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task_dir", [_TASK_0012, _TASK_0013])
def test_required_files_exist(task_dir):
    for fname in ("source.S", "source.elf", "spec.json", "task.toml"):
        assert (task_dir / fname).exists(), f"{fname} missing from {task_dir.name}"


@pytest.mark.parametrize("task_dir", [_TASK_0012, _TASK_0013])
def test_source_elf_is_aarch64(task_dir):
    data = (task_dir / "source.elf").read_bytes()
    assert data[:4] == b"\x7fELF", "not an ELF file"
    e_machine = int.from_bytes(data[18:20], "little")
    assert e_machine == 0xB7, f"e_machine=0x{e_machine:x}, expected 0xb7 (AArch64)"


@pytest.mark.parametrize("task_dir,expected_expr", [
    (_TASK_0012, "lt(reg(5), const(0))"),
    (_TASK_0013, "gt(reg(5), const(10))"),
])
def test_spec_engine_and_property(task_dir, expected_expr):
    spec = json.loads((task_dir / "spec.json").read_text())
    fields = spec["fields"]
    assert spec["pair"] == "aarch64-btor2"
    assert fields["analysis"]["engine"] == "z3-spacer"
    assert fields["analysis"]["bound"] is None
    assert fields["property"]["expression"] == expected_expr


@pytest.mark.parametrize("task_dir", [_TASK_0012, _TASK_0013])
def test_spec_has_register_init_x5_eq_0(task_dir):
    spec = json.loads((task_dir / "spec.json").read_text())
    assumptions = spec["fields"]["assumptions"]
    assert len(assumptions) == 1
    asm = assumptions[0]
    assert asm["__type__"] == "RegisterInit"
    assert asm["register"] == 5
    assert asm["op"] == "eq"
    assert asm["value"] == 0


@pytest.mark.parametrize("task_dir", [_TASK_0012, _TASK_0013])
def test_task_toml_expected_verdict_proved(task_dir):
    t = tomllib.loads((task_dir / "task.toml").read_text())
    assert t["expected"]["verdict"] == "proved"
    assert t["task"]["task_class"] == "global-invariant"


@pytest.mark.parametrize("task_dir,expected_id", [
    (_TASK_0012, "0012-aarch64-monotonic-x5-spacer"),
    (_TASK_0013, "0013-aarch64-bounded-counter-spacer"),
])
def test_task_toml_id_matches_directory(task_dir, expected_id):
    t = tomllib.loads((task_dir / "task.toml").read_text())
    assert t["task"]["id"] == expected_id


@pytest.mark.parametrize("task_dir", [_TASK_0012, _TASK_0013])
def test_spec_parses_via_aarch64_spec_class(task_dir):
    from gurdy.pairs.aarch64_btor2.spec import Aarch64Btor2Spec
    spec = Aarch64Btor2Spec.from_jsonable(json.loads((task_dir / "spec.json").read_text()))
    assert spec.analysis.engine == "z3-spacer"
    assert spec.analysis.bound is None


# ---------------------------------------------------------------------------
# _assemble_asm.py importability
# ---------------------------------------------------------------------------


def test_assemble_asm_importable():
    spec = importlib.util.spec_from_file_location(
        "_assemble_asm",
        _BENCH / "corpus" / "_assemble_asm.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "assemble")
    assert hasattr(mod, "TEXT_BASE")
    assert mod.TEXT_BASE == "0x400000"


# ---------------------------------------------------------------------------
# Harness integration — z3 required
# ---------------------------------------------------------------------------


@_Z3_AVAILABLE
def test_harness_0012_spacer_proves():
    import os
    orig = os.getcwd()
    os.chdir(str(_BENCH))
    try:
        from harness import run_task
        result = run_task(_TASK_0012)
    finally:
        os.chdir(orig)
    assert result.verdict == "proved"
    assert result.match is True
    assert result.engine == "z3-spacer"


@_Z3_AVAILABLE
def test_harness_0013_spacer_proves():
    import os
    orig = os.getcwd()
    os.chdir(str(_BENCH))
    try:
        from harness import run_task
        result = run_task(_TASK_0013)
    finally:
        os.chdir(orig)
    assert result.verdict == "proved"
    assert result.match is True
    assert result.engine == "z3-spacer"


@_Z3_AVAILABLE
def test_harness_spacer_elapsed_under_30s():
    """Both spacer tasks should prove in well under 30 s on any reasonable host."""
    import os
    orig = os.getcwd()
    os.chdir(str(_BENCH))
    try:
        from harness import run_task
        for task_dir in (_TASK_0012, _TASK_0013):
            result = run_task(task_dir)
            assert result.elapsed < 30.0, (
                f"{task_dir.name}: took {result.elapsed:.1f}s (limit 30s)"
            )
    finally:
        os.chdir(orig)


# ---------------------------------------------------------------------------
# oracle_cross integration — z3 required
# ---------------------------------------------------------------------------


@_Z3_AVAILABLE
def test_oracle_cross_0012_inductive_cross_pass(capsys):
    import oracle_cross as _oc
    ret = _oc.main([
        "--corpus", str(_SEED),
        "--task", "0012-aarch64-monotonic-x5-spacer",
        "--engines", "z3-spacer",
        "--per-profile-timeout", "30",
        "--json",
    ])
    assert ret == 0
    data = json.loads(capsys.readouterr().out)
    row = next(r for r in data["rows"] if "summary" in r)
    assert row["summary"]["status"] == "CROSS-PASS"
    assert row["summary"]["n_confirm"] >= 1


@_Z3_AVAILABLE
def test_oracle_cross_0013_inductive_cross_pass(capsys):
    import oracle_cross as _oc
    ret = _oc.main([
        "--corpus", str(_SEED),
        "--task", "0013-aarch64-bounded-counter-spacer",
        "--engines", "z3-spacer",
        "--per-profile-timeout", "30",
        "--json",
    ])
    assert ret == 0
    data = json.loads(capsys.readouterr().out)
    row = next(r for r in data["rows"] if "summary" in r)
    assert row["summary"]["status"] == "CROSS-PASS"
    assert row["summary"]["n_confirm"] >= 1


@_Z3_AVAILABLE
def test_oracle_cross_spacer_tasks_use_inductive_profiles(capsys):
    """When run without --engines filter, spacer tasks route to INDUCTIVE_PROFILES."""
    import oracle_cross as _oc
    from oracle_cross import INDUCTIVE_PROFILES
    ret = _oc.main([
        "--corpus", str(_SEED),
        "--task", "0012-aarch64-monotonic-x5-spacer",
        "--per-profile-timeout", "30",
        "--json",
    ])
    assert ret == 0
    data = json.loads(capsys.readouterr().out)
    row = next(r for r in data["rows"] if "summary" in r)
    engine_labels = {e["label"] for e in row["summary"]["engines"]}
    inductive_labels = {p.label for p in INDUCTIVE_PROFILES}
    assert engine_labels == inductive_labels
