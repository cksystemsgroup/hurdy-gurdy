"""aarch64-btor2 interpreter-layer commands over the CLI.

The CLI's binding decoder is now pair-generic (it reads each pair's binding
classes from ``Pair.extras``), so aarch64 — not just riscv — can drive
``simulate`` / ``cross-check`` / ``check`` from the command line. Mirrors
``tests/core/test_new_tool_cli.py`` for the second interpreter-complete pair.
"""

from __future__ import annotations

import importlib
import json

import pytest

from gurdy.core.pair import _clear_registry_for_tests
from gurdy.core.tools.describe import _reset_cache_for_tests
from gurdy.pairs.aarch64_btor2 import spec as A
from gurdy.pairs.aarch64_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.aarch64_btor2.source_interp.bindings import AArch64InputBinding

from tests.fixtures.elf_builder_aarch64 import FuncDef, build_elf


TEXT_BASE = 0x400000
_ADD_X0_1 = bytes.fromhex("00040091")  # add x0, x0, #1
_SVC = bytes.fromhex("010000D4")  # svc #0 (halts)


@pytest.fixture(autouse=True)
def _clean_registry():
    _clear_registry_for_tests()
    _reset_cache_for_tests()
    import gurdy.pairs.aarch64_btor2 as pkg
    importlib.reload(pkg)
    yield
    _clear_registry_for_tests()
    _reset_cache_for_tests()


def _binary_and_spec(tmp_path):
    code = _ADD_X0_1 + _ADD_X0_1 + _SVC
    p = tmp_path / "main.elf"
    p.write_bytes(
        build_elf(
            code, TEXT_BASE,
            [FuncDef(name="main", addr=TEXT_BASE, size=len(code))], entry=TEXT_BASE,
        )
    )
    spec = A.Aarch64Btor2Spec(
        binary=A.BinaryRef(path=str(p)),
        scope=A.AnalysisScope(entry_function="main"),
        property=A.Property(expression="false"),
        analysis=A.AnalysisDirective(engine="z3-bmc", bound=4),
    )
    return p, spec


def test_cli_simulate_writes_trace(tmp_path, capsys):
    from gurdy.core import cli

    binary, spec = _binary_and_spec(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec.to_jsonable()))
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps(AArch64InputBinding(register_init={0: 5}).to_jsonable()))

    rc = cli.main([
        "simulate", str(spec_path), str(binding_path),
        "--max-steps", "4", "--source", str(binary),
    ])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    payload = json.loads(captured.out)
    assert payload["pair"] == "aarch64-btor2"
    assert len(payload["steps"]) >= 2


def test_cli_check_emits_property_holds_diagnostic(tmp_path, capsys):
    from gurdy.core import cli

    binary, spec = _binary_and_spec(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec.to_jsonable()))
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps(AArch64InputBinding(register_init={0: 5}).to_jsonable()))

    rc = cli.main([
        "check", str(spec_path), str(binding_path),
        "--max-steps", "4", "--source", str(binary),
    ])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    payload = json.loads(captured.out)
    # property=false → holds concretely, no violation.
    assert payload["property"]["holds"] is True
    assert any(
        d.get("code") == "check/property_holds_concretely"
        for d in payload["diagnostics"]
    )


def test_cli_cross_check_reports_agreement(tmp_path, capsys):
    from gurdy.core import cli

    binary, spec = _binary_and_spec(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec.to_jsonable()))
    src_path = tmp_path / "src.json"
    src_path.write_text(json.dumps(AArch64InputBinding().to_jsonable()))
    reas_path = tmp_path / "reas.json"
    reas_path.write_text(
        json.dumps(Btor2ReasoningBinding(state_init_by_symbol={"pc": TEXT_BASE}).to_jsonable())
    )

    rc = cli.main([
        "cross-check", str(spec_path), str(src_path), str(reas_path),
        "--max-steps", "4", "--source", str(binary),
    ])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    payload = json.loads(captured.out)
    assert payload["outcome"] == "agreement", payload
