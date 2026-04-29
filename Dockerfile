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

# --- RISC-V cross toolchain (corpus build) --------------------------------
# Bare-metal RV64 assembler/linker/gcc, used by bench/riscv-btor2/corpus
# Makefile to produce source.elf from each task's source.S. Pinning the
# image pins the toolchain version, so source.elf bytes are reproducible.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc-riscv64-unknown-elf \
        binutils-riscv64-unknown-elf \
    && rm -rf /var/lib/apt/lists/*

# --- Source-level verifiers (BENCHMARKING.md §3 D) ------------------------
# Placeholder. RISC-V has no direct source-level verifier analogue for
# CBMC/ESBMC; if a future pair targets C or Python, install the verifier
# here and tag this layer with its version.

# --- Default working directory --------------------------------------------
# The repo is expected to be bind-mounted at /work; hurdy-gurdy itself is
# installed at runtime (`pip install -e .`) so source edits on the host
# are picked up without rebuilding the image.
WORKDIR /work
CMD ["bash"]
