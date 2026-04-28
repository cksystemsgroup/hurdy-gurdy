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

FROM python:3.12-slim-bookworm

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
        libtool \
        autoconf \
        automake \
        pkg-config \
        flex \
        bison \
        m4 \
        curl \
        wget \
    && rm -rf /var/lib/apt/lists/*

# --- pono (subprocess solver, built from source) --------------------------
# pono's contrib/setup-* scripts vendor smt-switch and btor2tools. Pin the
# pono commit; the sub-deps are pinned transitively by pono's own scripts.
ARG PONO_COMMIT=HEAD
RUN git clone https://github.com/upscale-project/pono.git /opt/pono \
 && cd /opt/pono \
 && git checkout "${PONO_COMMIT}" \
 && ./contrib/setup-smt-switch.sh \
 && ./contrib/setup-btor2tools.sh \
 && ./configure.sh \
 && cd build && make -j"$(nproc)" \
 && install -m 0755 pono /usr/local/bin/pono \
 && cd / && rm -rf /opt/pono/build /opt/pono/deps/*/build

# --- In-process Python solvers --------------------------------------------
# z3-bmc and z3-spacer share the z3-solver wheel; bitwuzla and cvc5 each
# ship their own Python bindings. Pin exact versions so the image hash
# uniquely identifies the solver inventory.
# TODO: replace `>=` with `==` once a baseline run is chosen.
RUN pip install --no-cache-dir \
        "z3-solver>=4.13" \
        "bitwuzla>=0.5" \
        "cvc5>=1.2"

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
