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

# --- btormc + boolector (native BTOR2 checker + SMT engine; from Boolector) ---
# The Boolector build also yields the `boolector` SMT CLI; install it too as a
# third SMT corroboration engine (smt_cli.BoolectorSmtBackend). Note it shares
# lineage with bitwuzla, so z3 remains the strongest independence axis.
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
 && install -m 0755 bin/boolector /usr/local/bin/boolector \
 && cd / && rm -rf /opt/boolector \
 && btormc --version && boolector --version | head -1

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

# --- Csmith (external-generator fuzzing for c-riscv) -----------------------
# Csmith generates random C programs for differential fuzzing (BENCHMARKS.md §3,
# the complement to the in-house tools/riscv_fuzz). libcsmith-dev provides the
# runtime header (/usr/include/csmith/csmith.h) the generated programs include;
# picolibc supplies the RV64 libc headers that header pulls in (string.h, ...),
# so a Csmith program compiles through the pinned riscv64-unknown-elf gcc with
# `--specs=picolibc.specs -I/usr/include/csmith`. Smoke-tested at build time
# (generate + compile to a RISC-V object). NOTE: *running* a Csmith program on
# the bare-metal interp still needs the harness to resolve picolibc's stdio
# (a semihosting crt0, or a no-libc shim + reading `crc32_context` from memory)
# and a reference oracle -- the documented next step (DOCKER.md "Gaps to close").
RUN apt-get update && apt-get install -y --no-install-recommends \
        csmith libcsmith-dev picolibc-riscv64-unknown-elf \
    && rm -rf /var/lib/apt/lists/* \
    && csmith --version \
    && csmith --no-packed-struct --max-funcs 3 --output /tmp/_csmith.c \
    && riscv64-unknown-elf-gcc --specs=picolibc.specs -w -O2 -I/usr/include/csmith \
         -march=rv64imc -mabi=lp64 -c /tmp/_csmith.c -o /tmp/_csmith.o \
    && rm -f /tmp/_csmith.c /tmp/_csmith.o

# --- C differential checker (CBMC) ----------------------------------------
# CBMC consumes ANSI C directly. It is the independent C-level verifier the
# c-riscv pair (pairs/c-riscv) runs as a differential cross-check: a verdict
# disagreement that is NOT a documented C-undefined-but-RISC-V-defined case
# localizes a fault to the compile hop (ROUTES.md §3, SOLVERS.md §7).
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

# --- Witness checkers (the `proved` tier) ---------------------------------
# Independent proof checkers for the assurance ceiling (SOLVERS.md §5-6).
# Carcara checks Alethe proofs; drat-trim checks DRAT/SAT proofs. The
# toolchain to build Carcara (a pinned rustup) is removed after install.
# The trust-free `proved` route for the platform's *bitvector* theory is now
# wired (gurdy/solvers/proved.py, issue #2): bitblast -> DRAT -> drat-trim
# (bitwuzla --write-cnf, cadical, drat-trim). It surfaces a `proved` verdict
# in-image -- demonstrated: prove(x*x==3) -> tier=proved, drat-trim VERIFIED.
# `cadical` (the DRAT producer) is installed below; the Carcara/LFSC routes stay
# blocked for BV (cvc5's Alethe proofs use BV bitblast rules Carcara does not
# implement, and its LFSC proofs insert trust steps), and the pono IC3 invariant
# -> certifaiger route is still future (DOCKER.md "Gaps to close").
RUN curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --default-toolchain 1.88.0 --profile minimal \
 && . "$HOME/.cargo/env" \
 && git clone --depth 1 https://github.com/ufmg-smite/carcara.git /opt/carcara \
 && cd /opt/carcara && CARGO_BUILD_JOBS=2 cargo build --release -j2 \
 && install -m 0755 target/release/carcara /usr/local/bin/carcara \
 && carcara --version \
 && rustup self uninstall -y \
 && cd / && rm -rf /opt/carcara
# drat-trim checks the DRAT proof; cadical produces it from bitwuzla's
# bit-blasted CNF (the SAT backend, an untrusted producer -- drat-trim is the
# trust anchor). Together they complete the route-(a) `proved` pipeline in-image.
RUN apt-get update && apt-get install -y --no-install-recommends drat-trim cadical \
 && rm -rf /var/lib/apt/lists/* \
 && cadical --version && drat-trim 2>/dev/null | head -1 || true

# --- LFSC checker (lfscc) + cvc5's LFSC signatures -------------------------
# The LFSC proof checker (SOLVERS.md §5; issue #2 "an LFSC checker"), the
# named obligation upgrade for cvc5's brief (solvers/brief.py). Pinned to the
# exact commit cvc5 1.3.4's own contrib/get-lfsc-checker pins, so the checker
# matches the cvc5 proof producer above. The signatures are cvc5's, taken
# from the source tree at the SAME tag as the cvc5 binary — a
# signature/producer version skew is a soundness hazard, so both pins move
# together (bump them as a pair). /usr/local/bin/lfsc-check bakes in the
# canonical signature order (from get-lfsc-checker). Smoke-tested at build
# time: a QF_UF unsat proved by the image's cvc5, the proof checked by lfscc
# (a corrupted proof is rejected — verified two-sided before this layer
# landed). KNOWN LIMIT (issue #2, DOCKER.md): cvc5's BV proofs insert trust
# steps (BV_POLY_NORM_EQ, EVALUATE) — LFSC checking is trust-free only
# outside BV, so the platform's bitvector `proved` route stays bitblast→DRAT.
ARG LFSC_COMMIT=5a127dbbcf9a0f822768e783dbf892ee90c435d5
RUN git clone https://github.com/cvc5/LFSC.git /opt/lfsc \
 && cd /opt/lfsc && git checkout "${LFSC_COMMIT}" \
 && mkdir build && cd build \
 && cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local .. \
 && make install -j2 \
 && curl -fsSL "https://github.com/cvc5/cvc5/archive/refs/tags/${CVC5_TAG}.tar.gz" -o /tmp/cvc5-src.tgz \
 && tar -xzf /tmp/cvc5-src.tgz -C /tmp --wildcards "*/proofs/lfsc/signatures" \
 && mkdir -p /usr/local/share/lfsc \
 && cp -r /tmp/cvc5-${CVC5_TAG}/proofs/lfsc/signatures /usr/local/share/lfsc/signatures \
 && printf '%s\n' '#!/bin/sh' \
      '# Check an LFSC proof (cvc5 --dump-proofs --proof-format=lfsc, minus' \
      '# the leading "unsat"/"(" and trailing ")") against cvc5 signatures' \
      '# in the canonical order (cvc5 contrib/get-lfsc-checker).' \
      'S=/usr/local/share/lfsc/signatures' \
      'exec lfscc "$S/core_defs.plf" "$S/util_defs.plf" "$S/theory_def.plf" \' \
      '  "$S/nary_programs.plf" "$S/boolean_programs.plf" "$S/boolean_rules.plf" \' \
      '  "$S/cnf_rules.plf" "$S/equality_rules.plf" "$S/arith_programs.plf" \' \
      '  "$S/arith_rules.plf" "$S/strings_programs.plf" "$S/strings_rules.plf" \' \
      '  "$S/quantifiers_rules.plf" "$@"' \
      > /usr/local/bin/lfsc-check \
 && chmod 0755 /usr/local/bin/lfsc-check \
 && printf '(set-logic QF_UF)\n(declare-fun p () Bool)\n(assert p)\n(assert (not p))\n(check-sat)\n' > /tmp/lfsc_smoke.smt2 \
 && cvc5 --dump-proofs --proof-format=lfsc /tmp/lfsc_smoke.smt2 | tail -n +3 | head -n -1 > /tmp/lfsc_smoke.plf \
 && grep -q check /tmp/lfsc_smoke.plf \
 && lfsc-check /tmp/lfsc_smoke.plf \
 && rm -rf /opt/lfsc /tmp/cvc5-src.tgz /tmp/cvc5-${CVC5_TAG} /tmp/lfsc_smoke.*

# --- cake_lpr (formally verified LRAT checker) -----------------------------
# The strongest rung of the bitvector `proved` route (SOLVERS.md §5-6;
# issue #2 "remaining checkers"): drat-trim elaborates the DRAT to LRAT
# (untrusted), cake_lpr re-validates the LRAT against the CNF from scratch,
# and its soundness is machine-proved down to the binary (CakeML) — with it
# present, gurdy/solvers/proved.py books tcb={bitwuzla:bit-blast,
# cake_lpr:verified} instead of trusting drat-trim. Upstream ships the
# CakeML-compiled assembly per arch (cake_lpr.S x64, cake_lpr_arm8.S arm8);
# the layer is just a gcc link, no CakeML toolchain. Pinned to the
# 2026-07-22 commit — note its interface change: heap/stack sizes are now
# runtime flags (--CML_HEAP_SIZE=<MB>/--CML_STACK_SIZE=<MB>), no longer the
# CML_* env vars; the platform passes neither and runs on the defaults.
# cake_lpr exits 0 even when checking FAILS — the exact status line
# `s VERIFIED UNSAT` is the only success signal (proved.py holds the same
# caution). Smoke-tested at build time along the platform's actual route
# (cadical DRAT -> drat-trim -L LRAT -> cake_lpr), plus upstream's example
# pair; negative control: the valid LRAT against a SATISFIABLE CNF must not
# verify (the vacuity a naive substring match would hide). The tr -d '\r'
# is load-bearing: drat-trim overwrites its progress line, so piped output
# carries "\rs VERIFIED" and an anchored grep misses it (proved.py is immune
# — Python splitlines() treats \r as a line break).
ARG CAKE_LPR_COMMIT=a36874a8b750b43fe4b385b8ddbf5b033e46a3fa
ARG TARGETARCH
RUN git clone https://github.com/tanyongkiam/cake_lpr.git /opt/cake_lpr \
 && cd /opt/cake_lpr && git checkout "${CAKE_LPR_COMMIT}" \
 && CAKE_SRC=$([ "${TARGETARCH}" = "amd64" ] && echo cake_lpr.S || echo cake_lpr_arm8.S) \
 && gcc -O2 basis_ffi.c "${CAKE_SRC}" -o cake_lpr -std=c99 \
 && install -m 0755 cake_lpr /usr/local/bin/cake_lpr \
 && printf 'p cnf 2 4\n1 2 0\n1 -2 0\n-1 2 0\n-1 -2 0\n' > /tmp/lpr_smoke.cnf \
 && { cadical --no-binary -q /tmp/lpr_smoke.cnf /tmp/lpr_smoke.drat; [ "$?" = 20 ]; } \
 && drat-trim /tmp/lpr_smoke.cnf /tmp/lpr_smoke.drat -L /tmp/lpr_smoke.lrat | tr -d '\r' | grep -q '^s VERIFIED' \
 && cake_lpr /tmp/lpr_smoke.cnf /tmp/lpr_smoke.lrat | tr -d '\r' | grep -q '^s VERIFIED UNSAT' \
 && cake_lpr example.cnf example.lpr | tr -d '\r' | grep -q '^s VERIFIED UNSAT' \
 && printf 'p cnf 2 1\n1 2 0\n' > /tmp/lpr_sat.cnf \
 && ! cake_lpr /tmp/lpr_sat.cnf /tmp/lpr_smoke.lrat | tr -d '\r' | grep -q '^s VERIFIED UNSAT' \
 && cd / && rm -rf /opt/cake_lpr /tmp/lpr_smoke.* /tmp/lpr_sat.cnf

# --- Default working directory --------------------------------------------
# The repo is expected to be bind-mounted at /work; hurdy-gurdy itself is
# installed at runtime (`pip install -e .`) so source edits on the host
# are picked up without rebuilding the image.
WORKDIR /work
CMD ["bash"]
