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

## Source

The Dockerfile, source code, and benchmarking playbook live at
<https://github.com/christophkirsch/hurdy-gurdy>.
