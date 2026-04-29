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
| pono          | `v2.0.0-beta.1-52-g59c5cb8` (commit `59c5cb88`) | subprocess BMC engine for the riscv-btor2 pair |
| z3            | 4.16.0              | in-process backend for `z3-bmc` and `z3-spacer` solvers |
| bitwuzla      | 0.9.0               | in-process backend for the `bitwuzla` solver |
| cvc5          | 1.3.3               | in-process backend for the `cvc5` solver |

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

Pinned: pono commit, base image (`python:3.12-slim-trixie`), parallelism
(`MAKEFLAGS=-j2`).

Not yet pinned (loose `>=` in the Dockerfile, drift possible):
`z3-solver`, `bitwuzla`, `cvc5` PyPI versions, and apt package versions.
Tighten to `==` and `apt-get install <pkg>=<version>` before any
publication-quality §7 run.

## What ships through the bind mount

The image deliberately does *not* bake the `gurdy` Python package
in. The recommended workflow bind-mounts the repo and runs
`pip install -e .` inside the container. This means the published
image's solver inventory is the load-bearing pinning artifact;
gurdy itself can evolve at the repo HEAD without rebuilding.

As of `:2466531`, the gurdy code that drives these solvers
includes (relative to the prior `:5e0ba4a` image's HEAD):

- z3-bmc lowering bug fixes (slice/sext/uext eager-eval; LBU/LHU/
  LWU missing zero-extend).
- A real bitwuzla backend (was a v1 stub).
- A real cvc5 backend (was a v1 stub).
- A real z3-spacer backend with Horn-clause encoding (was a v1 stub).
- A backend-protocol refactor making engine adapters ~180 lines each.
- DWARF sidecar emission from the corpus build, populating
  `LiftedStep.{file,line}` for every step.
- Lift's simulator-driving wired through (BTOR2 symbolic-name → nid
  mapping); witness traces now produce real source-mapped steps.
- Per-mnemonic lowering test coverage expanded from ~25 to 73
  parametrize cases plus a strict-evaluator regression suite that
  catches sort-mismatch bugs at unit-test time.

## Source

The Dockerfile, source code, and benchmarking playbook live at
<https://github.com/christophkirsch/hurdy-gurdy>.
