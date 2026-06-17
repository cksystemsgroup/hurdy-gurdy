# The pair-development toolchain image

[`Dockerfile`](./Dockerfile) builds the platform's **pinning artifact**: a
single image that bundles every *external* tool a pair needs, each at a
fixed, reproducible version. It was **salvaged from `origin/main`** (commit
`a7f3c6b`); the build layers and pins are verbatim, the orientation comments
re-pointed at this architecture.

The image matters because the architecture's guarantees rest on pins.
Determinism ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §4) and the
`reproducible` fidelity tier require an exact toolchain; the solver/checker
contract ([`SOLVERS.md`](./SOLVERS.md)) requires pinned engines. The image
*is* that pin: one digest fixes the whole external inventory.

## What's inside

| Tool | Pin | Role in the architecture |
|------|-----|--------------------------|
| `pono` | v2.0.0 (commit `c81aa36`), static | BTOR2 **solver** (BMC / k-induction / IC3) — [`SOLVERS.md`](./SOLVERS.md) §3 |
| `btormc` | Boolector 3.2.4 (CaDiCaL backend) | second native BTOR2 **solver** for the native-vs-bridged cross-check — [`SOLVERS.md`](./SOLVERS.md) §7 |
| `z3` | 4.16.0.0 (wheel + `z3` CLI) | SMT/BTOR2 **solver**; also re-discharges invariants as a **checker** |
| `bitwuzla` | 0.9.1 (wheel + CLI) | SMT-LIB **solver** (bit-vectors) |
| `cvc5` | 1.3.4 (wheel + static CLI) | SMT-LIB **solver**; proof-producing |
| `gcc-riscv64-unknown-elf` + binutils | Debian (apt) | the pinned RV64 toolchain `c-riscv` compiles through; also assembles RISC-V interpreter test inputs |
| `cbmc` | apt (tag `cbmc-6.4.0`) | independent **C differential checker** for `c-riscv` ([`PATHS.md`](./PATHS.md) §3) |
| `sail_riscv_sim` | sail-riscv 0.12 | **interpreter oracle**: the official Sail RISC-V model's emulator, ground truth for the RISC-V interpreter and `riscv-sail` |

Base: `python:3.12-slim-trixie`. Multi-arch (`amd64` + `arm64`) via
`TARGETARCH`. The `gurdy` package is **not** baked in (see below).

## Build and run

```sh
docker build -t hurdy-gurdy:dev .
# bind-mount the repo so host edits are live inside the container:
docker run --rm -it -v "$PWD":/work -w /work hurdy-gurdy:dev bash
```

A full build compiles `pono` (and its vendored cvc5 backend) from source —
~25 min, and OOM-prone. When the expensive solver layers already exist in a
prior image, **extend it** instead of rebuilding: a one-stage
`FROM <prior-image>` that adds only the missing layers (e.g. `sail_riscv_sim`
and `btormc`) builds in a couple of minutes and reuses everything else. With
all eight tools present, `python -m unittest discover -s tests` reports **0
skips** entirely in-container (no host fallback).

The repo is mounted at `/work`; once a pair ships code, `pip install -e .`
inside the container picks up host edits without rebuilding the image.

## How it's used during pair development

The image supplies the three things a pair's commuting square
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §3) needs from the outside world:

- **A pinned translator, for `reproducible` pairs.** `c-riscv`
  ([`pairs/c-riscv`](./pairs/c-riscv/README.md)) compiles C through the
  image's `riscv64-unknown-elf-gcc`. Because the toolchain is pinned by the
  image, "same container ⇒ byte-identical ELF" holds — run the
  recompile-and-diff check ([`PAIRING.md`](./PAIRING.md) §5) inside the
  container.
- **Solvers and checkers, for reasoning targets.** A BTOR2- or SMT-LIB-
  targeting pair (`riscv-btor2`, `sail-btor2`, `btor2-smtlib`, …) calls
  `decide` against `pono` / `z3` / `bitwuzla` / `cvc5` and verifies witnesses
  with the same engines ([`SOLVERS.md`](./SOLVERS.md) §3, §5). Having them at
  one pinned digest is what makes a verdict `reproducible` and a
  native-vs-bridged cross-check meaningful.
- **Interpreter oracles, for `checked` fidelity.** `sail_riscv_sim` is the
  gold reference the shared RISC-V interpreter ([`languages/riscv`](./languages/riscv/README.md))
  and `riscv-sail` are validated against; `cbmc` is the independent C-level
  verifier `c-riscv`'s differential runs ([`PATHS.md`](./PATHS.md) §3). The
  commuting-square check and the differential both run *in-container* so the
  oracle version is pinned too.

Workflow per pair: develop on the host, run translator/interpreter/oracle
checks in the container, and cite the **image digest** with any fidelity
claim (it identifies the exact external inventory behind it).

## Pins, and what is not yet pinned

Fully pinned (by `==` or commit/tag): `pono`, `z3`, `bitwuzla`, `cvc5`, the
base image, and `sail_riscv_sim`. **Not** yet pinned exactly — Debian apt may
drift: `cbmc` and the RISC-V GCC/binutils packages. Before any
publication-grade `reproducible`/`checked` claim, pin these with
`apt-get install <pkg>=<version>` (or install `cbmc` from upstream releases)
and record the resulting image digest.

## Gaps to close as pairs are built

The image is today's subset, not the whole [`SOLVERS.md`](./SOLVERS.md)
inventory. Add a pinned layer when a pair first needs one of these:

- **BTOR2 solvers** — `AVR` (`pono` and `btormc` are present; AVR not yet).
- **SMT solver** — `Yices2`.
- **Witness checkers** — `drat-trim` / `cake_lpr` (LRAT), `Carcara`
  (Alethe), an LFSC checker, `certifaiger` — needed to back any `proved`
  claim ([`SOLVERS.md`](./SOLVERS.md) §5–6).
- **ARM Sail emulator** — the oracle for `aarch64-sail`
  ([`pairs/aarch64-sail`](./pairs/aarch64-sail/README.md)); the analogue of
  `sail_riscv_sim` for AArch64.
- **Per-source oracles** — e.g. WasmCert/KWasm, CertrBPF, KEVM
  ([`REGISTRY.md`](./REGISTRY.md) "Formal models per source language"), as
  those pairs are built.
- **Pinned benchmark suites** — small, license-clean compliance suites
  (riscv-arch-test, the Wasm spec tests, `ethereum/tests` subsets) may be
  vendored here as pinned submodules; large suites (SV-COMP) stay
  streamed-with-pin ([`BENCHMARKS.md`](./BENCHMARKS.md) §4).

Each addition follows the existing layer pattern (pinned tag/commit,
`TARGETARCH` for multi-arch) and bumps the image digest — a versioned change,
like any other pin.
