# Hurdy-Gurdy v2 — Phase Plan

> The agent's working phase plan for the `v2-bootstrap` branch.
> Companion to `V2_BOOTSTRAP.md` (the spec) and `V2_AGENT_LOOP.md`
> (the per-iteration playbook). The v1 phase plan is preserved on
> the `main` branch as `PLAN.md` there.
>
> Each phase below has:
> - **Goal** — one sentence on what's true when it's done.
> - **Increments** — concrete, PR-sized steps the loop ticks through.
> - **Acceptance** — the test or oracle that must pass.
> - **References** — links to `V2_BOOTSTRAP.md` sections and to v1
>   code on `main` that may be inspected / copied
>   (`git show main:<path>`).
>
> Phases are sequential except where marked `[parallel-ok]`. The
> agent works one increment per iteration (`V2_AGENT_LOOP.md` §2).

## P0 — Audit & contracts (alongside v1)

**Important.** `v2-bootstrap` was branched from `main` and still
carries the full v1 implementation. v2 builds **alongside** v1 on
this branch (per `V2_BOOTSTRAP.md` §12 and the iter-2
`V2_PROGRESS.md` instruction). The `V2_BOOTSTRAP.md` §6 layout
sketch is the **logical** target; where v1 already occupies a
name, v2 modifies in place rather than shadowing.

**Goal.** Every contract in `V2_BOOTSTRAP.md` §3 (the three pillars
+ alignment oracle) is either satisfied by the current v1 public
surface or has an explicit, increment-sized gap recorded.

**Increments.**

- P0.1 — `pyproject.toml` updated for v2 dev marker + solver
  extras. ✅ (done in iter-2.)
- P0.2 — Audit v1's `gurdy/core/{schema,spec,pair}` and
  `gurdy/core/interp/` against the §3 contracts. Output: a single
  `V2_AUDIT.md` mapping each contract to (a) "v1 conforms" or (b)
  "v1 gap → sub-increment P0.2X". Do not edit any code in this
  increment; this is a read-only audit.
- P0.3 — Audit v1's `gurdy/pairs/riscv_btor2/{source_interp,
  reasoning_interp,translation,solvers,lift}/` against the §3
  contracts. Same output format: append a §"riscv-btor2 pair" to
  `V2_AUDIT.md`.
- P0.4 — Audit v1's `gurdy/pairs/riscv_btor2/SCHEMA.md` against
  the v2 v1.0.0 target (RV64I only). Append §"schema audit"; list
  fields/sections that exceed v1.0.0 scope (BranchPin,
  CycleInvariant dual_role, volatile layer, M, C, multi-callee).
- P0.5 — For each gap surfaced in P0.2–P0.4, file a sub-increment
  in this PLAN.md (renumbered as P0.2a, P0.2b, …) with concrete
  acceptance criteria. **Do not** start implementing gaps in this
  increment.
- P0.6 — Acceptance test: `python -m pytest tests/ -q` from v1
  still passes on this branch. v2 hasn't broken anything yet
  because v2 hasn't touched code. This is the green baseline that
  every later phase must preserve.

**Acceptance.** `V2_AUDIT.md` exists, covers all §3 contracts,
and every recorded gap has a sub-increment ID. v1 tests pass
unchanged.

**References.** `V2_BOOTSTRAP.md` §3, §6, §12. `git show
main:gurdy/core/...` for v1 contract shapes. The audit reads only;
no copy yet.

## P1 — Schema v1.0.0 for `riscv-btor2`

**Goal.** `gurdy/pairs/riscv_btor2/SCHEMA.md` defines exactly what
the **minimum viable** translator must implement: RV64I only, no M,
no C, no callees, single-function `_start`, BMC, reach-property
`QuestionSpec` only.

**Increments.**

- P1.1 — SCHEMA.md §1–§3: source-language scope, reasoning-language
  scope, observable model.
- P1.2 — SCHEMA.md §4–§6: layer registry (header, machine, init,
  bad), layer hashing rules, dispatch layer absent at v1.0.0.
- P1.3 — SCHEMA.md §7–§9: term shape, control-flow boundary, halt
  modeling.
- P1.4 — SCHEMA.md §10–§12: solver-witness format, lift rules,
  determinism statement.

**Acceptance.** A second reader (human or LLM) given only this
SCHEMA.md and a tiny RV64I program can predict the BTOR2 output
modulo node numbering. Tested by a `tests/pairs/riscv_btor2/
test_schema_predict.py` that round-trips one hand-written task.

**References.** `main:gurdy/pairs/riscv_btor2/SCHEMA.md` (v1.1.0
on `main`) — copy the structure, downgrade scope to v1.0.0.

## P2 — Source interpreter (RV64I, no shadow)

**Goal.** `RiscvSourceInterpreter` runs an RV64I ELF deterministically
and emits an observable `Trace`.

**Increments.**

- P2.1 — ELF loader: parse RV64 ELF headers, extract code+data,
  resolve `_start`. (No DWARF needed yet.)
- P2.2 — Decoder: RV32I + RV64I integer instructions; reject
  anything else with a clear error.
- P2.3 — State machine: register file, memory model (byte-addressed,
  little-endian, bounded heap), PC.
- P2.4 — Observable model: writes to specified output cells, halt,
  fault — emit one `ObservableEvent` per occurrence.
- P2.5 — `run(elf, scope, inputs) -> Trace`. No shadow yet.
- P2.6 — Tests: per-instruction goldens for ~20 representative
  instructions; one end-to-end "0001-x0-write" task.

**Acceptance.** Goldens pass; end-to-end task produces a reproducible
trace.

**References.** `main:gurdy/pairs/riscv_btor2/source_interp/
interpreter.py` — likely copy with minor edits to match v2 trace
types.

## P3 — Reasoning interpreter (BTOR2)

**Goal.** `Btor2ReasoningInterpreter` simulates a BTOR2 model and
replays BTOR2 witnesses.

**Increments.**

- P3.1 — BTOR2 parser: nodes (`sort`, `input`, `state`, `next`,
  `init`, `bad`, `constraint`, `output`, all bitvector ops). Reject
  arrays at first.
- P3.2 — Transition simulator: drive `input` from an assignment,
  step `state` per `next`, evaluate `bad`/`constraint`. Returns an
  observable trace shaped identically to the source interpreter's.
- P3.3 — Witness replayer: parse BTOR2 witness format, feed inputs
  step-by-step, emit the trace.
- P3.4 — Tests: 3–5 hand-written BTOR2 models with hand-derived
  traces; the simulator must match.

**Acceptance.** Hand-written models replay correctly; round-trip
test of (model, witness) → trace is stable.

**References.** `main:gurdy/pairs/riscv_btor2/reasoning_interp/
interpreter.py` — likely copy.

## P4 — Translator (RV64I → BTOR2, schema v1.0.0)

**Goal.** `translate(spec, elf, scope) -> Btor2Model` emits a BTOR2
artifact valid against schema v1.0.0 for any RV64I single-function
program.

**Increments.**

- P4.1 — `builder.py`: BTOR2 sort/node builder primitives.
- P4.2 — `exprs.py`: integer-op expression translation (ADD, SUB,
  SLL, etc.) RV64I → BTOR2 bitvector ops.
- P4.3 — `layers.py`: build header / machine / init / bad layers.
  No dispatch layer at v1.0.0 (single-function, fall-through PC).
- P4.4 — `translate.py`: orchestrator. Returns a `Btor2Model` with
  layer pointers.
- P4.5 — Determinism test: same `(spec, elf, scope)` twice → byte
  identical output.

**Acceptance.** Translator runs without crashing on the seed
program from P2.6; output parses cleanly via P3's BTOR2 parser.

**References.** `main:gurdy/pairs/riscv_btor2/translation/` —
the whole module is a strong starting point; review for v1.0.0
scope-down.

## P5 — Alignment oracle (the contract)

**Goal.** `oracle_align.py` enforces `V2_BOOTSTRAP.md` §4: for any
seed task, source trace and reasoning trace agree on observables.

**Increments.**

- P5.1 — `core/interp/align.py`: implement `align(trace_src,
  trace_rsn)` returning `AlignmentReport(ok: bool, diff: list)`.
- P5.2 — `bench/riscv-btor2/oracle_align.py`: per-task driver —
  run source interp, run translator + reasoning interp on zero
  inputs, align.
- P5.3 — Tests: synthetic mis-aligned pair → reports `ok=False`
  with localized diff.

**Acceptance.** Oracle passes on the seed task; fails noisily on a
manually mutated translator output.

## P6 — Dispatch + z3-bmc adapter

**Goal.** A BTOR2 model goes through a real solver and a verdict
comes back.

**Increments.**

- P6.1 — `core/dispatch.py`: subprocess driver with timeout, memory
  cap, capped output capture (see `V2_AGENT_LOOP.md` §4).
- P6.2 — `gurdy/pairs/riscv_btor2/solvers/z3_bmc.py`: adapter that
  invokes z3 in BMC mode on a BTOR2 model.
- P6.3 — Verdict capture: `reachable | unreachable | unknown |
  error`, plus witness if `reachable`.
- P6.4 — Tests: a known-reachable model returns `reachable` + a
  witness that P3 can replay.

**Acceptance.** End-to-end: seed task → translator → z3 → verdict
→ alignment oracle holds.

**References.** `main:gurdy/pairs/riscv_btor2/solvers/` — pick z3
adapter only at v1.0.0.

## P7 — Seed corpus + harness

**Goal.** `bench/riscv-btor2/corpus/seed/` holds 5–10 hand-crafted
tasks; `harness.py` runs them.

**Increments.**

- P7.1 — Tasks `0001-x0-write`, `0002-immediate-load`,
  `0003-add-loop`, `0004-branch-eq`, `0005-overflow-detect`. Each
  is `{name}.S` (assembly) + `{name}.yml` (spec + ground truth).
- P7.2 — `harness.py`: iterates the seed dir, runs translator →
  z3 → align oracle, prints a per-task verdict table.
- P7.3 — Tests: harness on `0001` returns `correct=True`.

**Acceptance.** All seed tasks run end-to-end; alignment oracle
holds on all of them.

## P8 — Shadow mode + `FREE` sentinel `[parallel-ok with P7]`

**Goal.** The source interpreter can run with symbolic-equivalent
bindings, matching havoc semantics in BTOR2.

**Increments.**

- P8.1 — `source_interp/bindings.py`: `Free` class, `FREE` sentinel.
- P8.2 — `source_interp/shadow.py`: `BranchEvent`, per-instruction
  shadow records, term-shape encoding.
- P8.3 — `RiscvSourceInterpreter.run(record_shadow=True)`: emits
  shadow events into the trace.
- P8.4 — Alignment oracle extends to compare shadow events against
  BTOR2 state-update events.

**Acceptance.** A program with a `FREE` input aligns under shadow
mode where it could not under concrete-only mode.

**References.** `main:gurdy/pairs/riscv_btor2/source_interp/
{bindings,shadow}.py` — copy, retrofit to v2 trace types.

## P9 — RV64M (mul/div/rem)

**Goal.** Schema v1.0.0 → v1.1.0; corpus tasks with multiplication
align.

**Increments.**

- P9.1 — Decoder + interpreter: M instructions.
- P9.2 — Translator: M instruction → BTOR2 bitvector ops.
- P9.3 — SCHEMA.md bump to v1.1.0 with M extension scope.
- P9.4 — One new corpus task `0006-mul-overflow`.
- P9.5 — Re-run align oracle on P1–P8 corpus: no regressions.

**Acceptance.** All prior tasks still align; new task aligns.

## P10 — RV64C (compressed)

Same shape as P9. Schema bump v1.1.0 → v1.2.0. Adds tasks that use
compressed instructions.

## P11 — Multi-callee scope (`included_callees`)

**Goal.** The translator emits a dispatch layer for multi-function
programs per the v1 SCHEMA's §6 self-loop terminator semantics.

**Increments.**

- P11.1 — Spec extension: `AnalysisScope.included_callees`.
- P11.2 — Translator: dispatch layer (PC-indexed ITE).
- P11.3 — Self-loop terminator for excluded callees.
- P11.4 — Corpus tasks `0007-call-add`, `0008-nested-call`,
  `0009-call-excluded`.

**Acceptance.** Multi-function tasks align under both shadow and
concrete modes.

## P12 — Multi-engine adapters

**Goal.** bitwuzla, cvc5, pono adapters exist alongside z3-bmc.

**Increments.**

- P12.1 — `solvers/bitwuzla.py`.
- P12.2 — `solvers/cvc5.py`.
- P12.3 — `solvers/pono.py` (BMC mode).
- P12.4 — `oracle_cross.py`: cross-engine agreement matrix on the
  current corpus.

**Acceptance.** Each adapter returns a verdict on the seed corpus;
the cross-oracle reports disagreement-free runs (or surfaces a
real disagreement worth diagnosing).

## P13 — Inductive engines

**Goal.** k-induction (pono-ind) and Spacer (z3-spacer) can prove
properties that BMC can only bound.

**Increments.**

- P13.1 — `solvers/pono_ind.py`.
- P13.2 — `solvers/z3_spacer.py`.
- P13.3 — `AnalysisDirective` accepts `engine ∈ {bmc, ind, horn}`.
- P13.4 — Corpus extension: one provable-only-with-induction task.

**Acceptance.** Inductive task returns `proved` from pono-ind and
z3-spacer; BMC returns `unreachable` with finite bound but cannot
prove.

## P14 — SV-COMP slice ingestion

**Goal.** A streaming pipeline materializes 25–50 SV-COMP `c/`
tasks as RV64 ELFs in `bench/riscv-btor2/corpus/svcomp_slice/`.

**Increments.**

- P14.1 — `corpus/_svcomp_stream.py`: fetch *one* file at a time
  by exact GitHub raw URL from a whitelist. No bulk clone.
- P14.2 — Whitelist construction: pick 50 tasks from
  `ReachSafety-Loops`, `NoOverflows-Main`, `MemSafety-Arrays`,
  filtered to integer-only / no-floats / no-FS.
- P14.3 — Cross-compile recipe: `riscv64-unknown-elf-gcc` with
  fixed flags; reproducible from a Makefile-style step file.
- P14.4 — Per-task `.yml` derived from SV-COMP metadata.
- P14.5 — Harness runs over the slice with the RAM-safety caps
  from `V2_AGENT_LOOP.md` §4.

**Acceptance.** Slice runs end-to-end. *No need* for all to pass —
we record failures and analyze.

## P15 — SOTA baselines

**Goal.** A Pareto table compares hurdy-gurdy against CBMC, ESBMC,
SeaHorn, Symbiotic, Pono-native on the same slice.

**Increments.**

- P15.1 — Baseline runners: one subprocess wrapper per tool.
- P15.2 — Uniform output schema: (tool, task, verdict, wall_s,
  rss_mb, correct).
- P15.3 — `engine_bench.py` aggregator: per-tool totals + Pareto
  table.
- P15.4 — First Pareto snapshot in `V2_PROGRESS.md`.

**Acceptance.** Pareto table exists; per-tool totals are
reproducible from the recorded outputs.

## P16+ — Iteration to dominance

**Goal.** From here the agent reads the Pareto table each loop and
proposes/lands changes that move hurdy-gurdy's cells toward the
Pareto frontier. No fixed end.

**Per-iteration loop** (one of):

- Identify a corpus cell where hurdy-gurdy is dominated; hypothesize
  why (schema gap, spec under-tightness, engine choice, abstraction
  level); design a fix; implement; re-run.
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

## Cross-cutting concerns (every phase touches these)

- **Schema discipline**: any rule that hurdy-gurdy applies but
  isn't in `SCHEMA.md` is a bug. Audit each phase's PR for new
  hidden choices.
- **Determinism**: every translator change has a "twice → same
  bytes" test.
- **Alignment**: every corpus task has an alignment oracle test.
- **RAM safety**: `V2_AGENT_LOOP.md` §4 is non-negotiable.
- **No `main` edits**: ever. Only `v2-bootstrap`.

## Open questions deferred until evidence

These are deliberately *not* answered now. The loop should not try
to settle them speculatively; let the corpus tell us.

- Whether an IR will eventually be needed across pairs. (`main`'s
  PLAN.md argues no; v2 inherits that until evidence appears.)
- Whether `python-smtlib` is the right second pair, or whether a
  different second source language gives faster Pareto signal.
- Whether the alignment oracle needs a "stress mode" with random
  inputs, vs. only the spec's declared inputs.
- Whether translator caching (layer reuse) belongs in v1.0.0 or
  later. Default: later — it's a perf optimization, not a
  contract.
