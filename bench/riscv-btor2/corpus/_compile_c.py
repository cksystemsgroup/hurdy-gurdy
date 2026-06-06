"""Compile a bare-metal C corpus task into ELF + sidecars + spec.json.

**Reproducible build (v0.5+).** This script now builds through the
``c-riscv`` compile hop (``gurdy/hops/c_riscv``) — the pinned compiler in
the bench Docker image, addressed *by digest* — instead of the host
toolchain. Same ``task.c`` (+ ``[c].opt_level``) ⇒ byte-identical
``source.elf`` on any host that can resolve the pin. This replaces the
earlier host-``gcc`` build, which embedded the local compiler version and
absolute host paths into DWARF and so was not reproducible (see
``gurdy/hops/c_riscv/CONTRACT.md`` §"What this fixes"). Requires Docker +
the pinned image (``toolchain_available()``); it errors out otherwise
rather than silently falling back to a non-reproducible local build.

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
    opt_level        = "2"               # gcc -O level; default "0".
                                         # "0"/"1"/"2"/"3"/"s"/"g" supported.

Artifacts written (the same set as before, now reproducible):
``source.elf``, ``pcs.json`` (via ``_emit_pcs.emit_pcs``, in-process and
deterministic from the ELF bytes), ``source.elf.dwarfmap.json`` (via the
hop's pinned ``objdump``, ``extract_line_map``), and ``spec.json`` (trap PC
resolved in-process from the ELF, no host ``nm``).

Usage:
    python bench/riscv-btor2/corpus/_compile_c.py <task_dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore

# Make the repo importable (gurdy.*) and this dir importable (_emit_pcs).
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
for _p in (str(_REPO_ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gurdy.hops.c_riscv import (  # noqa: E402
    ToolchainUnavailable,
    compile_c,
    default_pin,
    extract_line_map,
    toolchain_available,
)
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary  # noqa: E402

from _emit_pcs import emit_pcs  # noqa: E402  (same-dir import)

# Logical filename embedded in DWARF. Must be ``task.c`` so the recovered
# source map names the on-disk source (and matches the chain oracle, which
# also compiles with source_name="task.c").
_SOURCE_NAME = "task.c"
_VALID_OPT_LEVELS = {"0", "1", "2", "3", "s", "g"}


def _read_task_toml(task_dir: Path) -> dict:
    p = task_dir / "task.toml"
    if not p.exists():
        raise FileNotFoundError(f"missing {p}")
    return tomllib.loads(p.read_text())


def _compile(task_dir: Path, opt_level: str) -> tuple[Path, bytes]:
    """Compile ``task.c`` reproducibly via the pinned hop; write source.elf."""
    src = (task_dir / "task.c").read_bytes()
    res = compile_c(src, opt_level=opt_level, source_name=_SOURCE_NAME)
    elf = task_dir / "source.elf"
    elf.write_bytes(res.elf_bytes)
    print(
        f"  compiled task.c -> source.elf "
        f"(-O{opt_level}, {default_pin().compiler} {default_pin().compiler_version} "
        f"@{default_pin().digest[:19]}…, sha256={res.elf_sha256[:12]})"
    )
    return elf, res.elf_bytes


def _symbol_address(elf_bytes: bytes, name: str) -> int | None:
    """Return the start PC of ``name`` in the ELF, or None if absent.

    Resolved in-process via the pair's own ELF loader (deterministic from
    the bytes) — no host ``nm``."""
    fn = load_riscv_binary(elf_bytes).function(name)
    return fn.start if fn is not None else None


def _emit_dwarfmap(task_dir: Path, elf_bytes: bytes) -> None:
    """Write ``source.elf.dwarfmap.json`` from the *pinned* objdump.

    Uses the hop's ``extract_line_map`` (objdump in the pinned image) so the
    sidecar is reproducible and host-independent, then reshapes to the
    sidecar schema the pair's loader expects (``pc``/``end_pc`` as hex)."""
    entries, end_pc = extract_line_map(elf_bytes)
    payload: dict = {
        "entries": [
            {"pc": hex(e.pc), "file": e.file, "line": e.line} for e in entries
        ]
    }
    if end_pc is not None:
        payload["end_pc"] = hex(end_pc)
    out = task_dir / "source.elf.dwarfmap.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"  wrote {out.name} ({len(entries)} line entries)")


def _emit_pcs_sidecar(task_dir: Path, elf_path: Path) -> None:
    out = task_dir / "pcs.json"
    out.write_text(json.dumps(emit_pcs(elf_path), indent=2) + "\n")
    print(f"  wrote {out.name}")


def _build_spec(task_dir: Path, elf_bytes: bytes, task_toml: dict, opt_level: str) -> dict:
    c_cfg = task_toml.get("c", {}) if isinstance(task_toml, dict) else {}
    bad_fn = c_cfg.get("bad_function", "trap")
    bad_pc = _symbol_address(elf_bytes, bad_fn)
    if bad_pc is None:
        raise RuntimeError(
            f"cannot find symbol {bad_fn!r} in source.elf — "
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

    if not toolchain_available():
        print(
            "pinned bench Docker image unavailable; the reproducible C build "
            "needs it (docker + the pinned image). Not falling back to a "
            "non-reproducible local build.",
            file=sys.stderr,
        )
        return 3

    task_toml = _read_task_toml(task_dir)
    c_cfg = task_toml.get("c", {}) if isinstance(task_toml, dict) else {}
    opt_level = str(c_cfg.get("opt_level", "0"))
    if opt_level not in _VALID_OPT_LEVELS:
        print(
            f"unknown opt_level {opt_level!r}; supported: {sorted(_VALID_OPT_LEVELS)}",
            file=sys.stderr,
        )
        return 2

    try:
        elf_path, elf_bytes = _compile(task_dir, opt_level)
        _emit_pcs_sidecar(task_dir, elf_path)
        _emit_dwarfmap(task_dir, elf_bytes)
        spec = _build_spec(task_dir, elf_bytes, task_toml, opt_level)
    except ToolchainUnavailable as exc:  # pragma: no cover - env dependent
        print(f"toolchain unavailable: {exc}", file=sys.stderr)
        return 3

    spec_path = task_dir / "spec.json"
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    auto = spec["_auto"]
    print(
        f"  wrote spec.json "
        f"(bad_function={auto['bad_function']!r}, "
        f"bad_pc={auto['bad_pc']}, opt_level=-O{auto['opt_level']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
