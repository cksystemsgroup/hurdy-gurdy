# v0.6 — first two-family A/B/C run

**Started:** 2026-06-12.
**Conditions:** A (source-only), B (pair-equipped), C (solver-only) —
the BENCHMARKING.md §3 required trio.
**Corpus slice:** the 25 C-derived tasks (`0100`–`0124`) plus the
three iter-43 adversarial UB wedges (`0125-c-sdiv-by-zero`,
`0261-c-shift-oversized`, `0300-c-neg-int-min`) = 28 tasks.
Hand-written assembly tasks excluded (consistent with v0.4's scope).
**Seeds:** 1, 2, 3 per cell (extendable to §7's ≥ 5 by re-invoking
with `--seeds 4,5`; the JSONL resume skips completed cells).
**Models — two unrelated families (§7-grade, the first such run):**

| Slot | Family | Model | Routing |
|---|---|---|---|
| `slot_A` | Google Gemini | `gemini-2.5-flash` | AI Studio direct (`GOOGLE_API_KEY`), free tier |
| `slot_CC_haiku` | Anthropic Claude | `claude-haiku-4-5-20251001` | `claude` CLI + bench MCP server (v0.4 path) |

Matrix per slot: 28 × 3 × 3 = 252 cells; 504 total.

## Layout

- `slot_A/` and `slot_CC_haiku/` — one run_matrix output dir per
  slot: `runs.jsonl`, `transcripts/`, `manifest.json`.
- `slot_CC_haiku.model.json` — the `--model-config-json` payload for
  the Haiku slot (slot_A uses run_matrix's built-in default).

## Harness deviations from v0.4 (committed before this run)

1. `_starter_spec_for` now absolutizes `fields.binary.path` against
   the task directory. v0.4 transcripts show models burning a
   tool-error round-trip discovering that the corpus-relative
   `source.elf` doesn't resolve from the harness cwd; that was a
   harness artifact, not a measurement.
2. The in-process adapters' `on_tool_call` now returns tool
   exceptions as `{"error", "message"}` dicts — parity with the MCP
   path's existing behavior, required for in-process B/C cells
   (Gemini, Anthropic-API, OpenAI families).
3. A literal duplicate definition of `_starter_spec_for` was removed.

Prompts, corpus, rubric, and manifest schema are unchanged from the
v0.4 pre-registration; the three wedge tasks were already in the
corpus (commit `5b03064` / iter-43 validation).

## Known operational constraints

- **Gemini free tier:** 5 requests/min and a daily request cap.
  `run_matrix.py` honors Google's retry-after hints; cells that
  exhaust the retry budget land as error rows and are re-run on the
  next invocation (same command, same output dir). Expect the slot_A
  matrix to need one or more resume passes.
- **RAM discipline:** the two slot matrices each run strictly
  sequentially (one cell in flight); only the two processes run
  concurrently.

## Resume commands

```bash
cd bench/riscv-btor2
python3 run_matrix.py --conditions A,B,C --seeds 1,2,3 \
  --tasks $(cat runs/v0.6-two-family/tasks.txt) \
  --model-slot slot_A \
  --corpus-tag riscv-btor2-bench-v0.6-prereg \
  --output-dir runs/v0.6-two-family/slot_A

python3 run_matrix.py --conditions A,B,C --seeds 1,2,3 \
  --tasks $(cat runs/v0.6-two-family/tasks.txt) \
  --model-slot slot_CC_haiku \
  --model-config-json runs/v0.6-two-family/slot_CC_haiku.model.json \
  --corpus-tag riscv-btor2-bench-v0.6-prereg \
  --cell-interval 0 \
  --output-dir runs/v0.6-two-family/slot_CC_haiku
```
