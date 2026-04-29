# `riscv-btor2` LLM inventory

§9.6 instantiation. Pins which models the benchmark runs, at which
versions, with which inference parameters, and how many times per
cell. Committed before condition B/C runs (BENCHMARKING.md §7
pre-registration).

## Contract

- **≥ 2 LLMs from unrelated families** (BENCHMARKING.md §7). "Family"
  means provider lineage: Anthropic Claude, OpenAI GPT, Google
  Gemini, Meta Llama, etc. are each one family. Two Claude variants
  do *not* satisfy this requirement on their own.
- **≥ 5 runs per (task, condition, model)** (§7). Report median and
  IQR, not just means.
- **Versions and inference parameters committed** in this file before
  any run that produces transcripts intended for §8 publication.

## Pinned models

### Slot A — Anthropic (locked)

| Field | Value |
|---|---|
| Family | Anthropic Claude |
| Model ID | `claude-opus-4-7` |
| Vendor docs | <https://platform.claude.com/docs/en/models/claude-opus-4-7> |
| Context window | 1M tokens (extended-context variant available) |
| Tool use | Native (`tools` parameter) |
| Selection rationale | Current frontier in the Claude 4.x family as of pre-registration. Strong on tool-use chains; ≥ 128K context covers any realistic dispatch trace. |

Backup within family (for §6 manual-grading sanity checks only, *not*
counted toward the ≥ 2 requirement):

| Field | Value |
|---|---|
| Model ID | `claude-sonnet-4-6` |
| Used as | Rubric LLM (§9.7), not as a model under test |

### Slot B — non-Anthropic (TBD; resolve before pre-registration)

| Field | Value |
|---|---|
| Family | TBD — must be different from Slot A's family |
| Model ID | TBD |
| Selection criteria | Production-grade public API; native function/tool calling with multi-turn chains; ≥ 128K context; separately trained from Anthropic; pinnable to a specific dated snapshot ID. |
| Candidates (ordered by preference at the time of writing) | OpenAI GPT-x with tools API; Google Gemini 2.x/3.x via Vertex; xAI Grok if function calling has matured. Confirm exact dated snapshot IDs against vendor model lists at pre-reg time, since IDs change. |

The exact Slot B model ID **must** be filled in before condition B/C
runs; the commit that fills it in is part of the benchmark's
identity (§4.4).

### Slot C — third optional model

If wall-clock and budget allow, a third unrelated-family model
adds robustness against per-vendor idiosyncrasies. Fill in only if
landed before pre-reg; otherwise leave empty.

## Inference parameters

Identical across slots A and B unless otherwise noted. Parameters
are the same for conditions A, B, and C — only the prompt and tool
surface differ.

| Parameter | Value | Why |
|---|---|---|
| `temperature` | `0.7` | Some sampling variance is desired so the ≥ 5 runs per cell are not trivially identical. Lower (0.0–0.3) would suppress hallucination but defeat the multi-run policy; higher (≥ 1.0) blows up calibration. 0.7 is the conventional "natural" default. |
| `top_p` | `0.95` | Nucleus sampling keeps the tail bounded without truncating the calibration distribution. |
| `max_tokens` | `16384` per turn; up to 8 turns per session under condition B/C | Multi-step tool chains under B routinely produce ~3–6 dispatch calls plus a final answer. The cap is per-turn so a runaway chain self-terminates. |
| `seed` | per-run integer, recorded in the run manifest | Most vendors do not guarantee seed-determinism; we record the seed anyway so the per-run cell is reproducible *to the extent the vendor permits*. Document non-determinism in the §8.7 run manifest. |
| `system` prompt | per-condition, see `bench/riscv-btor2/prompts/` | Differences across A/B/C are strictly the bullets in BENCHMARKING.md §9.3. |

### Tool-calling parameters

Conditions B and C use tool calling. The tool surface differs:

- **Condition B**: the pair's `compile`, `dispatch`, `lift`,
  `introspect` exposed as tool definitions. Schema landed in
  `bench/riscv-btor2/prompts/tools_b.json` (TODO).
- **Condition C**: a single `solve_smt2` (or `solve_btor2`) tool that
  shells the same solver binary the pair uses, but with no
  translation help. Schema in `bench/riscv-btor2/prompts/tools_c.json`
  (TODO).

`tool_choice = "auto"` for both conditions. `parallel_tool_calls`
is provider-specific; document each vendor's setting in the run
manifest.

## Multi-run policy

For every `(task, condition, model)` cell, run **5 sessions** with
distinct seeds. Sessions run independently (no shared cache, no
shared transcript context). The harness records:

- Per-session seed
- Per-session wall-clock start/end
- Per-session token counts (input/output/cached)
- Per-session final answer JSON (the §6 grading input)

Median and IQR per cell are reported in §5; per-session traces are
preserved in §8.4 (raw transcripts).

## API access and redaction

| Vendor | Env var for key | Endpoint | Notes |
|---|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | <https://api.anthropic.com> | Use the Messages API with `tools`. |
| OpenAI | `OPENAI_API_KEY` | <https://api.openai.com> | Use Responses or Chat Completions. |
| Google | `GOOGLE_API_KEY` (AI Studio) or Vertex creds | varies | Document the chosen path in the run manifest. |

The harness **must redact API keys** from any artifact written to
disk. The run manifest records *only* the env-var name and a
fingerprint (e.g., last 4 chars), not the key itself.

## What this inventory deliberately does not pin

- **Which Anthropic Sonnet variant is the rubric LLM.** That's a
  separate §9.7 decision; rubric LLM pins live in
  `bench/riscv-btor2/rubric/rubric_prompt.md` (TODO).
- **Local / open-weights models.** Reproducibility for self-hosted
  weights requires also pinning the inference engine and hardware,
  which is more work than v1 needs. A future revision can add e.g.
  Llama 3.x via vLLM with a pinned commit + GPU class.
- **Cost budgets.** Total spend per run is reported in §5 but not
  pinned in advance; abort criteria belong in the harness, not here.

## Resolution log

| Date | Slot | Action |
|---|---|---|
| 2026-04-29 | A | Pinned `claude-opus-4-7`. |
| 2026-04-29 | B | Left TBD pending API-list confirmation. |
| 2026-04-29 | Rubric | Tentative `claude-sonnet-4-6`; confirm in §9.7. |
