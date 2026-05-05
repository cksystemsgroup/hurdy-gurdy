"""CLI subcommand tests for simulate / evaluate / cross-check / replay / check."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from gurdy.core.pair import _clear_registry_for_tests
from gurdy.core.tools.describe import _reset_cache_for_tests
from gurdy.pairs.riscv_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Property,
    RiscvBtor2Spec,
)

from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000


@pytest.fixture(autouse=True)
def _clean_registry():
    _clear_registry_for_tests()
    _reset_cache_for_tests()
    import gurdy.pairs.riscv_btor2 as pkg
    importlib.reload(pkg)
    yield
    _clear_registry_for_tests()
    _reset_cache_for_tests()


def _binary_and_spec(tmp_path):
    code = bytes.fromhex("13055000" "13057501" "73000000")  # ADDI; ADDI; ECALL
    p = tmp_path / "main.elf"
    p.write_bytes(
        build_elf(
            code,
            TEXT_BASE,
            [FuncDef(name="main", addr=TEXT_BASE, size=len(code))],
        )
    )
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="main"),
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=4),
    )
    return p, spec


def test_cli_simulate_writes_trace(tmp_path, monkeypatch, capsys):
    from gurdy.core import cli

    binary, spec = _binary_and_spec(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec.to_jsonable()))
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps(RiscvInputBinding().to_jsonable()))

    rc = cli.main(
        [
            "simulate",
            str(spec_path),
            str(binding_path),
            "--max-steps",
            "4",
            "--source",
            str(binary),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["pair"] == "riscv-btor2"
    assert len(payload["steps"]) == 3


def test_cli_evaluate_writes_trace(tmp_path, monkeypatch, capsys):
    from gurdy.core import cli
    from gurdy.core.tools.compile import compile_spec

    binary, spec = _binary_and_spec(tmp_path)
    artifact = compile_spec(spec, source_payload=binary)
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(
        json.dumps(cli._artifact_to_jsonable(artifact))
    )
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(
        json.dumps(
            Btor2ReasoningBinding(
                state_init_by_symbol={"pc": TEXT_BASE},
            ).to_jsonable()
        )
    )

    rc = cli.main(
        [
            "evaluate",
            str(artifact_path),
            str(binding_path),
            "--max-steps",
            "3",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["pair"] == "riscv-btor2"
    assert len(payload["steps"]) == 3


def test_cli_cross_check_reports_agreement(tmp_path, monkeypatch, capsys):
    from gurdy.core import cli

    binary, spec = _binary_and_spec(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec.to_jsonable()))
    src_binding_path = tmp_path / "src.json"
    src_binding_path.write_text(json.dumps(RiscvInputBinding().to_jsonable()))
    reas_binding_path = tmp_path / "reas.json"
    reas_binding_path.write_text(
        json.dumps(
            Btor2ReasoningBinding(
                state_init_by_symbol={"pc": TEXT_BASE},
            ).to_jsonable()
        )
    )

    rc = cli.main(
        [
            "cross-check",
            str(spec_path),
            str(src_binding_path),
            str(reas_binding_path),
            "--max-steps",
            "3",
            "--source",
            str(binary),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["outcome"] == "agreement", payload


def test_cli_check_emits_unsupported_diagnostic(tmp_path, capsys):
    from gurdy.core import cli

    binary, spec = _binary_and_spec(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec.to_jsonable()))
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps(RiscvInputBinding().to_jsonable()))

    rc = cli.main(
        [
            "check",
            str(spec_path),
            str(binding_path),
            "--max-steps",
            "4",
            "--source",
            str(binary),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert any(
        d.get("code") == "check/property_unsupported" for d in payload["diagnostics"]
    )
