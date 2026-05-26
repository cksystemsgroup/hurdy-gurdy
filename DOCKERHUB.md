# hurdy-gurdy-bench

Pinned solver toolchain for benchmarking hurdy-gurdy pairs against the
playbook in [BENCHMARKING.md](https://github.com/christophkirsch/hurdy-gurdy/blob/main/BENCHMARKING.md).

This image exists so that BENCHMARKING.md §7's *solver-version pinning*
requirement can be satisfied with one image hash. Bumping any solver
version is a new experiment; record the new image digest in §8.7's run
manifest.

## What's inside

| Solver        | Version             | How it's used                            |
|---------------|---------------------|------------------------------------------|
| pono          | `v2.0.0` (commit `c81aa36`) | subprocess BMC engine for the riscv-btor2 pair |
| z3            | 4.16.0              | in-process backend for `z3-bmc` and `z3-spacer` solvers |
| bitwuzla      | 0.9.1               | in-process backend for the `bitwuzla` solver |
| cvc5          | 1.3.4               | in-process backend for the `cvc5` solver |

Pono is built `--static` so the binary has no shared-library install
dance. smt-switch and btor2tools are vendored by pono's `contrib/`
scripts; their commits are pinned transitively by the pinned pono commit.

Also installed: `gcc-riscv64-unknown-elf` and `binutils-riscv64-unknown-elf`
(bare-metal RV64 toolchain, GNU binutils 2.44). Used by
`bench/riscv-btor2/corpus/Makefile` to assemble each task's `source.S`
into a reproducible `source.elf`.

## Tags

- `:<git-sha>` — the short SHA of the hurdy-gurdy commit whose `Dockerfile`
  produced this image. Use this for any scored run; it's the link between
  image bytes and source.
- `:latest` — most recent build. Convenient for development; do *not*
  cite in publication artifacts (see §8.7).

## Usage

```sh
# Run the benchmark harness against the riscv-btor2 pair, with the host
# repo bind-mounted so source edits are immediately visible:
docker run --rm -it \
    -v "$PWD":/work -w /work \
    christophkirsch/hurdy-gurdy-bench:latest \
    bash -c 'pip install -e ".[test]" && pytest tests/pairs/riscv_btor2'
```

Inside the container, `pono`, `python -c "import z3"`, `import bitwuzla`,
and `import cvc5` all work out of the box.

## Reproducibility status

Pinned: pono commit (v2.0.0 release), base image
(`python:3.12-slim-trixie`), parallelism (`MAKEFLAGS=-j2`), and the
`z3-solver` / `bitwuzla` / `cvc5` PyPI versions (now `==`-pinned).

Not yet pinned (drift possible): apt package versions (`cbmc`, the
RISC-V toolchain). Pin with `apt-get install <pkg>=<version>` before any
publication-quality §7 run.

## What ships through the bind mount

The image deliberately does *not* bake the `gurdy` Python package
in. The recommended workflow bind-mounts the repo and runs
`pip install -e .` inside the container. This means the published
image's solver inventory is the load-bearing pinning artifact;
gurdy itself can evolve at the repo HEAD without rebuilding.

As of `:prereg-v0.1.0` (= `:990f311`), the bind-mounted gurdy code
covers everything the riscv-btor2 benchmark pre-registration
(BENCHMARKING.md §9.1–§9.9) requires:

- All five engines (z3-bmc, z3-spacer with Horn encoding, bitwuzla,
  cvc5, pono) implemented and cross-validated on the corpus.
- Backend-protocol refactor: each engine adapter is ~180 lines
  against a shared BMC driver in `solvers/_bmc.py`.
- DWARF sidecar emission from the corpus build; lift produces
  source-mapped traces with file/line on every step.
- Lift's simulator-driving wired through the BTOR2 symbolic-name →
  nid mapping.
- Per-mnemonic lowering test coverage at 73 parametrize cases plus
  a strict-evaluator regression suite catching sort-mismatch bugs
  at unit-test time.
- Harness `call_llm` adapters for Anthropic + OpenAI; harness
  `tool_solve` subprocess wrapper for z3 and pono CLIs.

The git tag `riscv-btor2-bench-v0.1.0-prereg` points at the same
commit (`990f311`) and is the §4.4 pre-registration identity. The
image digest sha256:0c1bd1541e8d… is the §7 solver-pinning
identity.

## Source

The Dockerfile, source code, and benchmarking playbook live at
<https://github.com/christophkirsch/hurdy-gurdy>.
