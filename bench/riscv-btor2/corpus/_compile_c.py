"""Compile a bare-metal C corpus task into ELF + sidecars + spec.json.

Convention for ``task.c``::

    extern void trap(void) __attribute__((noreturn));

    void _start(void) {
        // ... compute, then assert via the trap pattern:
        if (bad_condition) trap();
        __asm__ volatile ("ebreak");   // normal halt
    }

    void trap(void) {
        __asm__ volatile ("ebreak");   // bad halt — distinct PC
        __builtin_unreachable();
    }

The auto-generated ``spec.json``:

- ``entry_function`` = "_start"
- ``included_callees`` = ["trap"] (override via ``[c].included_callees``)
- ``property.expression`` = ``eq(pc, const(<addr of trap>))``
- ``analysis.engine``    = "z3-bmc" (override via ``[c].engine``)
- ``analysis.bound``     = 20       (override via ``[c].bound``)
- ``analysis.timeout``   = 60       (override via ``[c].timeout``)

Per-task customisation lives under a ``[c]`` table in ``task.toml``::

    [c]
    engine           = "bitwuzla"
    bound            = 50
    bad_function     = "trap"            # default; override only if renamed
    included_callees = ["trap", "helper"]

Reuses the existing ``_emit_pcs.py`` and ``_emit_dwarfmap.py`` for the
sidecars so the C path produces the same artifact set as the assembly
path (``source.elf``, ``pcs.json``, ``source.elf.dwarfmap.json``,
``spec.json``).

Usage:
    python bench/riscv-btor2/corpus/_compile_c.py <task_dir>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore


CC = "riscv64-unknown-elf-gcc"
NM = "riscv64-unknown-elf-nm"

# Mirror the assembly-path build so source.elf bytes are reproducible.
# -Ttext=0x10000 matches the assembly Makefile's LDFLAGS so the entry
# PC is identical across paths.
CFLAGS = (
    "-march=rv64imc",
    "-mabi=lp64",
    "-O0",
    "-nostdlib",
    "-nostartfiles",
    "-ffreestanding",
    "-g",
    "-Wl,-Ttext=0x10000",
    "-Wl,--no-relax",
    # Place trap before _start in the linked output so its address is
    # predictable — actually, leave linker order to ld; the auto-spec-gen
    # discovers addresses by symbol lookup, so this doesn't matter.
)


def _read_task_toml(task_dir: Path) -> dict:
    p = task_dir / "task.toml"
    if not p.exists():
        raise FileNotFoundError(f"missing {p}")
    return tomllib.loads(p.read_text())


def _compile(task_dir: Path) -> Path:
    src = task_dir / "task.c"
    elf = task_dir / "source.elf"
    cmd = [CC, *CFLAGS, "-o", str(elf), str(src)]
    print("  " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    return elf


def _symbol_address(elf: Path, name: str) -> int | None:
    """Return the address of ``name`` in ``elf``, or None if absent.

    Uses ``riscv64-unknown-elf-nm``; matches a global text symbol by
    exact name. Multi-symbol files with the same name are not handled
    (intentionally — the C bench discipline forbids them)."""
    out = subprocess.run(
        [NM, str(elf)], check=True, capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == name:
            return int(parts[0], 16)
    return None


def _emit_sidecars(repo_root: Path, elf: Path) -> None:
    here = Path(__file__).resolve().parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    subprocess.run(
        [sys.executable, str(here / "_emit_pcs.py"), str(elf)],
        check=True, env=env,
    )
    subprocess.run(
        [sys.executable, str(here / "_emit_dwarfmap.py"), str(elf)],
        check=True, env=env,
    )


def _build_spec(task_dir: Path, elf: Path, task_toml: dict) -> dict:
    c_cfg = task_toml.get("c", {}) if isinstance(task_toml, dict) else {}
    bad_fn = c_cfg.get("bad_function", "trap")
    bad_pc = _symbol_address(elf, bad_fn)
    if bad_pc is None:
        raise RuntimeError(
            f"cannot find symbol {bad_fn!r} in {elf} — "
            "C task must declare and define `trap` (or override "
            "[c].bad_function in task.toml)"
        )
    callees = c_cfg.get("included_callees")
    if callees is None:
        callees = [bad_fn]

    return {
        "pair": "riscv-btor2",
        "fields": {
            "binary":  {"path": "source.elf"},
            "scope":   {
                "entry_function": "_start",
                "included_callees": list(callees),
            },
            "entry":   {"excluded_pc_ranges": []},
            "observables": [],
            "assumptions": [],
            "learned":     [],
            "property": {
                "expression": f"eq(pc, const(0x{bad_pc:x}))",
                "negate": False,
            },
            "analysis": {
                "engine":          c_cfg.get("engine",  "z3-bmc"),
                "bound":           c_cfg.get("bound",    20),
                "timeout":         c_cfg.get("timeout",  60),
                "havoc_registers": ["__set__"],
                "extra_options":   {},
            },
        },
        # Bookkeeping — record what auto-resolution picked so the
        # corpus author can read it back when filling in [witness].
        "_auto": {
            "bad_function": bad_fn,
            "bad_pc":       f"0x{bad_pc:x}",
            "bad_pc_int":   bad_pc,
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("task_dir", type=Path, help="task directory (contains task.c, task.toml)")
    args = ap.parse_args(argv)

    task_dir = args.task_dir.resolve()
    if not (task_dir / "task.c").exists():
        print(f"no task.c in {task_dir}", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[3]

    task_toml = _read_task_toml(task_dir)
    elf = _compile(task_dir)
    _emit_sidecars(repo_root, elf)
    spec = _build_spec(task_dir, elf, task_toml)
    spec_path = task_dir / "spec.json"
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    auto = spec["_auto"]
    print(
        f"  wrote {spec_path.relative_to(task_dir.parent.parent.parent)} "
        f"(bad_function={auto['bad_function']!r}, bad_pc={auto['bad_pc']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
