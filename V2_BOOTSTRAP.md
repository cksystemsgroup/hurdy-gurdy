# Hurdy-Gurdy v2 — Bootstrap Specification

> Self-contained brief for a long-running autonomous agent. The agent's
> job is to (re)build hurdy-gurdy from scratch on the `v2-bootstrap`
> branch, following this spec, until the `riscv-btor2` pair beats
> established C/C++ → RISC-V verification tools on standard benchmarks.
>
> A fresh Claude Code session should be able to pick up purely from
> this file + `V2_AGENT_LOOP.md` + `V2_PROGRESS.md`, with no other
> conversation context.

## 1. Thesis

Hurdy-gurdy is a **question compiler**: it deterministically translates
`(QuestionSpec, source program)` into a reasoning artifact for an
external solver, then lifts the verdict back to source-level facts.
*The framework does no reasoning; the LLM does.* See `README.md` and
`PLAN.md` on `main` for the full philosophy — v2 inherits it.

What changes in v2 is the foundation order. The three pillars below
are **load-bearing from commit zero**, not retrofitted as Phase 19/20
additions:

1. **Source interpreter** — a concrete executor of the source language.
2. **Reasoning interpreter** — a concrete executor of the reasoning
   language (BTOR2 simulator + witness replayer).
3. **Translator** — the deterministic compiler from source to reasoning.

The translator's *correctness contract* is interpreter-trace alignment:
for every `(spec, source)` and every concrete input the source
interpreter accepts, the reasoning interpreter (replaying any witness
or driven from the same input) produces an aligned trace on
observables. Translator bugs surface as alignment failures, not as
"the solver said something weird."

This is the only reason v2 can credibly claim to *outperform* SOTA:
SOTA tools cannot prove their translation correct against an
independent oracle of equal expressiveness, because they don't have
one. Hurdy-gurdy v2 does, by construction.

## 2. Why performance scales with LLM performance

The framework is deterministic by design — same `(spec, source)` →
byte-identical artifact, forever. So how does a deterministic system
get better as LLMs improve?

The variable input is the **spec**. The LLM constructs it. Every
choice that other tools bake in as a fixed heuristic, hurdy-gurdy
exposes as a spec parameter:

| Choice                                   | SOTA (fixed)          | Hurdy-gurdy (LLM-chosen per program) |
|------------------------------------------|-----------------------|--------------------------------------|
| Loop unroll depth                        | fixed bound           | `AnalysisDirective.bound`            |
| Which callees to inline                  | fixed inliner pass    | `scope.included_callees`             |
| Abstraction granularity (havoc what?)    | fixed widening        | spec-declared havoc layer            |
| Engine (BMC vs k-ind vs Horn)            | fixed default         | `AnalysisDirective.engine`           |
| Solver (z3, bitwuzla, cvc5, pono)        | fixed binding         | spec selects, cross-oracle records   |
| Property strength (reach / safety / inv) | tool-specific         | `QuestionSpec` shape                 |
| Counterexample → refinement              | tool-internal CEGAR   | LLM re-specs in source-level terms   |

A better LLM produces better specs → fewer false positives, tighter
abstractions, smarter engine choice, faster convergence on hard
programs. The framework's job is to make this loop *cheap and
mechanically faithful*, so the LLM never has to second-guess what
its spec means.

A separate axis: the **autonomous improvement loop** (Section 9) also
runs on the LLM. A better LLM proposes better translator refactors,
better corpus extensions, and better SOTA-comparison analyses per
iteration. Both axes compound.

## 3. The three pillars in detail

### 3.1 Source interpreter (`source_interp/`)

A concrete executor of the source ISA at the same fidelity the
translator claims.

Required capabilities:

- **Run**: `(elf, scope, inputs) → trace` where `trace` is the
  observable sequence (writes to bound output cells, halt, fault).
- **Bindings**: a `Free` sentinel for uninstantiated inputs, accepted
  in shadow mode only (Phase 19 in old plan; here it's a day-1
  capability).
- **Shadow mode**: `record_shadow=True` produces per-instruction
  records of which architectural state cells were read/written and
  with what symbolic-equivalent term-shape (see `SCHEMA.md` §14.6 in
  the old pair). This is the artifact the alignment oracle consumes.
- **Determinism**: same `(elf, scope, inputs)` → same trace, bit for
  bit. No timing, no async, no hidden state.
- **No solver dependency**: the source interpreter must be runnable
  with zero external tools. It is the cheapest possible oracle.

Out of scope at day one (add later, ISA-by-ISA): F/D float, A atomics,
V vector, privileged mode, multi-hart, interrupts.

### 3.2 Reasoning interpreter (`reasoning_interp/`)

A concrete executor of the reasoning language.

For BTOR2 that means:

- **Simulate**: `(btor2_model, input_assignment, k_steps) → trace`.
  Drive `input` nodes from the assignment, step the transition
  system, record observables (the same observables the source
  interpreter records).
- **Replay**: `(btor2_model, witness_btor) → trace`. Consume a
  solver-emitted witness in BTOR2 witness format and replay it.
- **No solver dependency** either. This is independent code from the
  solvers; it is the cross-check on what they tell us.

### 3.3 Translator (`translation/`)

The actual `(spec, source) → btor2_model` compiler. Mechanical, pure,
deterministic. Schema-pinned: any non-trivial choice is either fixed
in `SCHEMA.md` or a spec parameter.

The translator never inspects the source interpreter, never imports
it, never branches on its output. The translator's *test suite* uses
the source interpreter as an oracle, but the translator's *runtime*
does not.

## 4. The interpreter-alignment correctness oracle

For each task in the corpus:

```
trace_src  = source_interp.run(elf, scope, inputs, record_shadow=True)
artifact   = translator.compile(spec, elf, scope)
verdict, witness = dispatch(artifact, spec.engine)

if verdict == "reachable":
    trace_rsn = reasoning_interp.replay(artifact, witness)
    assert align(trace_src_with_same_inputs, trace_rsn).ok
elif verdict == "unreachable" or "proved":
    # cross-check: source_interp with FREE concretized to 0
    # must not reach the bad state within bound k.
    trace_src_concrete = source_interp.run(elf, scope, zero_inputs)
    assert not violates_property(trace_src_concrete, spec.property)
```

This is `bench/riscv-btor2/oracle_align.py` in the new layout. It is
the **primary** correctness oracle. The §4.5 multi-engine cross oracle
(`oracle_cross.py`) is secondary: it catches solver bugs;
`oracle_align.py` catches *translator* bugs.

A SOTA tool cannot offer this oracle because its IR has no independent
interpreter, and its property language has no independent semantics
against the source. Hurdy-gurdy's *raison d'être* is that it does.

## 5. Why this can outperform SOTA on C/C++ → RISC-V benchmarks

The relevant SOTA, on benchmarks where C compiles to RISC-V:

- **CBMC / ESBMC** — direct C BMC, no RISC-V step. Strong on
  pointer-light arithmetic.
- **SeaHorn** — LLVM IR Horn clauses. Strong on inductive loops.
- **Symbiotic** — slicing + multi-engine. Strong on reach properties.
- **Pono (native)** — BTOR2 BMC/k-ind from a hand-written front end.
- **KLEE / angr** — symbolic execution; not strictly verification but
  often compared on bug-finding.

Hurdy-gurdy's edge claims, to be validated empirically:

1. **LLM-curated scope beats fixed unrolling.** SV-COMP timeouts often
   stem from one tool's wrong-grain unroll/abstract decision. An LLM
   that reads the source can pick `bound`, `included_callees`, and
   havoc layer per program.

2. **Multi-engine portfolio + LLM dispatch beats single-engine
   defaults.** Already on `main` for the 4-engine cross-oracle. The
   LLM picks the engine *and* learns from cross-disagreement.

3. **Counterexample-guided refinement in spec space, not in IR
   space.** When BMC returns a false positive (witness fails
   alignment because some havoc was too loose), the LLM tightens the
   spec at the source level. SOTA tools do CEGAR inside the IR — they
   can't see that, e.g., this loop's iteration count is
   programmer-evident from `argc`.

4. **The translator is auditable and improvable.** Every translation
   choice is in `SCHEMA.md`. When the corpus surfaces a category the
   schema handles poorly, the agent (LLM) proposes a schema bump and
   re-verifies all earlier corpus tasks still align. This is faster
   than waiting for a CBMC release.

The goal is **not** a single number. The goal is, on a fixed corpus,
to dominate the Pareto frontier of (solved-true, solved-false,
time-to-verdict, false-positive rate) — with hurdy-gurdy holding
specific cells where other tools time out or mis-classify.

## 6. Repo scaffold (target, from scratch)

```
gurdy/
  core/
    schema.py        # schema-version + layer registry primitives
    spec.py          # QuestionSpec, AnalysisDirective, AnalysisScope
    pair.py          # Pair, PairRegistry, layer linking
    layers.py        # layer hashing + content-addressed cache
    dispatch.py      # solver subprocess driver, witness capture
    interp/
      align.py       # trace-alignment oracle primitives
      types.py       # ObservableEvent, Trace, AlignmentReport
      cache.py
      diagnostics.py
    cli.py           # `gurdy` entry point
  pairs/
    riscv_btor2/
      SCHEMA.md
      __init__.py
      spec.py
      source/                  # ELF loader, instruction decoder
      source_interp/           # RV64IMC concrete executor + shadow
      reasoning_interp/        # BTOR2 simulator + witness replay
      translation/             # the translator
      lift/                    # solver-witness → source-level facts
      solvers/                 # engine adapters (z3, bitwuzla, cvc5, pono)
bench/
  riscv-btor2/
    SCOPE.md
    corpus/
      seed/                    # T0–T3 hand-crafted
      svcomp_slice/            # SV-COMP subset that compiles to RV64
    harness.py
    oracle_align.py            # primary correctness oracle (§4)
    oracle_cross.py            # multi-engine agreement oracle
    engine_bench.py            # SOTA comparison runner
examples/
tests/
  core/
  pairs/riscv_btor2/
PLAN.md                        # v2 phase-by-phase plan (agent writes)
V2_BOOTSTRAP.md                # this file
V2_AGENT_LOOP.md               # iteration playbook
V2_PROGRESS.md                 # mutable state file
README.md
BENCHMARKING.md
PAIRING.md
```

Existing v1 code on `main` is the reference implementation. The agent
**may copy** v1 modules into v2 verbatim where they already conform to
this design — most of `gurdy/core/` and the existing `source_interp/`
+ `reasoning_interp/` likely do. The point of v2 is not novelty; it is
**foundation order**. Anything copied must be re-justified against
this spec, not just imported.

## 7. Phase plan (the agent owns and extends this)

The agent maintains the canonical phase plan in a fresh `PLAN.md`
written on this branch. The bootstrap order below is a starting
sketch; the agent should refine it.

- **P0 — Scaffold & contracts**: directory layout above; `core/schema`,
  `core/pair`, `core/spec` skeletons; package metadata; CI baseline.
- **P1 — Schema v1.0.0 for `riscv-btor2`**: minimal viable —
  RV64I only, no M/C, no callees, single-function `_start`, BMC engine,
  reach-property `QuestionSpec`. SCHEMA.md frozen for this version.
- **P2 — Source interpreter (RV64I)**: ELF loader; integer instructions;
  observable model; *no shadow mode yet*. Unit tests: instruction-level
  golden traces.
- **P3 — Reasoning interpreter (BTOR2)**: BTOR2 parser; transition-system
  simulator; witness-format replay. Unit tests: hand-written BTOR2
  models with known traces.
- **P4 — Translator (RV64I → BTOR2, schema v1.0.0)**: the minimum
  viable translator producing a BTOR2 model that any standard BTOR2
  solver accepts. No optimization yet.
- **P5 — Alignment oracle**: `core/interp/align.py` +
  `bench/riscv-btor2/oracle_align.py`. Define `ObservableEvent` shape;
  implement source/reasoning trace comparison; emit `AlignmentReport`.
- **P6 — Dispatch & solver adapter**: `core/dispatch.py` + one engine
  adapter (z3-bmc) end-to-end. Subprocess, timeout, witness capture.
- **P7 — Seed corpus + harness**: 5–10 hand-crafted tasks
  (`0001-x0-write` through `0008-simple-add`); `bench/harness.py`
  runs them through translator → solver → align oracle.
- **P8 — Shadow mode + `FREE` sentinel**: enables symbolic bindings on
  the source side; aligns havoc semantics across pillars.
- **P9 — RV64M (mul/div/rem)** + **P10 — RV64C compressed**:
  schema bumps `1.0.0 → 1.1.0 → 1.2.0`; per-bump re-verify all
  prior corpus tasks still align.
- **P11 — Multi-callee scope** (`included_callees`): inline boundary
  semantics + self-loop terminator.
- **P12 — Engines bitwuzla / cvc5 / pono**: each as a separate
  subprocess adapter. Run cross-oracle (`oracle_cross.py`).
- **P13 — k-induction via pono-ind + Spacer via z3-spacer**: enables
  `proved` verdicts strictly stronger than BMC `unreachable`.
- **P14 — SV-COMP slice ingestion**: stream files, never recurse-load
  (see RAM-safety in `V2_AGENT_LOOP.md`); compile a small batch to
  RV64; run end-to-end.
- **P15 — SOTA baselines**: CBMC, ESBMC, SeaHorn, Symbiotic, Pono-native
  on the same SV-COMP slice. Record per-task verdicts + times in a
  Pareto table.
- **P16+ — Iteration**: agent reads the Pareto table each loop,
  identifies cells where hurdy-gurdy loses, hypothesizes a fix (schema
  bump, new spec parameter, new engine, abstraction layer), implements,
  re-runs. *This is the steady-state work; it has no end condition
  except "no more wins available with current LLM".*

## 8. Concrete SOTA-comparison benchmark

The agent's claim of "outperforming SOTA" must be cashed out as a
specific number on a specific corpus.

**Initial target corpus**: SV-COMP `c/` track tasks where the harness
can produce an RV64 ELF (subset of `ReachSafety-Loops`,
`NoOverflows-Main`, `MemSafety-Arrays` filtered to integer-only,
no-floats, no-FS, no-network, fits in 4MiB RAM at runtime).

**Metrics**, per task:

- `verdict` ∈ {true, false, unknown, error}
- `wall_seconds` (timeout default: 300s)
- `peak_rss_mb`
- `ground_truth` (from SV-COMP `.yml`)
- `correct` = (verdict == ground_truth) for non-unknown

**Per-tool aggregates**: solved, correct, false-positive count,
false-negative count, total time, geomean time on commonly-solved.

**Pareto criterion**: hurdy-gurdy wins overall if there is no SOTA
tool with strictly better (correct, total_time) at the same or lower
false-positive rate.

The agent **does not declare victory** by single-task wins. The
ratchet is the Pareto table.

## 9. The autonomous improvement loop

Each iteration of the long-running agent does **one** of:

1. **Advance the phase plan** by one increment (e.g., implement P3
   step, commit, mark P3 in-progress → done).
2. **Run the harness** on the current corpus and update the Pareto
   table.
3. **Diagnose an alignment failure** (translator bug): bisect to the
   instruction or schema rule, propose a schema or translator change,
   implement, re-verify all prior tasks.
4. **Diagnose a cross-oracle disagreement** (engine bug or spec-bug):
   localize, file a per-engine note, decide whether to pin/escalate.
5. **Extend the corpus** by one batch (≤ 5 tasks; RAM-safe; the
   batch must be reproducible from a recipe checked into `bench/`).
6. **Propose a SOTA-comparison experiment**: pick N tasks where
   hurdy-gurdy currently times out or mis-classifies; design a
   targeted schema/spec change; run the comparison.

The agent picks among 1–6 by reading `V2_PROGRESS.md` and applying
the decision procedure in `V2_AGENT_LOOP.md`.

Every iteration ends with a commit on `v2-bootstrap` and a
`V2_PROGRESS.md` update. **No iteration may run the full SV-COMP
slice or any unbounded sweep.** RAM caps are in `V2_AGENT_LOOP.md` §4.

## 10. Stop / escalation conditions

The loop pauses and writes a `BLOCKER:` line in `V2_PROGRESS.md`
when:

- A schema change is needed that would break >25% of existing corpus
  tasks. (User decision: bump major or back off.)
- An alignment failure cannot be localized within a single iteration's
  budget and re-occurs after one fix attempt.
- The total corpus size or RSS approaches the caps in §4 of the
  playbook.
- The agent has run 10 consecutive iterations without measurable
  Pareto progress (no new wins, no new corpus tasks correctly
  solved, no closed schema gaps). This forces a strategy rethink
  rather than thrash.
- Any destructive operation is needed (force-push, history rewrite,
  dependency removal). The loop never does these autonomously.

## 11. What the agent is and is not authorized to do

**Authorized:**

- Create, edit, delete files on `v2-bootstrap`.
- Commit to `v2-bootstrap`.
- Install Python packages into a local venv at `.venv-v2/` (never
  global, never system).
- Run tests, run the harness on ≤ 5 corpus tasks per iteration.
- Spawn subprocesses with bounded timeout and memory caps.

**Not authorized:**

- Touching `main` branch in any way.
- Force-pushing, history rewrite, deleting branches.
- Pushing to `origin` (push only when user invokes it).
- Installing system packages, Docker images, or solvers globally.
- Running anything in parallel beyond `-j 2`.
- Cloning multi-GB corpora (SV-COMP full repo is forbidden; use the
  streaming recipe in `V2_AGENT_LOOP.md` §4).

## 12. Relationship to v1 on `main`

`main` is the working v1 reference. v2 is a parallel reset; the agent
**may inspect** v1 freely (`git show main:path`) and **may copy** code
that meets v2's contracts. The goal is not to break v1 nor to depend
on it. Once v2 demonstrates Pareto dominance on the SV-COMP slice for
30 consecutive iterations without regressions, the user will decide
whether to fast-forward `main` to `v2-bootstrap` or merge selectively.

The agent does not make that decision.
