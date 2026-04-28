"""Smoke-test that every example script runs to completion."""

import subprocess
import sys
from pathlib import Path


EXAMPLES = sorted((Path(__file__).resolve().parent.parent / "examples").glob("*.py"))


def test_examples_directory_has_scripts():
    assert EXAMPLES, "no example scripts found"


def _run(script):
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"{script.name} exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert result.stdout, f"{script.name} produced no output"


def test_example_01_compile_basic():
    _run(EXAMPLES[0])


def test_example_02_dispatch_z3bmc():
    _run(EXAMPLES[1])


def test_example_03_introspect_annotation():
    _run(EXAMPLES[2])


def test_example_04_describe_schema():
    _run(EXAMPLES[3])


def test_example_05_layer_reuse():
    _run(EXAMPLES[4])
