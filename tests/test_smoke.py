"""Phase 0 smoke test: package imports and CLI is invokable."""

from __future__ import annotations

import subprocess
import sys

import gurdy
from gurdy.core import cli


def test_package_has_version():
    assert isinstance(gurdy.__version__, str)
    assert gurdy.__version__


def test_cli_help_runs():
    parser = cli.build_parser()
    text = parser.format_help()
    assert "gurdy" in text
    assert "compile" in text


def test_cli_main_no_args_prints_help(capsys):
    rc = cli.main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "gurdy" in captured.out


def test_cli_version_flag(capsys):
    rc = cli.main(["--version"])
    captured = capsys.readouterr()
    assert rc == 0
    assert gurdy.__version__ in captured.out


def test_cli_module_invocable():
    # Invoking via -m gurdy.core.cli must exit 0 with --help.
    rc = subprocess.run(
        [sys.executable, "-m", "gurdy.core.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 0, rc.stderr
    assert "gurdy" in rc.stdout
