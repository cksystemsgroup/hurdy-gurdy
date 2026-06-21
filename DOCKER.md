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
| `boolector` | 3.2.4 (the SMT CLI from the btormc build) | a 4th SMT corroboration **solver** (`smt_cli`); shares bitwuzla's lineage, so z3 stays the independence axis |
| `gcc-riscv64-unknown-elf` + binutils | Debian (apt) | the pinned RV64 toolchain `c-riscv` compiles through; also assembles RISC-V interpreter test inputs |
| `csmith` + `libcsmith-dev` + `picolibc-riscv64-unknown-elf` | Debian (apt, 2.3.0 / 1.8.10) | **external-generator fuzzing** (BENCHMARKS.md §3): random C, the `csmith.h` runtime header, and the RV64 libc headers so a generated program compiles through the pinned gcc (`--specs=picolibc.specs -I/usr/include/csmith`). Run/checksum harness pending (see Gaps) |
| `cbmc` | apt (tag `cbmc-6.4.0`) | independent **C differential checker** for `c-riscv` ([`PATHS.md`](./PATHS.md) §3) |
| `sail_riscv_sim` | sail-riscv 0.12 | **interpreter oracle**: the official Sail RISC-V model's emulator, ground truth for the RISC-V interpreter and `riscv-sail` |
| `carcara` | git `45bfaed` | **witness checker** for Alethe proofs ([`SOLVERS.md`](./SOLVERS.md) §5-6) — present; BV proofs not yet checkable (see Gaps) |
| `drat-trim` | apt `0.0~git20240428` | **witness checker** for DRAT/SAT proofs — **wired**: validates the route-(a) `proved` certificate (`gurdy/solvers/proved.py`) |
| `cadical` | apt `1.7.4` | **DRAT producer** (untrusted): refutes bitwuzla's bit-blasted CNF and emits the DRAT `drat-trim` checks |

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
`FROM <prior-image>` that adds only the missing layers (e.g. `sail_riscv_sim`,
`btormc`, `carcara`) builds in a couple of minutes and reuses everything else.
With every tool present, `python -m unittest discover -s tests` reports **0
skips** entirely in-container (in-image the full suite is **230 tests, 1
legitimate skip** — only the host-only checker-absent test; all engines and
checkers are present). The current image is `christophkirsch/hurdy-gurdy-bench:dev`
@ `sha256:b5e944862e4290e7820cd3ae00addc966cf95826b6a1f5d0e158ce6d4e94bed5` — the
canonical **multi-arch (amd64 + arm64)** build from the Dockerfile (with `cadical`
inline for the route-(a) `proved` tier, `boolector` as a 4th SMT corroboration
engine, and `csmith` + `picolibc` for external-generator fuzzing), produced by the
`dev-image` CI workflow below.

### Canonical multi-arch build (CI)

The reproducible **amd64 + arm64** image is built and pushed by the
[`dev-image`](.github/workflows/dev-image.yml) GitHub Actions workflow — one
**native** runner per arch (no QEMU; the from-source layers are too heavy to
emulate), pushed by digest and stitched into a manifest list. It needs the repo
secrets `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`, and runs on a Dockerfile change
to `main` or via *Run workflow* (tag input, default `dev`); it also pushes an
immutable `:<short-sha>` pin. This is the canonical path — a local `docker build`
or an `extend-don't-rebuild` overlay (`FROM <prior-image>` adding only the
missing layers, ~minutes) is the single-arch convenience for dev iteration.

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

- **BTOR2 solvers** — `AVR` (`pono` and `btormc` are present; AVR not yet — it
  is absent everywhere, so its adapter can't be validated until the binary lands;
  `gurdy/solvers/native_btor2.py` is where it would be discovered/invoked).
- **SMT solver** — `Yices2` is now **wired** (`gurdy/solvers/smt_cli.py`,
  `YicesSmtBackend`) alongside `boolector`; both are inert in the image until the
  binaries are added (the cvc5/bitwuzla pattern).
- **Witness checkers + the `proved` tier — route (a) now wired and demonstrated.**
  The trust-free **bitblast → DRAT → `drat-trim`** route is built
  (`gurdy/solvers/proved.py`, `btor2-smtlib.prove`) and **surfaces a `proved`
  verdict in-image**: `prove(x*x==3, 1)` → `tier=proved`, `checker_ok=True`,
  `tcb={bitwuzla:bit-blast, drat-trim}` — a bitwuzla-bit-blasted CNF, refuted by
  `cadical`, the DRAT independently `VERIFIED` by `drat-trim`
  (`tests/test_proved.py::TestDratCertificate`, gated). This required installing
  **`cadical`** — the image *built* it for btormc but discarded it; it is now an
  apt layer next to `drat-trim`. Honest TCB caveat: the BV→CNF bit-blaster is
  trusted (drat-trim certifies the CNF, not the blasting), so this is short of
  *trust-free BV*. Still to add: `cake_lpr` (verified LRAT — strictly stronger
  TCB), an LFSC checker, and `certifaiger` for the **pono IC3 invariant** route
  (b). The Carcara/LFSC routes stay blocked for BV (the finding above stands).
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
- **Csmith fuzz harness — built** (`tools/csmith_fuzz.py`,
  `tests/test_csmith_differential.py`, gated on the toolchain so it runs only
  in-image). The c-riscv Csmith differential is wired via path **(b)**: a
  no-libc shim (`printf` no-op + `mem*`/`str*`) and a `_start` that sets `gp`
  (small globals are gp-relative — without it the checksum silently never
  updates), `sp`, and `argc=1`, linked `-nostdlib`; the program runs on the
  shared interp and `crc32_context` is read from memory by its ELF symbol, then
  compared to a **native `gcc`** run of the same program. The pure-Python interp
  caps the workable size — a tight `--no-arrays` Csmith config halts in ~16k
  steps; a program over `step_cap` is a first-class *skip*, not a hang. Validated
  in-image (a 10-seed campaign: 10 match, 0 mismatch). **`riscv-torture`**
  (RISC-V fuzz) is still pending — it additionally needs `sbt`/`scala`.

Each addition follows the existing layer pattern (pinned tag/commit,
`TARGETARCH` for multi-arch) and bumps the image digest — a versioned change,
like any other pin.
