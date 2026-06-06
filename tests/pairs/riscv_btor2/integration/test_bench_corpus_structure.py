"""Structural-completeness guard for the riscv-btor2 benchmark corpus.

Every corpus task directory must either be *structurally complete* -- it
carries the full set of files an oracle needs to actually run it -- or be
explicitly marked ``draft = true`` under ``[task]`` in its ``task.toml``
(source-only, not yet built via the pinned toolchain).

This catches the failure mode where a task's *source* is committed (e.g.
salvaged from a branch) but its *compiled artifacts* (``source.elf``, the
DWARF map, ``pcs.json``) are never generated -- leaving a silently
unrunnable entry that harnesses and oracles skip without complaint. That
is exactly what happened to ``0303-c-ptr-past-end`` (rescued source-only),
which is now flagged ``draft = true`` until it is compiled.

Pure-Python and read-only: no solver, subprocess, Docker, or built ELF
required, so it runs in any environment where the corpus dir is present.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"

# Files every *complete* (non-draft) task must carry, regardless of whether
# its source form is assembly (source.S) or C (task.c). task.cbmc.c is
# deliberately excluded -- it exists only for the C tasks that carry a CBMC
# differential, not corpus-wide.
REQUIRED = (
    "task.toml",
    "spec.json",
    "source.elf",
    "source.elf.dwarfmap.json",
    "pcs.json",
)


def _task_dirs() -> list[Path]:
    if not CORPUS.exists():
        return []
    return sorted(
        d
        for d in CORPUS.iterdir()
        if d.is_dir() and d.name[:1].isdigit() and (d / "task.toml").exists()
    )


def _is_draft(task_dir: Path) -> bool:
    raw = tomllib.loads((task_dir / "task.toml").read_text())
    return bool(raw.get("task", {}).get("draft", False))


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus dir missing")
@pytest.mark.parametrize("task_dir", _task_dirs(), ids=lambda d: d.name)
def test_corpus_entry_is_complete_or_draft(task_dir: Path) -> None:
    if _is_draft(task_dir):
        pytest.skip(f"{task_dir.name}: draft = true (source-only, not built)")

    missing = [f for f in REQUIRED if not (task_dir / f).exists()]
    assert not missing, (
        f"{task_dir.name} is missing {missing}. Build it via "
        f"corpus/_compile_c.py (C) or the assembly equivalent, or mark "
        f"`draft = true` under [task] in its task.toml."
    )

    # Exactly one source form: assembly (source.S) xor C (task.c).
    has_asm = (task_dir / "source.S").exists()
    has_c = (task_dir / "task.c").exists()
    assert has_asm ^ has_c, (
        f"{task_dir.name} must carry exactly one source form "
        f"(source.S xor task.c); found source.S={has_asm}, task.c={has_c}."
    )


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus dir missing")
def test_corpus_is_populated_and_drafts_stay_rare() -> None:
    """Guard the guard: the corpus is fully populated and drafts are rare.

    Without this, deleting the corpus or marking everything draft would let
    the per-task guard above vacuously pass.
    """
    dirs = _task_dirs()
    assert len(dirs) >= 100, f"expected a populated corpus, found {len(dirs)}"
    drafts = sorted(d.name for d in dirs if _is_draft(d))
    assert len(drafts) <= 3, f"draft tasks are piling up, build them: {drafts}"
