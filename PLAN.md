# Hurdy-Gurdy v2 — Phase Plan

> The phase plan for the v2 line, now on `main` (the former
> `v2-bootstrap` branch was merged into `main` and deleted). Its
> now-historical bootstrap companions — `V2_BOOTSTRAP.md` (spec),
> `V2_AGENT_LOOP.md` (playbook), `V2_AUDIT.md` (conformance map) — are
> superseded and kept for history (each carries a banner). The earlier v1
> phase plan this replaced is in git history (`git log --follow -- PLAN.md`).
>
> Each phase has:
> - **Goal** — one sentence on what's true when it's done.
> - **Increments** — concrete, PR-sized steps the loop ticks through.
> - **Acceptance** — the test or oracle that must pass.
> - **References** — links to `V2_BOOTSTRAP.md` sections, `V2_AUDIT.md`,
>   and v1 code paths (now in the working tree).
>
> Phases are sequential except where marked `[parallel-ok]`. The
> agent works one increment per iteration (`V2_AGENT_LOOP.md` §2).

## Where this plan changed (iter-7 retrospective)

The original v2 plan (P1–P13) assumed the v1 codebase needed to be
**rebuilt** under the three-pillar foundation order: downgrade
schema to v1.0.0 (RV64I only), then incrementally re-add M, C,
multi-callee, shadow mode, multi-engine, inductive engines. The
P0 audit (iters 2–6) showed this premise was wrong:

- **SCHEMA.md is already at v1.1.0**, byte-compatible with v1.0.0
  for specs that opt out of §14 vocabulary (`V2_AUDIT.md` §P0.4).
- Baseline ISA is **RV64I+M+C**, not RV64I (SCHEMA.md §12 line 341).
- Multi-callee, dispatch layer, shadow mode, FREE bindings,
  BranchPin, CycleInvariant.dual_role, volatile layer — all already
  shipped in v1.
- All five solver adapters (z3-bmc, z3-spacer, bitwuzla, cvc5,
  pono) already wired (`V2_AUDIT.md` §P0.3).
- The §4 alignment-oracle **primitives** exist
  (`gurdy/core/interp/align.py` + `gurdy/pairs/riscv_btor2/lift/
  replayer.py`); only the bench-side per-task wiring is missing
  (filed as **P0.5a** in `V2_AUDIT.md`).

So P1–P13 in the original v2 plan describe work that is already
done. The real remaining v2 work is small and concrete: one
operational gap, plus SV-COMP scale-up and SOTA comparison. The
plan below reflects that.

Old P1–P13 are not deleted because they're worth keeping as a map
of v1's surface area; they're **collected at the bottom of this file
under "Already-shipped (v1 parity verified by P0 audit)"** so future
LLMs see what's covered without re-discovering it.

## P0 — Audit & contracts (alongside v1) ✅

**Status.** Completed iters 2–6.

**What it produced.**

- `V2_BOOTSTRAP.md` — the spec (iter 1).
- `V2_AGENT_LOOP.md` — the playbook (iter 1).
- `V2_PROGRESS.md` — live state (iter 1, appended every iter).
- `PLAN.md` v1 (iter 1) → v2 retrospective (iter 7, this file).
- `pyproject.toml` v2-dev marker (iter 2).
- `V2_AUDIT.md` — conformance map: v1 broadly conforms; **one
  operational gap** (P0.5a) and one **plan-side correction** (P0.5b,
  this iter).

**Acceptance.** v1 tests still pass on this branch (P0.6, not yet
exercised by the loop — defer until P1 introduces a code change
worth re-running tests for).

## P1 — Primary alignment oracle (the §4 contract, operationally)

**Goal.** `bench/riscv-btor2/oracle_align.py` exists and, for every
seed-corpus task, runs the source interpreter and the reasoning
interpreter and reports per-task `align_ok` alongside the existing
`verdict_ok` from `framework_oracle.py`. The §4 contract becomes
operationally true.

**Why this is the only "build" phase in v2.** Every other §3 pillar
contract is already satisfied by v1. The §4 alignment-oracle
machinery exists in framework primitives (`align_traces` +
`replay_witness` + `JoinedTrace`) but is invoked per-witness via
the `replay` tool, not as a bench-side per-task primary check. See
`V2_AUDIT.md` §P0.3, §P0.5a.

**Increments.**

- **P1.1** — Sketch `bench/riscv-btor2/oracle_align.py` as a shell
  matching the shape of the existing `oracle.py` and
  `framework_oracle.py`: argparse, task discovery, per-task
  loop, PASS/SKIP/FAIL output. No alignment logic yet.
- **P1.2** — Wire it to the framework. For each task: load spec
  + ELF, call `compile`, call `dispatch` (engine from the task's
  pre-registered `analysis` directive), capture the raw solver
  result.
- **P1.3** — On `reachable` witness: call `replay_witness` and
  `align_traces` with the pair's `make_projection`. Report
  `align_ok` and any per-step divergence.
- **P1.4** — On `unreachable` / `proved` / `unknown`: report
  `align_ok=N/A` (alignment is meaningless without a concrete
  trajectory). Skip silently; this is not a failure.
- **P1.5** — Tests: a unit-level test in `tests/pairs/riscv_btor2/`
  that constructs a known-aligning task and asserts
  `oracle_align.run_one(task) == AlignOK`. Hand-mutate the BTOR2
  artifact to introduce a one-step divergence; assert the oracle
  reports the divergence step accurately.
- **P1.6** — Run on the current seed corpus (≤ 5 tasks per
  iteration per `V2_AGENT_LOOP.md` §4). Expected outcome: most
  reachable tasks should align cleanly; any failure is a real
  translator-vs-interpreters bug and goes to a **BLOCKER:** with
  diagnosis.

**Acceptance.** Running `python bench/riscv-btor2/oracle_align.py`
returns PASS for every task whose pre-registered `expected.verdict
== reachable` and whose dispatch produces a witness. Coverage
metric: `align_ok` reported on ≥ N tasks where N is the count of
reachable tasks in the seed corpus.

**RAM safety.** ≤ 5 tasks per iteration. `dispatch` calls inherit
the existing harness's timeout + memory cap. No new parallelism.

**References.** `V2_BOOTSTRAP.md` §4. `V2_AUDIT.md` §P0.3, §P0.5a.
`gurdy/pairs/riscv_btor2/lift/replayer.py:replay_witness`.
`gurdy/core/interp/align.py:align_traces`.
`bench/riscv-btor2/oracle.py` and `framework_oracle.py` as
structural references.

## P2 — SV-COMP slice scale-up

**Goal.** The SV-COMP slice in `bench/riscv-btor2/corpus/` (current
v0.5 pilot, 10 tasks) grows to ≥ 50 tasks with reproducible
ingestion + cross-compile, and `framework_oracle.py` +
`oracle_align.py` (P1) run end-to-end on the slice.

**Why this is needed.** A 10-task pilot can't support a Pareto
claim against SOTA. ~50 tasks is the smallest slice where
per-tool wall-time variance averages out enough to read the
Pareto frontier.

**Increments** (each one bounded to ≤ 5 added tasks per iter, RAM
safety):

- **P2.1** — Read `bench/riscv-btor2/CORPUS_V0.5_PLAN.md` for the
  SV-COMP selection criteria. The pilot tasks (`0250`–`0259`) are
  already committed; this increment decides the next batch.
- **P2.2 to P2.6** — Add tasks in 5-task batches via
  `corpus/_svcomp_extract.py`, which vendors one task at a time from
  the `external/sv-benchmarks` submodule per `CORPUS_V0.5_PLAN.md`.
  One batch per iteration.
- **P2.7** — Smoke run of `framework_oracle.py` on the full slice
  with z3-bmc (no parallelism beyond `-j 2`). Record verdict +
  wall time per task.
- **P2.8** — Smoke run of `oracle_align.py` (from P1) on the
  reachable subset. Verify all align cleanly or surface a
  translator bug as a BLOCKER:.

**Acceptance.** ≥ 50 tasks in `bench/riscv-btor2/corpus/`. Both
oracles report a verdict (PASS/SKIP/FAIL) per task. No alignment
failures, or all alignment failures filed as discrete BLOCKERs
with diagnosis.

**RAM safety.** ≤ 5 tasks added per iteration. Cross-compile via
`riscv64-unknown-elf-gcc` with `-j 2` (never parallel beyond that).
Each solver call inherits the harness's memory cap.

**References.** `bench/riscv-btor2/CORPUS_V0.5_PLAN.md`,
`EXTERNAL_BENCHMARKS_SURVEY.md`, `corpus/_svcomp_extract.py`.

## P3 — SOTA baselines

**Goal.** A Pareto table compares hurdy-gurdy against CBMC, ESBMC,
SeaHorn, Symbiotic, and Pono-native on the P2 slice.

**Increments.**

- **P3.1** — Decision: which SOTA tools to run locally vs to
  reference from published numbers. RAM-safety likely forces
  most to be subprocess-invoked single-task with caps, not
  bulk parallel runs.
- **P3.2 → P3.6** — One adapter per tool: subprocess wrapper +
  output parser + uniform schema `(tool, task, verdict, wall_s,
  rss_mb, correct)`.
- **P3.7** — `bench/riscv-btor2/engine_bench.py` (already exists)
  extends to aggregate per-tool totals and emit the Pareto table
  to `V2_PROGRESS.md`.

**Acceptance.** Pareto table exists; per-tool totals are
reproducible from the recorded raw outputs.

**RAM safety.** One tool subprocess at a time, with timeout +
memory cap.

**References.** SOTA tools' documentation, `V2_BOOTSTRAP.md` §5.

## P4+ — Iteration to dominance (steady state)

**Goal.** From here the agent reads the Pareto table each loop
and proposes/lands changes that move hurdy-gurdy's cells toward
the Pareto frontier. **No fixed end.**

**Per-iteration loop** (one of):

- Identify a corpus cell where hurdy-gurdy is dominated;
  hypothesize why (schema gap, spec under-tightness, engine
  choice, abstraction level); design a fix; implement; re-run.
- Extend corpus with a category the current schema handles poorly,
  forcing a refactor.
- Bump schema (semver discipline; minor for additive, major for
  breaking; re-verify all prior corpus tasks).
- Propose a new spec parameter when a single schema rule cannot
  cleanly capture the right choice.

**Stop condition** (`V2_AGENT_LOOP.md` §8): 30 consecutive
iterations of strict Pareto dominance on the SV-COMP slice without
regression. Or: user adds `STOP_LOOP` file. Or: 10 consecutive
iterations of no progress.

---

## Stage 7 — Land the source pairs into the BTOR2 hub

> A second axis, orthogonal to P0–P4+ (which drive the single
> `riscv-btor2` pair to Pareto dominance). Stage 7 continues the
> generalization staging of `DESIGN_pair_taxonomy.md` §11 and
> `DESIGN_generalized_pairs.md` §11 (Stages 1–6 ✅): turn the
> `riscv / aarch64 / wasm / evm / ebpf → BTOR2` star into a *populated*
> hub. The four source pairs live on the `*-btor2-bootstrap` branches;
> this stage merges them onto a shared core.

**Goal.** One shared BTOR2 core in `gurdy/core/btor2/`; the four
bootstrap source pairs landed onto it behind a common pair scaffold; a
cross-check fires between ≥ 2 source pairs through the `btor2-smtlib`
hub bridge.

**Critical ordering.** The core extraction lands on `main` *before* any
branch merge. Merge a branch first and it brings its own BTOR2 core
(evm has a full clone), turning convergence into a 5-way reconciliation.

**Increments** (✅ done · ◻ planned):

- **7.A** ✅ Safety net: green baseline; confirmed the cert re-checkers
  already have non-Docker z3 tests (`test_{,kind_}certificate.py`).
- **7.B** ✅ Extract the BTOR2 **IR** (`nodes/parser/printer/evaluator`,
  759 LOC) to `gurdy/core/btor2/` (commit `29b748b`). `btor2-smtlib`
  now imports core — the core-imports-a-pair inversion is resolved.
  Pure 1:1 import rename across 27 sites; all green.
- **7.C** ◻ Move the z3 compiler (`solvers/_bmc.py`) to core.
  **Deferred** — zero external importers today, so not demand-driven;
  relocate it during the first branch landing whose solvers want a
  shared BMC path (PAIRING.md §15).
- **7.D** ✅ Pair **scaffold** extracted — `gurdy/pairs/PAIR_TEMPLATE.md`
  (the `Pair` field contract + projection-factory pattern + a landing
  checklist), derived from `riscv_btor2/__init__.py`.
- **7.E** ◑ Land the source pairs, one at a time, RAM-safe.
  - ◑ **aarch64** — landed (merge `e0498e4`): rides `core/btor2`, its
    `__init__` modernized to the current `Pair` API, routes
    `aarch64-elf -> btor2`, unit suite green. **Tier-2 follow-up:**
    `source_interp/projection.py` + `predicates.py` are absent, so the
    alignment oracle, the hub cross-check (7.F), and the `check` tool are
    not yet wired.
  - ✅ **wasm** — landed (merge `8f9ddbb`): pair-complete on arrival
    (registers, routes `wasm -> btor2`, has `projection`), fully
    self-contained (own `btor2/` + solver copies, no riscv-internal
    imports), component-level tests — no rename / conftest / `__init__`
    change needed. The cleanest landing.
  - ◻ **evm**, ◻ **ebpf** — **deferred** (2026-06-07): both are P0 scaffold
    stubs — no `register_pair`, and evm has no solver backends. They carry
    translation machinery + component tests but were never wired as pairs
    (authors deferred to "P6+"). Land each once it is pair-complete, or as a
    separate write-the-`Pair` task.
  - **Shared Tier-2 dedup:** wasm (and evm when it lands) keep a private
    `btor2/` clone — a near-copy of `core/btor2` plus small additive
    extensions (e.g. `constarray`, array sorts); aarch64/wasm also carry
    solver copies. Fold every pair's BTOR2 + BMC needs into `core/btor2` in
    one pass, then delete the clones and re-validate riscv (per
    `DESIGN_certificate_module_sharing.md` "do it once, deliberately").
- **7.F** ◻ First hub payoff: generalize `oracle_cross.py` to
  "many paths, one question" (a translator-bug detector); first
  cross-language equivalence (same program in RV64 vs A64, both
  lowered to BTOR2).

**Acceptance.** `gurdy/core/btor2/` is the sole BTOR2 IR; no pair
re-implements it; ≥ 2 source pairs register and a cross-pair check
passes through the hub.

**RAM safety.** One pair's corpus at a time; never materialize multiple
pairs' BTOR2 outputs at once; cap corpus parallelism
(`DESIGN_pair_taxonomy.md` §11).

**References.** `DESIGN_generalized_pairs.md` §7 (the hub),
`DESIGN_certificate_module_sharing.md` (the core extraction),
`DESIGN_pair_taxonomy.md` §11 (staging).

---

## Cross-cutting concerns (every phase touches these)

- **Schema discipline**: any rule that hurdy-gurdy applies but
  isn't in `SCHEMA.md` is a bug. Audit each phase's PR for new
  hidden choices.
- **Determinism**: every translator change has a "twice → same
  bytes" test.
- **Alignment**: every corpus task has an alignment oracle test
  (P1 makes this operational; P2+ exercises it).
- **RAM safety**: `V2_AGENT_LOOP.md` §4 is non-negotiable.
- **Branching**: the `v2-bootstrap` branch was merged into `main` and
  deleted; durable work lands on `main`. The in-progress source pairs
  live on the `*-btor2-bootstrap` branches (Stage 7).

## Open questions deferred until evidence

- Whether `python-smtlib` is the right second pair, or whether a
  different second source language gives faster Pareto signal.
- Whether the alignment oracle needs a "stress mode" with random
  inputs, vs. only the spec's declared inputs.

---

## Appendix — Already-shipped (v1 parity verified by P0 audit)

These phases were in the original v2 plan as "to build". The P0
audit (iters 2–6, see `V2_AUDIT.md`) verified each is already
present in v1 and conforms to the relevant `V2_BOOTSTRAP.md` §3
contract. Listed here so future LLMs don't re-plan them.

- **(was P1) Schema v1.0.0 for `riscv-btor2`** — superseded.
  SCHEMA.md is at v1.1.0; v1.0.0 byte-equivalence is guaranteed for
  §14-opt-out specs (SCHEMA.md line 443–446). No downgrade needed.
- **(was P2) Source interpreter (RV64I)** — already shipped.
  `gurdy/pairs/riscv_btor2/source_interp/`.
- **(was P3) Reasoning interpreter (BTOR2)** — already shipped.
  `gurdy/pairs/riscv_btor2/reasoning_interp/`.
- **(was P4) Translator (RV64I → BTOR2)** — already shipped.
  `gurdy/pairs/riscv_btor2/translation/`.
- **(was P5) Alignment oracle (the contract)** — framework
  primitives shipped (`gurdy/core/interp/align.py`,
  `lift/replayer.py`); bench-side per-task wiring is the **only
  real remaining work** — now P1 in this plan.
- **(was P6) Dispatch + z3-bmc** — already shipped.
  `gurdy/core/dispatch/`, `gurdy/pairs/riscv_btor2/solvers/z3bmc.py`.
- **(was P7) Seed corpus + harness** — already shipped.
  `bench/riscv-btor2/corpus/` + `bench/riscv-btor2/harness.py`.
- **(was P8) Shadow mode + FREE sentinel** — already shipped.
  `source_interp/shadow.py`, `source_interp/bindings.py`. v1.1.0
  schema §14.
- **(was P9) RV64M** — already in v1 baseline. SCHEMA.md §5
  "Multiply / divide (RV64M)" (line 203).
- **(was P10) RV64C** — already in v1 baseline. SCHEMA.md §12
  line 341.
- **(was P11) Multi-callee scope** — already in v1 baseline.
  SCHEMA.md §6 Dispatch.
- **(was P12) Multi-engine adapters** — already shipped. All five
  solvers in `gurdy/pairs/riscv_btor2/solvers/`.
- **(was P13) Inductive engines** — already shipped. z3-spacer +
  pono-ind both in `solvers/`.
- **(was P14) SV-COMP slice ingestion** — pilot v0.5 shipped (10
  tasks); scale-up is **P2** in this plan.
- **(was P15) SOTA baselines** — not yet started; this is **P3**.
- **(was P16+) Iteration to dominance** — this is **P4+**.
