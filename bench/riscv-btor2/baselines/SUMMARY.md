# SOTA baselines — one-page summary

> Cold-landing overview. For full detail see
> `INITIAL_FINDINGS.md` in this directory.

## What's here

Adapters that run established C/C++ verifiers against the
`riscv-btor2` corpus, plus a Pareto aggregator and one
canonical findings document. Adapters skip-with-note when
their binary isn't on PATH, so the directory is safe to use
even with a partial install.

- `cbmc.py` — invokes `cbmc` on `task.cbmc.c`.
- `pono.py` — compiles spec → BTOR2 tempfile → `pono -e bmc`.
- `hurdy_gurdy.py` — thin shim over `framework_oracle.run_one`
  producing the same schema as the SOTA adapters.
- `pareto.py` — reads `_runs/*.jsonl`, prints per-tool
  aggregate + Pareto-dominance summary.
- `_runs/` — per-tool JSONL outputs (gitignored).
- `corpus_inputs.json` — per-task input-format inventory.
- `INITIAL_FINDINGS.md` — full empirical writeup.

## Headline (18-task pooled measurement, CBMC vs hurdy-gurdy)

|                 | CBMC | Hurdy-gurdy |
|-----------------|------|-------------|
| Correct         | 13   | **18**      |
| False positives | **5**| 0           |
| Median wall-clock | ~30 ms | ~800 ms |

All 5 of hurdy-gurdy's wins are on tasks whose property
depends on **C-undefined behavior that has a defined RV64
lowering**: signed overflow, divide-by-zero, INT_MIN/-1,
shift-amount overflow, mulw truncation. On that
**C-UB-but-RV64-defined** class the wedge rate is **5/5 =
100%**.

CBMC is ~25× faster median across all classes. The Pareto
frontier is two-dimensional: CBMC owns the fast-but-
conservative-on-UB corner; hurdy-gurdy owns the slower-but-
sound corner. Neither dominates the other.

## 2026-06-11 fresh-container re-measurement

The CBMC and ESBMC columns reproduce **bit-for-bit** on a fresh
container (CBMC 6.9.0, ESBMC 8.3.0 — the adapter's pinned
version, reinstalled from the official GitHub release):

- **CBMC 13/18** — the same 5 false positives (0115 int-overflow,
  0116 divu-sentinel, 0117 INT_MIN/-1, 0118 shift-amount-mask,
  0121 mulw-truncation).
- **ESBMC 16/18** — the same 2 false positives (0116, 0118).

**New: the full ESBMC wedge column.** iter-43 added the 6-task
adversarial wedge battery (0125, 0261, 0300–0303) but could not
measure ESBMC (binary absent that session). Now measured:

| Wedge battery (6 tasks)  | CBMC | ESBMC |
|--------------------------|------|-------|
| Correct                  | 0/6  | 2/6 genuine |
| False positives          | 6    | 2 (0125 sdiv-by-zero, 0261 oversized-shift) |
| Vacuously "correct"      | —    | 4 (0300–0303) |

The 4 ESBMC "correct" verdicts on 0300–0303 are **vacuous**: ESBMC
reports `Generated 0 VCC(s)` — its frontend slices the UB-guarded
trap away (constant-folding through the UB) rather than modeling
the RV64 lowering. They agree with the expected verdict for an
unverified reason, so the honest ESBMC wedge score is 2/6, not 6/6.
CBMC false-positives on the entire battery.

**Engine lever re-confirmed** (with bitwuzla 0.9.x / cvc5 1.3.x
pip-installed): bitwuzla is ~5× faster than z3-bmc per task
(0002: 18.5 ms vs 96.8 ms; 0004: 7.0 vs 38.0; 0007: 6.5 vs 37.0)
— the standing lever for hurdy-gurdy's wall-clock Pareto corner.

The hurdy-gurdy column on the C tasks requires the pinned bench
Docker image to rebuild the C-task ELFs reproducibly
(`corpus/_compile_c.py` refuses a non-reproducible local build);
HG's oracle path itself was validated on the assembly corpus in
the same session (`framework_oracle.py` / `oracle_align.py` PASS).

## Reproducing

```bash
# from repo root
for t in 0100 0101 0102 0103 0104 0105 0110 0114 \
         0115 0116 0117 0118 0119 0120 0121 \
         0122 0123 0124 ; do
  python3 bench/riscv-btor2/baselines/cbmc.py --task "${t}-" --max-tasks 1 \
    >> bench/riscv-btor2/baselines/_runs/cbmc.jsonl
  python3 bench/riscv-btor2/baselines/hurdy_gurdy.py --task "${t}-" --max-tasks 1 \
    >> bench/riscv-btor2/baselines/_runs/hurdy-gurdy.jsonl
done
python3 bench/riscv-btor2/baselines/pareto.py
```
