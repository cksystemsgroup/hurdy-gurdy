# `riscv-btor2` v0.3 — engine-selection prompt + bitwuzla corpus pin

> **Companion document:** [`results_C.md`](results_C.md) carries the
> §3.C measurement (condition C against the same v0.3 corpus and
> slot, run 2026-05-10). Headline: C 52/53 (98.1%); B beats C by
> +1.9 pp on verdict accuracy and **+60.0 pp on witness fidelity**.
> The pair's measurable value over a generic solver is dominated by
> trace/witness lift, not by verdict accuracy. Read `results_C.md`
> next.

**Date:** 2026-05-09
**Model under test:** Anthropic Haiku 4.5
(`claude-haiku-4-5-20251001`), routed through the `claude-code` CLI
adapter (`slot_CC_haiku`).
**Conditions:** A (no tools) and B (pair-equipped via the bench's
MCP stdio server).
**Corpus:** 51 tasks → 53 cells. The v0.2 corpus (49 tasks /
51 cells) plus the v0.3 expansion (`0050-deep-mul-chain` and
`0051-large-bound-loop-bitwuzla`, both pinned to `bitwuzla`).
**Seeds:** 1 per cell.
**Methodology:**
- Condition A — *delta sweep*. A's prompt (`prompts/condition_a.md`)
  did not change in v0.3, so v0.1.2 + v0.2-delta transcripts on the
  49 existing tasks remain valid; the v0.3 delta runs A on
  0050 and 0051 only.
- Condition B — *full re-sweep*. The v0.3 prompt
  (`prompts/condition_b.md`) gained an "Engine selection" section
  that names every engine in the inventory and when to pick it. The
  v0.2 B transcripts no longer represent v0.3 prompt behaviour, so
  all 53 cells were re-run against the v0.3 prompt.

> **Status: SINGLE-VENDOR EXPLORATORY.** Slot CC_haiku is an
> Anthropic-only slot. This run does not satisfy
> `BENCHMARKING.md` §7's "≥ 2 LLMs from unrelated families"
> requirement and is therefore not §7-grade. The v0.1.2 / v0.2
> caveat about needing an OpenAI / Google / Meta second slot
> still applies as the path back to §7-grade.

## Headline result

The **pair-helps-LLM finding holds** at the v0.3 corpus, and the
new "Engine selection" prompt block did **not regress B**.

| Metric | A (no tools) | B (pair) | Delta |
|---|---|---|---|
| Verdict accuracy | 47/53 (88.7%) | **53/53 (100%)** | **+11.3 pp** |
| High-confidence wrong (§5 hallucination) | 6 (11.3%) | **0 (0%)** | **−6** |
| Witness fingerprint match (of reachables) | 12/35 (34.3%) | **28/35 (80.0%)** | **+45.7 pp** |
| Brier score | 0.1091 | **0.0004** | **×273** |
| ECE (10-bucket) | 0.0942 | **0.0123** | **×8** |

**B nailed every cell** for the third consecutive evaluation
(v0.1.2 → v0.2 → v0.3) — including all 4 cells of the multi-q
T3 tasks (0048, 0049) and both v0.3 deltas (0050, 0051).

## Stream 6 — engine-selection finding

The v0.3 prompt change introduced an "Engine selection" section to
`prompts/condition_b.md` that names every engine in the inventory
and gives a one-line "use it when" rule, citing `engine_bench.py`'s
6–13× bitwuzla-vs-z3-bmc empirical advantage as the case for
considering bitwuzla over the default z3-bmc. The corpus pinned
0050 and 0051 to bitwuzla on the strength of that same data.

The Stream 6 measurement question was: does an LLM under B keep
the corpus's pinned engine, or does it default back to z3-bmc?

**Result.** Across 53 B cells, the LLM kept the corpus-pinned
engine on **50/53 (94.3%)**. Every cell made at least one
`dispatch` call — there were zero "answer without dispatching"
cells. The three switches:

| Cell | Pinned | LLM invoked | Comment |
|---|---|---|---|
| 0003-addiw-sign-ext | z3-bmc | z3-bmc → z3-spacer | Escalated to spacer; verdict still correct (matcher accepts `proved` for `unreachable`). |
| 0016-bge-signed | z3-bmc | z3-bmc → z3-spacer | Same pattern. |
| 0030-two-callees-mixed | z3-bmc | z3-bmc → bitwuzla×3 | The LLM tried z3-bmc, then re-dispatched under bitwuzla — exactly the substitution the prompt's "bitwuzla for bitvector-heavy" guidance recommends. Verdict correct. |

**Both bitwuzla-pinned v0.3 deltas (0050, 0051) kept the pin
without escalation** (1 dispatch call each, both to `bitwuzla`,
both verdicts correct, both witness fingerprints match). The pin
is not just docstring — the LLM reads the spec, sees `engine:
"bitwuzla"`, and dispatches it.

The 0030 switch is the most interesting data point: the LLM made
a *non-trivial* engine choice (started with the pin, then escalated
to bitwuzla on its own initiative). With 1/53 cells doing that on
this corpus, the engine-selection prompt block had a small but
non-zero effect on LLM behaviour beyond the corpus pin.

## Comparison vs. v0.2

| Metric | A v0.2 (51) | A v0.3 (53) | B v0.2 (51) | B v0.3 (53) |
|---|---|---|---|---|
| Verdict accuracy | 88.2% | 88.7% | 100% | **100%** |
| Witness match | 33.3% | 34.3% | 81.8% | 80.0% |
| Hallucination | 6 | 6 | 0 | 0 |
| Brier | 0.1134 | 0.1091 | 0.0005 | 0.0004 |
| ECE | 0.0982 | 0.0942 | 0.0131 | 0.0123 |

The v0.3 numbers track v0.2 within sampling noise. The two new
tasks moved A's accuracy slightly up (both reachables under A,
both correct), B held at 100%, and the B-side calibration stayed
essentially perfect. The "Engine selection" prompt block did not
introduce regressions — the most testable concern about the v0.3
prompt change.

## Source breakdown

| Source | Count | A correct | B correct |
|---|---|---|---|
| v0.1.2 originals | 32 | 28/32 (87.5%) | 32/32 (100%) |
| v0.2 deltas (17 tasks, 19 cells) | 19 | 17/19 (89.5%) | 19/19 (100%) |
| v0.3 deltas (2 tasks, 2 cells) | 2 | 2/2 (100%) | 2/2 (100%) |
| **Combined** | **53** | **47/53 (88.7%)** | **53/53 (100%)** |

## A misses, by source

The 6 A misses are *all* inherited from v0.1.2 / v0.2; v0.3 added
no new A failures.

| Cell | Source | Expected | Observed | Cause |
|---|---|---|---|---|
| 0014-twenty-iter-loop | v0.1.2 | reachable | proved | Verdict-vs-question polarity (v0.1.2 §"Diagnosis"). |
| 0015-nested-loop | v0.1.2 | reachable | proved | Same. |
| 0017-and-baseline | v0.1.2 | reachable | proved | Same. |
| 0018-or-baseline | v0.1.2 | reachable | proved | Same. |
| 0033-store-load-byte-roundtrip | v0.2-delta | reachable | unreachable | v0.2 §"A misses". Conjunctive-property misread without solver help. |
| 0045-x5-bounded-counter-spacer | v0.2-delta | proved | unreachable | v0.2 §"A misses". Articulated bound-only argument; matcher rejects (proved is strictly stronger). |

## B misses

**None.** All 53 cells correct. Third evaluation in a row
(v0.1.2 → v0.2 → v0.3) where pair-equipped Haiku produces a
perfect verdict score. The corpus is undersized for the claim
"Haiku-with-tools is at the corpus ceiling," but the headline
"the pair turns weaker-model verdicts from 88-89% to 100% with
zero hallucinations" survives a 1.66× corpus expansion across
new capability dimensions and a non-trivial prompt change.

## What's exercised, by capability

| Capability | First introduced in | A on this slice | B on this slice |
|---|---|---|---|
| MemoryAt + `[witness.memory]` | 0033–0037 (v0.2 / A1) | 5/5 verdict, 0/5 witness | 5/5 verdict, 0/5 witness |
| Path coverage (`executed_pcs`) | 0038–0040 (v0.2 / A2) | 3/3 verdict, 0/3 witness | 3/3 verdict, 3/3 witness |
| Free-input search (BMC synthesis) | 0041–0044 (v0.2 / A3) | 4/4 verdict, 2/3 witness | 4/4 verdict, 3/3 witness |
| Inductive invariants (z3-spacer) | 0045–0047 (v0.2 / A4) | 2/3 verdict, n/a witness | 3/3 verdict, n/a witness |
| Compositional T3 (multi-q, LearnedFact) | 0048–0049 (v0.2 / A5) | 4/4 verdict, n/a witness | 4/4 verdict, n/a witness |
| Engine pin to bitwuzla (v0.3) | 0050–0051 (v0.3) | 2/2 verdict, 1/2 witness | **2/2 verdict, 2/2 witness, 2/2 kept pin** |

The v0.3 row is the new measurement: every cell where the corpus
pins bitwuzla, the LLM under B keeps the pin and reaches the
correct verdict + witness. No regression on the existing 51 cells.

## Calibration

A and B both came in slightly better-calibrated than v0.2 (A's
Brier 0.1091 vs v0.2's 0.1134; B's Brier 0.0004 vs v0.2's 0.0005).
The improvements are within sampling noise. As in v0.2, A's
miss bucket (0.85–1.0 confidence) is where every wrong answer
landed; B has no wrong-answer bucket because there are no wrong
answers.

## Per-task breakdown (B v0.3)

All 53 cells produced `verdict_correct=True`. The witness
fingerprint failures (35 reachable cells, 28 OK = 7 misses):

- 0004 (v0.1.2 known issue — Haiku drops x6 from final_regs)
- 0033, 0034, 0035, 0036, 0037, 0042 — `[witness.memory]` cells
  where Haiku omits memory contents (v0.2 §"Comparison" diagnosed
  this as the matcher's strict-match-or-fail policy on memory
  fields; same finding here).

## What this run *doesn't* show

- **It is not §7-grade.** Single-vendor (Anthropic only). Path
  back: a slot from a different family under conditions A and B.
- **It is single-seed.** The five-seed multi-pass v0.1.2 §"How
  would you extend the sweep" sketched was not run. Single-seed
  observation; the determinism check at v0.1.2 (5/5 unique prose,
  1/1 unique verdicts on a T1 sample) suggests the verdict is
  stable across seeds.
- **The §9.7 rubric LLM is wired but not run.** Same as v0.2 —
  `lift_score = null` for all 5 T4 cells.
- **No second-vendor grading of the engine-choice column.** The
  Stream 6 finding (50/53 kept the pin) is the *Haiku* finding;
  whether an OpenAI / Google model behaves the same way is open.

## Run hygiene

- **Sweep transcripts**:
  - `runs/v0.3/_delta_A/` — 2 records (0050, 0051 under A).
  - `runs/v0.3/_full_B/` — 53 records (full B re-sweep against
    the v0.3 prompt). Wall-clock ~26 min on slot_CC_haiku.
  - The v0.1.2 and v0.2 transcripts are referenced by path; not
    duplicated.
- **Combined summaries** at `runs/v0.3/summaries/{A,B}.json` —
  one row per cell, source-tagged (`v0.1.2` / `v0.2-delta` /
  `v0.3-delta` for A; `v0.3` for B).
- **Stream 6 engine-choice report** at
  `runs/v0.3/summaries/engine_choice.json` — per-cell record of
  pinned engine + every engine the LLM actually invoked + a
  `kept_pin` boolean.
- **Combine driver** is `bench/riscv-btor2/_v03_combine.py`;
  re-running it regrades every cell with the current matcher.

## Acceptance criteria status

Per `CORPUS_V0.3_PLAN.md` §"Acceptance criteria":

1. ✅ ≥ 1 task pinned to `bitwuzla` with bitwuzla ≥ 5× faster
   than z3-bmc on a 5-sample median (engine_bench: 0050 ≈ 11×,
   0051 ≈ 9×).
2. ✅ ≥ 1 task pinned to `bitwuzla` with bound ≥ 100 (0051's
   bound = 170).
3. ✅ Every new task PASSes all four pre-flight oracles
   (oracle.py, framework_oracle.py, audit_anchors.py,
   oracle_cross.py — all 4 green pre-sweep).
4. ✅ Condition B's prompt carries the "Engine selection"
   section. The Stream 6 measurement (above) confirms the
   bitwuzla pin survives prompt-mediated LLM dispatch on every
   bitwuzla-pinned cell.

v0.3 is shippable.

## Next steps (not v0.3)

- §9.7 rubric LLM run on the 5 T4 cells under both conditions.
- Multi-seed sweep (5 seeds × 53 cells × 2 conditions).
- Second-vendor slot to satisfy §7's two-family requirement —
  the path back to publishable.
- Condition C sweep (Stream 5 measurement). The infrastructure
  is operational and reference-encoder-validated; needs an LLM
  run to measure how often condition C produces a correct
  hand-encoded verdict.
- Bitwuzla-domain corpus expansion if v0.4 wants to demonstrate
  the engine-choice signal more strongly than 1/53 cells (today's
  cleanest signal is 0030's spontaneous z3-bmc → bitwuzla
  switch).
