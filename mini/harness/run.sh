#!/bin/sh
# One autonomous bare-room run (PROTOCOL.md).
# usage: run.sh <kernel-dir> <btor2|dimacs|c> <model> [max-turns]
set -eu
K=$1; DOMAIN=$2; MODEL=$3; TURNS=${4:-120}
BASE=$(cd "$(dirname "$0")/.." && pwd)
STAMP=$(date +%Y%m%d-%H%M%S)
RUN="$BASE/runs/$STAMP-$(basename "$K")-$DOMAIN"
mkdir -p "$RUN/work/benchmarks"

case $DOMAIN in
  btor2)  B1=btor2-counters; B2=btor2-machines
          TOOLS="btormc, pono, bitwuzla, z3 (also as a python module), cadical";;
  dimacs) B1=dimacs-mixed; B2=dimacs-harder
          TOOLS="cadical, drat-trim, cake_lpr";;
  c)      B1=c-straightline; B2=c-loops
          TOOLS="cbmc, cc, z3 (also as a python module)";;
  *) echo "unknown domain $DOMAIN" >&2; exit 2;;
esac

cp "$K/kernel.py" "$K/CONTRACT.md" "$RUN/work/"
cp -R "$BASE/benchmarks/$B1" "$BASE/benchmarks/$B2" "$RUN/work/benchmarks/"
sed -e "s/@DOMAIN@/$DOMAIN/g" -e "s/@B1@/$B1/g" -e "s/@B2@/$B2/g" \
    -e "s/@TOOLS@/$TOOLS/g" \
    "$BASE/harness/PROMPT.template" > "$RUN/prompt.txt"

cd "$RUN/work"
# Unset key-based auth so the CLI uses the stored login (an exported
# ANTHROPIC_API_KEY takes precedence and may not be funded).
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
    claude -p "$(cat ../prompt.txt)" --model "$MODEL" \
    --max-turns "$TURNS" \
    --dangerously-skip-permissions > ../transcript.txt 2>&1
echo "RUN-EXIT=$?" >> ../transcript.txt
echo "$RUN"
