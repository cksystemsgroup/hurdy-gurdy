#!/usr/bin/env python3
"""Scope the c-riscv path against a pinned SV-COMP suite — the stated
prerequisite of the second campaign act (FRONTIER.md §5: "SV-COMP is
the natural second act — source-level C questions down the full
spine"). The census is mechanical and reproducible: every pinned
instance is walked through the *actual* front of the spine — pinned
fetch → the pinned compiler at the pinned flags → a freestanding link
against a scoping shim → the riscv-btor2 hub translator — and what
stops it is recorded as a typed gap, never a guess.

    python tools/scope_svcomp.py benchmarks/svcomp-bitvector.json \\
        -o benchmarks/svcomp-bitvector.scope.json

Per instance the row records, in path order:

* **fetch** — streamed-with-pin through ``core/benchmark.py`` (sha256
  verified; offline is a typed row, not a crash).
* **front** — does ``riscv64-unknown-elf-gcc`` at the pair's pinned
  ``FLAGS`` (rv64im / lp64) accept the source at all (``-c``)?
* **link** — freestanding link against a generated *scoping shim*: a
  separate translation unit stubbing exactly the task's referenced
  ``__VERIFIER_nondet_*`` signatures (returning 0 — this makes the
  linker happy and is **not** a semantics; the census exists to say
  so) plus ``__assert_fail`` / ``abort`` / ``exit``. Symbols still
  undefined after the shim are the family's *measured* libc surface
  (rv64im is soft-float, so float tasks surface libgcc here).
* **hub** — the linked ELF through ``pairs/riscv-btor2``'s translator:
  does the task reach the BTOR2 hub, or does an instruction outside
  the user slice raise a typed ``Unsupported``?
* **anchors** — which of ``reach_error`` / ``__assert_fail`` /
  ``abort`` survive into the linked ELF's symbol table. The shim's
  symbols live in their own TU and there is no LTO in the pinned
  flags, so a call *into the shim* can never be inlined away —
  ``__assert_fail``/``abort`` are the sound pc-reachability anchors
  for a future ``unreach-call`` property; task-defined
  ``reach_error`` alone is not (``-O2`` may inline its call sites).

Gaps that no probe can clear today are typed against the machinery
that would have to change (the why_not idiom — first failing obstacle
named, full set kept):

* ``harness.property`` — ``unreach-call`` is pc-reachability of an
  anchor symbol; ``pairs/riscv-btor2`` emits only a ``reg_eq`` bad
  signal (translate.py). Universal to the suite.
* ``harness.nondet`` — the hub model is deterministic in
  ``(image, init_regs)``; a task calling ``__VERIFIER_nondet_*``
  needs those reads modeled as free inputs, a pair-level design
  decision, not a stub.
* ``pin.data-model`` — the task is labeled under ILP32; the pair's
  pin is lp64. Flagged when a width-divergent construct is actually
  detected (a plain ``long``, or a divergent nondet type) — an
  under-approximating proxy (pointer/int games escape it), stated as
  such rather than silently ignored.

``answerable-today`` is a row with no gaps; the aggregate prints the
count honestly (the expected answer is 0/36 — the value of the run is
the typed distribution and the measured surfaces, which order the
implementation work). The report is pure: byte-identical on the same
pin file and toolchain (the toolchain line is recorded — the c-riscv
pin is per-toolchain), no timestamps.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gurdy.core.benchmark import Benchmark, fetch  # noqa: E402
from gurdy.core.errors import Unsupported  # noqa: E402
from gurdy.languages.riscv.elf import load_elf  # noqa: E402
from gurdy.pairs.c_riscv.translate import FLAGS, find_gcc  # noqa: E402
from gurdy.pairs.riscv_btor2.translate import translate as hub_translate  # noqa: E402

# The C return type for each __VERIFIER_nondet_* suffix the suite
# uses. The stub lives in its own translation unit, so it can never
# conflict with the task's own declaration. An unmapped suffix gets no
# stub and surfaces in link.unresolved — reported, never guessed.
NONDET_C_TYPES = {
    "bool": "_Bool", "char": "char", "uchar": "unsigned char",
    "short": "short", "ushort": "unsigned short",
    "int": "int", "uint": "unsigned int", "unsigned": "unsigned int",
    "long": "long", "ulong": "unsigned long",
    "longlong": "long long", "ulonglong": "unsigned long long",
    "float": "float", "double": "double",
    "pointer": "void *", "size_t": "__SIZE_TYPE__",
}

# Nondet suffixes whose width differs between ILP32 (the labels' data
# model) and lp64 (the pair's pinned ABI).
DIVERGENT_NONDET = {"long", "ulong", "pointer", "size_t"}

ANCHOR_SYMBOLS = ("reach_error", "__assert_fail", "abort")

_NONDET_RE = re.compile(r"__VERIFIER_nondet_(\w+)\s*\(")
_UNDEF_RE = re.compile(r"undefined reference to [`']([^']+)'")


def nondet_types(source: str) -> list[str]:
    """Sorted set of ``__VERIFIER_nondet_*`` suffixes the source calls."""
    return sorted(set(_NONDET_RE.findall(source)))


def plain_long_uses(source: str) -> int:
    """Occurrences of a *plain* ``long`` (32-bit under ILP32, 64 under
    lp64) — ``long long`` (64 under both) does not count."""
    total = len(re.findall(r"\blong\b", source))
    double = len(re.findall(r"\blong\s+long\b", source))
    return total - 2 * double


def shim_for(nondets: list[str]) -> tuple[str, list[str]]:
    """The scoping shim TU: stubs for exactly the referenced nondet
    signatures (returning 0 — link plumbing, not semantics) plus the
    anchor runtime. Returns ``(source, unmapped_suffixes)``."""
    lines = [
        "/* scoping shim (tools/scope_svcomp.py): makes the freestanding",
        "   link decidable; the constant returns are NOT a semantics. */",
        "void __assert_fail(const char *a, const char *f, unsigned l,",
        "                   const char *fn) {",
        "  (void)a; (void)f; (void)l; (void)fn; __builtin_trap();",
        "}",
        "void abort(void) { __builtin_trap(); }",
        "void exit(int c) { (void)c; for (;;) ; }",
    ]
    unmapped = []
    for suffix in nondets:
        ctype = NONDET_C_TYPES.get(suffix)
        if ctype is None:
            unmapped.append(suffix)
            continue
        zero = "0" if ctype != "void *" else "(void *)0"
        lines.append(f"{ctype} __VERIFIER_nondet_{suffix}(void) "
                     f"{{ return {zero}; }}")
    return "\n".join(lines) + "\n", unmapped


def parse_undefined(ld_stderr: str) -> list[str]:
    """Unique undefined-reference symbols, in first-seen order."""
    seen: list[str] = []
    for sym in _UNDEF_RE.findall(ld_stderr):
        if sym not in seen:
            seen.append(sym)
    return seen


def compile_probe(source: bytes, suffix: str, gcc: str,
                  nondets: list[str]) -> dict[str, Any]:
    """Front (``-c``) and link (shim TU) probes at the pinned FLAGS."""
    shim_src, unmapped = shim_for(nondets)
    with tempfile.TemporaryDirectory() as d:
        task = Path(d) / f"task{suffix}"
        task.write_bytes(source)
        obj, shim_c, shim_o, elf = (Path(d) / n for n in
                                    ("task.o", "shim.c", "shim.o", "task.elf"))
        front = subprocess.run([gcc, *FLAGS, "-c", str(task), "-o", str(obj)],
                               capture_output=True, text=True)
        if front.returncode != 0:
            return {"front_ok": False, "link_ok": False, "unresolved": [],
                    "nondet_unmapped": unmapped, "elf": None,
                    "front_error": front.stderr.strip().splitlines()[-1][:200]
                    if front.stderr.strip() else "compile failed"}
        shim_c.write_text(shim_src)
        shim = subprocess.run([gcc, *FLAGS, "-c", str(shim_c), "-o", str(shim_o)],
                              capture_output=True, text=True)
        if shim.returncode != 0:  # a shim that cannot compile is a tool bug
            raise RuntimeError(f"scoping shim failed to compile: {shim.stderr}")
        link = subprocess.run([gcc, *FLAGS, str(obj), str(shim_o),
                               "-o", str(elf)], capture_output=True, text=True)
        if link.returncode != 0:
            return {"front_ok": True, "link_ok": False,
                    "unresolved": parse_undefined(link.stderr),
                    "nondet_unmapped": unmapped, "elf": None}
        return {"front_ok": True, "link_ok": True, "unresolved": [],
                "nondet_unmapped": unmapped, "elf": elf.read_bytes()}


def hub_probe(elf_bytes: bytes) -> dict[str, Any]:
    """The linked ELF through the riscv-btor2 translator (no property,
    no execution — does the task *reach the hub*?), plus the anchor
    symbols that survived into the symbol table."""
    image = load_elf(elf_bytes)
    if "main" in image.symbols:
        image = load_elf(elf_bytes, entry_symbol="main")
    anchors = [s for s in ANCHOR_SYMBOLS if s in image.symbols]
    try:
        btor2 = hub_translate({"image": image})
        return {"hub_ok": True, "unsupported": None,
                "btor2_lines": btor2.count(b"\n"), "anchors": anchors}
    except Unsupported as e:
        return {"hub_ok": False, "unsupported": str(e),
                "btor2_lines": None, "anchors": anchors}


def gaps_for(row: dict[str, Any]) -> list[str]:
    """The typed gap set, in path order; ``[0]`` is the first binding
    obstacle (the why_not idiom)."""
    gaps: list[str] = []
    if not row.get("fetched"):
        return ["fetch.offline"]
    if not row.get("front_ok"):
        return ["front.error"]
    if not row.get("link_ok"):
        return [f"link.unresolved:{','.join(row.get('unresolved', []))}"]
    if not row.get("hub_ok"):
        return [f"hub.unsupported:{row.get('unsupported')}"]
    gaps.append("harness.property")  # unreach-call needs a pc anchor;
    #                                  riscv-btor2 emits reg_eq only
    if row.get("nondet_types"):
        gaps.append("harness.nondet")
    divergent = sorted(set(row.get("nondet_types", [])) & DIVERGENT_NONDET)
    if (row.get("meta", {}).get("data_model") == "ILP32"
            and (divergent or row.get("plain_long_uses", 0))):
        gaps.append("pin.data-model")
    return gaps


def scope_bench(bench: Benchmark, gcc: str,
                fetcher: Callable[..., bytes | None] = fetch,
                cache_dir: str | None = None) -> dict[str, Any]:
    """The census: one row per instance, then the aggregate."""
    rows = []
    for inst in bench.instances:
        row: dict[str, Any] = {"name": inst.name, "expected": inst.expected,
                               "meta": dict(inst.meta)}
        data = fetcher(bench, inst.name, cache_dir=cache_dir)
        row["fetched"] = data is not None
        if data is not None:
            source = data.decode("latin-1")
            row["nondet_types"] = nondet_types(source)
            row["plain_long_uses"] = plain_long_uses(source)
            probe = compile_probe(data, Path(inst.path).suffix or ".c",
                                  gcc, row["nondet_types"])
            elf = probe.pop("elf")
            row.update(probe)
            if elf is not None:
                row.update(hub_probe(elf))
        row["gaps"] = gaps_for(row)
        rows.append(row)

    gap_census: dict[str, int] = {}
    for r in rows:
        for g in r["gaps"]:
            key = g.split(":", 1)[0]
            gap_census[key] = gap_census.get(key, 0) + 1
    nondet_census: dict[str, int] = {}
    surface: dict[str, int] = {}
    for r in rows:
        for t in r.get("nondet_types", []):
            nondet_census[t] = nondet_census.get(t, 0) + 1
        for s in r.get("unresolved", []):
            surface[s] = surface.get(s, 0) + 1
    toolchain = subprocess.run([gcc, "--version"], capture_output=True,
                               text=True).stdout.splitlines()[0]
    aggregate = {
        "instances": len(rows),
        "fetched": sum(r["fetched"] for r in rows),
        "front_ok": sum(bool(r.get("front_ok")) for r in rows),
        "link_ok": sum(bool(r.get("link_ok")) for r in rows),
        "hub_ok": sum(bool(r.get("hub_ok")) for r in rows),
        "answerable_today": sum(not r["gaps"] for r in rows),
        "gap_census": dict(sorted(gap_census.items())),
        "nondet_census": dict(sorted(nondet_census.items())),
        "unresolved_surface": dict(sorted(surface.items())),
        "toolchain": toolchain,
        "flags": list(FLAGS),
    }
    return {"suite": bench.suite, "source": bench.source,
            "aggregate": aggregate, "rows": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bench", help="pinned benchmark JSON (pin_svcomp.py)")
    ap.add_argument("-o", "--out", help="write the report JSON here")
    args = ap.parse_args(argv)

    gcc = find_gcc()
    if not gcc:
        print("riscv64-unknown-elf-gcc not found (set $RISCV_GCC) — "
              "the compile/link/hub probes need the pinned toolchain",
              file=sys.stderr)
        return 2
    with open(args.bench) as f:
        bench = Benchmark.from_json(f.read())
    report = scope_bench(bench, gcc)

    agg = report["aggregate"]
    for r in report["rows"]:
        first = r["gaps"][0] if r["gaps"] else "answerable"
        nd = ",".join(r.get("nondet_types", [])) or "-"
        print(f"{r['name']:40s} {r['expected'] or 'unlabeled':12s} "
              f"nondet[{nd}] first-gap={first}")
    print(f"\n{agg['instances']} instances: {agg['fetched']} fetched, "
          f"{agg['front_ok']} front-ok, {agg['link_ok']} link-ok, "
          f"{agg['hub_ok']} hub-ok, {agg['answerable_today']} "
          f"answerable today")
    print(f"gap census: {agg['gap_census']}")
    print(f"nondet census: {agg['nondet_census']}")
    print(f"measured libc/libgcc surface: {agg['unresolved_surface']}")
    print(f"toolchain: {agg['toolchain']}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"report -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
