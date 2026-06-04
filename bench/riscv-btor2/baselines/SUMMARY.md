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
