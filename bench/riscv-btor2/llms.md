# `riscv-btor2` LLM inventory

§9.6 instantiation. Pins which models the benchmark runs, at which
versions, with which inference parameters, and how many times per
cell. Committed before condition B/C runs (BENCHMARKING.md §7
pre-registration).

> **v0.1.1 status: SINGLE-VENDOR EXPLORATORY — NOT §7-GRADE.** The
> first scored runs against this inventory will use only Slot A
> (`gemini-2.5-flash`). This violates §7's "≥ 2 LLMs from unrelated
> families" requirement and is therefore not a benchmark in the
> playbook's strict sense — it's a pipeline-soak that produces
> single-vendor evidence about the pair, not a comparative study.
> Reinstating §7-grade compliance requires activating a second
> vendor (OpenAI direct, paid Google tier for gemini-2.5-pro, or
> Anthropic re-enabled). See "Path back to §7" below.

## Contract

- **≥ 2 LLMs from unrelated families** (BENCHMARKING.md §7). "Family"
  means provider lineage: Anthropic Claude, OpenAI GPT, Google
  Gemini, Meta Llama, etc. are each one family. Two Claude variants
  do *not* satisfy this requirement on their own. **v0.1.1 runs are
  marked single-vendor; reports must label them as exploratory.**
- **≥ 5 runs per (task, condition, model)** (§7). Report median and
  IQR, not just means.
- **Versions and inference parameters committed** in this file before
  any run that produces transcripts intended for §8 publication.

## Pinned models

### Slot A — Google Gemini Flash (active for v0.1.1 exploratory runs)

| Field | Value |
|---|---|
| Family | Google Gemini |
| Model ID | `gemini-2.5-flash` |
| Vendor docs | <https://ai.google.dev/gemini-api/docs/models> |
| Context window | 1M tokens |
| Tool use | Native (`function_declarations` via the new `google-genai` SDK; the harness's `_call_google` adapter handles this) |
| Routing | Direct Google AI Studio API (`https://generativelanguage.googleapis.com`). Auth: `GOOGLE_API_KEY`. |
| Selection rationale | Free-tier eligible (the only Gemini variant that is — `gemini-2.5-pro` returns 429 RESOURCE_EXHAUSTED with `limit:0` on free tier). End-to-end pipeline validated 2026-04-30 against task `0007-simple-add-baseline`: `verdict=reachable`, all four register values correct, `bad_pc=65544` correct. |
| Inference params (override) | `temperature=0.7`, `top_p=0.95`, `max_tokens=16384`, `max_turns=8` (same as the global defaults) |

**Pinning caveat.** Google does not publish dated snapshot ids.
The run manifest records the floating `gemini-2.5-flash` id plus a
`snapshot_observed_at` ISO timestamp. If Google updates the
underlying weights mid-run, the date drift is visible in the
manifest and reported as a §5 limitation. v0.1.1's
single-vendor exploratory status compounds this — there is no
second-family agreement to triangulate against.

### Slot B — parked (no active second vendor)

The §7 two-families requirement is **not satisfied** under
v0.1.1. Slot B is documented but not active until one of these
unblocks:

- **OpenAI direct API**: requires `OPENAI_API_KEY` and a paid
  account. GPT-5.5 / gpt-5.5-2026-04-23 is the strongest pin
  available.
- **OpenAI via GitHub Models**: free with `GITHUB_TOKEN`
  (`models:read`), but rate-limited aggressively (the bot-detection
  warning fires on rapid retries) and lacks gpt-5.5 in the
  catalog (only gpt-5). Acceptable for low-rate exploratory cells;
  not for 1200-session matrices.
- **Paid Google tier for gemini-2.5-pro**: same vendor as Slot A,
  so doesn't satisfy §7's two-families rule even though it does
  unblock the stronger Gemini variant.
- **Anthropic re-enable**: requires Anthropic account credit.
  See "Parked: Anthropic" below.

Activating any of the first three after the run starts is a
v0.2.x experiment, not a continuation of v0.1.1.

### Path back to §7

To turn v0.1.1's exploratory single-vendor data into §7-grade
data:

1. Pick a second vendor from the Slot B candidates above.
2. Activate it: add the relevant `*_API_KEY` to the run-operator's
   environment.
3. Cut a new pre-reg tag (`riscv-btor2-bench-v0.2.0-prereg`)
   carrying both slots active.
4. Re-run the full ≥5-runs/cell matrix against the new tag's
   commit. v0.1.1 single-vendor results are not promoted; they
   stay in the artifact bundle as exploratory baselines that the
   §7-grade run can be compared against.

### Rubric LLM — OpenAI via GitHub Models (locked)

The §9.7 rubric LLM grades T4 lift quality and runs blind to
condition + model under test (§6 redactions handled in
`rubric/rubric_prompt.md`). Cheaper than the slots-under-test
because rubric calls scale linearly with transcript count.

| Field | Value |
|---|---|
| Family | OpenAI GPT |
| Model ID | `openai/gpt-4.1-mini` |
| Routing | GitHub Models (same `GITHUB_TOKEN` as Slot A) |
| Used as | Rubric LLM (§9.7), not as a model under test |
| Inference params | `temperature=0.0`, `top_p=1.0`, `max_tokens=4096` (deterministic; rubric output is a single small JSON object) |

### Slot C — third optional model

If wall-clock and budget allow, a third unrelated-family model
adds robustness against per-vendor idiosyncrasies. Fill in only if
landed before pre-reg; otherwise leave empty.

### Slot CC — Claude Code subprocess (no-API-key, single-vendor, condition A only)

A local-only adapter that spawns the operator's existing `claude`
CLI in non-interactive mode (`claude --print --output-format json`)
to act as the model under test. Uses whatever auth is already wired
into the local CLI (OAuth via keychain, or `ANTHROPIC_API_KEY` if
configured), so no separate vendor key needs to be plumbed into the
harness environment. Implemented in `harness._call_claude_code`
(family identifier: `claude-code`).

| Field | Value |
|---|---|
| Family | Anthropic Claude (via the local Claude Code CLI) |
| Model ID | Whatever string the operator passes; the adapter forwards it as `--model`. Defaults to `claude-opus-4-7` unless overridden. |
| Tool use | **Condition A only.** Conditions B/C would require an MCP server that re-exposes `B_TOOLS` / `tool_solve` to the spawned subprocess; not implemented in this adapter. Calling `_call_claude_code` with non-empty `tools` raises `NotImplementedError`. |
| Routing | Local subprocess. No HTTP from the harness. The CLI itself talks to Anthropic. |
| Selection rationale | Lets a solo operator run condition-A pipeline-soak cells against the corpus without configuring vendor API keys. Useful for harness-development feedback loops and for the no-LLM-API mode requested in the redesign discussion that motivated this slot. |
| Inference params | `timeout` (subprocess wall-clock, default 600s) and `extra_args` (forwarded to `claude` verbatim, e.g. `--append-system-prompt`). `temperature`/`top_p`/`max_tokens` are not configurable — the CLI picks them. |

**Status: not §7-grade.** Slot CC is a single-vendor adapter (one
family — Anthropic) and supports only condition A. It cannot
satisfy §7's "≥ 2 LLMs from unrelated families" requirement on its
own, and a benchmark run that uses only Slot CC must be labeled
single-vendor / condition-A-only. It is documented here so
solo-operator runs don't accidentally cross-pollinate evidence:
results from Slot CC stay in their own bundle, never in a §7-grade
manifest.

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
| GitHub Models | `GITHUB_TOKEN` (PAT, `models:read` scope) | <https://models.github.ai/inference> | Slot A (`openai/gpt-5`) AND Rubric LLM (`openai/gpt-4.1-mini`). One PAT covers both. |
| Google AI Studio | `GOOGLE_API_KEY` | <https://generativelanguage.googleapis.com> | Slot B (`gemini-2.5-pro`). Free-tier API key from <https://aistudio.google.com/app/apikey>. |
| OpenAI direct | `OPENAI_API_KEY` | <https://api.openai.com> | Optional — re-enable if upgrading Slot A from gpt-5 (GitHub-Models-routed) to gpt-5.5 (direct API). |
| Anthropic direct | `ANTHROPIC_API_KEY` | <https://api.anthropic.com> | Parked — re-enable when Anthropic credits are available. |

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
| 2026-04-30 | A | Routed via GitHub Models (`https://models.github.ai/inference`, PAT auth) instead of direct OpenAI API. Model id downgraded from `gpt-5.5-2026-04-23` to `openai/gpt-5` because GitHub Models' REST catalog does not carry GPT-5.5 (it's only in the Copilot Chat picker, not the programmatic API). Documented as a §5 limitation (weaker pinning + older model). |
| 2026-04-30 | Rubric | Routed via GitHub Models too (`openai/gpt-4.1-mini`); same `GITHUB_TOKEN`. |
| 2026-04-30 | --- | Resulting credential surface is two keys total: `GITHUB_TOKEN` (Slot A + Rubric) and `GOOGLE_API_KEY` (Slot B). No paid OpenAI / Anthropic billing for the v0.1.1 run. |
| 2026-04-30 | --- | Smoke-test outcomes against the two-slot lineup: openai/gpt-5 via GitHub Models hit aggressive rate-limiting and bot-detection warnings on rapid retries; gemini-2.5-pro returned 429 quota-exhausted on free tier (limit=0); only gemini-2.5-flash + openai/gpt-4.1-mini (rubric-scale) actually completed end-to-end. |
| 2026-04-30 | A | Reassigned to **Google `gemini-2.5-flash`** as the lone active slot for v0.1.1 exploratory runs. Slot B parked pending second-vendor activation. v0.1.1 explicitly marked as **single-vendor / not §7-grade** at the top of this file. |
