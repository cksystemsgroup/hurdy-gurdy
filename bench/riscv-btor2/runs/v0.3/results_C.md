# `riscv-btor2` v0.3 — condition C result (§3.C measurement)

**Date:** 2026-05-10
**Model under test:** Anthropic Haiku 4.5
(`claude-haiku-4-5-20251001`), routed through the `claude-code` CLI
adapter (`slot_CC_haiku`).
**Condition:** C only (solver-only; LLM hand-writes SMT-LIB and
calls `solve`, no pair tools, no schema, no starter spec).
**Corpus:** the v0.3 corpus, 51 tasks → 53 cells.
**Seeds:** 1 per cell.
**Methodology:** full sweep — 53 cells of `tool_solve` access, no
inheritance from prior versions (this is the first published
condition-C run on this corpus). Companion document to
[`results.md`](results.md) (the v0.3 A vs B sweep).

> **Status: SINGLE-VENDOR EXPLORATORY.** Same caveat as
> `results.md`: slot_CC_haiku is Anthropic-only, so this run is
> not §7-grade. The §3.C measurement is meaningful even
> single-vendor — it isolates *what the pair adds beyond the
> solver*, which is the single most-asked question about the
> bench, regardless of how many vendors run it.

## Why this matters

`BENCHMARKING.md` §3.C is the condition that makes B's improvement
defensible. The published v0.1.2 / v0.2 results showed B beating A
by ~12pp accuracy, but that result was reducible to "you gave the
LLM a solver" without a §3.C control. Until now the bench had the
infrastructure for C wired but never run; this is the first
published §3.C measurement.

## Headline result

The pair (B) does beat solver-only (C) — but the gap is small on
verdict accuracy and dramatic on witness fidelity.

| Metric | A (no tools) | C (solver-only) | B (pair) | B − A | B − C |
|---|---|---|---|---|---|
| Verdict accuracy | 47/53 (88.7%) | **52/53 (98.1%)** | 53/53 (100%) | +11.3 pp | **+1.9 pp** |
| Hallucination (wrong @ conf ≥ 0.8) | 6 | 1 | 0 | −6 | −1 |
| Witness fingerprint match (of reachables) | 12/35 (34.3%) | 7/35 (20.0%) | 28/35 (80.0%) | +45.7 pp | **+60.0 pp** |
| Brier score | 0.1091 | **0.0187** | 0.0004 | ×273 | ×47 |
| ECE (10-bucket) | 0.0942 | **0.0115** | 0.0123 | ×8 | ×1 |

The headline distinction:

- On *verdict accuracy*, condition C eats most of the A→B gap.
  C alone explains ~9.4 pp of B's 11.3 pp improvement; the pair
  adds the remaining ~1.9 pp.
- On *witness fidelity*, the pair adds **+60 pp over C** — a
  dramatically larger effect than on verdicts. C's witnesses are
  *worse* than A's (20.0% vs 34.3%) because the LLM under C
  emits witness fingerprints from its hand-encoded SMT-LIB
  reasoning, which is more error-prone than even unaided
  inspection. The pair's `lift` tool is what closes that gap.

This is the §3.C-defensible interpretation of the v0.1.2 / v0.2 /
v0.3 finding: the pair's value over a generic solver is small on
"is the property reachable" but large on "what trace witnesses
the reachability." Most of the verdict accuracy was already
accessible to a smart LLM with a solver; the *source-grounded
trace* is what hurdy-gurdy uniquely contributes.

## Stream 5 measurement: tool use under C

The other thing C measures: when the LLM has access to a solver
but no pair, *does it actually use the solver*? This is non-trivial
because the prompt is permissive (use solve when useful); a smart
LLM may reason directly on small programs.

| | Count |
|---|---|
| Cells calling `solve` at least once | 46/53 (86.8%) |
| Cells answering by direct reasoning (no `solve` call) | 7/53 (13.2%) |
| Of solve-using cells: correct | 45/46 (97.8%) |
| Of direct-reasoning cells: correct | 7/7 (100%) |
| Total `solve` invocations across 53 cells | 68 (mean 1.3/cell) |

The direct-reasoning cells are concentrated on trivial code
where SMT-LIB encoding would be wasted effort
(`0007-simple-add-baseline`, etc.). On every non-trivial cell
Haiku shelled to `solve`. The 1 hallucination — the only verdict
miss in the C sweep — was a solve-using cell, not a direct-
reasoning one (see "Failure mode" below).

### Engine choice under C

Engines invoked across the 68 `solve` calls:

| Engine | Calls |
|---|---|
| `bitwuzla` | 46 |
| `z3`       | 22 |
| `cvc5`     | 0 |
| `pono`     | 0 |

Haiku strongly preferred `bitwuzla` — the engine the
`condition_c.md` prompt names as "often dramatically faster on
bitvector-heavy queries (the riscv-btor2 pair's BMC tasks measure
6–13× faster vs `z3`)." 25 cells used only bitwuzla; `z3` mostly
appeared as a second-vendor cross-check after bitwuzla returned.
Neither `cvc5` nor `pono` was ever invoked. The condition-C
prompt's engine table is descriptive, not directive — Haiku
exercised real preference inside it.

## Failure mode

The single C miss: **`0020-monotonic-x5-spacer`**, expected
`proved`, observed `unreachable`, confidence 0.99, engine: bitwuzla.

The task asks whether `x5 < 0` is reachable from a program that
only writes non-negative values to `x5`. The pre-registered spec
under B uses `z3-spacer` to emit `proved` (an unbounded inductive
claim). Under C, Haiku had no proving engine available
(`tool_solve` exposes only BMC engines; the pair's z3-spacer
Horn-clause encoding is not callable from C). Haiku's reasonable
move was to encode the BMC question and conclude `unsat` at some
finite depth → "unreachable." The matcher rejects that mapping
because `proved` is *strictly stronger* than `unreachable` — the
asymmetric matcher rule documented in v0.1.2 §"Diagnosis."

This is a coverage limitation of the condition-C tool surface, not
a Haiku miss per se. To get C parity with B on inductive tasks,
condition C would need to expose pono in k-induction mode
(`pono -e ind`) — already wired through the pair's solver
inventory, just not yet plumbed through `tool_solve`'s
`_SOLVE_ALLOWED` set. A v0.4 follow-up.

The 8 other inductive cells (0021, 0045, 0046, 0047, 0048-q1,
0048-q2, 0049-q1, 0049-q2) all returned `proved` correctly under
C. Haiku used hand-written SMT-LIB to argue an inductive
invariant on those — sometimes by writing a Horn-clause-style
encoding directly to `solve(z3, smt2, ...)` with custom
fixed-point assertions, sometimes by recognising a small enough
state space to enumerate. Both approaches worked; the matcher
accepted the verdict.

## v0.3 deltas under C

The two bitwuzla-pinned v0.3 deltas (intended to exercise engine
choice) under condition C:

| Cell | Verdict | Witness | Engines invoked |
|---|---|---|---|
| 0050-deep-mul-chain | reachable ✓ | OK | bitwuzla, bitwuzla |
| 0051-large-bound-loop-bitwuzla | reachable ✓ | wrong | (none — direct reasoning) |

0050: Haiku encoded the deep mul chain in SMT-LIB and dispatched
bitwuzla — the engine the prompt advertised as bitvector-strong.
Verdict and witness both correct. This is an instance where the
pair's bitwuzla pin (B) and the LLM's free engine choice (C)
arrive at the same engine via different routes.

0051: Haiku reasoned directly about an 80-iter counter loop
without calling `solve`. The verdict ("after 80 iterations the
post-loop marker is reached") is trivially correct, but the
witness fingerprint at the bad PC requires register state at
exactly cycle 164 — Haiku's directly-emitted witness misses some
register pins. The pair's `lift` tool produced the matching
witness under B; C had no equivalent.

## Calibration

| | A | C | B |
|---|---|---|---|
| Brier | 0.1091 | **0.0187** | 0.0004 |
| ECE   | 0.0942 | **0.0115** | 0.0123 |
| Mean conf \| correct | 0.981 | 0.993 | 0.988 |
| Mean conf \| wrong | 0.978 | 0.990 | n/a (no wrong) |

C is dramatically better-calibrated than A (×6 Brier) and roughly
on par with B's ECE (the residual difference is dominated by C's
single high-confidence miss vs B's zero). C with a solver is *not*
the overconfident A baseline; it's a well-calibrated baseline that
the pair only slightly improves on the verdict axis — and
substantially improves on the witness axis.

## Per-task summary

All 53 cells produced one of {`reachable`, `unreachable`,
`proved`}; no cell returned `unknown`. The verdict distribution:

| Verdict | A | B | C | Expected |
|---|---|---|---|---|
| reachable | 35 | 35 | 35 | 35 |
| unreachable | 8 | 5 | 6 | 9 |
| proved | 10 | 13 | 12 | 9 |

Both B and C produced more `proved` verdicts than the corpus
expects (13 and 12 vs 9) — the matcher accepts `proved` as
strictly stronger than `unreachable`, so this is correct, not
wrong. The single C miss is the inverse: the corpus expected
`proved`, C produced `unreachable`.

## What this run *doesn't* show

- **It is not §7-grade.** Single-vendor (Anthropic only). Path
  back: a slot from a different family (OpenAI / Google / Meta).
  This applies to all of A / B / C identically.
- **It is single-seed.**
- **The §9.7 rubric LLM is wired but not run.**
- **Condition C's tool surface has a coverage gap on inductive
  questions.** The 0020 miss is a *bench limitation*, not a Haiku
  failure; closing it requires extending `tool_solve`'s
  `_SOLVE_ALLOWED` set to include `pono` in `ind` mode (already
  available to the pair). A small v0.4 plumbing change.

## Run hygiene

- Sweep transcripts at `runs/v0.3/_full_C/` (53 records,
  `manifest.json` + `runs.jsonl` + per-cell transcripts).
- Combined summary at `runs/v0.3/summaries/C.json` (one row per
  cell, source-tagged).
- Stream 5 solve-usage report at
  `runs/v0.3/summaries/solve_usage.json` (per-cell engines
  invoked + roll-up).
- Combine driver `bench/riscv-btor2/_v03_combine.py` regrades all
  three conditions through the current matcher.
- Wall-clock: ~50 min on slot_CC_haiku (≈55s/cell on average,
  longer than B's ≈30s/cell because the LLM under C spends more
  turns iterating SMT-LIB).
- Total `solve` invocations: 68 across 53 cells (mean 1.3/cell).

## Implications for the v0.1.2 / v0.2 / v0.3 narrative

Three published evaluations now have headline numbers comparable
to "B beats A by 12pp." With C in hand, that finding refines:

> **What the pair adds over a generic solver: ~2pp verdict
> accuracy, +60pp witness fidelity, and one fewer hallucination.**
> What the pair adds over no tools at all: ~11pp verdict
> accuracy, +46pp witness fidelity, and six fewer hallucinations.

The headline value of `riscv-btor2` is therefore *trace
fidelity*, not verdict accuracy. The translation, the schema, and
the lift contribute most of their measurable value as a
*structured output substrate* the LLM doesn't have to invent.
This is the conceptual claim PAIRING.md and BENCHMARKING.md make,
now backed by an empirical §3.C measurement.

## Next steps (not v0.3)

- Add `pono -e ind` to condition-C's `_SOLVE_ALLOWED` so
  inductive tasks have a proving engine option under C; re-run
  0020 to see if the miss closes. Small change.
- Multi-seed sweep on C (5 seeds × 53 cells = 265 cells).
- Second-vendor slot to satisfy §7's two-family requirement.
- §9.7 rubric LLM run on the 5 T4 cells under all three
  conditions — the lift-quality measurement that's been wired
  but not run since v0.1.2.
