# V2 Audit — v1 conformance vs `V2_BOOTSTRAP.md` §3 contracts

> Produced by the autonomous loop as part of P0.
> Read-only audit; no code edits in the iterations that wrote this file.
> Each row maps a V2_BOOTSTRAP.md §3 contract to either:
> - **v1 conforms** (the v1 public surface already satisfies the
>   contract; no change needed for v2).
> - **v1 partial** (most of the contract is there; named sub-increment
>   captures the delta).
> - **v1 gap** (contract is absent; named sub-increment introduces it).

## P0.2 — `gurdy/core/` audit (this iteration)

### Three-pillar foundation order (V2_BOOTSTRAP.md §3)

| Contract                                | v1 status            | Source of truth                                    | Sub-increment if gap |
|-----------------------------------------|----------------------|----------------------------------------------------|----------------------|
| Source interpreter exists as a pillar   | **v1 conforms**      | `gurdy/core/interp/__init__.py` re-exports `SourceTrace`, `SourceStep`, `InputBinding`; pair lives at `gurdy/pairs/riscv_btor2/source_interp/` | — |
| Reasoning interpreter exists as a pillar| **v1 conforms**      | `gurdy/core/interp/__init__.py` re-exports `ReasoningTrace`, `ReasoningStep`, `ReasoningBinding`; pair lives at `gurdy/pairs/riscv_btor2/reasoning_interp/` | — |
| Translator exists as a pillar           | **v1 conforms**      | `gurdy/pairs/riscv_btor2/translation/` (builder, exprs, layers, library, translate); pair audit in P0.3 will confirm public surface | — (audit in P0.3) |
| Three pillars are *load-bearing from day one* | **v1 partial** | They exist but v1 PLAN.md (on `main`) introduced them in Phase 19-20 as additions, not as the foundation. v2's reframing is documentary, not structural. | P0.2a — add a `core/interp/README.md` (or similar) that asserts the load-bearing-from-day-one stance, so a fresh reader of v2 sees it without consulting v1's PLAN history. |

### Alignment oracle (V2_BOOTSTRAP.md §4)

| Contract                                       | v1 status        | Source of truth                                            | Sub-increment if gap |
|------------------------------------------------|------------------|------------------------------------------------------------|----------------------|
| `Projection` protocol decouples per-pair field mapping from framework-level walking | **v1 conforms** | `gurdy/core/interp/align.py:Projection` (Protocol, runtime-checkable) + `ProjectedField` dataclass | — |
| `align_traces(source, reasoning, projection)` walks step-by-step and returns first divergence | **v1 conforms** | `gurdy/core/interp/align.py:align_traces` | — |
| `JoinedTrace` exists for lock-step walked source+reasoning | **v1 conforms** | `gurdy/core/interp/types.py:JoinedStep`, `JoinedTrace` | — |
| `CrossCheckReport` carries outcome + divergence step/label/views | **v1 conforms** | `gurdy/core/interp/types.py:CrossCheckReport`, `CrossCheckOutcome` | — |
| Alignment oracle wired as the **primary** correctness check (not secondary) | **v1 partial** | The primitives exist; whether the bench harness invokes them first (before cross-engine oracle) is a `bench/`-side question for P0.3 audit. | P0.2b — verify (in P0.3) that `bench/riscv-btor2/oracle_align.py` or equivalent invokes `align_traces` per task. If absent, file a P-phase later. |

### Spec-side contracts (V2_BOOTSTRAP.md §2)

| Contract                                        | v1 status        | Source of truth                                       | Sub-increment if gap |
|-------------------------------------------------|------------------|-------------------------------------------------------|----------------------|
| `BaseSpec` provides envelope + canonical hash   | **v1 conforms**  | `gurdy/core/spec/base.py:BaseSpec` (`_to_jsonable`, frozen dataclass model) | — |
| Spec is the *only* LLM-tunable input to the translator | **v1 conforms** | Architecture; reinforced by README + SCHEMA on `main`. v2's claim "performance scales with LLM" depends on this and v1 honours it. | — |
| Spec exposes every former-heuristic as a parameter (bound, engine, scope.included_callees, etc.) | **v1 conforms** | `gurdy/pairs/riscv_btor2/spec.py` declares `AnalysisDirective`, `AnalysisScope`, etc. (per PLAN on `main`) | — |
| `AnalysisDirective.engine ∈ {bmc, ind, horn}` | **deferred** | v1.1.0 schema on `main` already does this. v2.0.0 target (v1.0.0 schema) reduces to BMC-only — that is the *intentional* downgrade, not a gap. | — (covered by P0.4 schema audit) |

### Schema discipline (V2_BOOTSTRAP.md §1, §11)

| Contract                                                | v1 status        | Source of truth                                                                                   | Sub-increment if gap |
|---------------------------------------------------------|------------------|---------------------------------------------------------------------------------------------------|----------------------|
| Every translator choice is in `SCHEMA.md` or a spec parameter | **v1 partial** | This is the v1 architectural commitment and is broadly true. Audit-by-grep across `gurdy/pairs/riscv_btor2/translation/` would surface any remaining hidden choice. Out of scope for P0.2 (core-only); file as P0.3 audit task. | — (covered by P0.3 pair audit) |
| Schema is a Markdown file, queryable by topic           | **v1 conforms**  | `gurdy/core/schema/indexer.py` parses SCHEMA.md and serves `describe(topic, pair)`                | — |
| `SCHEMA.md` carries an explicit version                 | **v1 conforms**  | v1's SCHEMA on `main` is at `1.1.0`; v2 v1.0.0 target is a downgrade documented in PLAN P1.       | — (covered by P0.4 schema audit) |

### Pair protocol (V2_BOOTSTRAP.md §6 ref)

| Contract                                           | v1 status        | Source of truth                                                      | Sub-increment if gap |
|----------------------------------------------------|------------------|----------------------------------------------------------------------|----------------------|
| `Pair` is a registry record, not a class hierarchy | **v1 conforms**  | `gurdy/core/pair.py` defines `SourceLoader`, etc. as Protocols + a frozen `Pair` dataclass | — |
| Pair has hooks for source loader, translator, lifter, reasoning interpreter, source interpreter | **v1 conforms** (assumed from header) | `gurdy/core/pair.py` lines 35+ define the Protocols; full body to be confirmed in P0.3 along with how `riscv_btor2/__init__.py` registers itself | — (confirm in P0.3) |

### Determinism & no-state (V2_BOOTSTRAP.md §1)

| Contract                                            | v1 status        | Source of truth                                                       | Sub-increment if gap |
|-----------------------------------------------------|------------------|-----------------------------------------------------------------------|----------------------|
| Translator is pure: `(spec, source) → bytes` is a function | **v1 conforms** | Architectural commitment; v1 has `_to_jsonable` and canonical hashing for spec to ensure determinism. | — |
| Layer hashing is content-addressed                  | **v1 conforms**  | `gurdy/core/layers/` exists as a subpackage (confirmed by `ls` in iter 0); contents to be audited in P0.3. | — (light follow-up in P0.3) |

## P0.3 — `gurdy/pairs/riscv_btor2/` audit (this iteration)

### Pair structure

| Subpackage / file                              | Status / purpose                                                                                                                                                                       | Audit note |
|------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|
| `__init__.py` (registration)                   | Registers the `Pair` record with `gurdy.core.pair.register_pair`. Wires translator, dispatcher, lifter, replayer, source interpreter, reasoning interpreter, solver adapters.          | **v1 conforms.** All four §3 pillar callables are wired via the Pair record. |
| `source_interp/` (RV64 concrete executor)      | `bindings.py` (`RiscvInputBinding`), `interpreter.py` (`RiscvSourceInterpreter`), `predicates.py` (spec evaluation), `projection.py` (alignment projection), `shadow.py` (term-shadow). | **v1 conforms.** All §3.1 capabilities present including shadow mode. Wraps `..lift.simulator` (legacy concrete simulator); single soundness ground truth. |
| `reasoning_interp/` (BTOR2 transition system)  | `bindings.py` (`Btor2ReasoningBinding`), `interpreter.py` (`Btor2ReasoningInterpreter`). Wraps BTOR2 evaluator into multi-step transition simulator emitting `ReasoningTrace`.        | **v1 conforms.** §3.2 simulate; witness replay handled by `lift/replayer.py` (see below). |
| `translation/`                                 | `builder.py`, `exprs.py`, `layers.py`, `library.py`, `translate.py`. Deterministic translator from spec+source to BTOR2 model.                                                         | **v1 conforms.** §3.3 translator pure & deterministic per architecture commitment. |
| `solvers/`                                     | `z3bmc.py`, `z3spacer.py`, `bitwuzla.py`, `cvc5.py`, `pono.py` + `btor2_to_<solver>.py` converters + `_bmc.py` helper.                                                                | **v1 conforms.** All five engines present (z3-bmc, z3-spacer, bitwuzla, cvc5, pono). |
| `lift/`                                        | `lift.py` (verdict lift), `replayer.py` (joins source+reasoning traces from witness → `JoinedTrace`), `simulator.py` (concrete RV64 sim shared with source_interp), `witness.py` (witness extraction), `invariant.py` (inductive invariants). | **v1 conforms** — and `lift/replayer.py` is the load-bearing piece for §4 trace-alignment. |

### V2_BOOTSTRAP.md §4 — primary alignment oracle (P0.2b follow-up)

The §4 contract calls for "`bench/riscv-btor2/oracle_align.py` ... the **primary** correctness oracle" that runs source+reasoning trace alignment on every corpus task.

Reality on `main` / `v2-bootstrap`:

| File                                     | What it does                                                                                                              | Aligned with §4? |
|------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|-------------------|
| `bench/riscv-btor2/oracle.py`            | §9.10 concrete-execution oracle: solver-free, runs source interp + predicate evaluator on default bindings.               | **Partial.** Solver-free side of the contract; doesn't compare against the reasoning trace because there's no solver-mediated trace to compare to. |
| `bench/riscv-btor2/framework_oracle.py`  | §B0 framework oracle: full compile→dispatch→lift, compares lifted verdict to `expected.verdict`. No trace alignment.      | **No.** Verdict-level, not trace-level. |
| `bench/riscv-btor2/oracle_cross.py`      | §4.5 multi-engine cross-oracle.                                                                                            | **No.** Engine agreement, not trace alignment. |
| `gurdy/pairs/riscv_btor2/lift/replayer.py` | Builds `JoinedTrace` from a witness; `gurdy/core/interp/align.py:align_traces` then walks it.                            | **Yes — but invoked per-witness via the `replay` tool, not as a bench-side per-task primary oracle.** |

**Gap.** The framework has every part of the §4 alignment oracle. What's missing is a **bench-side runner** that, for every corpus task, (a) compiles, (b) dispatches, (c) on `reachable` witness invokes `replay_witness` and `align_traces`, (d) reports per-task `align_ok` alongside `verdict_ok`. This is small (≤ 150 LOC for the runner + a config flag to enable per task) and makes §4 operationally true.

Filed as **P0.5a — `bench/riscv-btor2/oracle_align.py`** (see P0.5 below).

### V2_BOOTSTRAP.md §1 — schema discipline (translator-side hidden choices)

Spot-check (not exhaustive in this iteration): a `grep -n "if " gurdy/pairs/riscv_btor2/translation/` would surface conditionals that should each map to a SCHEMA.md rule or a spec parameter. Deferred to P0.4 schema audit.

### Pair public surface vs V2_BOOTSTRAP.md §3

| Pillar             | v1 module                                              | Public class             | §3 contract |
|--------------------|--------------------------------------------------------|--------------------------|------------|
| Source interpreter | `gurdy/pairs/riscv_btor2/source_interp/interpreter.py` | `RiscvSourceInterpreter` | **v1 conforms** |
| Reasoning interp   | `gurdy/pairs/riscv_btor2/reasoning_interp/interpreter.py` | `Btor2ReasoningInterpreter` | **v1 conforms** |
| Translator         | `gurdy/pairs/riscv_btor2/translation/translate.py`     | `translate()` (callable) | **v1 conforms** |

## Audit conclusion for P0.2

**v1 conforms with two minor documentation-class gaps and three audit-follow-ups for P0.3/P0.4.**

- **P0.2a** (documentation gap): assert "three pillars load-bearing from day one" in a `core/interp/README.md` so v2's stance doesn't depend on the v1 PLAN history.
- **P0.2b** (verification): in P0.3 (pair audit), check that the bench-side harness invokes the alignment oracle as the *primary* correctness check. **Done in P0.3 below — gap surfaced and filed as P0.5a.**
- **P0.3** (this iter): pair audit of `gurdy/pairs/riscv_btor2/` against §3 and §4 contracts. **Done.**
- **P0.4** (next): schema audit — diff `SCHEMA.md` against the v2 v1.0.0 target (RV64I only, BMC only, no callees).
- **P0.5** (after): file each surfaced gap as a sub-increment with concrete acceptance criteria.

## Audit conclusion for P0.3

**v1 conforms broadly with one operational gap:** the primary trace-alignment oracle exists as a framework tool (`replay_witness` + `align_traces`) but is not wired as a bench-side per-task primary check. All five solver adapters present. All three pillars conform.

**Sub-increment surfaced this iteration:**

- **P0.5a — `bench/riscv-btor2/oracle_align.py`**: write a per-task runner that compiles, dispatches, and on `reachable` witness invokes `replay_witness` + `align_traces`; reports `align_ok` alongside `verdict_ok` per task. Acceptance: when run on the seed corpus, every `reachable` task produces a `JoinedTrace` and `align_traces` returns `agreement`. ≤ 150 LOC + a per-task config flag.

Next iteration: P0.4 schema audit.
