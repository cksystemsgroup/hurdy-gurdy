"""Compile a bare-metal AArch64 C corpus task into ELF + spec.json.

Convention for ``task.c``::

    extern void trap(void) __attribute__((noreturn));

    void _start(void) {
        // ... compute, then assert via the trap pattern:
        if (bad_condition) trap();
        __asm__ volatile ("svc #0");       // normal halt
        __builtin_unreachable();
    }

    void trap(void) {
        __asm__ volatile ("brk #0");       // bad halt — distinct PC
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
    opt_level        = "2"               # gcc -O level; default "0".
                                         # "0"/"1"/"2"/"3"/"s"/"g" supported.

The AArch64-vs-riscv-btor2 differences:
- ``pair`` = "aarch64-btor2" (not "riscv-btor2")
- Normal halt: ``svc #0``.  Bad halt: ``brk #0``.  Both set halted=1 in the
  BTOR2 model; the property distinguishes them by PC.
- Text base: 0x400000 (matches tests/fixtures/elf_builder_aarch64.py).
- Compiler: ``aarch64-linux-gnu-gcc`` / ``aarch64-linux-gnu-nm``.
- No sidecar scripts yet (_emit_pcs.py / _emit_dwarfmap.py are deferred to
  a later phase once the DWARF line-table support is wired).

The gcc version used to compile must be pinned in task.toml::

    [c]
    gcc_version = "13.3.0-6ubuntu2~24.04.1"

Usage:
    python bench/aarch64-btor2/corpus/_compile_c.py <task_dir>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore


CC = "aarch64-linux-gnu-gcc"
NM = "aarch64-linux-gnu-nm"

# Text base matches tests/fixtures/elf_builder_aarch64.py so hand-crafted
# and C-compiled ELFs live in the same address space.
_TEXT_BASE = "0x400000"

_BASE_CFLAGS = (
    "-march=armv8-a",
    "-nostdlib",
    "-nostartfiles",
    "-ffreestanding",
    "-g",
    f"-Wl,-Ttext={_TEXT_BASE}",
)
_VALID_OPT_LEVELS = {"0", "1", "2", "3", "s", "g"}


def _cflags_for(opt_level: str) -> tuple[str, ...]:
    if opt_level not in _VALID_OPT_LEVELS:
        raise ValueError(
            f"unknown opt_level {opt_level!r}; "
            f"supported: {sorted(_VALID_OPT_LEVELS)}"
        )
    return (f"-O{opt_level}", *_BASE_CFLAGS)


def _read_task_toml(task_dir: Path) -> dict:
    p = task_dir / "task.toml"
    if not p.exists():
        raise FileNotFoundError(f"missing {p}")
    return tomllib.loads(p.read_text())


def _compile(task_dir: Path, opt_level: str) -> Path:
    src = task_dir / "task.c"
    elf = task_dir / "source.elf"
    cflags = _cflags_for(opt_level)
    cmd = [CC, *cflags, "-o", str(elf), str(src)]
    print("  " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    return elf


def _symbol_address(elf: Path, name: str) -> int | None:
    """Return the start address of symbol ``name`` in ``elf``, or None."""
    out = subprocess.run(
        [NM, str(elf)], check=True, capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == name:
            return int(parts[0], 16)
    return None


def _build_spec(task_dir: Path, elf: Path, task_toml: dict, opt_level: str) -> dict:
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
        "pair": "aarch64-btor2",
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
        "_auto": {
            "bad_function": bad_fn,
            "bad_pc":       f"0x{bad_pc:x}",
            "bad_pc_int":   bad_pc,
            "opt_level":    opt_level,
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

    task_toml = _read_task_toml(task_dir)
    c_cfg = task_toml.get("c", {}) if isinstance(task_toml, dict) else {}
    opt_level = str(c_cfg.get("opt_level", "0"))
    elf = _compile(task_dir, opt_level)
    spec = _build_spec(task_dir, elf, task_toml, opt_level)
    spec_path = task_dir / "spec.json"
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    auto = spec["_auto"]
    print(
        f"  wrote {spec_path.relative_to(task_dir.parent.parent)} "
        f"(bad_function={auto['bad_function']!r}, "
        f"bad_pc={auto['bad_pc']}, opt_level=-O{auto['opt_level']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
