# `riscv-btor2` v0.2 corpus expansion plan

## Why this exists

The v0.1.2 evaluation (`bench/riscv-btor2/runs/v0.1.2/results.md`)
landed a meaningful headline finding (pair-equipped Haiku
+12.5pp verdict accuracy over unaided Haiku), but the corpus that
finding was measured against is much narrower than it might
appear:

- 30 of 32 tasks share the property shape "register x*N* equals
  value *V* at the halt PC."
- All observables are `RegisterAt`. The schema's `MemoryAt`,
  `PCAtStep`, `Executed` types are unused.
- Property expressions never call `mem(addr, width)`. The `mem`
  reference is dead in the LLM's prompt context.
- Assumptions are `RegisterInit` only, on 7 of 32 tasks. The
  schema's `MemoryInit` and `CycleInvariant` types are unused.
- `witness.memory` and `witness.executed_pcs` -- both supported
  by `rubric/matcher.py` -- are unused.
- `LearnedFact` (the T3 compositional reuse mechanism) is unused
  even on the 6 T3-tagged tasks.
- Every task is deterministic from entry. BMC essentially does
  concrete simulation; the "find an input that drives the
  program to a state" capability is unexercised.
- T4 lift quality is tagged on 5 tasks but `graded.lift_score`
  is permanently `None` (the §9.7 rubric LLM is not wired).

The goal of v0.2 is to take the bench from "register equality on
RV64IM lowering quirks" to a corpus that exercises the schema,
matcher, and pair tool surface in proportion to what they
declare.

## Dimensions to expand into

Five dimensions, each with concrete task proposals. Per-task
effort assumes ~30-45 min per task (write source.S + spec.json +
task.toml; build via Makefile; validate via framework_oracle and
audit_anchors).

### A1. Memory observables (5 new tasks, ~3h)

Exercises `MemoryAt`, `MemoryInit`, `mem(addr, width)`, and
`[witness.memory]`.

| Proposed | Property | What it probes |
|---|---|---|
| **0033-store-load-byte-roundtrip** | `sb x5, 0(x6)` then `lbu x10, 0(x6)`; assert x10 = stored byte. | Memory model is sound. |
| **0034-sw-then-lh-truncation** | `sw` 0xAABBCCDD, then `lh` from same address; assert x10 = 0xFFFFFFFFFFFFCCDD (sign-extended low halfword). | Width-mismatched access; classic partial-overlap. |
| **0035-misaligned-load-undef** | Load word at unaligned address. Tests that the schema's UB convention agrees with the BMC behaviour. | Forces a SCHEMA decision into a corpus question. |
| **0036-stack-canary-replay** | Push x5 to stack, do work, pop into x10. With free-input x5, prove x5 = x10 at halt. | Round-trip integrity through memory. |
| **0037-zero-init-bss** | Read uninitialized memory; verdict says it equals the spec-pinned `MemoryInit` value. | First task that uses `MemoryInit`. |

### A2. Path coverage (3 new tasks, ~2h)

Exercises `[witness.executed_pcs]` as a required-set check.

| Proposed | Path constraint | What it probes |
|---|---|---|
| **0038-cleanup-must-run** | "Verdict: x10 = 0 at halt **and** PC P_cleanup was executed before halt." | Two-clause witness; positive path. |
| **0039-skip-suspicious-branch** | Conditional branch around a "bad" PC; matcher requires the bad PC to NOT appear. | Negative path constraint via list omission. |
| **0040-init-then-loop** | Require both an init PC and a loop body PC to appear at least once. | Multi-PC required set. |

### A3. Free-input search (4 new tasks, ~3h)

Exercises BMC's actual search property -- finds inputs that
drive the program to a target state rather than just simulating
a deterministic trace.

| Proposed | Search problem | What it probes |
|---|---|---|
| **0041-find-input-makes-42** | `f(a0, a1)` with simple arithmetic; find a0, a1 such that x10 = 42 at halt. No RegisterInit on a0, a1. | Canonical input-synthesis shape. |
| **0042-collision-easy** | Two paths through a small program produce the same x10 for different a0; show the matched-output input pair is reachable. | Synthesis through control flow. |
| **0043-overflow-trigger** | Find a0 such that `addw a0, a0, a0` produces 0x80000000 (sign-bit set after add). | Bit-precise synthesis. |
| **0044-shift-zero-input** | Find a shift amount where `sllw 1, a0` masks to produce a specific value. | Modular arithmetic synthesis. |

### A4. Inductive invariants (3 new tasks, ~3h)

Exercises z3-spacer beyond the existing two `proved` tasks.

| Proposed | Invariant | What it probes |
|---|---|---|
| **0045-x5-bounded-by-iter** | "x5 is always less than (loop iteration count squared)." | Multi-variable inductive invariant. |
| **0046-no-write-x0-effects** | "x0 stays at 0 across all cycles" -- tautological-looking but validates SCHEMA §3 mechanically. | Pair's strongest claim. |
| **0047-monotonic-counter-with-skip** | Counter increments unless skipped; "x6 ≥ initial_x6 always." | Mixed monotonic/skip invariant. |

### A5. T3 compositional (2 new task groups, ~5h)

The 6 existing T3-tagged tasks don't exercise `LearnedFact`. Real
T3 requires multiple ordered questions per task with state
threading. B2 (multi-question harness) shipped — see corpus task
`0202-mul-bound-dualrole` for a working multi-question example.

| Proposed group | Q1 | Q2 |
|---|---|---|
| **0048-monotonic-then-bounded** | Prove "loop counter stays ≤ N." | Use that to prove "downstream register stays in range" without re-verifying the loop. |
| **0049-callee-clobbers-then-saves** | Prove "callee never modifies x18." | Use that to derive caller-side x18 invariants. |

## Infrastructure tracks

### B1. Wire the §9.7 rubric LLM — **shipped**

`harness.grade()` (`harness.py:1635`) now dispatches the rubric
LLM for T4 tasks via `rubric/rubric_llm.py:grade_lift`. The
populated pieces:

- `bench/riscv-btor2/rubric/rubric_prompt.md` — the rubric
  prompt template (frames the LLM with
  `expected_explanation_summary` / `expected_keywords`, instructs
  a 0/1/2 verdict).
- `rubric/rubric_llm.grade_lift` calls `MODELS["rubric"]`
  (`openai/gpt-4.1-mini` via GitHub Models) as a single
  deterministic turn; harness records `lift_score`,
  `lift_reason`, `lift_matched_pc`, etc. in `graded`.
- Fixture test
  `tests/pairs/riscv_btor2/integration/test_bench_rubric_llm.py`
  validates the wiring against a hand-written reference answer.

### B2. Multi-question task format — **shipped**

Multi-question tasks are now first-class. The shipped pieces:

- `task.toml` admits `[questions.qN]` sections with per-question
  `[expected]` and `[witness]` blocks; `harness._parse_questions`
  (`harness.py:147`) reads them.
- `harness.run_one_task` emits one `RunRecord` per question and
  threads state forward across the loop (`harness.py:1893`).
- `rubric/matcher.match` takes a `question_id` argument that
  picks which `[questions.qN]` block to grade against.
- Manifests carry `runs[].question_id`
  (`manifest_schema.json`).

Backwards-compatible: single-question tasks (the original 32)
emit one `RunRecord` with `question_id=None`. Corpus task
`0202-mul-bound-dualrole` is the working multi-question
example.

### B3. Property-shape coverage tracker (~2h)

Small audit script (`bench/riscv-btor2/coverage_tracker.py`) that
walks the corpus and reports utilization rates for each
schema-declared capability:

- Observable type usage: `RegisterAt %`, `MemoryAt %`, `PCAtStep %`, `Executed %`
- Assumption type usage: `RegisterInit %`, `MemoryInit %`, `CycleInvariant %`
- Property DSL usage: `mem() %`, `pc %`, `add/sub %`, `<comparator types>`
- Witness fingerprint shape: `final_regs %`, `executed_pcs %`, `memory %`
- Verdict distribution: `reachable / unreachable / proved / unknown`
- Difficulty / lowering-sensitive distribution
- Free-input usage (tasks with no RegisterInit on argument registers)

Run pre-expansion to fix the v0.1.2 baseline; run post-expansion
to verify the new tasks actually filled the gaps.

## Recommended sequencing

| Step | Task | Effort | Cumulative new tasks | Dependency |
|---|---|---|---|---|
| 1 | B3 coverage tracker | 2h | 0 | — |
| 2 | A1 memory (0033-0037) | 3h | 5 | — |
| 3 | A2 paths (0038-0040) | 2h | 8 | — |
| 4 | A4 invariants (0045-0047) | 3h | 11 | — |
| 5 | A3 free-input (0041-0044) | 3h | 15 | — |
| 6 | B1 rubric LLM | 4h | 15 | — |
| 7 | B2 multi-question harness | 6-8h | 15 | — |
| 8 | A5 compositional (0048-0049, 4 questions) | 5h | 17 | B2 |

Steps 1-5 can run end-to-end in ~13h with no new infrastructure
investment. They take the corpus from 32 tasks to 47 with full
property-language coverage.

Steps 6 and 7 unlock dormant bench capabilities (T4 grading and
T3 compositional reuse). 6 is independent; 7 is the largest
single piece and gates step 8.

## Acceptance criteria

A v0.2 release is ready when:

1. `coverage_tracker.py` reports >50% of declared schema capabilities
   are exercised by at least one task (current v0.1.2 baseline:
   ~15-20%).
2. Every new task PASSes `framework_oracle.py`, `oracle.py`
   (where applicable), and `audit_anchors.py`.
3. The §7 hygiene rules continue to hold: pre-registered corpus
   in a tagged commit, every task has `oracle_provenance`, no
   task is added without an accompanying `expected.verdict` and
   matching `[witness]` (or explicit "no witness needed" rationale
   for `unreachable` / `proved`).
4. Re-running the v0.1.2 evaluation against the expanded corpus
   produces a `results.md` whose pair-helps-LLM finding holds at
   the new larger sample size, or surfaces a new failure mode
   worth diagnosing.

## Things this plan deliberately defers

- **Atomics, FP, vector, privileged, CSR-write effects**:
  excluded by SCHEMA.md §13 by design; not a v0.2 target.
- **Memory havoc**: schema rejects this at v1; would require a
  schema bump.
- **Multi-core / concurrency**: out of scope per PLAN.md.
- **Source-level verifier baseline (condition D)**: separate
  decision; D is optional in BENCHMARKING.md §3.
- **Second-vendor slot for §7 grading**: orthogonal to corpus
  expansion; tracked separately.
