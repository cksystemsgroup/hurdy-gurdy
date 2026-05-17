# Hurdy-Gurdy — `wasm-btor2` Pair Bootstrap

> Self-contained brief for a long-running autonomous agent. The agent's
> job is to build the `wasm-btor2` pair from scratch on the
> `wasm-btor2-bootstrap` branch, following this spec, until the pair
> beats established WebAssembly verification tools on standard
> benchmarks.
>
> A fresh Claude Code session should be able to pick up purely from
> this file + `V2_AGENT_LOOP.md` + `V2_PROGRESS.md`, with no other
> conversation context. The reference `riscv-btor2` pair lives on
> branch `v2-bootstrap` (and at `gurdy/pairs/riscv_btor2/` on that
> branch); inspect it freely.

## 1. Thesis

Hurdy-gurdy is a **question compiler**: it deterministically translates
`(QuestionSpec, source program)` into a reasoning artifact for an
external solver, then lifts the verdict back to source-level facts.
*The framework does no reasoning; the LLM does.* See `README.md` and
`PLAN.md` on `main` for the full philosophy — the `wasm-btor2` pair
inherits it.

This pair's **wedge thesis**: WebAssembly has a **fully formal,
deterministic, UB-free specification** (W3C WASM Core 2.0, formalized
in Coq/Isabelle/K). Verifiers that reason at the original source
level (Rust, C, AssemblyScript, Go, Swift) inherit *source-language*
undefined behavior — signed overflow, uninitialized reads, alignment
assumptions, sequence-point hazards — that the WASM lowering
silently eliminates or makes deterministic. Reasoning at the WASM
level is **strictly more sound** for the class of programs whose
properties depend on behavior the source language leaves undefined
but WASM defines.

The three pillars, load-bearing from commit zero:

1. **Source interpreter** (`source_interp/`) — a concrete executor of
   WASM modules. Stack machine + linear memory + function tables.
2. **Reasoning interpreter** (`reasoning_interp/`) — a concrete
   executor of the reasoning language (BTOR2 simulator + witness
   replayer). Reusable from the `v2-bootstrap` branch.
3. **Translator** (`translation/`) — the deterministic compiler from
   WASM module + scope to BTOR2.

The translator's *correctness contract* is interpreter-trace
alignment: for every `(spec, wasm_module)` and every concrete input
the source interpreter accepts, the reasoning interpreter (replaying
any witness or driven from the same input) produces an aligned trace
on observables.

## 2. Why this can outperform SOTA

Existing WebAssembly verification:

- **Manticore-WASM** — symbolic execution; mature on bug-finding,
  weaker on proof. Last release 2023.
- **KLEE-WASM** — research prototype, ad-hoc memory model.
- **Wasabi** — instrumentation, not verification; useful for
  property monitors but no soundness guarantee.
- **Crucible-WASM (Galois)** — symbolic execution + SMT; closed
  ecosystem.
- **wasmtime + cranelift-fuzz / wasm-smith** — fuzzing, not proof.

None of the above offer interpreter-trace alignment as a translator
correctness oracle. None expose unrolling / abstraction / engine
selection as LLM-curatable spec parameters.

Hurdy-gurdy's edge claims, to validate empirically:

1. **C/Rust → WASM modules whose properties hinge on source-level
   UB are sound under WASM-level reasoning, unsound under
   source-level reasoning.** This is the direct analogue of the
   riscv-btor2 wedge cluster (5/5 on C-UB-but-RV64-defined). The
   WASM analogue is bigger because WASM is the actual deployment
   format, not an intermediate.

2. **LLM-curated unrolling beats default-bound BMC** on small WASM
   modules with evident trip counts in the source.

3. **Multi-engine portfolio** — z3-bmc, bitwuzla, cvc5, pono — with
   LLM-dispatched selection beats single-engine defaults.

4. **Counterexample-guided refinement in spec space.** When BMC
   returns a false positive (witness fails alignment because some
   havoc was too loose), the LLM tightens the spec at the WASM level
   — e.g., narrowing a `Free` import binding to a concrete range.

## 3. The three pillars in detail

### 3.1 Source interpreter (`gurdy/pairs/wasm_btor2/source_interp/`)

A concrete executor of the WASM 2.0 core ISA at the same fidelity
the translator claims.

Required capabilities:

- **Run**: `(module_bytes, scope, inputs) → trace`.
- **Bindings**: a `Free` sentinel for uninstantiated imports
  (host function calls, table imports, memory imports).
- **Shadow mode**: per-instruction records of which stack slots /
  locals / memory cells were read/written, for the alignment oracle.
- **Determinism**: same `(module, scope, inputs)` → same trace.
- **No solver dependency**.

Out of scope at day one (add later, feature-by-feature):
- SIMD (`v128`) — large opcode surface, defer.
- Threads / atomics — concurrency outside scope until P14+.
- Reference types beyond `funcref` — defer.
- Exception handling proposal — defer.
- GC proposal — defer.
- WASI host calls — model as `Free` imports initially; later P15
  may model specific WASI fds as bv-arrays.

### 3.2 Reasoning interpreter (`gurdy/pairs/wasm_btor2/reasoning_interp/`)

A concrete executor of BTOR2. **Reuse the riscv-btor2 implementation
verbatim** unless the WASM translator produces BTOR2 nodes the
existing simulator doesn't handle. The reasoning interpreter is
pair-agnostic by design (BTOR2 is BTOR2).

The expected reuse path: `gurdy.pairs.riscv_btor2.reasoning_interp`
is importable; either depend on it or copy it under the wasm pair
and tag the copy with `INTERPRETER_VERSION` so divergence is
audit-traceable.

### 3.3 Translator (`gurdy/pairs/wasm_btor2/translation/`)

The `(spec, wasm_module) → btor2_model` compiler. Mechanical, pure,
deterministic. Schema-pinned: any non-trivial choice is either fixed
in `SCHEMA.md` or a spec parameter.

Translator topology:

- **header**: BTOR2 sort declarations (`bv1`, `bv32`, `bv64`,
  array sorts for linear memory and tables).
- **machine**: state-variable declarations — value stack
  (abstracted as a finite array or per-step explicit unroll),
  locals, globals, linear memory, function tables, PC (function
  index + offset), trap flag.
- **library**: per-instruction lowering definitions. Each WASM
  opcode becomes a parameterized lowering keyed on the operand
  types.
- **dispatch**: PC-keyed ITE selecting which library lowering
  applies at each step.
- **init**: initial state (linear memory data segments, table
  element segments, globals from initializers, locals zeroed).
- **constraint**: invariants and assumptions; carries provenance.
- **bad**: property under investigation.
- **binding**: next clauses wiring states to dispatch.

Schema version begins at `1.0.0`. Bumps follow the riscv-btor2
pattern: minor for additive features, major for breaking property
shape.

## 4. The interpreter-alignment correctness oracle

For each task:

```
trace_src  = source_interp.run(module, scope, inputs, record_shadow=True)
artifact   = translator.compile(spec, module, scope)
verdict, witness = dispatch(artifact, spec.engine)

if verdict == "reachable":
    trace_rsn = reasoning_interp.replay(artifact, witness)
    assert align(trace_src_with_same_inputs, trace_rsn).ok
elif verdict in {"unreachable", "proved"}:
    trace_src_concrete = source_interp.run(module, scope, zero_inputs)
    assert not violates_property(trace_src_concrete, spec.property)
```

This is `bench/wasm-btor2/oracle_align.py`. It is the **primary**
correctness oracle. The §4.5 multi-engine cross oracle
(`oracle_cross.py`) is secondary.

## 5. Repo scaffold (logical target)

```
gurdy/
  pairs/
    wasm_btor2/
      SCHEMA.md
      __init__.py
      spec.py
      source/                  # WASM module loader, instruction decoder
      source_interp/           # WASM concrete executor + shadow
      reasoning_interp/        # BTOR2 simulator (reused from riscv-btor2)
      translation/             # the translator
      lift/                    # witness → source-level facts
      solvers/                 # engine adapters (z3, bitwuzla, cvc5, pono)
bench/
  wasm-btor2/
    SCOPE.md
    corpus/
      seed/                    # hand-crafted T0–T3
      external/                # curated WASM modules from public repos
    harness.py
    oracle_align.py
    oracle_cross.py
    engine_bench.py
    baselines/
      manticore_wasm.py
      hurdy_gurdy.py
      pareto.py
tests/
  pairs/wasm_btor2/
V2_BOOTSTRAP.md                # this file
V2_AGENT_LOOP.md
V2_PROGRESS.md
```

Existing `riscv-btor2` code on the `v2-bootstrap` branch is reference;
the agent **may copy** modules (especially `core/`, `reasoning_interp/`,
dispatch infrastructure) where they already conform.

## 6. Phase plan (the agent owns and extends this)

- **P0 — Scaffold & contracts**: directory layout above; package
  metadata; CI baseline; copy `gurdy/core/` from `v2-bootstrap`.
- **P1 — Schema v1.0.0 for `wasm-btor2`**: minimal viable — WASM
  1.0 MVP only (no SIMD, no threads, no reference types beyond
  funcref); single-function entry; BMC engine; reach-property
  `QuestionSpec`. SCHEMA.md frozen.
- **P2 — Source interpreter (WASM MVP)**: module decoder; stack
  machine; integer + control + memory + call instructions; trap
  semantics. Unit tests against the W3C WASM conformance suite
  (handpicked integer/control subset).
- **P3 — Reasoning interpreter (BTOR2)**: port from `v2-bootstrap`.
- **P4 — Translator (WASM MVP → BTOR2)**: minimum viable translator.
- **P5 — Alignment oracle**: `bench/wasm-btor2/oracle_align.py`.
- **P6 — Dispatch & solver adapter**: z3-bmc end-to-end.
- **P7 — Seed corpus + harness**: 5–10 hand-crafted tasks targeting
  the wedge class — Rust/C source patterns that lower to defined
  WASM but are UB at source level. Example seeds:
  - `0001-i32-add-wrap` — signed overflow in C, wraps in WASM.
  - `0002-div-trap` — div-by-zero traps in WASM (defined).
  - `0003-bounds-trap` — out-of-bounds memory access traps.
  - `0004-shift-amount-mask` — shift count masked mod 32/64.
  - `0005-trunc-saturating` — `i32.trunc_sat_f32_s` defined behavior.
- **P8 — Shadow mode + `FREE` sentinel** for imports.
- **P9 — Multi-engine cross oracle**: bitwuzla, cvc5, pono adapters.
- **P10 — k-induction + Spacer**: enables `proved` verdicts.
- **P11 — External corpus**: stream small Rust→WASM modules from
  public source (e.g., `rust-lang/rust` snippets compiled to
  `wasm32-unknown-unknown`). Streaming recipe per
  `V2_AGENT_LOOP.md` §4 — never bulk-clone.
- **P12 — SOTA baselines**: Manticore-WASM, KLEE-WASM, Wasabi
  (instrumentation comparison only) on the same corpus. Record
  Pareto table.
- **P13+ — Iteration**: Pareto-driven schema/spec/translator
  refinements.

## 7. Concrete SOTA-comparison benchmark

**Initial target corpus**: 20–30 hand-crafted WASM modules paired
with the source program they were compiled from, where the property
is `reach(trap)` or `reach(host-call-with-specific-arg)`. The
wedge subset is modules where the *source-level* UB and the WASM
semantics diverge.

**Metrics per task**: `verdict ∈ {true, false, unknown, error}`,
`wall_seconds`, `peak_rss_mb`, `ground_truth`, `correct`,
`false_positive`.

**Pareto criterion**: hurdy-gurdy wins overall if there is no SOTA
tool with strictly better (correct, total_time) at the same or
lower false-positive rate.

## 8. Stop / escalation conditions

The loop pauses and writes a `BLOCKER:` line in `V2_PROGRESS.md`
when:

- A schema change is needed that would break > 25% of existing
  corpus tasks.
- An alignment failure cannot be localized within one iteration's
  budget and re-occurs after one fix attempt.
- RAM caps in `V2_AGENT_LOOP.md` §4 would be exceeded.
- 10 consecutive iterations without measurable Pareto progress.
- Any destructive operation is needed.

## 9. What the agent is and is not authorized to do

**Authorized:**

- Create, edit, delete files on `wasm-btor2-bootstrap`.
- Commit and push to `wasm-btor2-bootstrap` on origin.
- Install Python packages into a local venv at `.venv-wasm/`.
- Run tests, run the harness on ≤ 5 corpus tasks per iteration.
- Spawn subprocesses with bounded timeout (60s default) and memory
  caps (2 GiB).

**Not authorized:**

- Touching `main`, `v2-bootstrap`, or any other pair's branch.
- Force-pushing, history rewrite, deleting branches.
- Installing system packages, Docker images, or solvers globally.
- Running anything in parallel beyond `-j 2`.
- Cloning multi-GB corpora; use streaming.

## 10. Relationship to `main` and `v2-bootstrap`

`main` is v1 reference. `v2-bootstrap` is the `riscv-btor2` v2 line
where the foundation patterns (interpreter alignment, schema
versioning, multi-engine cross oracle) were established. This
branch **inherits the patterns** but builds an independent pair.
Do not modify `riscv-btor2` from this branch.
