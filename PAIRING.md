# Adding a new pair to gurdy

This document describes what it takes to add a new (source language,
reasoning language) pair to hurdy-gurdy, to the extent that is known
now. Only one pair is fully built (`riscv-btor2`) and one is planned
(`python-smtlib`). Most of what follows is generalized from a single
data point and should be read as guidance, not law. The document will
evolve as more pairs are built; sections marked **[likely to evolve]**
are the places where current advice is most likely to be revised.

For background, read `README.md` and `PLAN.md` first. For benchmarking
a new pair, see `BENCHMARKING.md`.

## 1. What a pair is

A pair is a fixed combination of one source language and one reasoning
language with a documented translation between them. It is the unit
that produces meaningful output in hurdy-gurdy. Each pair is
independent: pairs share the framework but not their semantics. There
is deliberately no intermediate representation between source and
reasoning — the rationale is in `PLAN.md` under "Architectural
commitments, point 2."

A pair is exposed to the framework as one `Pair` object registered in
its package's `__init__.py`. That registration is the pair's entire
public surface to the framework.

## 2. What the framework gives you

You inherit, automatically:

- The translator-layer LLM surface — `describe`, `compile`, `dispatch`,
  `lift`, `introspect` — and the `gurdy` CLI mirroring it. Pairs that
  declare an `interpreter_version` (see §11) additionally inherit the
  interpreter-layer surface — `simulate`, `evaluate`, `cross_check`,
  `replay`, `check` — gated on the pair-supplied interpreter callables.
- `BaseSpec` and friends, with structural validation, serialization,
  and content hashing.
- The annotation sidecar: data types, persistence, lookup engine.
- The layered artifact format and a generic linker that resolves
  cross-layer names.
- `SolverBackend` Protocol with subprocess and in-process helpers,
  timeout enforcement, and a structured `RawSolverResult`.
- Content-addressed caching keyed on
  `(spec_hash, source_hash, schema_version)`.
- Schema-document indexer that parses your `SCHEMA.md` and serves
  entries via `describe`.
- Diagnostics, provenance threading, and `LearnedFact` plumbing.

You do not write any of these. If you find yourself wanting to, the
pair protocol is probably wrong — fix the protocol, not the framework
(see `PLAN.md` working note 7).

## 3. What you must build (the irreducible six)

Every pair, regardless of source/reasoning languages, ships these:

1. **Source loader.** Bytes → an in-memory model of the source
   program. Format-specific (ELF+DWARF, Python AST, …).
2. **`SCHEMA.md`.** The contract. Every translation rule from source
   semantics to the reasoning language, every state-variable
   convention, every default added at translation time. The largest
   deliverable in most pairs.
3. **Spec vocabulary.** A subclass of `BaseSpec` and pair-specific
   `Observable`, `Assumption`, `Property`, `AnalysisDirective`
   types. This is the LLM-facing question language.
4. **Translation function.** `(spec, source) → CompiledArtifact`.
   Implements `SCHEMA.md` mechanically; does no reasoning, makes no
   adaptive choices.
5. **Lifter.** Raw solver output → source-grounded structured facts,
   using the annotation.
6. **Solver wrappers.** Shallow `SolverBackend` subclasses for the
   engines compatible with your reasoning language.

Plus: a reasoning-language in-memory model with text I/O (you almost
certainly need to read and emit the reasoning language's text format).
For `riscv-btor2` this is `gurdy.pairs.riscv_btor2.btor2`; for an
SMT-LIB pair it would be an SMT-LIB AST + parser/printer.

## 4. Recommended phase order [likely to evolve]

This ordering worked for `riscv-btor2` (phases 5–14 of `PLAN.md`).
The shape is probably general; the details certainly are not.

1. **Reasoning-language model + text I/O.** Round-trip golden tests
   first. Until this is byte-exact, nothing downstream can be trusted.
2. **Source loader.** Smallest possible API: enumerate the
   constructs the translator will need (functions, instructions,
   AST nodes, …) and locate them in source.
3. **Source decoder / parser.** For machine-code pairs, an
   instruction decoder; for high-level languages, the AST is
   typically already structured enough that this collapses into the
   loader. **[likely to evolve]** as non-machine-code pairs land.
4. **`SCHEMA.md`, written before the translation code.** This is
   non-negotiable. The schema is authoritative; the implementation
   follows it. Writing the schema first forces every translation
   choice to be made deliberately rather than emerging from code.
5. **Per-construct lowering library**, strictly implementing the
   schema. One function per source construct (instruction or AST
   node kind).
6. **A concrete witness simulator that mirrors the lowering
   exactly.** This is the soundness story for witness replay. The
   library and the simulator must agree on every concrete trace; a
   cross-check test enforces this. **[likely to evolve]** —
   high-level-language pairs may need a different soundness story
   (e.g., re-execution against a real interpreter rather than a
   purpose-built simulator). Open question.
7. **Spec language.** Now that the lowering vocabulary is concrete,
   you can name the observables, assumptions, and properties an LLM
   should be able to express.
8. **Translation pipeline,** layer by layer. Use the framework's
   annotation emitter throughout. Golden tests for each layer.
9. **Solver wrappers.** One per engine. Keep them shallow — they
   wrap `SolverBackend`, they don't reimplement it.
10. **Lifter.** Witness replay through the simulator; invariant
    re-naming through the annotation.
11. **Registration.** Assemble the `Pair` object, call
    `register_pair`, ship a smoke test that exercises the full
    LLM tool surface from a fresh import.
12. **Examples and benchmark.** See §13.

The bottleneck phase is consistently **the schema document**. Budget
generously. Do not start the translation pipeline until the schema
covers every construct you will lower.

## 5. Schema-first discipline (settled)

Two rules apply to every pair:

1. **Code follows schema.** If the implementation and `SCHEMA.md`
   disagree, the implementation is wrong. (If the schema is wrong,
   that is a versioned change — bump `schema_version` and
   invalidate caches.)
2. **The LLM-predictability invariant.** For any
   `(spec, source, schema_version)`, an LLM that has read the spec,
   the source, and the schema must in principle be able to predict
   the reasoning artifact byte-for-byte. No internal state, no
   learned heuristics, no adaptivity at translation time. Anywhere
   the framework or pair would otherwise make a heuristic choice,
   that choice becomes either schema-documented and fixed forever,
   or a spec parameter the LLM specifies. There is no third option.

This invariant is the architectural test. When in doubt, ask:
*would removing this code make hurdy-gurdy simpler without changing
what an LLM could in principle do?* If yes, the code shouldn't be
there.

## 6. Naming and registration conventions (settled)

- The pair's public identifier is a kebab-case string:
  `riscv-btor2`, `python-smtlib`. Use the form `<source>-<reasoning>`.
- The Python sub-package uses the underscored form:
  `gurdy/pairs/riscv_btor2/`.
- The pair registers itself in its `__init__.py` via
  `register_pair(PAIR)`.
- Bump `schema_version` (semver) on any change that affects the
  byte-level reasoning artifact for any spec. Cached compilations
  are tagged with the version they were produced under.

## 7. Layer declarations and cross-layer references [likely to evolve]

A pair declares its own layer set via `LayerSpec`. The `riscv-btor2`
layers (header / machine / library / dispatch / init / constraint /
volatile / bad / binding / havoc) are documented in `PLAN.md` and are
*one example*, not a template. Other pairs will factor differently
according to what is stable and what changes per question. The
``volatile`` layer in particular was added in v1.1.0 specifically to
absorb per-question churn (branch pins, dual-role bad clauses) so
that the more expensive lower layers stay content-stable; whether
other pairs need an analogous churn-isolation layer is **open**.

Two practical guidelines, drawn from the one pair we have:

- **Stratify by stability.** The bottom layers should change rarely;
  the top layers change per question. The LLM will issue many
  questions about one source program, and incremental compilation
  caches the bottom layers across questions.
- **Cross-layer references go through symbolic names.** The pair
  registers a small parser/printer with the framework's linker to
  describe its export/import directive syntax. For BTOR2 that's
  `;@export` / `;@import` comments; SMT-LIB or other reasoning
  languages will need their own convention.

How many layers a high-level-language pair needs, and whether stability
stratification looks the same, is **open**.

## 8. Determinism contract (settled)

- The translation function is pure: same `(spec, source,
  schema_version)` produces a byte-identical `CompiledArtifact`.
- Caching depends on this. So does the benchmark playbook's
  determinism check (see `BENCHMARKING.md` §7).
- Sources of accidental nondeterminism to watch for: dictionary
  iteration order in older Python, hash randomization in symbol
  emission, file-system ordering when the source loader walks
  directories, time/date stamps in any emitted comment. None of
  these belong in artifact bytes.

A small re-compile-and-diff test is cheap and worth shipping with
every pair.

## 9. Soundness and witness replay [likely to evolve]

For `riscv-btor2`, the soundness story is: the BMC encoding and a
concrete simulator share a single source of truth (the per-instruction
lowering), and a cross-check test runs both on the same instruction
sequences and asserts agreement. Witnesses produced by the solver are
replayed through the simulator to produce source-tagged traces.

For a high-level-language pair, this approach may not scale: writing
a Python interpreter that mirrors an SMT-LIB encoding is much harder
than writing a RISC-V simulator that mirrors a BTOR2 encoding. Likely
alternatives:

- Re-execute the witness against the language's real interpreter and
  compare observable state.
- Restrict the source language to a subset whose semantics are simple
  enough to mirror in a small simulator.
- Define soundness only at the property level: a witness is sound if
  the property fails when the witness is concretized and the
  program executed.

This section is the largest open design question for the second pair.
Whichever option the second pair chooses, it should document its
soundness story explicitly in `SCHEMA.md` and link it from here.

## 10. Solver inventory (settled, with caveat)

Each pair declares a `solvers: Mapping[str, type[SolverBackend]]`. The
LLM picks an engine via `AnalysisDirective.engine`. Two practical
notes:

- Optional solvers should `ImportError`-guard their imports and
  `shutil.which`-guard subprocess solvers. The pair should be
  installable and usable with only one engine present.
- The `RawSolverResult.payload` is *pair-specific*. Document its
  schema in `SCHEMA.md` (witness format, invariant format, …) so
  the lifter has a stable contract to consume.

Caveat: the right division of labor between the pair-specific solver
wrapper and the framework's `SolverBackend` is **likely to evolve** as
more reasoning languages are wired up.

## 11. Source and reasoning interpreters [likely to evolve]

A pair *may* declare a deterministic concrete interpreter for its source
language and a deterministic step-evaluator for its reasoning language.
Together with a *projection* that maps both into a comparable post-step
view, these unlock the framework's interpreter-layer tools: `simulate`,
`evaluate`, `cross_check`, `replay`, and `check`. The framework gates
each tool on the pair fields it needs, so a pair without interpreters
remains usable through the original five translator-layer tools.

The contract is opt-in by version:

- If `Pair.interpreter_version` is non-empty, the pair MUST supply
  `source_interpreter` and `reasoning_interpreter`. Registration enforces
  this.
- `projection` is required to use `cross_check`, but is checked at tool
  call time, not at registration.
- `witness_replayer` is optional and gates `replay`.
- `predicate_evaluator` is optional and gates `check`.

Concretely, for `riscv-btor2`:

- `source_interpreter` runs the RV64 simulator over a `RiscvInputBinding`
  (initial register / memory state, max steps, halting predicate).
- `reasoning_interpreter` evaluates BTOR2 transitions under a
  `Btor2ReasoningBinding` (initial state values keyed by symbol,
  per-step inputs).
- `projection` compares post-step `pc`, `reg_x{N}` for `N ∈ 1..31`, and
  `halted` between the two traces.
- `witness_replayer` decodes the Z3 witness payload and replays it
  through the source interpreter.
- `predicate_evaluator` evaluates the spec's observables, assumptions,
  and properties on a concrete `SourceTrace`.

See `gurdy/pairs/riscv_btor2/SCHEMA.md §13` for the post-step convention,
the supported predicate grammar, and the cross-check correspondence.

**Partial bindings.** A pair's source interpreter may accept binding
cells whose value is a per-pair sentinel meaning "this input is
symbolic" (the `riscv-btor2` pair calls the sentinel `FREE`). When
the interpreter is run with `record_shadow=True`, free cells are
concretized to a documented default for execution and the interpreter
records per-instruction events (branch taken/not-taken, memory
accesses, the inventory of free cells) on the trace's
`final_state["shadow"]`. The events are consumed by a pair-local
helper that synthesizes a follow-up spec from the recorded prefix —
the concolic-style "same path, opposite at step k" pattern. The
pair's `SCHEMA.md` documents which cells admit the free sentinel,
the default concretization, and the soundness contract (typically:
running the plain interpreter on the same binding with free cells
pinned to the default reproduces the shadow run's trace
step-for-step). For `riscv-btor2`, see SCHEMA.md §14.

Whether high-level-language pairs benefit from the same machinery —
or need a different shape — is **open**. The `riscv-btor2` design
exploits a clean separation between concrete execution and symbolic
state names; languages with first-class symbolic values may not need
a separate "shadow" mode at all.

Two practical guidelines from the one pair we have:

- **Post-step state convention.** Both interpreters record state
  *after* each transition. This keeps cross-check comparisons local
  and avoids off-by-one alignment bugs. A pair that prefers pre-step
  state must document the choice in its SCHEMA and ensure both
  interpreters agree.
- **Versioning.** `interpreter_version` is independent of
  `schema_version`: it bumps when the interpreter's observable
  behavior changes (e.g., a new halting condition, a wider set of
  supported predicates) without any change to the translation rules.
  Bumping it invalidates the interpreter cache without invalidating
  compilation caches.

How a high-level-language pair will populate these — whether the source
interpreter is the language's real interpreter, a subset interpreter,
or a property-level oracle — is **open** and connects to the soundness
discussion in §9.

## 12. Tests you must ship (settled minimum)

At a minimum, every pair ships:

- **Round-trip tests** for the reasoning-language model.
- **Per-construct lowering unit tests.**
- **Lowering / simulator cross-check** (or the pair's chosen
  soundness check; see §9).
- **Golden tests** for the translation pipeline: small
  `(spec, source) → expected (layers, annotation, flattened)`
  fixtures, byte-identical on re-compile.
- **Layer-reuse tests:** changing only the volatile layers' inputs
  produces new top layers but identical bottom layers.
- **Linker tests** through the pair's cross-layer reference syntax.
- **End-to-end smoke test** exercising the full LLM tool surface
  from a fresh import.
- **Determinism check** (see §8).

The benchmark corpus (next section) is *not* a substitute for these.
Tests verify correctness; the benchmark evaluates effectiveness.

## 13. Examples, documentation, and benchmark

Three deliverables on top of the irreducible six:

- **Examples.** A handful of short scripts demonstrating common
  question shapes against the pair, runnable as smoke tests in CI.
  See `examples/` for the `riscv-btor2` set.
- **Documentation.** Make sure `SCHEMA.md` is reviewable as a
  self-contained specification of the encoding — sufficient for an
  LLM (or human) to predict the reasoning output for any well-formed
  spec. Reference it from the pair's package docstring and from
  this file's pair list once it lands.
- **Benchmark.** Instantiate `BENCHMARKING.md` §9 for the pair. A
  pair without a benchmark is a pair we cannot make claims about.

## 14. What to expect to discover [likely to evolve]

We do not yet know, for sure:

- Whether the irreducible-six list above is complete, or whether a
  high-level-language pair will surface a seventh thing.
- Whether the layer factoring of `riscv-btor2` generalizes, or
  whether each pair invents its own layer set with little overlap.
- The right soundness story for non-machine-code pairs (§9).
- Whether `LearnedFact` translation across pairs is even
  meaningful (a BTOR2 invariant referencing register state is not
  obviously a fact about the C source it came from, much less about
  a Python source).
- Whether the schema-document indexer's H2/H3 parsing convention
  scales to schemas with very different structure.

When the second pair lands, this document should be revisited
end-to-end. Sections marked **[likely to evolve]** are the most
likely to need rewriting; sections marked **(settled)** are the
ones we expect to keep.

## 15. A note on how this document evolves

This file is intentionally written from a single data point. As
each new pair lands:

1. Add a brief retrospective at the bottom: what surprised us,
   what the irreducible-six list missed, which **[likely to
   evolve]** tags were borne out and which were not.
2. Promote sections from **[likely to evolve]** to **(settled)**
   only when at least two pairs agree, not just because the latest
   pair worked a particular way.
3. Resist the urge to abstract prematurely. If three pairs do
   something three different ways, document the divergence; do
   not paper over it with an abstraction not yet earned. The "no
   IR" commitment in `PLAN.md` is the canonical example.

The aim is a document that gets *more* useful as it grows, by
recording what we have learned rather than by smoothing over the
disagreements between pairs.
