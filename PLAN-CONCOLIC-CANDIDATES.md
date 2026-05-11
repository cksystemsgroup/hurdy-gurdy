# Plan: concolic + candidate-directive extension for `riscv-btor2`

This document is the working plan for adding *concolic exploration*
and *candidate directives* to the `riscv-btor2` pair, plus the small
amount of framework surface they need. It is self-contained: a fresh
Claude Code session should be able to pick it up cold without
consulting the conversation that produced it.

Read `README.md`, `PLAN.md`, and `PAIRING.md` first if you are new
to hurdy-gurdy. Read `gurdy/pairs/riscv_btor2/SCHEMA.md` before
touching the translation.

---

## 1. Goal

Give the LLM two new primitives, composable in a single
*propose-and-check* reasoning loop:

- **B — concolic exploration.** A symbolic shadow of the RV64
  simulator that, given a seed `RiscvInputBinding` with some fields
  marked *symbolic*, runs concretely and emits a BTOR2-term path
  condition plus a branch trace.
- **E — candidate directives.** Spec-level vocabulary by which the
  LLM proposes an invariant, ranking function, witness binding, or
  unrolling bound, and the translation mechanically lowers each
  candidate into the existing layered artifact.

Together (B + E) the LLM proposes a candidate, falsifies it cheaply on
concrete and concolic traces, and only escalates surviving candidates
to a solver — without the framework orchestrating any of it.

This is one specific design point. The architectural commitments
in `PLAN.md` ("Architectural commitments") and `PAIRING.md` §5
("Schema-first discipline") apply unchanged.

## 2. Scope

**In scope.**

- A `concolic_interpreter` capability on the `riscv-btor2` pair.
- A `concolic_explore` translator-layer tool gated on that capability.
- New spec directives: `CandidateInvariant`, `CandidateRanking`,
  `CandidateBound`, `CandidateWitness`.
- Schema rules lowering each candidate into existing or new layers.
- Tests, examples, and a minimal benchmark stanza.

**Out of scope.**

- Any change to whole-program translation that isn't a strict
  extension. The pre-existing v1.0.0 schema for whole-program
  questions stays byte-identical for specs that don't use the new
  directives.
- Changes to other pairs (`python-smtlib` does not exist yet).
- Any framework-level *orchestration* (the B+E *loop* lives in LLM
  prompts and tests, not in core code).
- Adapting `LearnedFact` plumbing to candidates. Deferred.

## 3. Settled design decisions

Lock these before implementation starts; revisit only with a written
note in this file.

1. **Path conditions live in the BTOR2 term grammar** the translator
   already uses (`gurdy/pairs/riscv_btor2/btor2/`). No new IR; no
   parallel term language.
2. **The concolic interpreter is pair-specific.** It is *not*
   inserted at the framework level. It is supplied via a new optional
   `concolic_interpreter` field on `Pair`, gated like
   `source_interpreter` / `reasoning_interpreter` are
   (`gurdy/core/pair.py:249-254`). Pairs without it remain valid.
3. **Seeds are part of the spec hash.** Any candidate or seed binding
   the LLM proposes is included in `BaseSpec.canonical_bytes()` so
   the `(spec_hash, source_hash, schema_version)` cache key continues
   to work and the LLM-predictability invariant survives.
4. **Candidates are translated mechanically by SCHEMA.md rules.**
   No heuristics, no adaptive choices. Each candidate type has a
   fixed lowering documented before code is written. (`PAIRING.md` §5.)
5. **Schema version bump.** `riscv-btor2` moves to schema_version
   `1.1.0`. Pre-existing v1.0.0 specs (those using none of the new
   directives) compile to byte-identical artifacts under v1.1.0;
   this is enforced by a regression test.
6. **Interpreter version bump.** `interpreter_version` bumps when
   the concolic interpreter is added, because observable
   capabilities (the gated tool surface) change.
   `interpreter_version` is independent of `schema_version`
   (`PAIRING.md` §11).
7. **Determinism contract applies to concolic traces.**
   `(spec, source, seed, schema_version, interpreter_version) →
   byte-identical ConcolicTrace`. Same testing discipline as for the
   simulator: emit a normalized JSON form and golden-test it.

## 4. Open design questions (resolve in Phase 0)

These cannot be answered without writing prose; resolve them in
SCHEMA.md before writing code.

- **What exactly is a "symbolic" field on `RiscvInputBinding`?** A
  per-register flag? A per-byte memory flag? A list of symbolic
  immediates? The path-condition grammar must be expressible over
  exactly the symbolic surface chosen.
- **What is recorded at a memory access whose address is symbolic?**
  Options: (i) refuse and halt the concolic run; (ii) constrain the
  address concretely to its actually-resolved value and record that
  as part of the path condition; (iii) record an `ite` over a
  finite resolved set. Choose one and document; v1 should pick the
  simplest sound option (likely ii).
- **What is the lowering of `CandidateInvariant` exactly?** Does it
  add to the `constraint` layer, or warrant a new `candidate` layer?
  Either is defensible; pick before writing the translator. Stability
  matters: candidate clauses change per question, so a separate
  `candidate` layer keeps the lower layers cache-stable.
- **What is the syntax in which the LLM writes candidate predicates?**
  A small Boolean expression grammar over named state (`pc`,
  `reg_x{N}`, `mem[addr]`), with BTOR2 bitvector operators. Lock the
  grammar in SCHEMA.md §14 (new).
- **Should `concolic_explore` return *one* path condition or a
  branch-trace structure?** Recommended: branch trace (list of
  `(pc, condition_term, taken)`), and the conjunction is a derived
  view. Gives the LLM more material to compose negations.

## 5. Files and where the work lives

Framework surface (small, additive):

- `gurdy/core/pair.py` — add `concolic_interpreter: ... | None = None`
  field to `Pair`. No registration enforcement: tool-call-time gate
  in the new tool.
- `gurdy/core/interp/types.py` — add `ConcolicTrace`, `BranchEvent`,
  `PathCondition` (the last may just be `Any` opaque, since it's a
  pair-specific BTOR2 term).
- `gurdy/core/tools/concolic_explore.py` — new tool, mirroring
  `simulate.py`. Gated on `pair.concolic_interpreter is not None`.
- `gurdy/core/cli.py` — expose `gurdy concolic-explore` mirroring
  `gurdy simulate`. CLI is mechanical wrapper; no logic here.

Pair surface (the bulk of the work):

- `gurdy/pairs/riscv_btor2/source_interp/concolic.py` — new module.
  Wraps the concrete simulator; threads a `(concrete, term)` value
  through registers and memory; records branch conditions and
  symbolic memory-address resolutions.
- `gurdy/pairs/riscv_btor2/source_interp/bindings.py` — extend
  `RiscvInputBinding` (or add a `RiscvConcolicInputBinding`
  subclass) with a per-field *symbolic mask*.
- `gurdy/pairs/riscv_btor2/spec.py` — add `CandidateInvariant`,
  `CandidateRanking`, `CandidateBound`, `CandidateWitness` directive
  types. Add validators in `pairs/riscv_btor2/`'s spec validator.
- `gurdy/pairs/riscv_btor2/translation/` — add candidate-lowering
  pass that emits into the new `candidate` layer (or `constraint`,
  see open question). Register the layer in `pairs/riscv_btor2/
  __init__.py`'s `LayerSpec` tuple.
- `gurdy/pairs/riscv_btor2/SCHEMA.md` — new §14
  "Candidate directives and concolic exploration". Bump version to
  `1.1.0`. Document path-condition grammar, candidate grammar,
  candidate lowering, soundness contract for the concolic
  interpreter, and the `candidate` layer's stability profile.
- `gurdy/pairs/riscv_btor2/__init__.py` — wire `concolic_interpreter`
  into the `Pair` registration; bump `interpreter_version`.
- `gurdy/pairs/riscv_btor2/lift/` — extend `replayer.py` to accept
  candidate-targeted witnesses, mapping them back through the
  source interpreter the same way property witnesses are mapped.

Tests:

- `tests/pairs/riscv_btor2/test_concolic_interpreter.py` — unit
  tests per instruction class, mirroring
  `test_source_interpreter.py`.
- `tests/pairs/riscv_btor2/test_concolic_simulator_crosscheck.py` —
  every concolic run on a fully-concretized seed must match the
  plain simulator step-for-step. This is the soundness anchor.
- `tests/pairs/riscv_btor2/test_candidate_translation.py` — golden
  tests for each candidate type's lowering.
- `tests/pairs/riscv_btor2/test_schema_v10_backcompat.py` —
  byte-identical compilation for v1.0.0-shaped specs under v1.1.0.
- `tests/pairs/riscv_btor2/test_concolic_determinism.py` — repeat
  compile, repeat trace, hash-equal.
- `tests/core/test_concolic_explore_tool.py` — gate checks: tool
  errors cleanly when pair has no `concolic_interpreter`.
- `tests/integration/test_be_loop_smoke.py` — small end-to-end:
  candidate invariant on a known program, concrete falsification
  path, concolic-trace path, surviving-candidate dispatch path.

Examples + bench:

- `examples/05_concolic_explore.py` — analogue of the
  `01_compile_basic` style: shortest possible script that produces
  a concolic trace.
- `examples/06_candidate_invariant.py` — propose an invariant on a
  small loop, run the B+E loop manually with print statements.
- `bench/concolic_candidates/` — small corpus following
  `BENCHMARKING.md` conventions. Three programs minimum: a true
  invariant, a false invariant with a short counterexample, a
  candidate that survives concrete falsification but fails
  inductiveness.

## 6. Phased implementation

Order matters because each phase rests on earlier ones. Estimates
are placeholders; the next session should refine them after Phase 0.

### Phase 0 — SCHEMA.md §14 (the bottleneck)

Write the schema *before* writing any code. This is non-negotiable
(`PAIRING.md` §5). Cover:

- Symbolic-field model on `RiscvInputBinding`.
- Path-condition grammar: BTOR2 expressions over the symbolic
  inputs, with a documented top-level shape.
- Candidate-predicate grammar: small Boolean DSL over named state.
- Lowering rules:
  - `CandidateInvariant(pc, P)` → at every transition that reaches
    `pc`, emit a `bad` clause asserting `¬P`; emit a `constraint`
    asserting `P` as an assumption for downstream candidates.
    Layer placement: `candidate`.
  - `CandidateRanking(pc, expr)` → `bad` on `¬(expr_next < expr_now)`
    along back-edges to `pc`; well-foundedness predicate as
    `constraint`. Layer: `candidate`.
  - `CandidateBound(steps)` → translates to a cap on BMC unroll
    length; recorded in annotation but does not add nodes.
  - `CandidateWitness(binding)` → no translation (degenerate);
    spec consumers use `check(spec, binding)`.
- Concolic soundness contract: every concrete concretization of a
  symbolic field must reproduce the plain simulator's trace; the
  emitted path condition must be entailed by the whole-program
  encoding's transition relation along the same path.
- Annotation: how `candidate` layer nodes are tagged. Suggested
  `role` values: `candidate_invariant_assumption`,
  `candidate_invariant_check`, `candidate_ranking_assumption`,
  `candidate_ranking_check`.
- Stability declaration for the new `candidate` layer (per-question).

Exit criterion: the schema is reviewable as a self-contained
specification; an LLM could in principle predict the candidate
lowering for a given spec from §14 alone.

### Phase 1 — concolic interpreter

1. Extend `RiscvInputBinding` with the symbolic mask chosen in
   Phase 0.
2. Implement the concolic interpreter in `source_interp/concolic.py`.
   Reuse the existing instruction handlers via composition; do not
   fork them. Each handler returns both the concrete value and the
   BTOR2 term whose evaluation yields it.
3. Record branch events at every conditional branch and at every
   symbolic-address memory access (per the Phase 0 choice).
4. Emit `ConcolicTrace` with `to_jsonable()` matching the framework
   convention in `core/interp/types.py`.
5. Cross-check test: every fully-concrete seed reproduces the plain
   simulator step-for-step.

Exit criterion: concolic-simulator cross-check passes on the
existing per-instruction unit tests, instantiated symbolically.

### Phase 2 — concolic tool surface

1. Add `Pair.concolic_interpreter` field, default `None`. Gate
   `concolic_explore` at tool-call time, not registration time
   (matches how `projection` is gated, `PAIRING.md` §11).
2. Implement `gurdy/core/tools/concolic_explore.py`. Signature:
   `concolic_explore(spec, seed_binding, max_steps) → ConcolicTrace`.
3. Wire CLI `gurdy concolic-explore` to mirror `gurdy simulate`.
4. Smoke test the tool surface from a fresh import (mirrors the
   PAIRING.md §12 requirement for new tools).

Exit criterion: `gurdy concolic-explore` works on the
`examples/05_*` script and produces a stable JSON-emitted trace.

### Phase 3 — candidate directives and translation

1. Add the four `Candidate*` types to
   `gurdy/pairs/riscv_btor2/spec.py`, with structural validation
   (e.g. `CandidateInvariant.pc` must be a valid address;
   `predicate` must parse under the Phase 0 grammar).
2. Add the `candidate` layer to the layer spec tuple.
3. Implement the lowering pass; thread provenance through the
   annotation emitter.
4. Verify v1.0.0 byte-for-byte back-compat with the regression
   test (any spec without `Candidate*` produces identical bytes).
5. Bump `schema_version` to `1.1.0`; document the bump in `SCHEMA.md`
   §0 changelog.

Exit criterion: golden tests pass for each candidate type and the
back-compat regression test is green.

### Phase 4 — lifter extension and witness replay

1. Extend `lift/replayer.py` to handle witnesses targeting
   candidate-layer `bad` nodes. The replay path is identical: it's
   a concrete RV64 execution; only the source-tagged trace's label
   changes (e.g. "invariant violated at pc=0x...").
2. Update `lift/invariant.py` if/where invariant naming needs to
   absorb candidate provenance.

Exit criterion: a candidate-invariant counterexample lifts to a
human-readable source-tagged trace.

### Phase 5 — tests, examples, bench

1. Ship every test file in §5.
2. Ship the two examples.
3. Add the bench stanza per `BENCHMARKING.md` §9. The bench should
   measure: candidate-falsification rate on a corpus of (good,
   subtly-bad, structurally-bad) candidates; mean time to falsify
   concrete-vs-concolic-vs-solver; coverage growth across seed
   rounds.

Exit criterion: `pytest -q` is green; both examples run end-to-end;
the bench produces a stable summary table.

### Phase 6 — documentation and retrospective

1. Cross-link from `PAIRING.md` §11 to the new SCHEMA.md §14 as an
   exemplar of "what an interpreter-version bump looks like."
2. Add a brief retrospective at the bottom of `PAIRING.md` per
   `PAIRING.md` §15 — but only if a second pair has also implemented
   anything analogous. Otherwise leave it; one data point is not
   evidence.
3. If concolic-style exploration generalizes obviously to
   `python-smtlib`, note it in PLAN.md's "Working notes" section
   for future sessions. Do not abstract until at least one other
   pair adopts it.

## 7. Invariants the implementer must not break

Reproduced here so the implementing session does not need to
re-derive them:

1. **Same `(spec, source, schema_version) → byte-identical artifact.**
   Seeds and candidates are part of `spec`, so the invariant covers
   them too.
2. **The framework does not orchestrate.** The B+E loop is composed
   in the LLM's prompts and in the example scripts; no
   "auto-CEGAR" code, no "try concrete then escalate" function
   inside `gurdy/`. The framework supplies primitives only.
3. **The schema is authoritative.** If code and SCHEMA.md disagree,
   the code is wrong (or the schema needs an explicit version bump).
4. **No IR.** Path conditions are BTOR2 terms in the existing
   grammar; candidate predicates parse directly to BTOR2 terms.
   There is no intermediate language.
5. **Determinism for the new tool.** The concolic interpreter is
   pure with respect to `(source, seed, interpreter_version)`.
6. **Test parity.** Every new primitive ships unit tests, a
   cross-check test, a determinism check, and an end-to-end smoke
   test, per `PAIRING.md` §12.

## 8. Risk register

- **Concolic-encoding drift from the whole-program encoding.**
  Hardest soundness obligation. Mitigation: the smoke test in §5
  solves a small candidate-bearing artifact, lifts the witness,
  replays it through both the concrete simulator and the concolic
  interpreter, and asserts agreement. If divergence appears, the
  per-instruction lowering is the single source of truth and both
  encodings must reconcile to it.
- **Spec-hash explosion.** Each unique seed or candidate produces
  a new spec hash, defeating the cache. Mitigation: this is by
  design for the new flow; the bottom layers (`header`, `machine`,
  `library`, `init`, `dispatch`) remain stable across questions
  and the layer linker reuses them via content hashing.
- **Candidate-predicate grammar drift.** If the grammar is
  under-specified the schema fails the LLM-predictability
  invariant. Mitigation: write the grammar with a formal BNF in
  SCHEMA.md §14, plus a parser test corpus.
- **Symbolic-memory blowup.** Even a few symbolic addresses can
  produce huge path conditions. Mitigation: pick the conservative
  Phase 0 option (concretize symbolic addresses, record the
  resolution as a constraint). Document the limitation explicitly.

## 9. What "done" looks like

- `gurdy concolic-explore` is a CLI command that works end-to-end
  on `examples/05_*`.
- `gurdy compile` accepts a spec carrying any combination of the
  four `Candidate*` directives and produces a v1.1.0 artifact.
- `pytest -q` is green, including the v1.0.0 back-compat test.
- `bench/concolic_candidates/` has at least one run captured and
  a one-paragraph summary in its README.
- SCHEMA.md §14 is complete, internally consistent, and references
  the path-condition grammar, the candidate grammar, and the
  soundness contract.

When all six bullets hold, this plan is exhausted. Open the next
question in a fresh document.

## 10. Hand-off notes for the implementing session

- Start in `gurdy/pairs/riscv_btor2/SCHEMA.md`. Do not write any
  code until §14 is drafted and self-consistent.
- After §14 is drafted, write the per-instruction concolic
  handlers next; everything else depends on them.
- The cross-check test in Phase 1 is the most important test in
  the plan. Do not skip it, and do not weaken it to "agree on
  final state" — it must agree step-for-step.
- If you find yourself adding heuristics anywhere ("try this seed
  first," "fall back to whole-program if the path is too long"),
  stop and re-read `PAIRING.md` §5. Heuristics go in the LLM, not
  the pair.
- If a design question not listed in §4 arises, write it down in
  this file under §4 with a brief discussion, decide, and proceed.
  Do not invent a third path silently.
