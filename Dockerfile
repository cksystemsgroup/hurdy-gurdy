# hurdy-gurdy benchmark image.
#
# This image is the pinning artifact for BENCHMARKING.md §7 (solver-version
# pinning). Every solver binary the riscv-btor2 pair can dispatch to is
# installed here at a fixed version. Bumping any pin is a new experiment;
# record the new image hash in §8.7's run manifest.
#
# The image grows over time as new pairs and source-level verifiers (§3 D)
# are added — keep additions grouped by purpose and pin everything.
#
# Build:
#   docker build -t hurdy-gurdy-bench:dev .
# Run (bind-mount the repo so the host edits are visible):
#   docker run --rm -it -v "$PWD":/work -w /work hurdy-gurdy-bench:dev bash
# Inside the container:
#   pip install -e .
#   pytest

FROM python:3.12-slim-trixie

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# --- System build dependencies --------------------------------------------
# Needed to compile pono (and smt-switch + btor2tools, which pono's setup
# scripts fetch and build under /opt/pono/deps).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        ca-certificates \
        libgmp-dev \
        libmpfr-dev \
        libtool \
        autoconf \
        automake \
        pkg-config \
        flex \
        libfl-dev \
        bison \
        m4 \
        curl \
        wget \
        gettext-base \
        ninja-build \
        meson \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# --- pono (subprocess solver, built from source) --------------------------
# pono's contrib/setup-* scripts vendor smt-switch and btor2tools. Pin the
# pono commit; the sub-deps are pinned transitively by pono's own scripts.
ARG PONO_COMMIT=59c5cb88de75ebed36027dc0a917407f84bfe020
# Cap parallelism: smt-switch's vendored cvc5 build OOMs at -j$(nproc) on
# typical Docker Desktop memory budgets (~8GB). MAKEFLAGS and CMAKE_BUILD_-
# PARALLEL_LEVEL apply to both the outer make and the setup-script subbuilds.
# Bump Docker Desktop memory to ~12GB before changing back to -j$(nproc).
ENV MAKEFLAGS="-j2" \
    CMAKE_BUILD_PARALLEL_LEVEL=2

# Layer 1: clone + slow sub-builds (smt-switch's cvc5 backend ~25 min).
# Kept separate so changes to pono's configure flags below don't re-trigger.
RUN git clone https://github.com/upscale-project/pono.git /opt/pono \
 && cd /opt/pono \
 && git checkout "${PONO_COMMIT}" \
 && ./contrib/setup-smt-switch.sh \
 && ./contrib/setup-btor2tools.sh

# Layer 2: pono itself (static binary, so no runtime .so deps to ship).
RUN cd /opt/pono \
 && ./configure.sh --static \
 && cd build && make -j2 \
 && install -m 0755 pono /usr/local/bin/pono \
 && cd / && rm -rf /opt/pono/build /opt/pono/deps/*/build

# --- In-process Python solvers --------------------------------------------
# z3-bmc and z3-spacer share the z3-solver wheel; bitwuzla and cvc5 each
# ship their own Python bindings. Pin exact versions so the image hash
# uniquely identifies the solver inventory.
# TODO: replace `>=` with `==` once a baseline run is chosen.
RUN pip install --no-cache-dir --timeout=120 --retries=5 \
        "z3-solver>=4.13" \
        "bitwuzla>=0.5" \
        "cvc5>=1.2"

# --- Solver CLI binaries (BENCHMARKING.md §3 condition C) -----------------
# Condition C exposes whatever the LLM can shell to. The pip wheels above
# install Python bindings only — they do NOT install CLI binaries — so
# without these layers, condition C falls back to z3-only (`z3` is a
# console_script the z3-solver wheel does install).
#
# bitwuzla CLI: built from source. The bench image's Python `bitwuzla`
# wheel and this CLI must agree on version, else the in-process pair
# (B path) and the LLM's hand-encoded SMT-LIB (C path) measure different
# solver versions. Pin to the same tag as the wheel.
ARG BITWUZLA_TAG=0.9.0
RUN git clone --depth 1 --branch "${BITWUZLA_TAG}" https://github.com/bitwuzla/bitwuzla /opt/bitwuzla \
 && cd /opt/bitwuzla \
 && ./configure.py \
 && cd build && ninja \
 && install -m 0755 src/main/bitwuzla /usr/local/bin/bitwuzla \
 && cd / && rm -rf /opt/bitwuzla

# cvc5 CLI: install the static-linked binary release from upstream. The
# tag must match the cvc5 wheel pin above so B and C measure the same
# version.
ARG CVC5_TAG=cvc5-1.3.3
RUN curl -fsSL "https://github.com/cvc5/cvc5/releases/download/${CVC5_TAG}/cvc5-Linux-x86_64-static.zip" -o /tmp/cvc5.zip \
 && (cd /tmp && unzip -o cvc5.zip && install -m 0755 cvc5-Linux-x86_64-static/bin/cvc5 /usr/local/bin/cvc5) \
 && rm -rf /tmp/cvc5.zip /tmp/cvc5-Linux-x86_64-static

# --- RISC-V cross toolchain (corpus build) --------------------------------
# Bare-metal RV64 assembler/linker/gcc, used by bench/riscv-btor2/corpus
# Makefile to produce source.elf from each task's source.S. Pinning the
# image pins the toolchain version, so source.elf bytes are reproducible.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc-riscv64-unknown-elf \
        binutils-riscv64-unknown-elf \
    && rm -rf /var/lib/apt/lists/*

# --- Source-level verifiers (BENCHMARKING.md §3 D) ------------------------
# CBMC consumes ANSI C directly. The v0.4 C-derived corpus
# (bench/riscv-btor2/corpus/0100+, see CORPUS_V0.4_PLAN.md) provides
# the C source CBMC needs; condition_d_reference.py rewrites each
# task.c to a CBMC-friendly variant (task.cbmc.c) and runs CBMC for
# the §3.D source-level baseline.
ARG CBMC_TAG=cbmc-6.4.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        cbmc \
    && rm -rf /var/lib/apt/lists/*
# Note: Debian's cbmc package version may lag the upstream tag pinned
# above. If reproducibility across image rebuilds matters, install
# from upstream releases (.deb or .tar.gz) — see
# https://github.com/diffblue/cbmc/releases.

# --- Default working directory --------------------------------------------
# The repo is expected to be bind-mounted at /work; hurdy-gurdy itself is
# installed at runtime (`pip install -e .`) so source edits on the host
# are picked up without rebuilding the image.
WORKDIR /work
CMD ["bash"]
