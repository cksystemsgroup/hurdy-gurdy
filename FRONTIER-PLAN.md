# Frontier plan — from instrument to cartographer

This is the working plan of branch `frontier`. Its destination is
[`FRONTIER.md`](./FRONTIER.md) taken literally: the current vision —
deterministic, fidelity-graded translations with quantified trust — is
demoted to the **means**, and the platform's product becomes the
**map**: benchmarks in, the frontier of reducible decidability in
practice out. The plan has three deliverables, in dependency order:

- **A. The facilitation argument** (§1) — how to prove, formally where
  the mathematics permits and informally where only assumptions can
  stand, that hurdy-gurdy's architecture facilitates exploring the
  frontier of reducible decidability in practice *in any given domain*.
- **B. Code and docs** (§2–§3) — the extensions that make the map
  mechanical (frontier pairs as the registry's third tier, saturation,
  way-census, the report, the loop driver, the mandate), the
  design-oracle instruments that read the far side, and the
  simplifications that keep the repository one story told once.
- **C. The new arXiv paper** (§4) — written fresh, frontier-first, all
  necessary sections except benchmarks, in the simplest form that
  carries the theorems of A.

Standing constraints: the POPL tree (`paper/main.tex`, unforked
sections, `appendix/body.tex`) stays frozen; the arXiv v3 fork stays
buildable; RAM discipline for any benchmark runs (stream one instance,
release, cap parallelism).

## 1. The facilitation argument

### 1.1 The claim, decomposed

> hurdy-gurdy's architecture facilitates exploring the frontier of
> reducible decidability in practice in any given domain.

"Facilitates exploring" is not one property; it is six, and each is a
statement an explorer must satisfy or it is not an explorer. The
decomposition is the proof plan:

| # | An explorer must… | Frontier theorem | Status |
|---|---|---|---|
| F1 | draw a map its untrusted explorer cannot falsify | **Unfalsifiable map** | mostly mechanized |
| F2 | never lose ground | **Monotone exploration** | mechanized at pair level; needs lifting |
| F3 | know, at every open point, what would extend the map *here* | **Complete local gradient** | new; formalizable |
| F4 | eventually reach every point inside the true frontier | **Relative completeness** | new; formalizable with named assumptions |
| F5 | know when a survey is finished | **Saturation is a decidable, reachable fixpoint** | new; formalizable + executable |
| F6 | work in any territory, not one | **Domain-genericity** | free formally; informal kit per domain |

Each theorem has a *sufficiency* half (the architecture has the
property) and a *necessity* half (drop the load-bearing feature and the
property fails). The necessity halves are the rows of
[`FRONTIER.md`](./FRONTIER.md) §3 turned into ablation arguments — they
stay informal, one paragraph each, and they are what makes "the current
vision is exactly the means" a claim rather than a slogan.

### 1.2 The model the theorems live in

Everything is stated over the **domain signature** and the **registry
state**, never over concrete languages — that is what buys F6.

- A **domain** `D` supplies: a set of languages with formal semantics
  (the membership rule, [`ARCHITECTURE.md`](./ARCHITECTURE.md) §1),
  their observables, a set of question shapes, a set of mechanized
  decision procedures with declared budgets `β`, and a (finite) supply
  of independent semantic anchors.
- A **registry state** `G` is a finite set of admitted pairs, each
  carrying its contract (projection `π`, direction, assurance class,
  measured cost) — exactly the `Contract` of the mechanization.
- A **question** `q = (p, φ)` is **answerable at `G`** iff five
  conditions hold, in order: **connectivity** (a route exists), **loss**
  (`φ`'s observables survive the route's `keep`), **shape** (`φ`'s form
  is solver-decidable at the destination), **cost** (a verdict other
  than `unknown`/`resource-out` within `β`), **trust** (the player's
  assurance floor is met). This is [`POTENTIAL.md`](./POTENTIAL.md) §1
  plus the fifth obstacle, made definitional.
- `Solved(G)` is the answerable set with evidence attached;
  `Frontier(G)` is its boundary: the open questions with their first
  failing obstacle.
- The **candidate universe** `U` is the enumerable set of registerable
  reductions (pairs over the domain's languages, endo-pairs included,
  identified by *target signature*: source, target, projection delta,
  direction). The **gate** is an acceptor over `U`.
- A **benchmark** `B` is a pinned finite set of questions
  ([`BENCHMARKS.md`](./BENCHMARKS.md) §4).

The five conditions are **exhaustive by construction**: answerability
is *defined* as their conjunction, so every unanswerable question has a
well-defined first failing condition. That single definitional move is
what turns the demand taxonomy from a design choice into a theorem
input — the diagnosis (`why_not`) is a *total function* on the open
set, not a heuristic.

### 1.3 The six theorems, with proof obligations

**F1 — Unfalsifiable map (soundness).** Whatever the generator does —
blind or adversarial — the map's labels are truthful: (i) every
existential answer is true at the source, assuming only source-
interpreter adequacy (`existential_self_certifying`, axiom-free);
(ii) every universal answer carries exactly the assurance class,
direction, and TCB computed by the componentwise meet of its route
(`weakest_link_universal`, `Contract.comp_glb`,
`lax_universal_transfer`) — the label never overstates, because meets
never exceed their arguments. *New obligation:* one wrapper statement
("map soundness": a solved-entry's label is a lower bound on its
evidence) assembling the existing lemmas; small.
*Residue, stated not hidden:* the uncorroborated-universal corner
([`SCALING.md`](./SCALING.md) §2) — bounded empirically by the
escape-rate experiment, shrunk by branches and negative controls,
never proved away.

**F2 — Monotone exploration.** `G ⊆ G'` implies
`Solved(G) ⊆ Solved(G')` and every standing verdict stands. The
mechanization has the pair-level ratchet
(`ratchet_preserves_faithful`, `ratchet_coverage_mono`); *new
obligation:* lift to the answerable set — adding an edge adds routes
and removes none, so each of the five conditions is monotone in `G`.
Easy induction; mechanize.

**F3 — Complete local gradient.** For every `q ∉ Solved(G)`:
(i) *totality/correctness* — the diagnosis returns the first failing
obstacle (immediate from §1.2's definition once `why_not` is modeled
as the first-failure function); (ii) *relevance* — the named
generation target, if admitted, strictly weakens that obstacle for
`q`; (iii) *progress* — per question, the index of the first failing
obstacle never decreases along the loop (by F2), and each targeted
admission either solves `q` or strictly advances the index or moves
the demand outside the known set. So per question the in-set diagnosis
chain is finite. *New obligation:* mechanize (i)–(iii) over the
abstract model; this is the platform's "self-directing" property made
precise.

**F4 — Relative completeness (the semi-algorithm claim of
[`POTENTIAL.md`](./POTENTIAL.md) §7, proved rather than asserted).**
Assume (a) **fair enumeration**: every demanded target is eventually
attempted (the books plus `recommendations` plus a human or mandate
that eventually acts on standing demand); (b) **gate liveness**: a
sound candidate with adequate evidence is eventually admitted (builder
competence — an empirical premise, measured by the SCALING pipeline,
never provable); (c) fixed budgets `β`. Then every question answerable
at *some* finite extension of `G` within `U` is eventually in
`Solved`. Proof shape: induction on the length of the reduction chain
that witnesses answerability, using F3(ii) to show the loop's demands
trace the chain and F2 to keep every step. *New obligation:* mechanize
the induction over an abstract loop; state (a) and (b) as hypotheses —
they are the theorem's honest TCB, and they are exactly what
[`SCALING.md`](./SCALING.md) exists to supply in practice.

**F5 — Saturation is a decidable, reachable fixpoint.** For a pinned
finite `B` and the finite in-set pool of target signatures (finitely
many registered languages, solvers, observable fields, directions):
(i) the saturation predicate of [`FRONTIER.md`](./FRONTIER.md) §1 —
every `q ∈ B` solved-all-ways or open with only out-of-set targets —
is computable from the books; (ii) the loop restricted to in-set
targets reaches it in finitely many iterations (each iteration retires
at least one in-set signature — dedup by signature plus the ratchet
forbid recurrence — and the pool is finite). *New obligations:*
mechanize the finite-combinatorics argument; make the predicate
executable (`gurdy saturation`, §2.1/C4). "All ways" is where the
way-census enters: the terminal state quantifies over the *known set*,
which is what keeps it decidable — reopening on good news (a new
solver, anchor, logic) is the intended non-monotonicity *of the pool*,
not of the solved set.

**F6 — Domain-genericity.** The Lean development is already parametric
in languages, behaviors, observables, and projections (abstract types
in `Basic.lean`); F1–F5 add nothing domain-specific, so the theorems
transfer to any domain by instantiation. What does *not* transfer for
free is the supply side, and honesty requires saying so: per domain,
the architecture needs the **domain kit** — (1) at least one reasoning
hub with a mechanized decision procedure and declared budgets, (2)
deterministic shared interpreters for each language touched, (3) at
least one external semantic anchor if trust beyond `checked` is
wanted, (4) a pinned benchmark to aim the loop at. The kit is a
checklist, not a theorem; the theorems are conditional on it, and the
books *measure* the condition (anchor census, `resource-out` rates,
`unmeasured` honesty). "In any given domain" therefore means: **for
any domain supplying the kit, the loop is a sound (F1), monotone (F2),
self-directing (F3), relatively complete (F4) explorer whose surveys
terminate detectably (F5)** — and the registry's own field-blind
corners (SMILES, CRN) are the cheap existence proof that the kit is
instantiable outside the C/RISC-V heartland.

### 1.4 Necessity ablations (the means, shown to be needed)

One short argument per load-bearing feature, mirroring the
[`FRONTIER.md`](./FRONTIER.md) §3 table: without determinism the
square check cannot distinguish defect from coin flip and F1 falls;
without the ratchet F2 falls and the curve can regress; without the
typed-abort/first-failure discipline the gradient (F3) degenerates to
blind enumeration; without the asymmetry (replay of existentials) an
untrusted generator forges map entries and F1 falls adversarially;
without pinned ingestion "the benchmark" is not a fixed set and F5 is
undefined; without the human valve (or its mandate generalization) the
enumeration in F4 has no scope and the books no meaning. These are
paper prose, not mechanization.

### 1.5 The far side as a design oracle

By the honest-failure discipline, an open question is not
"unanswered" — it is a bundle of typed evidence, and each obstacle
class comes with its own **extraction operator** turning that
evidence into a design specification for the missing instrument:

| Obstacle | Evidence on the books | Extraction operator |
|---|---|---|
| shape | the blocked `φ`s verbatim | **fragment hull**: cluster the forms (theory symbols, quantifier structure, bit-widths), locate the hull in the fragment atlas (§2.2/O1), name the feature crossing to the nearest decidable fragment |
| cost | resource-out traces with measured curves | **binding-parameter fit**: which parameter (unrolling depth, state bits, theory mix) the wall is exponential in — each fingerprint maps to a remedy family (unbounded engine, localization abstraction, native procedure) |
| cost, via `over` hops | the spurious-counterexample corpus | **separating predicates**: what discriminates spurious from real across the corpus is the precision contract of the missing abstraction pair — CEGAR's refinement signal, persisted across questions instead of reset per solver run |
| trust | uncorroborated verdicts, by (engine, witness kind) | **certificate joins**: the missing checker, certifying wrapper, or new-artifact leg, named mechanically |
| outside the closure | the wall itself | **nearest in-closure relaxation**: the property transformation (bounded inputs, weakened `φ`, a monitor) that would pull the question to the boundary — a lax square on the *property* side, dual to abstraction's lax square on the program side |

Three cross-cutting instruments sharpen the operators:

- **Scouting.** Whether a demanded fragment wants a native procedure
  or a reduction into an existing fragment is measurable before
  either is built: run prototype encodings of the open cluster and
  record the blowup. Polynomial on samples → demand the pair; every
  embedding explodes → demand the native procedure, with the measured
  explosion as the justification. Failed scouts still deposit cost
  evidence; a `scout` origin (beside `organic`/`campaign`) keeps them
  from laundering into demand.
- **Active probing.** Parameterized question families straddling the
  boundary (sweep state bits, depth, quantifier structure) measure
  the frontier as a response surface; its gradient says which
  parameter the missing procedure must tame — before it is designed.
- **Re-parameterization.** A demand cluster incoherent in current
  coordinates may be one point in better ones. The signal is players
  repeatedly hand-composing the same multi-hop reduction — the
  no-hidden-IR rule surfacing at ecosystem level; mining sessions for
  such motifs yields depth demands that failure analysis alone would
  never name.

One audit closes the loop on the guidance itself: every
recommendation is a **prediction** ("this target closes demand set
D"), checkable ex post by the ratchet — realized closure vs
predicted, the shadow-ledger discipline applied to design advice
(§2.2/O4). A recommender whose predictions are never checked is
exactly the kind of unaudited oracle the platform exists to refuse.

### 1.6 Frontier pairs — pairs and routes as the one currency

Saturation should not emit a report vocabulary *beside* the
registry's — it should emit **pairs**. The registry then holds three
tiers of one lifecycle, and the books become the evidence stream
*behind* the third tier rather than a parallel currency:

```text
frontier ──register (human/mandate)──▶ registered ──build+gate──▶ partial ──▶ built
(design unknown; required contract     (design known: the brief's   (achieved contract,
 + the §1.5 payload, derived            "intended translator"        measured)
 from the books)                        filled in)
```

- **Contract duality.** An implemented pair carries an **achieved**
  contract, verified from above; a frontier pair carries a
  **required** contract, demanded from below — the join over its
  citing questions on observables, direction, and assurance, with
  cost kept as the *histogram* of citing budgets (a design may target
  a quantile; the ratchet absorbs partial closure). Same lattice,
  used from both sides. Registering a frontier pair *means*
  exhibiting a design whose achievable contract dominates the
  required one; the gate then verifies the achieved contract,
  unchanged. The valve does not move: frontier→registered *is*
  registration, the human act of [`AGENTS.md`](./AGENTS.md) §1.
- **Typed holes.** A shape-blocked frontier pair may name a
  **hypothetical** target — a language sketch (name, needed question
  shapes), not a registered language. That is what a missing
  reasoning language is, stated honestly in the graph.
- **Conditional routes.** Routes may mix implemented and frontier
  hops (opt-in in enumeration, like endo-hops): the composed contract
  is the meet over achieved hops, *conditional on* each frontier hop
  achieving its requirement. One object then carries what works, what
  is pending, what is missing, and exactly what the missing piece
  must satisfy. ROI becomes graph-native — a frontier pair is priced
  by the questions its completed routes would unlock, chains included
  — and F4's chain induction becomes executable: hypothetical routes
  materialize the chains `why_not` would otherwise discover one hop
  at a time.
- **F5, restated.** A benchmark is saturated exactly when the
  pair-shaped objects its questions derive contain **no tier-2
  candidate** — only frontier pairs. The terminal board *is* a set of
  frontier pairs partitioned by obstacle; the fixpoint predicate is
  an emptiness check on a derived set.
- **Two new lemmas** (companions to F1/F2): the **status ratchet** —
  a pair's tier only advances, its evidence payload traveling with
  it, so a finished pair carries its causal history from demand
  through design evidence to measured closure; and
  **conditional-plan soundness under discharge** — if every frontier
  hop is discharged by a pair whose achieved contract dominates its
  requirement, the realized route contract dominates the conditional
  one (monotonicity of the meet; cheap in `Contract.lean`).
- **Two honest strains, stated not blurred.** (i) Not every demand is
  edge-shaped: solver advances, checkers, and anchors attach to
  *languages* (frontier **capabilities**), not edges — the currency
  claim holds at the **route** level, since a route composes its
  edges with its destination's capabilities. (ii) The outermost wall
  names nothing: an outside-the-closure question may carry no honest
  frontier pair, and the board must be allowed to say so
  ([`POTENTIAL.md`](./POTENTIAL.md) §5).
- **Guard rails.** Frontier pairs are **derived, never stored**: a
  pure function of (registry, ledger) — an advisory read under S3 —
  materialized in `gurdy saturation` output and the pinned report,
  written under `pairs/` only by the human act of promotion. No
  execution through a frontier hop: `translate`/`cross_check` refuse
  them at the type level. Identity is the target signature, which is
  what lets frontier pairs **compound across benchmarks**: the next
  benchmark's derivation starts from pairs already enriched by the
  last one's evidence — [`FRONTIER.md`](./FRONTIER.md) §6's
  compounding maps, carried by the currency itself.

### 1.7 Mechanization work items

Extend `paper/mechanization/` (no mathlib, audit discipline intact).
*Pruned at Phase 1:* designed from scratch, the planned
Registry/Diagnosis/Loop trio collapses into **one file** — the model
is a single structure (answerability as a filtration of admitted
candidate lists through `N` ordered conditions), and F2, F3, and the
chain lemma are consequences of its two monotonicities. No behaviors,
no interpreters: the calculus is the instrument's theory, consumed as
an interface, never re-derived.

- `Calculus/Frontier.lean` *(landed — registries, the filtration,
  F2 `answerable_mono`, F3 `diagnosis_total`/`unique`/`progress`/
  `strict_progress`, the F4 seed `adequate_chain_answerable` (N
  adequate extensions answer the question — the chain induction the
  plan scheduled for Phase 4, already done; what remains of F4 is
  stating fairness + gate liveness as the hypotheses that supply the
  chain), the tier ratchet `lifecycle_ratchet`, and
  `conditional_plan_sound` over `Contract` with the new
  `Contract.comp_mono`)*. Axiom footprint per the audit:
  monotonicity and the ratchet axiom-free; the diagnosis-order and
  plan lemmas `propext`/`Quot.sound`; `diagnosis_total` and the chain
  lemma are the model's classical pair, documented.
- Still to add (Phase 3, same file): the finite-pool fixpoint (F5),
  stated as tier-2 emptiness.
- `Calculus/Audit.lean` — *(landed)* extended to the nine new
  theorems.

Statements and mechanization stay in lockstep: the paper's §2 and §5
(`paper/frontier/sections/problem.tex`, `theorems.tex`) cite the Lean
names inline, and a statement without a Lean name says where its
content lives instead.

## 2. Code — extend, then simplify

### 2.1 Extensions — the mechanics of the map

| # | Item | Contract | Acceptance |
|---|---|---|---|
| C1 | **Benchmark object** — `gurdy/core/benchmark.py`: pinned identity (commit + sha256), question set, provenance; generalizes what `tools/abstraction_bench.py` and `tools/riscv_slice.py` each do privately | [`BENCHMARKS.md`](./BENCHMARKS.md) §4 | both existing harnesses re-express over it; ingestion provenance identical |
| C2 | **Scoped, fingerprinted books** — demand records gain an optional `suite` tag and a **fingerprint**: the normalized `φ` form for shape (theory symbols, quantifier structure, bit-widths, cone size), the measured-curve stats for cost; `gurdy recommendations --suite B` restricts the board to `B`'s questions | [`FRONTIER.md`](./FRONTIER.md) §1(2); §1.5 | old ledgers still parse; the `organic`/`campaign`/`scout` origin discipline intact |
| C3 | **Frontier derivation** — `gurdy/core/frontier.py`: a pure function of (registry, ledger) yielding frontier **pairs** (required contract = join of citing demands, cost histogram, the §1.5 payload) and frontier **capabilities** (language-attached solver/checker/anchor demands), deduped by target signature | §1.6 | deterministic re-derivation; covered by the S3 purity test; no write path exists |
| C4 | **`gurdy saturation <suite>`** — the F5 predicate executable: derives `B`'s frontier set, partitions solved-all-ways / tier-2-candidate / frontier-only (by obstacle), prints the terminal board *as frontier pairs*, exits by tier-2 emptiness | F5; §1.6; [`FRONTIER.md`](./FRONTIER.md) §1 | fixpoint on a toy benchmark demonstrated in tests; a registered-but-unbuilt tier-2 target keeps it non-saturated |
| C5 | **Way-census + conditional routes** — per solved question, the full option set (feasible routes, cost profiles, assurance, corroboration) persisted during campaign runs; `routes --conditional` enumerates mixed routes with the conditional-meet annotation (opt-in, like endo-hops) | [`FRONTIER.md`](./FRONTIER.md) §5 deliverable 3; §1.6 | census for one spine question round-trips through the report; no conditional route is executable |
| C6 | **`tools/saturation_report.py`** — the deliverable: answered-fraction curve per iteration, cost-per-answer per iteration, way-census, terminal board serialized as frontier pairs with evidence counts; caps and pins ride in the output | [`FRONTIER.md`](./FRONTIER.md) §5 | regenerates byte-identically from a ledger + registry snapshot |
| C7 | **`tools/frontier_loop.py`** — the §5 protocol as one driver: pin → player over `B` (`GURDY_LEDGER`, `origin=campaign`, suite-tagged) → books → recommendations → *human registration pause* → builders/gate/queue → re-run; RAM-disciplined (one instance streamed at a time) | [`FRONTIER.md`](./FRONTIER.md) §5 | one full iteration on the pinned HWMCC slice, curve emitted |
| C8 | **Promotion** — `gurdy frontier promote <signature>`: emits the registration brief pre-filled with the frontier pair's required contract and evidence payload (generalizes `why-not --brief-stub`); writing under `pairs/` stays the human act | §1.6; [`AGENTS.md`](./AGENTS.md) §1 | a promoted brief cites its evidence verbatim; no auto-write |
| C9 | **L4 mandate-registration** — `mandate.yaml` (benchmark, obstacle classes in scope, admissible languages, protected floors), coordinator instantiation of demand-cited briefs inside it, shadow rung in `tools/autonomy.py` + `tools/shadow_ledger.py`; human writes and revokes the mandate | [`FRONTIER.md`](./FRONTIER.md) §4.2; [`SCALING.md`](./SCALING.md) §12.8 pattern | shadow mode only until the zero-false-go window is earned; any scope rejection burns the rung |

C1–C4 are prerequisites of everything else (they make saturation
*mechanically detectable*, which F5 promises, and give the far side
its currency); C5–C7 make the map an artifact and close the loop;
C8 closes demand→brief with the valve unmoved; C9 is deliberately
last and lands as a SCALING increment with its own `partial`→`built`
status.

*Phase-2 status (landed 2026-07-16): C1–C4 and S1 shipped*
(`gurdy/core/question.py`, `benchmark.py`, `frontier.py`; `gurdy
saturation` / `recommendations --suite`; spec in
[`FRONTIER.md`](./FRONTIER.md) §1.1; `tests/
test_frontier_saturation.py`), *with four from-scratch prunings and
one fix the tests forced:*

- **C2's stored fingerprint pruned to a derived view.** Demand
  records already carry everything the required-contract join needs
  (observables, shape, floor, spent verdict), and cost curves live on
  the ledger's cost side — storing a fingerprint would duplicate
  derivable data. One ledger, no parallel currencies.
- **`suite` is a record field like `origin`, never question
  identity** — the same question from two suites is one question
  filed twice; old ledgers parse and old hashes stand. The question
  type gained the missing **`program`** field instead: the books had
  been recording φ and dropping *p*.
- **`riscv_slice` reclassified.** It *authors* a compliance slice; it
  never ingested. C1 generalizes the one real streamed-with-pin
  ingestion (`abstraction_bench`'s HWMCC block, now expressed over
  the Benchmark object with identical pins) and gives local corpora
  the `dir:` source instead of forcing builders into a fetch model.
- **The registered tier straddles two stores** — a real finding: a
  brief-only registration (`pairs/btor2-interval/README.md`) is
  invisible to the code registry, so the derivation names
  `btor2-havoc` (`partial`, in flight) and honestly cannot name
  `btor2-interval`. C8's promotion is what bridges prose briefs and
  the registry; until then the gap is documented where it bites.
- **The zero-hop native route** (fix forced by the tests): a question
  about a program already at a hub had no route in the diagnosis —
  connectivity could fire spuriously and the cost branch missed the
  hub's own reductions. `why_not` now carries the native route, whose
  contract is the meet's unit — exactly the HWMCC case
  ([`FRONTIER.md`](./FRONTIER.md) §5, "no translation debt").

### 2.2 Extensions — the design-oracle instruments

Each attaches its output to the frontier pairs of C3 (§1.5):

- **O1 Fragment atlas.** A registry-side reference lattice of known
  decidable fragments (complexity, procedures, canonical citations);
  shape-blocked frontier pairs carry their atlas location and the
  feature crossing to the nearest decidable fragment.
- **O2 Failure-mode classifier.** Curve fitting over the ledger's
  cost profiles → the binding parameter and remedy class; generalizes
  `gurdy suggest-reduction` from "which havoc set" to "which engine
  family".
- **O3 Scouting harness.** Prototype encodings of an open cluster
  into existing fragments, blowup measured and recorded as evidence
  (never as verdicts), under the `scout` origin.
- **O4 Closure calibration.** Predicted closure recorded at
  registration; realized closure measured after merge by re-running
  the citing questions — the recommender's own shadow ledger (§1.5).

### 2.3 Simplifications

- **S1 One `Question` type.** `(program, φ/observables, shape, floor)`
  with `question_key` — today an ad-hoc dict shared by convention
  across `whynot`, `ledger`, `question_campaign`, and the player
  harnesses. One dataclass, one identity, suite tag and fingerprint
  hooks included (C2).
- **S2 One benchmark runner skeleton.** `tools/riscv_bench.py`,
  `tools/riscv_slice.py`, `tools/question_campaign.py`,
  `tools/abstraction_bench.py` converge on C1's object: one ingestion,
  one streamed-run loop, harness-specific measurement only.
- **S3 Advisory purity pinned.** All advisory reads (`why_not`,
  `trust_options`, `recommendations`, `suggest_reduction`,
  `route_report`) are pure functions over (registry, ledger); add the
  one invariant test that says so, so the use-plane/evolution-plane
  line stays executable rather than prose.
- **Non-goals.** No registry/oracle rewrite, no CLI renaming, no
  touching the POPL tree, no v2-era archaeology.

## 3. Docs — invert the story, one definition each

- **D1 README reframe.** Open with the frontier story (benchmarks in,
  map out; [`FRONTIER.md`](./FRONTIER.md) early in the reading order);
  the instrument sections stand unchanged but are introduced as the
  means. The lineage, name, and license sections stay.
- **D2 Canonical answerability.** [`POTENTIAL.md`](./POTENTIAL.md) §1
  stays the one definition of the five obstacles;
  [`AGENTS.md`](./AGENTS.md) §1, [`INTERFACE.md`](./INTERFACE.md) §2A,
  and [`FRONTIER.md`](./FRONTIER.md) §1 link instead of restating.
- **D3 FRONTIER mechanics.** As C1–C6 land, FRONTIER.md gains the
  precise saturation predicate, the frontier-pair schema (three
  tiers, required vs achieved contracts, §1.6), and the report
  schema — specification before code, per the standing discipline.
- **D4 View-trimming.** The "framework provides vs pair declares" §8
  triplicates in ARCHITECTURE/SOLVERS/BENCHMARKS shrink to links at
  [`FRAMEWORK.md`](./FRAMEWORK.md) §2, which already declares itself
  the single source.
- **D5 Theorem residence.** F1–F6 live in the paper and
  `paper/mechanization/README.md`'s map; FRONTIER.md references them
  once landed rather than restating proofs.

## 4. The new arXiv paper

**Record.** A **new submission**, not a v4: the thesis changes — the
map is the contribution, the calculus is cited as the means — and the
existing record's title *is* the means. The instrument paper (arXiv
v3, "Untrusted Authors, Trusted Answers") becomes the primary
citation. New sources under `paper/frontier/` sharing `macros.tex` and
`references.bib`; the POPL flow and the v3 fork are untouched.

**Working title.** *Saturating Benchmarks: Mapping the Frontier of
Reducible Decidability in Practice* (candidate; alternatives recorded
in the draft's header).

**Form.** Simplest possible: ~12–15 pages, two figures (the loop with
the map as output; the two-plane diagram inherited), no evaluation
section, every theorem either mechanized or carrying its named
assumptions, no measured numbers (the one deliberate exception: none —
even the registry census is cited to v3, not restated).

**Skeleton — all necessary sections except benchmarks:**

1. **Introduction** (~1.5 pp). The promise verbatim: present any
   benchmark whose questions reduce to decision procedures; the
   platform learns all ways feasible in practice and books everything
   else with the reason. The instrument exists and is measured
   (cite v3); this paper says what it is *for* and proves that it can
   do it. Contributions: the frontier problem stated (saturation per
   benchmark); the explorer architecture (two planes, two loops); the
   facilitation theorems F1–F6 with their mechanized core; the domain
   kit.
2. **The frontier problem** (~2 pp). Domain signature; questions;
   answerability as five ordered conditions; decidable-in-practice
   (budgets declared, cost measured, `resource-out` permanent);
   saturation's two terminal states; the three-tier pair lifecycle
   and the required/achieved contract duality (§1.6) — the map is
   drawn in the same currency the instrument is built from; the map
   schema (curve, way-census, terminal board of frontier pairs).
   Purely definitional — this section is the paper's contribution of
   *problem*, and it must stand alone.
3. **The instrument, as means** (~2.5 pp). The
   [`FRONTIER.md`](./FRONTIER.md) §3 table as the section's spine: for
   each requirement of trustworthy cartography, the feature that
   supplies it — directional squares and the contract meet
   (compressed to one subsection), the asymmetry, the gate and
   ratchet, the books. Details and proofs pointed at v3 and the
   mechanization; nothing re-derived.
4. **The loop** (~1.5 pp). Capability loop and trust loop; the
   diagnosis as total function; recommended-then-registered with the
   human valve and its mandate generalization; the two production
   lanes; CEGAR-on-the-platform as the cost axis's engine.
5. **Why this explores the frontier** (~3 pp). F1–F6: statements,
   proof sketches, the sufficiency/necessity pairing (ablations
   inline, one paragraph each); the currency lemmas — the status
   ratchet and conditional-plan soundness — with F5 stated as tier-2
   emptiness (§1.6); assumptions typeset as the theorems' TCB (fair
   enumeration, gate liveness, anchor supply); the
   relative-completeness framing named for what it is (completeness
   relative to the candidate universe and the kit, in the lineage of
   relative completeness results, not an oracle claim).
6. **The domain kit, and the far side as a design oracle** (~2 pp).
   The four instantiation obligations; what supplying each costs; the
   existing registry cited as the existence proof that the kit closes
   outside one field; the §1.5 extraction operators as the principled
   reading of a terminal board, with the board exported as frontier
   pairs — self-contained challenge bundles (pinned instances,
   budgets, required contracts, baseline census) for the solver
   community; the **pre-registered saturation protocol** for HWMCC —
   protocol, pinned and dated, explicitly *not* results: the
   benchmarks section is deliberately absent and this is its
   placeholder and promise.
7. **Related work** (~1 p). CEGAR with throwaway vs registered
   refinements; abstract interpretation; translation validation and
   certified compilation (as single-edge theories); competition
   infrastructure (HWMCC, SV-COMP, StarExec) as benchmark suppliers
   rather than explorers; proof-carrying answers; relative
   completeness; LLM agents in formal methods.
8. **Limitations and conclusion** (~0.5 p). The four walls
   ([`POTENTIAL.md`](./POTENTIAL.md) §5) as the boundary of the
   theorems; anchors don't scale; a cost plateau is a finding; the map
   compounds across benchmarks.

**Writing discipline.** §2 and §5 are written first (they are the
paper); §3–§4 compress existing prose and must not grow; any sentence
§5 does not need is deleted from §2. Abstract last, two paragraphs on
the v3-abstract model: the problem and the theorems, then the
instrument and the protocol.

## 5. Order of work

1. **Phase 1 — the argument.** *(landed 2026-07-16)* F2 + the §1.6
   currency lemmas + F3 in Lean — plus the F4 chain lemma, which the
   from-scratch filtration model made cheap
   (`Calculus/Frontier.lean`, §1.7); paper §2 and §5 drafted in
   lockstep (`paper/frontier/`, new-submission skeleton, stubs
   elsewhere, no benchmarks section by design). The modeling did not
   fight back; the pruning it forced is recorded in §1.7.
2. **Phase 2 — the mechanics.** *(landed 2026-07-16)* C1–C4 (+S1
   alongside C2), D2–D3. Saturation is demonstrably mechanical — the
   board emitted as frontier objects — on the toy benchmarks of the
   tests and the pinned HWMCC slice (`gurdy saturation` reports the
   slice statically saturated: six hub-native questions, all
   answerable; whether cost bites is the loop's dynamic business,
   Phase 3). The prunings and the two findings are recorded at the
   end of §2.1.
3. **Phase 3 — the map.** C5–C8, O2, F5 in Lean, D1, D4. One full
   loop iteration produces a real (small) saturation report.
4. **Phase 4 — the paper.** O1; `paper/frontier/` complete except
   benchmarks — the six stubs written out, abstract rewritten last,
   kit checklist frozen. (F4's Lean content landed in Phase 1 as the
   chain lemma, and the necessity ablations are already drafted in
   §5; what Phase 4 adds to F4 is nothing but prose.)
5. **Phase 5 — the valve, widened.** C9 in shadow mode, O3–O4
   accruing calibration evidence beside it. They graduate on their
   own ledgers, or they don't — either way the plan does not block
   on them.

Risks worth naming: ~~the F4 mechanization~~ (resolved in Phase 1 —
the filtration model made the chain lemma a page, and fairness/gate
liveness stayed hypotheses, exactly as intended); saturation's
"all ways" quantifier must stay over the *known set* or F5's
decidability dies; a frontier pair must be impossible to execute or
to confuse with capability (refused at the type level, not by
convention), and the currency must keep room for the outermost wall's
honest "no target to name"; and every benchmark-touching item
inherits the RAM discipline — stream, release, cap.

The vision is the means. The map is the end. This plan is the road.
