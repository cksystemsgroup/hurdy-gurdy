# hurdy-gurdy — pair-development toolchain image.
#
# Salvaged from origin/main (commit a7f3c6b); the build layers and version
# pins are preserved verbatim — only this orientation header and a few
# section comments were re-pointed at the lean architecture. This image is
# the platform's *pinning artifact*: every external tool a pair needs, at a
# fixed, reproducible version — the solvers and witness checkers a reasoning
# target dispatches to (SOLVERS.md), the pinned RISC-V cross toolchain the
# c-riscv pair compiles through, an independent C differential checker, and
# the Sail-RISCV reference emulator used as an interpreter oracle.
# Determinism (ARCHITECTURE.md §4) rests on these pins; bumping any pin is a
# versioned change — record the new image digest.
#
# The image grows as new pairs and languages are registered — keep additions
# grouped by purpose and pin everything. See DOCKER.md for how it is used
# during pair development.
#
# Build:
#   docker build -t hurdy-gurdy:dev .
# Run (bind-mount the repo so host edits are visible):
#   docker run --rm -it -v "$PWD":/work -w /work hurdy-gurdy:dev bash
# The gurdy package is NOT baked in; once a pair ships code, install it inside
# the container (`pip install -e .`) so host edits are picked up live.

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
# This commit is the v2.0.0 release tag (2026-05-05), up from the prior
# v2.0.0-beta.1+52 commit.
ARG PONO_COMMIT=c81aa363f4c1b1d4f05669478d9a94c16a0d4b44
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

# --- btormc (second native BTOR2 model checker; Boolector) ----------------
# A second, independent BTOR2 engine for the native-vs-bridged cross-check
# (SOLVERS.md §7) alongside pono -- two engines deciding the same reachability
# question is exactly the corroboration §7 calls for. Built from source; its
# SAT (CaDiCaL) and BTOR2-parsing deps are vendored and pinned by Boolector's
# own contrib/setup-* scripts (the pono pattern). 3.2.4 is the version the
# harness was developed against. Build with CaDiCaL only: Boolector's bundled
# MiniSat glue does not compile under the image's gcc, and one SAT backend is
# all btormc needs. Arch-agnostic (built natively), so no TARGETARCH dance.
ARG BOOLECTOR_TAG=3.2.4
RUN git clone --depth 1 --branch "${BOOLECTOR_TAG}" \
        https://github.com/Boolector/boolector.git /opt/boolector \
 && cd /opt/boolector \
 && ./contrib/setup-cadical.sh \
 && ./contrib/setup-btor2tools.sh \
 && ./configure.sh --only-cadical \
 && cd build && make \
 && install -m 0755 bin/btormc /usr/local/bin/btormc \
 && cd / && rm -rf /opt/boolector \
 && btormc --version

# --- In-process Python solvers --------------------------------------------
# z3-bmc and z3-spacer share the z3-solver wheel; bitwuzla and cvc5 each
# ship their own Python bindings. Pin exact versions so the image hash
# uniquely identifies the solver inventory.
RUN pip install --no-cache-dir --timeout=120 --retries=5 \
        "z3-solver==4.16.0.0" \
        "bitwuzla==0.9.1" \
        "cvc5==1.3.4"

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
ARG BITWUZLA_TAG=0.9.1
RUN git clone --depth 1 --branch "${BITWUZLA_TAG}" https://github.com/bitwuzla/bitwuzla /opt/bitwuzla \
 && cd /opt/bitwuzla \
 && ./configure.py \
 && cd build && ninja \
 && install -m 0755 src/main/bitwuzla /usr/local/bin/bitwuzla \
 && cd / && rm -rf /opt/bitwuzla

# cvc5 CLI: install the static-linked binary release from upstream. The
# tag must match the cvc5 wheel pin above so B and C measure the same
# version. Upstream names its release assets x86_64/arm64; map Docker's
# TARGETARCH (amd64/arm64) accordingly so multi-arch builds get a native
# binary on both platforms.
ARG CVC5_TAG=cvc5-1.3.4
ARG TARGETARCH
RUN CVC5_ARCH=$([ "${TARGETARCH}" = "amd64" ] && echo x86_64 || echo "${TARGETARCH}") \
 && curl -fsSL "https://github.com/cvc5/cvc5/releases/download/${CVC5_TAG}/cvc5-Linux-${CVC5_ARCH}-static.zip" -o /tmp/cvc5.zip \
 && (cd /tmp && unzip -o cvc5.zip && install -m 0755 "cvc5-Linux-${CVC5_ARCH}-static/bin/cvc5" /usr/local/bin/cvc5) \
 && rm -rf /tmp/cvc5.zip /tmp/cvc5-Linux-*-static

# --- RISC-V cross toolchain -----------------------------------------------
# Bare-metal RV64 assembler/linker/gcc. The c-riscv pair (pairs/c-riscv)
# compiles through a pinned toolchain to obtain reproducible ELF bytes;
# pinning the image pins that toolchain. Also assembles hand-written RISC-V
# for the shared RISC-V interpreter's test corpus.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc-riscv64-unknown-elf \
        binutils-riscv64-unknown-elf \
    && rm -rf /var/lib/apt/lists/*

# --- C differential checker (CBMC) ----------------------------------------
# CBMC consumes ANSI C directly. It is the independent C-level verifier the
# c-riscv pair (pairs/c-riscv) runs as a differential cross-check: a verdict
# disagreement that is NOT a documented C-undefined-but-RISC-V-defined case
# localizes a fault to the compile hop (PATHS.md §3, SOLVERS.md §7).
ARG CBMC_TAG=cbmc-6.4.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        cbmc \
    && rm -rf /var/lib/apt/lists/*
# Note: Debian's cbmc package version may lag the upstream tag pinned
# above. If reproducibility across image rebuilds matters, install
# from upstream releases (.deb or .tar.gz) — see
# https://github.com/diffblue/cbmc/releases.

# --- Sail-RISCV reference emulator (interpreter oracle) -------------------
# The official Sail RISC-V model's emulator. It is the gold oracle for the
# shared RISC-V interpreter (languages/riscv) and the riscv-sail pair
# (pairs/riscv-sail): the commuting-square check validates our interpreter
# against this model. Installed from the upstream binary release (the
# sail-riscv README "strongly recommends" it over an opam source build),
# matching the cvc5 layer pattern: pinned tag, multi-arch via TARGETARCH.
# NOTE: an ARM Sail emulator (the analogous oracle for aarch64-sail) is not
# yet installed — add a pinned layer when building that pair.
#
# NOTE on naming (verified against github.com/riscv/sail-riscv/releases/0.12):
#   * release assets are `sail-riscv-Linux-{x86_64,aarch64}.tar.gz`
#     (Docker amd64 -> x86_64, arm64 -> aarch64);
#   * the tarball ships a single unified binary `bin/sail_riscv_sim`
#     (RV64 by default; `--rv32` selects RV32). This REPLACES the old
#     make-build name `riscv_sim_RV64`. The oracle discovers the binary via
#     $SAIL_RISCV_SIM, then `sail_riscv_sim`, then `riscv_sim_RV64` on PATH.
ARG SAIL_RISCV_TAG=0.12
ARG TARGETARCH
RUN SAIL_ARCH=$([ "${TARGETARCH}" = "amd64" ] && echo x86_64 || echo aarch64) \
 && curl -fsSL "https://github.com/riscv/sail-riscv/releases/download/${SAIL_RISCV_TAG}/sail-riscv-Linux-${SAIL_ARCH}.tar.gz" -o /tmp/sail.tgz \
 && mkdir -p /opt/sail-riscv && tar -xzf /tmp/sail.tgz -C /opt/sail-riscv --strip-components=1 \
 && install -m 0755 /opt/sail-riscv/bin/sail_riscv_sim /usr/local/bin/sail_riscv_sim \
 && rm -rf /tmp/sail.tgz /opt/sail-riscv \
 && sail_riscv_sim --version

# --- Default working directory --------------------------------------------
# The repo is expected to be bind-mounted at /work; hurdy-gurdy itself is
# installed at runtime (`pip install -e .`) so source edits on the host
# are picked up without rebuilding the image.
WORKDIR /work
CMD ["bash"]
