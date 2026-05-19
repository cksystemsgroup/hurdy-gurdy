"""Smoke tests for the wasm-btor2 pair scaffold.

Verifies that all seven submodule packages are importable and carry
the expected docstrings. No solver or WASM runtime dependency.
"""

import importlib


SUBMODULES = [
    "gurdy.pairs.wasm_btor2",
    "gurdy.pairs.wasm_btor2.source",
    "gurdy.pairs.wasm_btor2.source_interp",
    "gurdy.pairs.wasm_btor2.reasoning_interp",
    "gurdy.pairs.wasm_btor2.translation",
    "gurdy.pairs.wasm_btor2.lift",
    "gurdy.pairs.wasm_btor2.solvers",
]


def test_all_submodules_importable():
    for name in SUBMODULES:
        mod = importlib.import_module(name)
        assert mod.__doc__, f"{name} is missing a module docstring"


def test_schema_md_is_present():
    import importlib.resources as ir
    data = ir.files("gurdy.pairs.wasm_btor2").joinpath("SCHEMA.md").read_text()
    assert "wasm" in data.lower() or "SCHEMA" in data
