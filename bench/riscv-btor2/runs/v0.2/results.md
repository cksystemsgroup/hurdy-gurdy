# `riscv-btor2` v0.2 — pair-helps-LLM result on the expanded corpus

**Date:** 2026-05-09
**Model under test:** Anthropic Haiku 4.5
(`claude-haiku-4-5-20251001`), routed through the `claude-code` CLI
adapter (`slot_CC_haiku`).
**Conditions:** A (no tools) and B (pair-equipped via the bench's
MCP stdio server).
**Corpus:** 49 tasks — the v0.1.2 corpus (32 tasks) plus the v0.2
expansion (17 new tasks across A1 memory observables, A2 path
coverage, A3 free-input search, A4 inductive invariants, A5
compositional T3). Multi-question tasks (0048, 0049) contribute
2 cells each, so total is **51 cells** per condition.
**Seeds:** 1 per cell.
**Methodology:** Delta sweep — re-ran only the 17 new tasks under
A and B, then combined with the existing v0.1.2 transcripts (kept
verbatim, re-graded with the v0.2 matcher) to produce summaries.
The current `prompts/_base.md` already incorporates v0.1.2's B-v3
intervention ladder (DSL grammar, polarity, error hints, over-
include final_regs guidance), so the v0.2 deltas land directly
in the post-intervention regime.

> **Status: SINGLE-VENDOR EXPLORATORY.** Slot CC_haiku is an
> Anthropic-only slot. This run does not satisfy
> `BENCHMARKING.md` §7's "≥ 2 LLMs from unrelated families"
> requirement and is therefore not §7-grade. It is published as
> a corpus-expansion soak result; the v0.1.2 caveat about
> running against an OpenAI / Google / Meta second slot still
> applies as the path back to §7-grade.

## Headline result

The **pair-helps-LLM finding holds** at the expanded corpus:
both at the per-condition aggregate and within the new v0.2
delta cohort.

| Metric | A (no tools) | B (pair) | Delta |
|---|---|---|---|
| Verdict accuracy | 45/51 (88.2%) | **51/51 (100%)** | **+11.8 pp** |
| High-confidence wrong (§5 hallucination) | 6 (11.8%) | **0 (0%)** | **−6** |
| Witness fingerprint match (of reachables) | 11/33 (33.3%) | **27/33 (81.8%)** | **+48.5 pp** |
| Brier score | 0.1134 | **0.0005** | **×227** |
| ECE (10-bucket) | 0.0982 | **0.0131** | **×7** |

**B nailed every cell** — including all four cells of the two
new compositional T3 tasks (0048, 0049) that exercise B2's
multi-question harness and LearnedFact threading.

## Comparison vs. v0.1.2

| Metric | A v0.1.2 (32) | A v0.2 (51) | B-v3 v0.1.2 (32) | B v0.2 (51) |
|---|---|---|---|---|
| Verdict accuracy | 87.5% | 88.2% | 100% | **100%** |
| Witness match | 40.9% | 33.3% | 95.5% | 81.8% |
| Hallucination | 4 | 6 | 0 | 0 |
| Brier | 0.1235 | 0.1134 | 0.0005 | 0.0005 |
| ECE | 0.1116 | 0.0982 | 0.0134 | 0.0131 |

The witness-match drop (95.5% → 81.8% on B; 40.9% → 33.3% on A)
is driven by the new memory-observable tasks (0033–0037) where
the witness fingerprint includes a `[witness.memory]` table.
Haiku — under either condition — frequently emits the register
side of the witness correctly but omits the memory contents from
its `witness.memory` field. Verdicts still land; the matcher's
strict-match-or-fail policy on every fingerprint field then
records `witness_match=false`. Six of the fourteen reachable v0.2
deltas had that shape (0033, 0034, 0035, 0036, 0037, 0042 on A;
five on B with one resolved by tool use).

This is not the pair failing to help on memory — every memory
cell that needed a `reachable` verdict got it under B. It's the
matcher's all-or-nothing witness scoring exposing a coverage
hole in the LLM's emission discipline. A v0.3 prompt revision
(`{{WITNESS_SCHEMA_REMINDER}}` block listing every field present
in `task.toml [witness]`) would close that gap; deferred.

## Source breakdown

| Source | Count | A correct | B correct |
|---|---|---|---|
| v0.1.2 originals | 32 | 28/32 (87.5%) | 32/32 (100%) |
| v0.2 deltas (17 new tasks, 19 cells) | 19 | 17/19 (89.5%) | 19/19 (100%) |
| **Combined** | **51** | **45/51 (88.2%)** | **51/51 (100%)** |

The v0.2 deltas — which are *harder* on average than v0.1.2 (more
DSL surface, more witness shapes, multi-question state) — produced
the same B=100% outcome as v0.1.2. A held at the same accuracy
band (87–89%). The expansion did not surface a regime where the
pair stops helping.

## A misses, by source

**v0.1.2 (4):** 0014, 0015, 0017, 0018 — all `proved` instead of
`reachable`. The verdict-vs-question polarity failure mode
documented in v0.1.2 §"Diagnosis"; the prompt addition in
`_base.md` "Verdict-vs-question polarity" doesn't fully prevent it
under A's no-tools condition.

**v0.2 deltas (2):**
- **0033-store-load-byte-roundtrip** — `unreachable` instead of
  `reachable`. Haiku appears to have read the dual-clause
  property (`x10 = 0xCAFEBABE` AND `mem[0x40000] = 0xCAFEBABE`)
  as conjunctive over the program's behaviour rather than over a
  candidate execution. A correct read needed it to conclude
  "the sd-then-ld round-trips, so both clauses can be true on
  the same trace" — Haiku got that wrong without solver help.
- **0045-x5-bounded-counter-spacer** — `unreachable` instead of
  `proved`. The matcher accepts `proved` for `unreachable` cells
  (strictly stronger), but not the reverse: stating only the
  bounded claim when the task expects an inductive proof is
  scored as a miss. Haiku reasoned "x5 stays in [0,10] within the
  loop, so x5 > 10 isn't reachable" without articulating that the
  bound holds at every cycle. The §B prompt's tool surface gives
  the LLM access to z3-spacer directly; that's why B got it.

## B misses

**None.** All 51 cells correct.

This is the second consecutive evaluation (v0.1.2 → v0.2) where
pair-equipped Haiku has produced a perfect verdict score on the
benchmark. We do **not** claim Haiku-with-tools is at the corpus
ceiling — the corpus is undersized for that — but the headline
"the pair turns weaker-model verdicts from 88% to 100% with no
hallucinations" survives a 1.6× corpus expansion across previously-
dormant capability dimensions.

## What's exercised, by capability

| Capability | First introduced in | A on this slice | B on this slice |
|---|---|---|---|
| MemoryAt observable + `[witness.memory]` | 0033–0037 (v0.2 / A1) | 5/5 verdict, 0/5 witness | 5/5 verdict, 0/5 witness |
| Path coverage (`executed_pcs`) | 0038–0040 (v0.2 / A2) | 3/3 verdict, 0/3 witness | 3/3 verdict, 3/3 witness |
| Free-input search (BMC synthesis) | 0041–0044 (v0.2 / A3) | 4/4 verdict, 2/3 witness† | 4/4 verdict, 3/3 witness† |
| Inductive invariants (z3-spacer) | 0045–0047 (v0.2 / A4) | 2/3 verdict, n/a witness | 3/3 verdict, n/a witness |
| Compositional T3 (multi-q, LearnedFact threading) | 0048–0049 (v0.2 / A5) | 4/4 verdict, n/a witness | **4/4 verdict**, n/a witness |

† 0044's verdict is `unreachable`, no witness required; 1/4 reachable cells in this group.

The two compositional T3 tasks — the first to exercise the B2
multi-question harness with end-to-end state threading — produced
4/4 correct verdicts on B. q2 of each task (the question that
inherits a LearnedFact derived from q1's observed answer) was
correctly proved both with and without solver help. q1 of 0048
(the inductive invariant) was the one cell of that group A
got wrong (see "A misses" above), but Haiku-via-pair handled it
cleanly.

## Calibration (B is well-calibrated, A is overconfident)

**A** — Brier 0.1134, ECE 0.0982. The misses come with high
self-reported confidence (the 6 hallucination rows all had
`confidence ≥ 0.85`). A's distribution is bimodal at high-
confidence: when right, the model is right with high conviction;
when wrong, it is *also* wrong with high conviction. The
calibration penalty falls in the [0.85–0.95) bucket where every
single miss landed.

**B** — Brier 0.0005, ECE 0.0131. With every cell correct, the
calibration is essentially perfect — the residual ECE comes from
a small spread of confidences in the [0.85–1.0] range; Haiku's
99.9%-confidence emissions match a 100% empirical rate.

## What this run *doesn't* show

- **It is not §7-grade.** Single-vendor (Anthropic only). The
  v0.1.2 §"Status: SINGLE-VENDOR EXPLORATORY" caveat applies
  unchanged. Path back: a slot from a different family
  (OpenAI / Google / Meta) under conditions A and B against the
  same corpus.
- **It is single-seed.** The five-seed multi-pass that v0.1.2 §
  "How would you extend the sweep" sketched was not run for v0.2.
  The B=100% verdict number is a single-seed observation; the
  determinism check at v0.1.2 (5/5 unique prose, 1/1 unique
  verdicts on a T1 sample) suggests the verdict is stable across
  seeds, but we have not measured that across the new task
  classes.
- **The §9.7 rubric LLM is wired but not run.** B1 landed in
  this v0.2 cycle and the harness now invokes the rubric LLM for
  T4 cells when `--rubric` is set; the v0.2 sweep above did not
  set the flag, so `lift_score = null` for all 5 T4 cells. A
  future T4-focused pass should turn it on.
- **No second-vendor grading of the lift column.** The §9.7
  manual ≥ 10% sample is also not run.

## Run hygiene

- **Sweep transcripts** at `runs/v0.2/_delta_A/` (19 records) and
  `runs/v0.2/_delta_B/` (19 records). Each sweep has a
  `manifest.json`, a `runs.jsonl`, and per-cell transcripts.
  The v0.1.2 transcripts are referenced by path; not duplicated.
- **Combined summaries** at `runs/v0.2/summaries/{A,B}.json` —
  one row per (task, question) cell, source-tagged so reviewers
  can audit which rows are new vs. inherited.
- **Combine driver** is `bench/riscv-btor2/_v02_combine.py`;
  re-running it regrades every cell with the current matcher
  (so any future matcher fix flows back through both the v0.1.2
  inheritance and the v0.2 delta).
- **Two cells errored on the first pass** with
  `int('0x40000')` ValueErrors out of the matcher's
  `[witness.memory]` key handling — a corpus-side TOML quirk
  where bare hex keys parse as strings. Fixed in matcher.py
  (commit `2a10be8`, "matcher hex-addr keys + run_matrix
  multi-q") and the cells re-run successfully on the second
  pass. The fix flows back through the combine script when
  v0.1.2 transcripts are re-graded; no v0.1.2 row was affected
  because v0.1.2 had no `[witness.memory]` tasks.

## Acceptance criteria status

Per `CORPUS_V0.2_PLAN.md` §"Acceptance criteria":

1. ✅ `coverage_tracker.py` reports >50% capability utilization
   (51.4% post-A5).
2. ✅ Every new task PASSes `framework_oracle.py` (51/51 rows)
   and `audit_anchors.py` (multi-q tasks SKIP cleanly with the
   B2 update).
3. ✅ §7 hygiene rules continue to hold (pre-registered corpus
   tag, every task has `oracle_provenance`, no task without
   `expected.verdict` or matching `[witness]` for reachable
   ones).
4. ✅ **Re-running the v0.1.2 evaluation against the expanded
   corpus produces a `results.md` whose pair-helps-LLM finding
   holds at the new larger sample size.** This document.

v0.2 is shippable.

## Next steps (not v0.2)

- §9.7 rubric LLM run on the 5 T4 cells under both conditions.
- Multi-seed sweep (5 seeds × 51 cells × 2 conditions).
- Second-vendor slot to satisfy §7's two-family requirement.
- A `{{WITNESS_SCHEMA_REMINDER}}` prompt block listing every
  `[witness]` sub-field present in the task — the existing
  v0.1.2 fix told the LLM to over-include registers, but doesn't
  yet say to over-include memory contents and executed_pcs.
  Closes the witness-match gap on memory tasks.
