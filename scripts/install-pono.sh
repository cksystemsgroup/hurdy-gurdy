#!/usr/bin/env bash
# Install pono v2.0.0 natively from stanford-centaur/pono.
#
# This script is idempotent: if pono is already on PATH it exits early.
# Total build time: ~15 minutes (bitwuzla + smt-switch + pono, no cvc5 from
# source — cvc5 1.3.3 pre-built static binary is used instead).
#
# Usage (from repo root):
#   bash scripts/install-pono.sh
#
# Environment variables:
#   BUILD_DIR   directory for build artefacts (default: /opt/pono-build)
#   INSTALL_BIN directory to install pono binary (default: /usr/local/bin)
#   JOBS        make/cmake parallelism (default: $(nproc))

set -euo pipefail

PONO_TAG="${PONO_TAG:-v2.0.0}"
BUILD_DIR="${BUILD_DIR:-/opt/pono-build}"
INSTALL_BIN="${INSTALL_BIN:-/usr/local/bin}"
JOBS="${JOBS:-$(nproc)}"

# --- early exit if already installed ---
if command -v pono &>/dev/null; then
    echo "pono already on PATH: $(command -v pono)"
    pono --version 2>&1 || true
    exit 0
fi

echo "=== Installing pono ${PONO_TAG} ==="
echo "BUILD_DIR=${BUILD_DIR}  INSTALL_BIN=${INSTALL_BIN}  JOBS=${JOBS}"

# --- apt dependencies ---
apt-get install -y --no-install-recommends \
    build-essential cmake git ca-certificates \
    libgmp-dev libmpfr-dev libtool autoconf automake pkg-config \
    flex libfl-dev bison m4 gettext-base unzip ninja-build \
    2>&1 | tail -5

# Install meson (not in Ubuntu 24.04 apt at the right version)
pip install --quiet meson

mkdir -p "${BUILD_DIR}"

# --- clone pono ---
if [ ! -d "${BUILD_DIR}/pono" ]; then
    git clone --depth 1 --branch "${PONO_TAG}" \
        https://github.com/stanford-centaur/pono.git "${BUILD_DIR}/pono"
fi
PONO_DIR="${BUILD_DIR}/pono"

# --- btor2tools ---
if [ ! -f "${PONO_DIR}/deps/install/lib/libbtor2parser.a" ]; then
    (cd "${PONO_DIR}" && bash contrib/setup-btor2tools.sh 2>&1 | tail -3)
fi

# --- smt-switch (bitwuzla + cvc5) ---
SMT_SWITCH_DIR="${PONO_DIR}/deps/smt-switch"
SMT_SWITCH_INSTALL="${SMT_SWITCH_DIR}/deps/install"

if [ ! -d "${SMT_SWITCH_DIR}" ]; then
    git clone --depth 1 --branch v1.1.3 \
        https://github.com/stanford-centaur/smt-switch.git "${SMT_SWITCH_DIR}"
fi

# --- bitwuzla (needed by smt-switch) ---
if [ ! -f "${SMT_SWITCH_INSTALL}/lib/x86_64-linux-gnu/libbitwuzla.a" ]; then
    (cd "${SMT_SWITCH_DIR}" && bash contrib/setup-bitwuzla.sh 2>&1 | tail -5)
    # bitwuzla installs to lib/x86_64-linux-gnu/pkgconfig; copy to lib/pkgconfig
    cp "${SMT_SWITCH_INSTALL}/lib/x86_64-linux-gnu/pkgconfig/bitwuzla.pc" \
       "${SMT_SWITCH_INSTALL}/lib/pkgconfig/" 2>/dev/null || true
fi

# --- cvc5 (pre-built static binary, avoids ~25 min from-source build) ---
# cvc5-1.3.3 static zip includes headers + libcvc5.a — all smt-switch needs.
CVC5_HOME="${BUILD_DIR}/cvc5-home"
if [ ! -f "${CVC5_HOME}/build/src/libcvc5.a" ]; then
    TMP_CVC5="$(mktemp -d)"
    curl -fsSL -L \
        "https://github.com/cvc5/cvc5/releases/download/cvc5-1.3.3/cvc5-Linux-x86_64-static.zip" \
        -o "${TMP_CVC5}/cvc5.zip"
    (cd "${TMP_CVC5}" && unzip -q cvc5.zip)
    mkdir -p "${CVC5_HOME}/include" "${CVC5_HOME}/build/src/parser" \
             "${CVC5_HOME}/build/deps/lib" "${CVC5_HOME}/src"
    cp -r "${TMP_CVC5}/cvc5-Linux-x86_64-static/include/cvc5" "${CVC5_HOME}/include/"
    cp "${TMP_CVC5}/cvc5-Linux-x86_64-static/lib/libcvc5.a" \
       "${CVC5_HOME}/build/src/libcvc5.a"
    cp "${TMP_CVC5}/cvc5-Linux-x86_64-static/lib/libcvc5parser.a" \
       "${CVC5_HOME}/build/src/parser/libcvc5parser.a"
    cp "${TMP_CVC5}/cvc5-Linux-x86_64-static/lib/libpicpoly.a" \
       "${CVC5_HOME}/build/deps/lib/libpicpoly.a" 2>/dev/null || true
    cp "${TMP_CVC5}/cvc5-Linux-x86_64-static/lib/libpicpolyxx.a" \
       "${CVC5_HOME}/build/deps/lib/libpicpolyxx.a" 2>/dev/null || true
    cp "${TMP_CVC5}/cvc5-Linux-x86_64-static/lib/libcadical.a" \
       "${CVC5_HOME}/build/deps/lib/libcadical.a" 2>/dev/null || true
    rm -rf "${TMP_CVC5}"
fi

# --- smt-switch (bitwuzla + cvc5) ---
PKG_CONFIG_PATH="${SMT_SWITCH_INSTALL}/lib/pkgconfig:${SMT_SWITCH_INSTALL}/lib/x86_64-linux-gnu/pkgconfig"
export PKG_CONFIG_PATH

if [ ! -f "${SMT_SWITCH_DIR}/local/lib/libsmt-switch-cvc5.a" ]; then
    rm -rf "${SMT_SWITCH_DIR}/build" "${SMT_SWITCH_DIR}/local"
    (cd "${SMT_SWITCH_DIR}" && \
        PKG_CONFIG_PATH="${PKG_CONFIG_PATH}" \
        ./configure.sh --prefix=local --static --smtlib-reader --bitwuzla \
            --cvc5 --cvc5-home="${CVC5_HOME}" 2>&1 | tail -5)
    (cd "${SMT_SWITCH_DIR}" && \
        PKG_CONFIG_PATH="${PKG_CONFIG_PATH}" \
        cmake --build build -j"${JOBS}" 2>&1 | tail -5)
    (cd "${SMT_SWITCH_DIR}" && cmake --install build --prefix local 2>&1 | tail -3)
fi

# --- pono itself ---
if [ ! -f "${PONO_DIR}/build/pono" ]; then
    rm -rf "${PONO_DIR}/build"
    (cd "${PONO_DIR}" && \
        PKG_CONFIG_PATH="${PKG_CONFIG_PATH}" \
        ./configure.sh --static 2>&1 | tail -5)
    (cd "${PONO_DIR}" && \
        PKG_CONFIG_PATH="${PKG_CONFIG_PATH}" \
        cmake --build build -j"${JOBS}" 2>&1 | tail -5)
fi

install -m 0755 "${PONO_DIR}/build/pono" "${INSTALL_BIN}/pono"
echo "=== pono installed: $(command -v pono) ==="
pono --version 2>&1 || true
