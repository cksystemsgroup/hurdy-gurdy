# Plan: make concolic reasoning native by generalising the spec

This plan replaces `PLAN-CONCOLIC-CANDIDATES.md`. Where the old plan
added a *parallel* concolic surface (new tool, new interpreter, new
directive family, new layer), this plan absorbs concolic reasoning
into the existing surface by recognising that a `QuestionSpec` is
already a description of a set of program runs, and BMC, concolic
exploration, and concrete simulation are the same **question
compiler** asking different questions about it. Its terminal phase
deletes both `PLAN-CONCOLIC-CANDIDATES.md` and this file: the
unification lives in `PLAN.md`, `PAIRING.md`, and the pair `SCHEMA.md`
once it lands.

Read `README.md`, `PLAN.md`, `PAIRING.md`, and
`gurdy/pairs/riscv_btor2/SCHEMA.md` first.

---

## 1. The unifying idea

hurdy-gurdy is already a **question compiler** (`PLAN.md`, "What
hurdy-gurdy is"). The reframe this plan needs is that a `QuestionSpec`
*describes a set of program runs* — its init clauses, invariants,
branch pins, and input pins all narrow that set — and BMC, concolic
exploration, and concrete simulation are the same compilation pipeline
asking different questions about it. Compilation lowers the
description to a reasoning-language formula; "the solver" is whichever
discharger can answer the resulting search problem cheapest.

| Mode               | Trace constraints                     | Cheapest discharger              |
|---|---|---|
| Whole-program BMC  | init + cycle invariants + bad         | z3-bmc / spacer / bitwuzla / pono |
| Symbolic execution | init + branch sequence                | z3-bmc on a path-shaped formula   |
| Concolic           | init + branch sequence + some inputs  | z3-bmc on a tightly pinned path   |
| Concrete sim.      | init + branch sequence + all inputs   | the source interpreter (O(n))     |

Three primitives realise the full spectrum:

1. **Partial input bindings.** A binding pins some input fields and
   leaves others free. The plain simulator requires all fields pinned;
   the symbolic-shadow simulator (below) accepts any prefix.
2. **Branch pins.** A spec clause that asserts "at step k (or at
   pc=X on its n-th visit) the conditional branch went direction D."
   Lowers mechanically into the existing `constraint` layer.
3. **Dual-role predicates.** A predicate tagged so it appears as
   both an `assumption` (in `constraint`) and a `check` (in `bad`)
   in a single compilation. This is what the old plan called a
   "candidate invariant"; here it's a flag on existing vocabulary.

The "concolic interpreter" of the old plan becomes the existing source
interpreter run with two enhancements: it accepts a partial binding,
and it threads a BTOR2-term shadow alongside the concrete value at
each handler. Its output is the existing `SourceTrace` enriched with
optional branch-term and address-term fields. No new tool exists; the
LLM gets a trace from `simulate`, builds a spec patch from it (input
pins + branch pins + optionally a flipped pin), and compiles/dispatches
through the existing pipeline.

`PLAN.md`'s architectural commitments survive intact — and are
*reinforced*, because removing the parallel surface eliminates the
"two ways to ask the same question" tension that the old plan would
have introduced.

## 2. End state

When this plan is exhausted:

- The `Pair` protocol has **no** `concolic_interpreter` field.
- There is **no** `concolic_explore` tool or CLI command.
- The spec vocabulary has **no** `CandidateInvariant`,
  `CandidateRanking`, `CandidateBound`, `CandidateWitness` types.
- `RiscvInputBinding` supports per-field pinning, with "free" as
  a valid value for any field.
- A `BranchPin` assumption type exists in `spec.py`.
- `CycleInvariant` carries a `dual_role: bool` flag (default `False`,
  preserving v1.0.0 byte-equality).
- A volatile-assumption layer (named `volatile`, not `candidate`)
  sits between `constraint` and `bad`. It holds clauses whose hash
  is expected to churn per question — recently-recorded branch pins
  and dual-role predicates being tested.
- The source interpreter records optional `branch_term` and
  `address_term` payloads on `SourceStep.deltas` when the input
  binding contains free fields. With a fully-pinned binding it is
  byte-identical to today's interpreter.
- `gurdy/pairs/riscv_btor2/SCHEMA.md §14` documents the partial
  binding, branch pins, dual-role predicates, the volatile layer,
  and the term-shadow contract — under the title "Partial bindings
  and the question compiler," not "concolic exploration."
- `PLAN.md` "Architectural commitments" gains a short subsection
  framing the spec as a description of a set of program runs; the
  framing is language-agnostic and applies to future pairs.
- `PAIRING.md §11` documents partial bindings as part of the
  interpreter contract, not a separate "concolic" contract.
- `PLAN-CONCOLIC-CANDIDATES.md` is deleted.
- `PLAN-NATIVE-CONCOLIC.md` (this file) is deleted.

## 3. Settled design decisions

Lock before implementation. Revisit only with a written note here.

1. **One spec language, one tool surface.** No parallel `concolic_*`
   types, no parallel tool. Concolic is a fill level of the existing
   spec.
2. **"Free" is a value of the binding, not a separate type.** A
   binding field that is `None` (or `Free`, a sentinel) is symbolic.
   The plain simulator raises a clean diagnostic if any field is
   free; the term-shadow simulator accepts it. Same binding class
   either way.
3. **Branch pins are step-indexed or pc/visit-indexed, not both.**
   Pick step-indexed for v1.1.0; pc/visit-indexed is a later extension
   if needed. Decision lives in SCHEMA.md §14.
4. **Dual-role is a flag, not a directive.** A `CycleInvariant` with
   `dual_role=True` emits one annotated clause in `constraint` and a
   paired negated clause in `volatile`'s `bad` companion. Provenance
   links the two.
5. **Volatile layer name.** `volatile` (not `candidate`) — its purpose
   is per-question churn isolation, which applies whether the clause
   came from a candidate or any other transient assumption.
6. **The term shadow is a `Pair`-provided callable, not a separate
   interpreter.** The source interpreter's handlers receive an
   optional `shadow` parameter; pairs that don't supply one work
   exactly as today. This avoids a new `Pair` field.
7. **Schema version 1.1.0.** Specs that use only v1.0.0 vocabulary
   compile to byte-identical artifacts. Enforced by a regression
   test using the existing fixture corpus.
8. **Interpreter version bumps.** Because the trace payload grows
   (optional term fields on deltas), `interpreter_version`
   increments. Specs that pin all fields produce byte-identical
   traces; tests pin the contract.
9. **Determinism contract unchanged.** `(spec, source,
   schema_version)` → byte-identical artifact; `(source, binding,
   interpreter_version)` → byte-identical trace. The binding is
   already in the trace hash via `inputs_hash`.

## 4. Open design questions

Resolve in Phase 0; write the resolution into SCHEMA.md §14 before
any code lands.

- **Indexing of `BranchPin`.** Step-indexed (settled per §3.3), but
  the spec needs a canonical "step" definition when the trace halts
  early. Decide: pin only fires if the step is reached; pin missing
  the step is a soft no-op, not a diagnostic. Document.
- **Memory at a free address.** Same options the old plan enumerated:
  refuse / concretize-and-record / ite. Take option (ii) for v1.1.0,
  identical to the old plan. The mechanism that records it is just a
  branch pin against the equality `addr == resolved_value`, lowered
  to a `constraint` clause in `volatile`.
- **`dual_role` provenance.** When the same predicate emits clauses
  in two layers, the annotation must link them so a witness on the
  bad clause can be lifted as "violation of the assumed invariant."
  Spell out the link in SCHEMA.md §14 as a `paired_with_nid` field.
- **Trace shadow term storage.** Either a parallel
  `branch_terms: tuple[BTOR2Node, ...]` field on `SourceTrace`, or
  embedded in `SourceStep.deltas`. The first is cleaner for typing;
  the second matches the framework's "opaque deltas" convention.
  Pick the second.
- **Cache key for partial bindings.** A binding with one free field
  hashes differently from a binding with that field pinned to its
  concrete value. That's correct, but the LLM may want to ask "is
  this trace feasible at all?" before exploring — which is a strict
  refinement question. Note that the cache *behaves correctly* and
  no fancy partial-order caching is needed in v1.1.0.

## 5. Files and where the work lives

Framework surface (smaller than the old plan):

- `gurdy/core/interp/types.py` — `InputBinding`'s docstring gains the
  "fields may be `Free`" contract. No structural type change; pairs'
  subclasses pick their own field types and may include `None` /
  sentinel as a free value. Add `BranchTerm` opaque payload type if
  the trace-shadow contract needs it (likely not — `Any` suffices).
- `gurdy/core/spec/base.py` — `BaseAssumption` gains a `dual_role:
  bool = False` field. Default `False` preserves v1.0.0 byte-equality.
- `gurdy/core/tools/simulate.py` — no surface change. Existing
  behavior with fully-pinned bindings is byte-identical.

That is the entire framework delta. No new tool, no new `Pair` field,
no new core module.

Pair surface (where the work concentrates):

- `gurdy/pairs/riscv_btor2/source_interp/bindings.py` — `Free`
  sentinel (or `None`-as-free per the SCHEMA decision); per-field
  partial-pinning. Plain interpreter raises if a field is free.
- `gurdy/pairs/riscv_btor2/source_interp/interpreter.py` — accept an
  optional `shadow` callable; thread `(concrete, term)` through
  registers and memory at every handler when present. Without it the
  handlers behave exactly as today (byte-identical traces).
- `gurdy/pairs/riscv_btor2/source_interp/shadow.py` (new) —
  BTOR2-term-producing shadow. One function per instruction class,
  mirroring `library.py` and the existing handlers. This is the
  largest single file in the plan.
- `gurdy/pairs/riscv_btor2/spec.py` —
  - Add `BranchPin(step: int, taken: bool, pc: int | None = None)`.
    `pc` is optional and used only as a structural cross-check
    against the binding's recorded trace; not part of the lowering.
  - Add `dual_role: bool = False` to `CycleInvariant` if not
    inherited from `BaseAssumption`.
  - No `Candidate*` types.
- `gurdy/pairs/riscv_btor2/translation/` —
  - New `volatile.py` layer emitter. Receives `BranchPin`s and
    `dual_role` companions.
  - `constraint.py` emits paired clauses with `paired_with_nid`
    annotation when `dual_role` is set.
  - `bad.py` extended to accept the volatile bad companions.
  - Layer spec tuple in `__init__.py` gains `volatile` between
    `constraint` and `bad`.
- `gurdy/pairs/riscv_btor2/SCHEMA.md §14` — "Partial bindings and
  the question compiler." Documents the spectrum, the term
  shadow contract, branch-pin lowering, dual-role lowering, the
  volatile layer's stability profile, the memory-at-free-address
  resolution.
- `gurdy/pairs/riscv_btor2/__init__.py` — bump `interpreter_version`
  and `schema_version`. No new field on `PAIR`.
- `gurdy/pairs/riscv_btor2/lift/replayer.py` — handles witnesses on
  volatile-layer `bad` nodes the same way as on `bad` (it's just a
  layer name change; the replay path is unchanged).

Helper (optional, pair-local, may or may not ship):

- `gurdy/pairs/riscv_btor2/spec_helpers.py` — a tiny pure-Python
  function `trace_to_spec_patch(trace, *, flip_branch_at=None,
  pin_inputs=...)` that builds an `AssumptionSet` from a trace. This
  is not a tool; it's a convenience. It composes, it doesn't
  orchestrate.

Tests (replaces the old plan's seven test files with five):

- `tests/pairs/riscv_btor2/test_partial_binding.py` — per-instruction
  unit tests that the shadow records the right BTOR2 term.
- `tests/pairs/riscv_btor2/test_shadow_crosscheck.py` — soundness
  anchor: every fully-pinned binding produces a trace byte-identical
  to today's simulator (back-compat) **and** every partially-pinned
  binding, when concretized to its actually-taken values, produces
  the same trace.
- `tests/pairs/riscv_btor2/test_branchpin_dualrole_translation.py` —
  golden tests for `BranchPin` lowering and `dual_role=True`
  emission, including the `paired_with_nid` annotation link.
- `tests/pairs/riscv_btor2/test_schema_v10_backcompat.py` —
  byte-identical compilation for v1.0.0-shaped specs under v1.1.0.
- `tests/integration/test_propose_check_loop_smoke.py` —
  end-to-end: propose a `CycleInvariant` with `dual_role=True`,
  falsify with a concrete `simulate`, refine with a partial binding,
  escalate one surviving candidate to z3-bmc, lift the witness.
  No `concolic_explore` is invoked because none exists.

Examples + bench:

- `examples/05_partial_binding.py` — shortest script that pins some
  inputs, leaves others free, and prints the recorded path terms.
  (The file number replaces the old plan's `05_concolic_explore.py`;
  the script is shorter because there's no new tool to demonstrate.)
- `examples/06_propose_check_loop.py` — propose a `CycleInvariant`
  with `dual_role=True`, falsify, refine, dispatch.
- `bench/propose_check/` — same three-program corpus shape the
  old plan asked for (true / false-with-short-CEX / inductive-only),
  using the unified primitives.

## 6. Phased implementation

Each phase ships green tests and a usable system. No phase relies on
later phases.

### Phase 0 — SCHEMA.md §14 and a one-paragraph patch to PLAN.md

The bottleneck. No code until the schema is internally consistent.

Cover:

- The set-of-runs framing of `QuestionSpec` (one paragraph; the rest
  is mechanics).
- "Free" semantics for binding fields and the per-pair `Free`
  sentinel convention.
- Term-shadow contract: at every handler, what BTOR2 sub-term the
  shadow must record. One row per instruction class.
- `BranchPin` indexing (step-based, soft no-op if not reached).
- `dual_role` flag semantics and the `paired_with_nid` annotation
  link.
- Volatile-layer stability profile and ordering in the layer tuple.
- Memory-at-free-address: concretize-and-record via a branch-pin
  on the equality, lowered to a `constraint` clause in `volatile`.
- Soundness contract: every concretization of a partially-pinned
  binding reproduces the plain simulator step-for-step; every
  recorded term is entailed by the whole-program encoding along the
  same path.

Plus a one-paragraph addition to `PLAN.md` "Architectural commitments"
articulating that a spec describes a set of program runs and that the
question compiler operates on it — in language-agnostic terms.

Exit: an LLM could, from §14 alone, predict the BTOR2 lowering of any
partial binding + branch-pin + dual-role combination.

### Phase 1 — Spec extensions (no interpreter change)

1. `BaseAssumption.dual_role: bool = False` in `core/spec/base.py`.
2. `BranchPin` in `riscv_btor2/spec.py`.
3. Spec validator updates: `BranchPin.step >= 0`; `dual_role` only
   meaningful on `CycleInvariant` for v1.1.0.
4. v1.0.0 back-compat regression test green.

Exit: specs accept new vocabulary; old specs compile byte-identical.

### Phase 2 — Translation: volatile layer and dual-role

1. New `volatile.py` emitter.
2. Layer tuple in `__init__.py` gains `volatile` between
   `constraint` and `bad`.
3. `BranchPin` lowers into `volatile` as a clause asserting
   `(branch_cond at step) == taken`.
4. `dual_role=True` on a `CycleInvariant` emits one clause in
   `constraint` and one negated paired clause in `volatile`, linked
   via `paired_with_nid`.
5. Bump `schema_version` to `1.1.0`. Document in SCHEMA.md §0.
6. Golden tests green; back-compat regression green.

Exit: `compile` accepts a spec with `BranchPin`s and `dual_role`
clauses and produces a v1.1.0 artifact that dispatches successfully.

### Phase 3 — Partial bindings (no shadow yet)

1. `RiscvInputBinding` accepts `Free` (or `None`) as a per-field
   value.
2. Plain interpreter raises a clean diagnostic on any free field.
3. Spec hash includes the free-field positions (already true via
   `canonical_bytes`).

Exit: the binding type is general; nothing yet exercises the free
positions.

### Phase 4 — Term-shadow interpreter

1. Threaded `shadow` parameter on the interpreter, optional.
2. `source_interp/shadow.py` with one shadow handler per
   instruction class; reuses `library.py` lowerings so the term
   shadow and the whole-program encoding share a single source of
   truth (the soundness anchor).
3. `SourceStep.deltas` carries optional `branch_term` and
   `address_term` entries when free fields are present.
4. Memory-at-free-address: shadow concretizes the address and
   appends a synthesized `BranchPin` to the trace's recorded
   constraints.
5. Cross-check test: fully-pinned bindings produce byte-identical
   traces to today's simulator.

Exit: a partial binding produces a `SourceTrace` whose deltas record
BTOR2 terms; the cross-check test is the soundness anchor and must be
step-for-step.

### Phase 5 — Helper, examples, bench, lift adjustments

1. `spec_helpers.trace_to_spec_patch` (pair-local; not a tool).
2. `examples/05_partial_binding.py`, `examples/06_propose_check_loop.py`.
3. `bench/propose_check/` with the three-program corpus.
4. Lifter recognizes `volatile`-layer `bad` nodes the same way as
   `bad`, with `paired_with_nid` used to phrase the violation as
   "assumed invariant ⟨P⟩ violated."

Exit: `pytest -q` green; both examples run end-to-end; the bench
produces a stable summary table.

### Phase 6 — Documentation, retirement, deletion

1. `PAIRING.md §11` updated: partial bindings as part of the
   interpreter contract; no separate "concolic" contract.
2. `PLAN.md` "Architectural commitments" sub-section finalized.
3. `README.md` updated: surface the **"question compiler"** framing
   explicitly in "What hurdy-gurdy does" (today it's implicit in the
   `compiles (QuestionSpec, source program)` phrasing). One short
   sentence — the README is reader-facing and should not carry the
   `BMC = concolic = simulation` reframing in detail, only the noun.
4. `PLAN-CONCOLIC-CANDIDATES.md` **deleted** in the same commit
   that lands phase 5 (if not already deleted earlier).
5. **This file deleted** in the same commit. The unified design
   lives in the canonical docs.
6. Retrospective bullet at the bottom of `PAIRING.md §15` only if
   `python-smtlib` (or another pair) has also adopted partial
   bindings. Otherwise leave it; one data point is not evidence.

Exit: the repository contains no `PLAN-CONCOLIC-*.md`. The history
of the unification is in the git log and in the schema document.

## 7. What this plan does **not** add

Reproduced so the implementing session does not re-derive them:

- No `concolic_interpreter` field on `Pair`.
- No `concolic_explore` tool, CLI verb, or core module.
- No `Candidate*` directive types.
- No "candidate layer." (The `volatile` layer is general, not
  candidate-specific.)
- No new term grammar. Path conditions live in the existing BTOR2
  grammar (this was already settled in the old plan; reaffirmed).
- No framework-level orchestration. The propose-and-check loop is
  composed by the LLM and demonstrated in `examples/06_*`.

## 8. Invariants the implementer must not break

1. **Byte-identical v1.0.0 specs.** Any spec not using new vocabulary
   compiles to byte-identical artifacts under v1.1.0. Enforced by
   regression test.
2. **Byte-identical fully-pinned traces.** A `SourceTrace` produced
   from a fully-pinned binding under `interpreter_version` v(N+1)
   matches one produced under v(N), modulo trace metadata fields
   that are explicitly absent in v(N). Enforced by golden test.
3. **The framework does no reasoning.** Same as `PLAN.md`. The
   set-of-runs framing is a *re-description*, not a new policy.
4. **The schema is authoritative.** As always.
5. **No IR.** Terms are BTOR2; predicates parse to BTOR2.

## 9. Risk register

- **Shadow drift from `library.py`.** Mitigation: shadow handlers
  call the same lowering helpers as `library.py`. A dedicated
  cross-check test runs the BMC encoding and the shadow side-by-side
  on a fixture corpus and asserts agreement.
- **Spec-hash churn.** Each unique binding produces a new hash; each
  per-question volatile-layer clause changes its hash. Mitigation:
  the lower layers (`header`, `machine`, `library`, `dispatch`,
  `init`, `constraint`) stay stable across questions and are cached.
- **Annotation `paired_with_nid` drift.** If the link between
  paired clauses is broken, lift produces ambiguous traces.
  Mitigation: emit and assert the link in golden tests.
- **`Free` sentinel semantics.** Picking `None` as "free" collides
  with pythonic defaults. Mitigation: introduce an explicit `Free`
  sentinel in the pair, documented in SCHEMA.md §14.

## 10. What "done" looks like

- `gurdy compile` accepts specs with partial bindings, branch pins,
  and dual-role predicates; produces v1.1.0 artifacts.
- `gurdy simulate` accepts a partial binding and produces a trace
  whose deltas carry BTOR2 terms.
- The propose-and-check loop runs end-to-end in
  `examples/06_propose_check_loop.py` using only the existing tool
  surface plus the pair-local helper.
- `pytest -q` is green; the v1.0.0 back-compat regression test is
  green; the term-shadow cross-check is green step-for-step.
- `bench/propose_check/` has at least one captured run.
- `PLAN-CONCOLIC-CANDIDATES.md` and `PLAN-NATIVE-CONCOLIC.md` are
  both deleted; their content has been absorbed into `SCHEMA.md
  §14`, `PLAN.md`, `PAIRING.md §11`, and `README.md` (which names
  the system a "question compiler").

When all seven bullets hold, this plan has terminated successfully —
*by erasing itself*.

## 11. Hand-off notes for the implementing session

- Start in `gurdy/pairs/riscv_btor2/SCHEMA.md §14`. Do not write any
  code until §14 is drafted and self-consistent. The phase-0 prose
  is the bottleneck; everything else is mechanical.
- After §14 is drafted, write the term-shadow handlers next. They
  must call the same lowering helpers as `library.py` so the shadow
  and the BMC encoding cannot diverge.
- If you find yourself reaching for a "concolic-only" abstraction
  (a separate interpreter, a separate tool, a separate spec
  vocabulary), stop. The whole point of this plan is that those
  abstractions are not needed. Re-read §1.
- If a design question not listed in §4 arises, write it down in
  this file under §4 with a brief discussion, decide, and proceed.
- Phase 6 deletes both planning documents. Do this only after every
  exit criterion above is met and the canonical docs (`PLAN.md`,
  `PAIRING.md`, `SCHEMA.md §14`) carry the full design. The
  deletion is the *test* that the unification is complete: if
  anything important would be lost by deleting these files, the
  unification is not yet done.
