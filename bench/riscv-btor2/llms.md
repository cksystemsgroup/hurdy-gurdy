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

### Slot A — OpenAI GPT (locked)

| Field | Value |
|---|---|
| Family | OpenAI GPT |
| Model ID (floating) | `gpt-5.5` |
| Model snapshot (pinned) | `gpt-5.5-2026-04-23` |
| Vendor docs | <https://developers.openai.com/api/docs/models/gpt-5.5> |
| Context window | ≥ 128K (verify at pre-reg) |
| Tool use | Native (`tools` parameter on the Responses / Chat Completions API) |
| Selection rationale | Most mature tool-use API among non-Anthropic frontier models; longest-established dated-snapshot pinning; conventional "unrelated to Anthropic" choice in published benchmarks. GPT-5.5 became available 2026-04-23 and supersedes GPT-5.2 as the current frontier. |
| Routing | Direct OpenAI API. Copilot Pro routing is acceptable for ad-hoc prototyping but **not for scored runs** — Copilot can swap underlying snapshots without telling the caller, which corrupts the snapshot pinning the run manifest is keyed on. |

**The pinned snapshot is the load-bearing identifier.** The run
manifest records `gpt-5.5-2026-04-23`; the floating alias `gpt-5.5`
is not used in scored runs. If OpenAI publishes a newer snapshot
during the run, that's a separate experiment.

### Slot B — Google Gemini (locked)

| Field | Value |
|---|---|
| Family | Google Gemini |
| Model ID | `gemini-2.5-pro` |
| Vendor docs | <https://ai.google.dev/gemini-api/docs/models> |
| Context window | 1M tokens (2M for select enterprise tiers) |
| Tool use | Native (function calling via `tools`) |
| Selection rationale | Distinct lineage from OpenAI: multimodal-first architecture, separate training corpus and pipeline, independent tool-use API. The §7 unrelated-families requirement is met as cleanly as possible — Anthropic vs OpenAI vs Google are all pairwise unrelated in the published-benchmark sense. |
| Routing | Direct Google AI Studio API (`https://generativelanguage.googleapis.com`). Vertex AI is an acceptable alternative for billing reasons; record the chosen path in the run manifest. |

**Pinning caveat for Slot B.** Google does not publish dated
snapshot ids the way OpenAI does. The run manifest records the
floating `gemini-2.5-pro` id plus a `snapshot_observed_at` ISO
timestamp; if Google updates the underlying weights mid-run, that
shows up as date drift in the manifest and is reported as a
limitation in §5. This is weaker pinning than Slot A's; it is
nonetheless the strongest-divergence non-OpenAI frontier model
available, which is the property §7 actually cares about.

### Rubric LLM — OpenAI (locked)

The §9.7 rubric LLM grades T4 lift quality and runs blind to
condition + model under test (§6 redactions handled in
`rubric/rubric_prompt.md`). Cheaper than the slots-under-test
because rubric calls scale linearly with transcript count.

| Field | Value |
|---|---|
| Family | OpenAI GPT |
| Model ID | `gpt-4.1-mini` |
| Used as | Rubric LLM (§9.7), not as a model under test |
| Inference params | `temperature=0.0`, `top_p=1.0`, `max_tokens=4096` (deterministic; rubric output is a single small JSON object) |

### Slot C — third optional model

If wall-clock and budget allow, a third unrelated-family model
adds robustness against per-vendor idiosyncrasies. Fill in only if
landed before pre-reg; otherwise leave empty.

### Parked: Anthropic Claude (re-enable when credits available)

Anthropic was Slot A in v0.1.0-prereg but was swapped out of the
active inventory because no Anthropic credits were available at
the time the live runs were due to start. The harness's Anthropic
adapter (`harness._call_anthropic`) remains functional and was
structurally validated against the Messages API; only the live
runs are deferred.

To re-enable Anthropic, add it back as Slot C (preserving the
two-vendor unrelated-families requirement on A+B) and pin a
current Claude snapshot. Leading candidate as of this commit:
`claude-opus-4-7`. The rubric LLM may also be moved back to
`claude-sonnet-4-6` if so desired (the prose register the corpus
notes were authored in is Anthropic-shaped, so Anthropic-graded
rubric runs may exhibit slightly tighter alignment).

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
| OpenAI | `OPENAI_API_KEY` | <https://api.openai.com> | Slot A — Use Chat Completions with `tools`. |
| Google | `GOOGLE_API_KEY` (AI Studio) or Vertex creds | <https://generativelanguage.googleapis.com> | Slot B — Document the chosen path in the run manifest. |
| OpenAI | `OPENAI_API_KEY` | <https://api.openai.com> | Rubric LLM (`gpt-4.1-mini`). |
| Anthropic | `ANTHROPIC_API_KEY` | <https://api.anthropic.com> | Parked — re-enable when Anthropic credits are available. |

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
| 2026-04-29 | Rubric | Tentative `claude-sonnet-4-6`; confirmed in §9.7. |
| 2026-04-29 | B | Locked family to OpenAI GPT (model id `gpt-5`); dated snapshot to be resolved against the OpenAI model list at pre-registration time. Direct OpenAI API; no Copilot routing for scored runs. |
| 2026-04-29 | B | Resolved snapshot to `gpt-5.5-2026-04-23` (latest GPT-5.5 dated snapshot per developers.openai.com). |
| 2026-04-30 | A → parked | Anthropic Claude moved out of active Slot A — no Anthropic credits available for the live runs. Adapter remains functional; documented in "Parked" section above. |
| 2026-04-30 | A | Reassigned to OpenAI `gpt-5.5-2026-04-23` (was Slot B). |
| 2026-04-30 | B | Pinned to Google Gemini `gemini-2.5-pro` (floating alias; Google does not publish dated snapshot ids — manifest records `snapshot_observed_at` instead). |
| 2026-04-30 | Rubric | Reassigned to OpenAI `gpt-4.1-mini` (cheap, deterministic; Anthropic moved to Parked). |
| 2026-04-30 | --- | These changes are §9.6-scope and therefore **invalidate `riscv-btor2-bench-v0.1.0-prereg`**. A new pre-reg tag (proposed: `v0.1.1-prereg`) should be cut before the first scored run against this revised inventory. |
