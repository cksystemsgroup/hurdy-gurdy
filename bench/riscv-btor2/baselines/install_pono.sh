#!/usr/bin/env bash
# Build and install pono from source (bitwuzla backend only, no cvc5).
#
# Tested on Ubuntu 24.04 LTS (the hurdy-gurdy remote execution container).
# Run from anywhere; installs pono to /usr/local/bin/pono.
#
# After running, add the bitwuzla shared-lib directory to LD_LIBRARY_PATH:
#   export LD_LIBRARY_PATH=/tmp/pono-build/smt-switch/deps/install/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
# Or make that permanent by writing to /etc/profile.d/pono.sh (requires root).
#
# Known limitation (iter-44): pono enforces BTOR2 constraint
#   "state_nid > init_value_nid" that our translator violates.
#   All tasks return verdict=error until the translator is fixed.
#   Tracked in V2_PROGRESS.md, planned for next iteration.

set -euo pipefail

BUILD_DIR="${PONO_BUILD_DIR:-/tmp/pono-build}"
INSTALL_BIN=/usr/local/bin/pono

# ── 0. System dependencies ──────────────────────────────────────────────────
apt-get install -y --no-install-recommends \
    git cmake ninja-build g++ make bison flex \
    libgmp-dev libmpfr-dev gettext-base 2>&1 | grep -E "^(Setting up|already)" || true
pip3 install --quiet meson

# ── 1. Create build dir ──────────────────────────────────────────────────────
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# ── 2. Clone pono ────────────────────────────────────────────────────────────
if [[ ! -d pono ]]; then
    git clone --depth=1 https://github.com/stanford-centaur/pono.git pono
fi
cd pono
SMT_SWITCH_VERSION=$(grep smt_switch_version contrib/setup-smt-switch.sh | head -1 | grep -oP 'v[0-9.]+')

# ── 3. Clone smt-switch ──────────────────────────────────────────────────────
mkdir -p deps
if [[ ! -d deps/smt-switch ]]; then
    git clone --depth=1 --branch "$SMT_SWITCH_VERSION" \
        https://github.com/stanford-centaur/smt-switch.git deps/smt-switch
fi
SMT_SWITCH_DIR="$BUILD_DIR/pono/deps/smt-switch"

# ── 4. Build cadical (bitwuzla dependency) ──────────────────────────────────
cd "$SMT_SWITCH_DIR"
PKG_CONFIG_PATH="$SMT_SWITCH_DIR/deps/install/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export PKG_CONFIG_PATH
if [[ ! -f deps/install/lib/libcadical.a ]]; then
    bash contrib/setup-cadical.sh
fi

# ── 5. Build bitwuzla (the C library, not the Python binding) ───────────────
if [[ ! -f deps/install/lib/x86_64-linux-gnu/libbitwuzla.a ]]; then
    # Download source if missing
    if [[ ! -d deps/bitwuzla ]]; then
        BZLA_COMMIT=$(grep git_commit contrib/setup-bitwuzla.sh | head -1 | grep -oP '[0-9a-f]{40}')
        wget -q -O /tmp/bitwuzla.tar.gz \
            "https://github.com/bitwuzla/bitwuzla/archive/${BZLA_COMMIT}.tar.gz"
        tar -xf /tmp/bitwuzla.tar.gz -C deps/
        mv "deps/bitwuzla-${BZLA_COMMIT}" deps/bitwuzla
    fi
    BZLA_PKG="$SMT_SWITCH_DIR/deps/install/lib/x86_64-linux-gnu/pkgconfig"
    mkdir -p "$BZLA_PKG"
    export PKG_CONFIG_PATH="$BZLA_PKG:${PKG_CONFIG_PATH:-}"
    cd deps/bitwuzla
    python3 ./configure.py --prefix "$SMT_SWITCH_DIR/deps/install"
    cd build
    meson compile -j4
    meson install
    cd "$SMT_SWITCH_DIR"
fi

BZLA_PKG="$SMT_SWITCH_DIR/deps/install/lib/x86_64-linux-gnu/pkgconfig"
export PKG_CONFIG_PATH="$BZLA_PKG:${PKG_CONFIG_PATH:-}"

# ── 6. Build smt-switch (bitwuzla only) ──────────────────────────────────────
if [[ ! -f local/lib/libsmt-switch.a ]]; then
    [[ -d build ]] && rm -rf build
    ./configure.sh --prefix=local --static --bitwuzla \
        --bitwuzla-dir="$SMT_SWITCH_DIR/deps/install" \
        --without-tests --smtlib-reader
    cd build && cmake --build . -j4 && cmake --install . && cd ..
fi
# Stub for cvc5 (pono CMakeLists checks for it but BMC never calls it)
[[ -f local/lib/libsmt-switch-cvc5.a ]] || ar rcs local/lib/libsmt-switch-cvc5.a

# ── 7. Build btor2tools ──────────────────────────────────────────────────────
cd "$BUILD_DIR/pono"
if [[ ! -f deps/install/lib/libbtor2parser.a ]]; then
    bash contrib/setup-btor2tools.sh
fi

# ── 8. Patch pono: replace cvc5 default with bitwuzla ───────────────────────
# ts.h: use BitwuzlaSolverFactory as the default TS solver
sed -i 's|#include "smt-switch/cvc5_factory.h"|#include "smt-switch/bitwuzla_factory.h"|' core/ts.h
sed -i 's|smt::Cvc5SolverFactory::create(false)|smt::BitwuzlaSolverFactory::create(false)|' core/ts.h
# available_solvers.cpp: guard all cvc5 calls
python3 - <<'PYEOF'
import re, pathlib
p = pathlib.Path("smt/available_solvers.cpp")
txt = p.read_text()
# guard include
txt = txt.replace(
    '#include "smt-switch/cvc5_factory.h"',
    '#ifdef WITH_CVC5\n#include "smt-switch/cvc5_factory.h"\n#endif'
)
# guard create call
txt = txt.replace(
    '      s = Cvc5SolverFactory::create(logging);\n      printing_style = CVC5_STYLE;',
    '#ifdef WITH_CVC5\n      s = Cvc5SolverFactory::create(logging);\n      printing_style = CVC5_STYLE;\n#else\n      throw smt::SmtException("CVC5 not available in this build");\n#endif'
)
# guard interpolating create
txt = txt.replace(
    '      s = Cvc5SolverFactory::create_interpolating_solver();\n      printing_style = CVC5_STYLE;',
    '#ifdef WITH_CVC5\n      s = Cvc5SolverFactory::create_interpolating_solver();\n      printing_style = CVC5_STYLE;\n#else\n      throw smt::SmtException("CVC5 not available in this build");\n#endif'
)
# fallback solver: use BZLA instead of CVC5
txt = txt.replace('const SolverEnum fallback_se = CVC5;', 'const SolverEnum fallback_se = BZLA;')
p.write_text(txt)
PYEOF

# ── 9. Configure and build pono ──────────────────────────────────────────────
export PKG_CONFIG_PATH="$BZLA_PKG:${PKG_CONFIG_PATH:-}"
[[ -d build ]] && rm -rf build
./configure.sh --smt-switch-dir="$SMT_SWITCH_DIR"
cd build
cmake --build . -j4
cd ..

# ── 10. Install ──────────────────────────────────────────────────────────────
cp build/pono "$INSTALL_BIN"
chmod 755 "$INSTALL_BIN"

# Persist LD_LIBRARY_PATH for bitwuzla shared libs
BITWUZLA_LIBDIR="$SMT_SWITCH_DIR/deps/install/lib/x86_64-linux-gnu"
cat > /etc/profile.d/pono.sh <<EOF
export LD_LIBRARY_PATH=${BITWUZLA_LIBDIR}:\${LD_LIBRARY_PATH:-}
EOF

echo ""
echo "pono installed to $INSTALL_BIN"
echo "bitwuzla libs in $BITWUZLA_LIBDIR"
echo "Source /etc/profile.d/pono.sh or re-login to set LD_LIBRARY_PATH."
echo ""
echo "NOTE: All hurdy-gurdy corpus tasks currently fail pono with"
echo "  'state id must be greater than id of second operand'"
echo "  Fix: reorder translator to emit state nodes after init values."
echo "  Tracked in V2_PROGRESS.md iter-44."
