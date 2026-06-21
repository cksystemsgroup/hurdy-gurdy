"""External-generator differential fuzzing of `c-riscv` with Csmith
(BENCHMARKS.md §3) — the complement to the in-house `tools/riscv_fuzz`.

Csmith emits a random, UB-free C program that accumulates a CRC checksum over
its globals. This harness compiles it two ways and requires the checksums to
agree:

  - **reference:** native `gcc` (host arch), checksum read from stdout;
  - **subject:**  the pinned `riscv64-unknown-elf-gcc` + a tiny ``-nostdlib``
    runtime shim, run on the shared RISC-V interpreter, with ``crc32_context``
    read from memory by its ELF symbol after the run (`printf` is a no-op; the
    checksum is computed before the program's final, ignored, print).

A divergence (both sides ran, checksums differ) localizes a fault to the c-riscv
compile hop or the interpreter. Csmith is deterministic per ``--seed``.

The shim resolves the only libc functions a generated program references
(`printf`, `mem*`, a couple of `str*`); ``_start`` sets ``gp`` (small globals are
gp-relative — without it the checksum silently never updates), ``sp``, and
``argc=1`` (so `main`'s argv path is skipped), then ``ecall``s to halt.

**Runtime note (the load-bearing constraint).** The interpreter is pure Python
(~10-15k steps/s), so only *small* programs are runnable: a tight
``--no-arrays`` config halts in ~16k steps (~1-2 s); a program that exceeds
``step_cap`` is a first-class **skip** (`too-big`), not a hang. This is a
gated, dev-image-only tool (Csmith + the cross toolchain live there, DOCKER.md).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

# A tight config: no arrays (the main source of long loops), shallow blocks —
# so the generated program halts within a few tens of thousands of interp steps.
CSMITH_FLAGS = [
    "--no-packed-struct", "--no-bitfields", "--no-arrays",
    "--max-funcs", "2", "--max-block-depth", "1", "--max-block-size", "2",
    "--max-expr-complexity", "2", "--max-pointer-depth", "1",
]

_SHIM = r"""
typedef unsigned long size_t;
int printf(const char*f,...){(void)f;return 0;}
void *memcpy(void*d,const void*s,size_t n){char*a=d;const char*b=s;while(n--)*a++=*b++;return d;}
void *memset(void*d,int c,size_t n){char*a=d;while(n--)*a++=(char)c;return d;}
void *memmove(void*d,const void*s,size_t n){char*a=d;const char*b=s;if(a<b)while(n--)*a++=*b++;else{a+=n;b+=n;while(n--)*--a=*--b;}return d;}
int strcmp(const char*a,const char*b){(void)a;(void)b;return 0;}
int strncmp(const char*a,const char*b,size_t n){(void)a;(void)b;(void)n;return 0;}
unsigned long strlen(const char*s){const char*p=s;while(*p)p++;return p-s;}
void abort(void){__builtin_trap();}
void exit(int c){(void)c;for(;;);}
"""

_START = r"""
.section .text._start,"ax"
.global _start
_start:
.option push
.option norelax
    la gp, __global_pointer$
.option pop
    li sp, 0x80000000
    li a0, 1
    li a1, 0
    call main
    ecall
"""

_RISCV = "riscv64-unknown-elf-gcc"
_ARCH = ["-march=rv64imc", "-mabi=lp64"]


def available() -> bool:
    """True iff the full toolchain is present (csmith + native gcc + the pinned
    cross gcc) — false on the host, true in the dev image."""
    return all(shutil.which(t) for t in ("csmith", "gcc", _RISCV, _RISCV[:-3] + "nm"))


def _csmith_include() -> str:
    if os.path.isfile("/usr/include/csmith/csmith.h"):
        return "/usr/include/csmith"
    hit = subprocess.run(["find", "/usr", "-name", "csmith.h"], capture_output=True, text=True)
    line = hit.stdout.strip().splitlines()
    return os.path.dirname(line[0]) if line else "/usr/include/csmith"


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kw)


def _skip(seed: int, reason: str) -> dict:
    return {"seed": seed, "status": "skip", "reason": reason}


def differential(seed: int, step_cap: int = 500_000, opt: str = "-O2") -> dict:
    """Run one Csmith program through both routes. Returns a dict with ``status``
    in ``{"match", "mismatch", "skip"}`` (skip carries a ``reason``)."""
    from gurdy.languages.riscv import load_elf
    from gurdy.languages.riscv.interp import run

    inc = _csmith_include()
    with tempfile.TemporaryDirectory() as d:
        c = os.path.join(d, "p.c")
        # run csmith inside the temp dir: it writes platform.info to the cwd, so
        # keeping cwd=d confines that artifact to the auto-cleaned tempdir.
        if _run(["csmith", "--seed", str(seed), *CSMITH_FLAGS, "--output", c], cwd=d).returncode:
            return _skip(seed, "csmith failed")

        # reference: native compile + run, checksum from stdout
        aout = os.path.join(d, "a.out")
        if _run(["gcc", "-w", opt, f"-I{inc}", c, "-o", aout]).returncode:
            return _skip(seed, "native compile failed")
        native_out = _run([aout]).stdout
        m = re.search(r"checksum\s*=\s*([0-9A-Fa-f]+)", native_out)
        if not m:
            return _skip(seed, "no native checksum")
        native = int(m.group(1), 16)

        # subject: cross compile + shim link
        for name, text in (("shim.c", _SHIM), ("start.s", _START)):
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        obj, shim, start, elf = (os.path.join(d, x) for x in ("p.o", "shim.o", "start.o", "p.elf"))
        steps = [
            [_RISCV, "--specs=picolibc.specs", "-w", opt, "-fno-stack-protector",
             f"-I{inc}", *_ARCH, "-c", c, "-o", obj],
            [_RISCV, *_ARCH, "-fno-stack-protector", "-O2", "-c", os.path.join(d, "shim.c"), "-o", shim],
            [_RISCV, *_ARCH, "-c", os.path.join(d, "start.s"), "-o", start],
            [_RISCV, "-nostdlib", "-nostartfiles", *_ARCH, "-e", "_start", start, obj, shim, "-o", elf],
        ]
        for cmd in steps:
            if _run(cmd).returncode:
                return _skip(seed, "riscv build failed")

        nm = _run([_RISCV[:-3] + "nm", elf]).stdout
        addr = next((int(ln.split()[0], 16) for ln in nm.splitlines()
                     if ln.endswith(" crc32_context")), None)
        if addr is None:
            return _skip(seed, "no crc32_context symbol")

        with open(elf, "rb") as f:
            img = load_elf(f.read())
        trace = run(img, {}, max_steps=step_cap)
        if not trace[-1]["halted"]:
            return _skip(seed, f"too-big (> {step_cap} steps)")
        riscv = (img.load(addr, 4) ^ 0xFFFFFFFF) & 0xFFFFFFFF

        return {"seed": seed, "status": "match" if riscv == native else "mismatch",
                "native": native, "riscv": riscv, "steps": len(trace)}


def campaign(seeds, step_cap: int = 500_000) -> dict:
    """Run a batch; return the tally and any mismatches (a fuzzing entry point —
    not a unit test; the interp is slow)."""
    out = {"match": 0, "mismatch": [], "skip": 0}
    for s in seeds:
        r = differential(s, step_cap)
        if r["status"] == "match":
            out["match"] += 1
        elif r["status"] == "mismatch":
            out["mismatch"].append(r)
        else:
            out["skip"] += 1
    return out


if __name__ == "__main__":  # pragma: no cover - manual campaign
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    print(campaign(range(n)))
