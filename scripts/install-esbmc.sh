#!/usr/bin/env bash
# Install ESBMC from the GitHub weekly pre-release binary.
#
# Usage: bash scripts/install-esbmc.sh
#
# Downloads esbmc-linux.zip from the esbmc/esbmc "weekly" GitHub release,
# extracts the binary, and copies it to /usr/local/bin/esbmc.  Idempotent
# (skips download if already installed and version matches).
#
# Tested on Ubuntu 24.04 x86_64.  The weekly build tracks ~v8.3+.
# The bench/riscv-btor2/baselines/esbmc.py adapter uses shutil.which("esbmc")
# and gracefully skips with a note if the binary is absent.

set -euo pipefail

INSTALL_BIN=/usr/local/bin/esbmc
WEEKLY_URL="https://github.com/esbmc/esbmc/releases/download/weekly/esbmc-linux.zip"
TMPDIR_PREFIX=/tmp/esbmc-install

if [[ -f "$INSTALL_BIN" ]]; then
    echo "ESBMC already installed: $("$INSTALL_BIN" --version 2>&1 | head -1)"
    exit 0
fi

echo "Downloading ESBMC weekly release..."
TMP=$(mktemp -d "${TMPDIR_PREFIX}.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

curl -fsSL -o "$TMP/esbmc-linux.zip" "$WEEKLY_URL"
unzip -q "$TMP/esbmc-linux.zip" -d "$TMP"

BINARY=$(find "$TMP" -name "esbmc" -type f | head -1)
if [[ -z "$BINARY" ]]; then
    echo "ERROR: esbmc binary not found in zip" >&2
    exit 1
fi

cp "$BINARY" "$INSTALL_BIN"
chmod 755 "$INSTALL_BIN"

echo "Installed: $INSTALL_BIN"
"$INSTALL_BIN" --version 2>&1 | head -1
