"""Smoke-test that every example script runs to completion.

The examples are a numbered walkthrough (``01_``, ``02_``, …). Tests are
parametrized over the sorted glob rather than bound to fixed positions, so
renaming, inserting, or deleting an example can't silently desync the run
(the previous positional ``EXAMPLES[i]`` mapping would have run the wrong
script or raised IndexError). ``test_examples_are_sequentially_numbered``
guards the numbering itself.
"""

import subprocess
import sys
from pathlib import Path

import pytest


EXAMPLES = sorted((Path(__file__).resolve().parent.parent / "examples").glob("*.py"))


def test_examples_directory_has_scripts():
    assert EXAMPLES, "no example scripts found"


def test_examples_are_sequentially_numbered():
    for i, script in enumerate(EXAMPLES, start=1):
        assert script.name.startswith(f"{i:02d}_"), (
            f"example #{i} is {script.name!r}, expected a {i:02d}_ prefix; "
            f"the numbered walkthrough has a gap or an out-of-order file"
        )


@pytest.mark.parametrize("script", EXAMPLES, ids=lambda p: p.stem)
def test_example_runs(script):
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"{script.name} exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert result.stdout, f"{script.name} produced no output"
