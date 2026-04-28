import json
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from gurdy.core.annotation.lookup import IntrospectQuery
from gurdy.core.pair import _clear_registry_for_tests
from gurdy.core.spec.base import BaseSpec
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.describe import describe, _reset_cache_for_tests
from gurdy.core.tools.dispatch import dispatch
from gurdy.core.tools.introspect import introspect
from gurdy.core.tools.lift import lift

from tests.core._synthetic_pair import SyntheticSpec, install


@pytest.fixture
def installed_pair(tmp_path):
    _clear_registry_for_tests()
    _reset_cache_for_tests()
    schema = tmp_path / "SCHEMA.md"
    schema.write_text(
        dedent(
            """\
            # Synthetic Pair

            ## Sorts

            One bitvector sort of width N.

            ## Lowering

            Each spec.name produces one layer.
            """
        )
    )
    pair = install(schema)
    yield pair
    _clear_registry_for_tests()
    _reset_cache_for_tests()


def test_describe_routes_by_pair(installed_pair):
    e = describe("Sorts", "synthetic-test")
    assert e is not None
    assert e.heading == "Sorts"


def test_describe_miss_returns_hint(installed_pair):
    e = describe("verify", "synthetic-test")
    assert e is not None
    assert e.body == ""
    assert e.hint is not None


def test_compile_dispatch_lift_roundtrip(installed_pair):
    spec = SyntheticSpec(name="hello", width=64)
    artifact = compile_spec(spec, source_payload=b"abc")
    assert artifact.pair == "synthetic-test"
    assert b"name=hello" in artifact.flattened

    class Directive:
        engine = "echo"
        timeout = None
        bound = None

    raw = dispatch(artifact, Directive())
    assert raw.verdict == "proved"
    out = lift(artifact, raw)
    assert out["pair"] == "synthetic-test"
    assert "name=hello" in out["echo"]


def test_dispatch_unknown_engine_returns_error(installed_pair):
    spec = SyntheticSpec(name="x")
    artifact = compile_spec(spec, source_payload=b"")

    class Directive:
        engine = "no-such"
        timeout = None
        bound = None

    raw = dispatch(artifact, Directive())
    assert raw.verdict == "error"


def test_introspect_returns_emitted_annotations(installed_pair):
    spec = SyntheticSpec(name="x")
    artifact = compile_spec(spec, source_payload=b"")
    res = introspect(artifact, IntrospectQuery(layer="body"))
    assert len(res.matches) == 2


def test_cli_describe_subcommand(installed_pair, tmp_path, monkeypatch, capsys):
    from gurdy.core import cli

    monkeypatch.setattr(cli, "_load_pair_module", lambda *a, **k: None)
    rc = cli.main(["describe", "Sorts", "--pair", "synthetic-test"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Sorts" in captured.out


def test_cli_pairs_subcommand(installed_pair, capsys):
    from gurdy.core import cli

    rc = cli.main(["pairs"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "synthetic-test" in captured.out


def test_cli_compile_dispatch_lift_via_files(installed_pair, tmp_path, monkeypatch):
    from gurdy.core import cli

    monkeypatch.setattr(cli, "_load_pair_module", lambda *a, **k: None)

    spec = SyntheticSpec(name="cli-roundtrip", width=8)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec.to_jsonable()))
    artifact_path = tmp_path / "artifact.json"

    rc = cli.main(
        [
            "compile",
            str(spec_path),
            "-o",
            str(artifact_path),
        ]
    )
    assert rc == 0
    assert artifact_path.exists()

    directive_path = tmp_path / "directive.json"
    directive_path.write_text(json.dumps({"engine": "echo"}))

    # Capture stdout for dispatch.
    rc = cli.main(["dispatch", str(artifact_path), str(directive_path)])
    assert rc == 0
