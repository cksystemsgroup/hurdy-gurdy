"""Structural-completeness guard for the riscv-btor2 benchmark corpus.

Every corpus task directory must carry its *authored* files: a parseable
``task.toml``, a parseable ``spec.json``, and exactly one source form
(``source.S`` for assembly tasks, ``task.c`` for C tasks). Those are the
files committed to git.

The compiled artifacts (``source.elf``, ``source.elf.dwarfmap.json``,
``pcs.json``, ``task.cbmc.c``) are deliberately ``.gitignore``d build
outputs, regenerated on demand by the corpus Makefile (``_compile_c.py`` /
``_emit_*.py``); they do not exist in a fresh checkout, so this guard does
**not** require them (the Docker-gated bench tests that need real ELFs gate
themselves on ``source.elf`` existing).

This catches the failure mode where a task directory is committed without
its spec or its source — e.g. a salvage that rescued only part of a task.

Pure-Python and read-only: no solver, subprocess, Docker, or built ELF, so
it runs in any environment where the corpus directory is present.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"


def _task_dirs() -> list[Path]:
    if not CORPUS.exists():
        return []
    return sorted(
        d
        for d in CORPUS.iterdir()
        if d.is_dir() and d.name[:1].isdigit() and (d / "task.toml").exists()
    )


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus dir missing")
@pytest.mark.parametrize("task_dir", _task_dirs(), ids=lambda d: d.name)
def test_corpus_entry_has_authored_files(task_dir: Path) -> None:
    tomllib.loads((task_dir / "task.toml").read_text())  # parses

    spec = task_dir / "spec.json"
    assert spec.exists(), f"{task_dir.name} has no spec.json"
    json.loads(spec.read_text())  # parses

    # Exactly one authored source form: assembly (source.S) xor C (task.c).
    has_asm = (task_dir / "source.S").exists()
    has_c = (task_dir / "task.c").exists()
    assert has_asm ^ has_c, (
        f"{task_dir.name} must carry exactly one source form "
        f"(source.S xor task.c); found source.S={has_asm}, task.c={has_c}."
    )


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus dir missing")
def test_corpus_is_populated() -> None:
    """Guard the guard: a deleted/empty corpus must not pass vacuously."""
    assert len(_task_dirs()) >= 100, f"expected a populated corpus, found {len(_task_dirs())}"
