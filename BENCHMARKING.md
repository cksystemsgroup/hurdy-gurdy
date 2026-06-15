# Pair benchmarking playbook

This document specifies how any pair in hurdy-gurdy is benchmarked. It
is pair-agnostic: it tells you *what* to measure and *under what
conditions*, not *which programs* to use. Each pair instantiates the
playbook with its own corpus, questions, oracle, and source-level
baselines (see [§9 Per-pair instantiation checklist](#9-per-pair-instantiation-checklist)).

The playbook is the contract. A new pair's benchmark must satisfy it
before claims of "effectiveness" are made.

## 1. Purpose

A pair exists so that an LLM, given a source program, can reason about
that program more correctly and more efficiently than it could without
the pair. The benchmark must produce evidence for or against that
claim, with enough rigor that:

- a skeptical reader can locate the contribution of the pair,
  separately from the contribution of the underlying solver and
  separately from the contribution of the LLM;
- the result holds across more than one LLM and more than one run;
- a future schema bump can be re-evaluated against the same corpus.

## 2. What we are actually measuring

Hurdy-gurdy itself does no reasoning — pairs translate, dispatch, and
lift. The framework's invariant is determinism from
`(spec, source, schema_version)`; that determinism is *necessary* for
benchmarking but is not what the benchmark evaluates.

The benchmark evaluates **an LLM-plus-pair system** on tasks of the
form `(source, question, expected_verdict, witness_shape)`. A pair is
"effective" when an LLM equipped with its tool surface
(`describe`, `compile`, `dispatch`, `lift`, `introspect`) produces
better task outcomes than the same LLM without the pair, and the
improvement is not explainable by the LLM merely having access to a
solver.

The experimental unit is one LLM session over one task under one
condition.

## 3. Conditions

Every task is run under at least conditions A, B, and C. Conditions
D and E are optional; D is recommended whenever a source-level
verifier exists, and E is recommended for pairs that ship a v1.1.0+
schema with partial bindings.

### A — Source-only baseline (required)

The LLM sees the source program and the question in natural language.
No tools beyond what it would normally have (file reading, perhaps a
sandbox to execute the source). It must commit to a verdict from its
own reasoning.

Isolates: the LLM's unaided reasoning over the source language.

### B — Pair-equipped (required)

Same as A, plus the pair's tool surface and its `SCHEMA.md`. The LLM
chooses when to call `compile` / `dispatch` / `lift` / `introspect`
and when to reason directly.

Isolates: the value of the pair, *if* condition C also holds equal.

### C — Solver-only (required)

Same as A, plus direct access to the same external solver that the
pair would have used in B, but **without** the pair's translation,
schema, annotation, or lift. The LLM must hand-write its own
encoding of the question into the solver's input language.

Isolates: the value the pair adds *over and above* the solver itself.
Without C, any improvement of B over A can be attributed to "you gave
it a solver" rather than "you gave it a structured pair." C is the
condition that makes the benchmark defensible.

### D — Source-level verifier (optional, recommended)

Same as A, plus a verifier that operates directly on the source
language (e.g., CBMC / ESBMC for C, CrossHair / Nagini for Python).
The LLM may invoke the verifier and read its output but does not have
access to the pair.

Isolates: whether the pair offers anything an existing source-level
verifier does not. The strongest case for a pair is a task class on
which D answers `unknown` or wrong and B answers correctly — typically
the lowering-sensitive subset (see §4.3).

### E — Pair-equipped + propose-and-check (optional, v1.1.0+)

Same as B, plus the v1.1.0 question-compiler hook: partial input
bindings (`Free` cells), shadow-recorded simulation
(`record_shadow=True`), and `BranchPin` / `dual_role` assumptions
on the spec. The LLM can iteratively narrow the spec — pin a path
prefix, flip a branch, propose an invariant — between `compile` /
`dispatch` calls. Requires a pair that ships the v1.1.0 schema
contract (SCHEMA.md §14) and the matching interpreter hook.

Isolates: the value of *iterative* spec patching relative to the
single-shot translate-then-solve workflow that B measures.
Improvements of E over B (same model, same engine budget) attribute
specifically to the propose-and-check loop: shorter effective
bounds via pinned prefixes, witness disambiguation via flipped
branches, invariant proposal via dual-role predicates. E uses the
same engines as B; differences in `solver_seconds` and
`tokens_*` must be reported per cell so the cost of iteration is
visible.

When E does *not* improve on B for a given task class, that's
evidence the question compiler doesn't help on that class — a
useful negative result. Pairs that don't expose a v1.1.0
interpreter or schema simply skip E.

### Reporting matrix

Results are reported per `(condition, LLM, task class)` cell. Aggregate
claims must be backed by per-cell tables in the artifact bundle.

## 4. Task design principles

Each task is a tuple:

```
(source, question, expected_verdict, witness_shape, task_class, difficulty)
```

The corpus must satisfy all five principles below. Drift on any one
invalidates the benchmark.

### 4.1 Encodable

The question must be expressible in the pair's spec vocabulary
(observables, assumptions, properties). Tasks the pair *cannot*
encode are recorded as **coverage gaps**, not omitted. Coverage-gap
rate is itself a first-class metric: a pair that scores well on
encodable tasks but cannot encode most natural questions is not
effective.

### 4.2 Spans difficulty

Each corpus must include all four difficulty tiers. Quotas are
recommended in parentheses; instantiations may adjust but must
document the choice.

- **T1 (≈25%)** — trivially decidable at default bound / engine.
- **T2 (≈25%)** — requires a non-default analysis directive
  (different bound, different engine, havoc set, …).
- **T3 (≈25%)** — requires decomposition: a task where the natural
  approach is to prove a lemma as a separate question and inject it
  as a `LearnedFact` into a follow-up.
- **T4 (≈25%)** — requires source-level interpretation of a witness
  via `lift` to answer the question correctly (e.g., explaining the
  *cause* of a refutation, not just its existence).

### 4.3 Includes a lowering-sensitive subset

A non-trivial fraction (≥ 20% of the corpus) must turn on something
the source language hides — semantics that only become visible after
translation to the reasoning language. Without this subset, condition
A is too strong and the pair's distinctive value is invisible.

What "lowering-sensitive" means is pair-specific:

- For a machine-code → bitvector pair: ABI widths, undefined
  behavior the compiler resolved one way, alignment, integer
  overflow at machine width, sign-/zero-extension at calls.
- For a high-level-language → SMT pair: bignum vs. fixed-width
  semantics, default mutability, exception edges, aliasing.

The instantiation must document its lowering-sensitive criterion in
prose and tag every task that satisfies it.

### 4.4 Held out from pair development

Tasks must not have been used while writing `SCHEMA.md`, fixtures,
examples, or any code in the pair. Pre-register the corpus in a
tagged commit *before* running condition B. This commit hash is part
of the benchmark's identity.

### 4.5 Independent oracle

`expected_verdict` is established by one of:

1. a manual proof recorded alongside the task,
2. agreement of at least two unrelated tools,
3. an executable witness that demonstrates refutability,
4. a property-by-construction (the program was *built* to satisfy
   or violate the property).

The pair under test never establishes its own oracle. For refutable
tasks, the `witness_shape` is also recorded in advance (e.g., the
observable-state pattern at the bad step) so a coincidentally correct
verdict with a wrong witness can be distinguished from a genuinely
correct answer.

## 5. Metrics

Reported per `(condition, LLM, task class)`:

- **Verdict accuracy.** Fraction of correct final verdicts. The
  verdict vocabulary follows the pair's `RawSolverResult` —
  `reachable`, `unreachable`, `proved`, `unknown`. `unknown` is
  graded as neither correct nor wrong but tracked separately.
- **Hallucination rate.** Fraction of tasks where the LLM committed
  to a wrong verdict with high stated confidence. This is the metric
  most users care about; condition A typically loses on it badly.
- **Calibration.** Reliability diagram of stated confidence vs.
  correctness. Report Brier score or expected calibration error.
- **Cost-to-answer.** Tokens, wall-clock seconds, dispatch count,
  and cumulative external-solver seconds.
- **Compositional reuse.** On T3 tasks, did the LLM successfully
  factor the problem and reuse a `LearnedFact`? Binary per task,
  reported as a rate.
- **Lift utility.** On T4 tasks, scored against a hand-written
  explanation: does the LLM correctly identify the source-level
  cause of the refutation? 0/1/2 rubric.
- **Coverage-gap rate.** Fraction of corpus tasks the pair could not
  encode (condition B and C report this; A and D are not subject to
  it).

Headline single-number summaries are fine for abstracts but the
artifact bundle must include the full per-cell table.

## 6. Oracle and scoring

- Oracle is written in full *before* any condition runs and committed
  alongside the corpus.
- Transcripts are graded by a **rubric LLM** running blind to
  condition and to the model under test. A random sample (≥ 10%) is
  also graded by hand and the inter-rater agreement reported.
- For refutable tasks, the rubric checks the witness fingerprint, not
  just the verdict label.
- Disagreements between automated rubric and manual grading are
  resolved by a second human reviewer; the resolution rate is part
  of the artifact bundle.

## 7. Experimental hygiene

- **Pre-register** corpus, conditions, metrics, and per-condition
  prompts in a tagged commit before running B/C.
- **Multiple LLMs** — at least two from unrelated families — under
  every condition. Single-model results are demonstrations, not
  benchmarks.
- **Multiple runs** per `(task, condition, model)`. At least five.
  Report median and inter-quartile range, not just means.
- **Schema-version pinning.** Tag every result row with the pair's
  `schema_version`. A schema bump triggers a re-run; coverage-gap
  rate and verdict accuracy on the re-run are the headline
  regression signals.
- **Leakage check.** Note whether the pair's `SCHEMA.md` is plausibly
  in the LLM's training data. If yes, condition A's prompt should
  include a generic description of the source language so A is not
  artificially handicapped relative to B/C.
- **Solver-version pinning.** Conditions B, C, and D must use
  byte-identical solver binaries with the same options. A solver
  upgrade is a separate experiment.
- **Determinism check.** Hurdy-gurdy guarantees byte-identical
  compilation for fixed `(spec, source, schema_version)`. The
  benchmark must verify this on a sample (re-compile, diff bytes).
  If determinism breaks, the benchmark is invalid until fixed.

## 8. Publishing

A benchmark publication consists of:

1. **Corpus repository.** Source programs, questions, oracles, and
   witness shapes, in a single tagged commit.
2. **Spec bundle.** For every task, the `QuestionSpec` used in
   condition B, plus the hand-written solver input used in C, plus
   the source-verifier invocation used in D.
3. **Compiled artifacts.** Cached `CompiledArtifact`s with their
   `schema_version` and `spec_hash`, so any reader can re-run
   condition B's solver step without an LLM in the loop.
4. **Raw transcripts.** Full LLM sessions for every
   `(task, condition, model, run)`. Lossless.
5. **Grading.** Per-transcript rubric output, manual-grade samples,
   and disagreements.
6. **Aggregate tables.** Per-cell metric tables and any headline
   summaries. Source data must be derivable from §8.4 and §8.5.
7. **Run manifest.** Solver versions, LLM versions, hardware,
   wall-clock dates, environment hashes.

Reproducibility is cheap because compilation is deterministic; it is
expected.

## 9. Per-pair instantiation checklist

A pair benchmark instantiates the playbook by producing the following
artifacts. Until each item exists and is reviewed, the benchmark is
not ready to run.

### 9.1 Scope document (one page)

- The source language and dialect (e.g., RV64IMC; Python 3.11
  subset).
- The reasoning language and solver inventory in scope (engines and
  versions).
- The question taxonomy: which `Observable` / `Property` shapes the
  benchmark exercises.
- The lowering-sensitive criterion in prose, with two or three
  motivating examples.
- An explicit list of question shapes the pair *cannot* encode (so
  coverage-gap rate is interpretable).

### 9.2 Corpus

- ≥ 30 tasks, balanced across difficulty tiers T1–T4 (§4.2).
- ≥ 20% of tasks tagged as lowering-sensitive (§4.3).
- Each task: `source`, `question` in natural language,
  `expected_verdict`, `witness_shape`, `task_class`, `difficulty`,
  `lowering_sensitive` flag, `oracle_provenance` (which of §4.5's
  four sources established it).
- Pre-registered in a tagged commit before B/C run.

### 9.3 Per-condition prompt templates

- A: source + natural-language question + verdict-and-confidence
  required output schema.
- B: A + tool surface description + `SCHEMA.md` link.
- C: A + solver input language reference + a description of the
  solver's I/O contract.
- D (if used): A + source-verifier invocation guide.

Prompts are committed as files; differences across conditions are
strictly the bullets above.

### 9.4 Source-level baseline

Pick the source-level verifier for condition D. If no credible
verifier exists for the source language, document why D is omitted.

### 9.5 Solver inventory and budgets

- Which engines from the pair's `solvers` mapping are exercised in B.
- Which solver-input language is used in C, and which solver
  consumes it (must be the same engine family as B, ideally the same
  binary).
- Per-task budget caps: bound, timeout, memory.

### 9.6 LLM inventory

At least two LLMs from unrelated families. Versions and inference
parameters (temperature, max tokens, etc.) committed.

### 9.7 Grading rubric

The rubric LLM's prompt and the manual-grading instructions, both
committed before B/C run.

### 9.8 Run manifest template

A schema for §8.7. Filled in at run time; committed with results.

**Pinned oracle/solver inventory (manifest entries).** Every binary the
framework can dispatch to is pinned in the repo-root `Dockerfile`; the image
hash plus these tags uniquely identify the inventory for a run:

| Component | Pin | Dockerfile ARG | Notes |
|---|---|---|---|
| pono | commit `c81aa36…` (v2.0.0) | `PONO_COMMIT` | built from source |
| z3 / bitwuzla / cvc5 (wheels) | 4.16.0.0 / 0.9.1 / 1.3.4 | — | in-process |
| bitwuzla / cvc5 (CLI) | 0.9.1 / cvc5-1.3.4 | `BITWUZLA_TAG`/`CVC5_TAG` | condition C |
| **Sail-RISCV emulator** | **release `0.12`** | **`SAIL_RISCV_TAG`** | `sail_riscv_sim`; v3 `sail-riscv` group oracle |

The Sail layer installs the upstream binary release
`sail-riscv-Linux-{x86_64,aarch64}.tar.gz` (binary `sail_riscv_sim`). The v3
`sail-riscv` group's `reference_rv64.py` is cross-validated against this
emulator (`reference_vs_sail_ok`); see
`v3/semantics/sail-riscv/realizations/btor2-machine/MACHINE_BUILD_LOG.md`. The
Sail layer was validated on Linux (aarch64) in the bench image; record the new
full-image digest here on the next `docker build` of the complete image.

### 9.9 Determinism check script

A small script that, for a sample of compiled artifacts, recompiles
and asserts byte-equality. Run before publication.

### 9.10 Pre-flight verdict consistency check (optional, recommended)

If the pair declares an `interpreter_version` (see `PAIRING.md` §11),
ship a solver-free oracle script that walks the corpus, runs the
framework's `check` tool on each task with a default input binding,
and reports whether the concrete-trace verdict agrees with the
pre-registered `expected_verdict`. The oracle is not a substitute for
§6's grading — its purpose is to flag tasks whose ground-truth label
seems inconsistent with concrete execution, *before* LLM runs are
recorded against them.

For the `riscv-btor2` pair this lives at `bench/riscv-btor2/oracle.py`.
Run it as `python bench/riscv-btor2/oracle.py`; it exits non-zero on
any FAIL row. SKIP rows are permitted (default-input concrete
execution is one input out of many; absence of a violation on the
default binding is inconclusive evidence, not a soundness bug).

### 9.11 Pre-flight framework consistency check (optional, recommended)

A complementary, strictly stronger pre-flight: for every corpus task,
load the pre-registered `spec.json`, drive it through the pair's
`compile` → `dispatch` → `lift` pipeline using each task's pinned
`AnalysisDirective`, and compare the resulting verdict to
`expected_verdict`. Unlike §9.10 (which runs only the source
interpreter), this oracle exercises the full framework end-to-end
without any LLM in the loop, validating translation correctness +
solver inventory adequacy + lift correctness as a single artifact.

This is the benchmark's *condition B0*: B with the LLM removed and
the spec given. It does not measure LLM effectiveness — it gates
whether the bench infrastructure can produce the right answer when
fed a correct spec, before paid LLM runs are charged against the
corpus. Any FAIL flags either a framework regression, a spec
authored against the wrong analysis budget, or a mislabeled
`expected_verdict`.

For the `riscv-btor2` pair this lives at
`bench/riscv-btor2/framework_oracle.py`. Run it as
`python bench/riscv-btor2/framework_oracle.py`; it exits non-zero on
any FAIL row. SKIP rows correspond to solver `unknown`/`error`
returns (timeout, resource limit, spec error) — inconclusive, not a
soundness bug.

### 9.12 Multi-engine cross oracle (optional, recommended)

A strictly-stronger variant of §9.11 that, for every task, dispatches
the same compiled artifact under *every compatible engine* in the
pair's solver inventory and compares the per-engine verdicts both to
`expected_verdict` and to each other.

Two purposes:

1. **§4.5 cross-solver oracle.** Agreement between two unrelated
   solvers is one of the four oracle-establishment methods §4.5 lists.
   The cross oracle exercises that mechanism for every corpus task,
   so each `expected_verdict` is independently witnessed by every
   available engine before any LLM run is charged.
2. **Translation / dispatch / lift bug detection.** Same artifact
   bytes, multiple solvers — a single-engine disagreement that a
   one-engine pre-flight cannot see.

Rolled-up per-task verdicts:

- `CROSS-PASS`     all engines that returned a definitive verdict
                   agreed with the expected verdict.
- `CROSS-MISMATCH` engines returned conflicting definitive verdicts.
- `CROSS-FAIL`     at least one engine contradicted `expected_verdict`.
- `CROSS-SKIPPED`  no engine returned a definitive verdict
                   (all `unknown`/`error`); inconclusive.

Engine selection is by *task class*: BMC tasks are cross-checked
against every BMC engine in the inventory at the pinned bound;
inductive tasks are cross-checked against every engine that can
emit `proved` (e.g., spacer plus pono in k-induction mode).

For the `riscv-btor2` pair this lives at
`bench/riscv-btor2/oracle_cross.py`. Run it as
`python bench/riscv-btor2/oracle_cross.py`; it exits non-zero on any
`CROSS-FAIL` or `CROSS-MISMATCH`. `CROSS-SKIPPED` is permitted —
it's the normal outcome for engines whose binaries / bindings are
absent in the local environment (the bench Docker image carries the
full inventory; a developer machine usually does not).

---

A pair that has produced §9.1 through §9.9 and run §3's conditions
under §7's hygiene rules has a defensible benchmark. A pair that has
not, has a demonstration.
