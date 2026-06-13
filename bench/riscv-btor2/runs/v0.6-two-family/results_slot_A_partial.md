# v0.6 — slot_A (Gemini) PARTIAL — paused pending second-family decision

**Model:** `gemini-2.5-flash` via Google AI Studio direct, free tier.
**State as of 2026-06-13:** **36/252 cells banked**, all condition A
(36/84). Conditions B and C did not start.

| Condition | Cells | Accuracy |
|---|---:|---:|
| A (source-only) | 36/84 | 34/36 (94%) |
| B (pair) | 0/84 | — |
| C (solver-only) | 0/84 | — |

Condition-A accuracy (94%) tracks Haiku's A-condition level (90.5%);
too few cells and no B/C to compare, so no claim is drawn from this.

## Why paused

The Google free tier (~5 req/min, a tight daily request cap) yielded
only ~16–20 good cells per reset-day on condition A — the cheapest
condition at one request per cell. B and C are multi-turn tool-use
(several requests per cell), so they exhaust the daily quota faster
still. The full 252-cell matrix is not reachable on the free tier in
any reasonable timeframe.

**Decision deferred** (operator, 2026-06-13): pause and revisit the
second-family question with a budget decision in hand. The live
options are:

1. **Paid Google key** — same pinned `gemini-2.5-flash`, no
   pre-registration change, finishes A/B/C in ~1 hour, costs a few
   dollars.
2. **Switch second family to OpenAI** via GitHub Models — free but
   rate-limited; needs a pre-registration amendment to pin the model.
3. **Ship Haiku-only** as single-vendor exploratory (consistent with
   v0.1–v0.4); the POPL headline then rests on the CBMC/ESBMC oracle
   differentials, with the LLM data as supporting, labeled
   not-§7-grade.

## Resume (free tier, if continued)

```bash
cd bench/riscv-btor2
python3 run_matrix.py --conditions A,B,C --seeds 1,2,3 \
  --tasks "$(cat runs/v0.6-two-family/tasks.txt)" \
  --model-slot slot_A \
  --corpus-tag riscv-btor2-bench-v0.6-prereg \
  --output-dir runs/v0.6-two-family/slot_A
```

The JSONL resume skips banked-good cells and retries error rows. For
a paid key, export the billable `GOOGLE_API_KEY` first; for OpenAI,
pass `--model-config-json` with the amended pin.

## Note for analysis

`runs.jsonl` contains stale error rows from prior passes alongside
successful retries. Dedup on `(task_id, condition, seed,
question_id)`, preferring non-error rows, before tallying. The
`results_slot_CC_haiku.md` headline is unaffected (Haiku had 0 error
rows).
