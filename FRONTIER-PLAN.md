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
  mechanical (saturation, way-census, the report, the loop driver, the
  mandate) and the simplifications that keep the repository one story
  told once.
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
executable (`gurdy saturation`, §2.1/C3). "All ways" is where the
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

### 1.5 Mechanization work items

Extend `paper/mechanization/` (no mathlib, audit discipline intact):

- `Calculus/Registry.lean` — registries as finite edge sets;
  `Answerable` as the five-condition conjunction over enumerated
  routes; `Solved`; monotonicity (F2 lift).
- `Calculus/Diagnosis.lean` — first-failure function; totality,
  relevance, obstacle-progress (F3).
- `Calculus/Loop.lean` — the abstract loop; fair-enumeration and
  gate-liveness hypotheses; chain induction (F4); the finite-pool
  fixpoint (F5).
- `Calculus/Audit.lean` — extend the axiom audit to the new theorems.

Order: F2 lift (small, verifies the modeling), then F3, then F5, then
F4 (hardest). Each lands with its paper-side statement drafted in
parallel so statement and mechanization never drift.

## 2. Code — extend, then simplify

### 2.1 Extensions (the missing mechanics of the map)

| # | Item | Contract | Acceptance |
|---|---|---|---|
| C1 | **Benchmark object** — `gurdy/core/benchmark.py`: pinned identity (commit + sha256), question set, provenance; generalizes what `tools/abstraction_bench.py` and `tools/riscv_slice.py` each do privately | [`BENCHMARKS.md`](./BENCHMARKS.md) §4 | both existing harnesses re-express over it; ingestion provenance identical |
| C2 | **Scoped books** — demand records gain an optional `suite` tag; `gurdy recommendations --suite B` restricts the board to `B`'s questions | [`FRONTIER.md`](./FRONTIER.md) §1(2) | old ledgers still parse; campaign origin discipline unchanged |
| C3 | **`gurdy saturation <suite>`** — the F5 predicate executable: partitions `B` into solved-all-ways / open-with-in-set-target / open-out-of-set (by obstacle), prints the terminal board, exits by fixpoint status | F5; [`FRONTIER.md`](./FRONTIER.md) §1 | fixpoint on a toy benchmark demonstrated in tests; a registered-but-unbuilt in-set target keeps it non-saturated |
| C4 | **Way-census persistence** — per solved question, the full option set (feasible routes, cost profiles, assurance, corroboration) persisted during campaign runs; `route_report` already computes the per-route rows | [`FRONTIER.md`](./FRONTIER.md) §5 deliverable 3 | census for one spine question round-trips through the report |
| C5 | **`tools/saturation_report.py`** — the deliverable: answered-fraction curve per iteration, cost-per-answer per iteration, way-census, terminal board with evidence counts; caps and pins ride in the output | [`FRONTIER.md`](./FRONTIER.md) §5 | regenerates byte-identically from a ledger + registry snapshot |
| C6 | **`tools/frontier_loop.py`** — the §5 protocol as one driver: pin → player over `B` (`GURDY_LEDGER`, `origin=campaign`, suite-tagged) → books → recommendations → *human registration pause* → builders/gate/queue → re-run; RAM-disciplined (one instance streamed at a time) | [`FRONTIER.md`](./FRONTIER.md) §5 | one full iteration on the pinned HWMCC slice, curve emitted |
| C7 | **L4 mandate-registration** — `mandate.yaml` (benchmark, obstacle classes in scope, admissible languages, protected floors), coordinator instantiation of demand-cited briefs inside it, shadow rung in `tools/autonomy.py` + `tools/shadow_ledger.py`; human writes and revokes the mandate | [`FRONTIER.md`](./FRONTIER.md) §4.2; [`SCALING.md`](./SCALING.md) §12.8 pattern | shadow mode only until the zero-false-go window is earned; any scope rejection burns the rung |

C1–C3 are prerequisites of everything else (they make saturation
*mechanically detectable*, which F5 promises); C4–C5 make the map an
artifact; C6 closes the loop; C7 is deliberately last and lands as a
SCALING increment with its own `partial`→`built` status.

### 2.2 Simplifications

- **S1 One `Question` type.** `(program, φ/observables, shape, floor)`
  with `question_key` — today an ad-hoc dict shared by convention
  across `whynot`, `ledger`, `question_campaign`, and the player
  harnesses. One dataclass, one identity, suite tag included (C2).
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
- **D3 FRONTIER mechanics.** As C1–C5 land, FRONTIER.md gains the
  precise saturation predicate, board schema, and report schema —
  specification before code, per the standing discipline.
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
   saturation's two terminal states; the map schema (curve,
   way-census, terminal board). Purely definitional — this section is
   the paper's contribution of *problem*, and it must stand alone.
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
   inline, one paragraph each); assumptions typeset as the theorems'
   TCB (fair enumeration, gate liveness, anchor supply); the
   relative-completeness framing named for what it is (completeness
   relative to the candidate universe and the kit, in the lineage of
   relative completeness results, not an oracle claim).
6. **The domain kit** (~1.5 pp). The four instantiation obligations;
   what supplying each costs; the existing registry cited as the
   existence proof that the kit closes outside one field; the
   **pre-registered saturation protocol** for HWMCC — protocol,
   pinned and dated, explicitly *not* results: the benchmarks section
   is deliberately absent and this is its placeholder and promise.
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

1. **Phase 1 — the argument.** F2 lift + F3 in Lean; paper §2 and §5
   drafted in lockstep. (Cheap, and it de-risks the whole plan: if the
   modeling fights back, better to learn while the statements are
   drafts.)
2. **Phase 2 — the mechanics.** C1–C3 (+S1 alongside C2), D2–D3.
   Saturation becomes demonstrably mechanical on a toy benchmark and
   the pinned HWMCC slice.
3. **Phase 3 — the map.** C4–C6, F5 in Lean, D1, D4. One full loop
   iteration produces a real (small) saturation report.
4. **Phase 4 — the paper.** F4 in Lean; `paper/frontier/` complete
   except benchmarks; ablations written; kit checklist frozen.
5. **Phase 5 — the valve, widened.** C7 in shadow mode, evidence
   accruing while everything above ships. It graduates on its own
   ledger, or it doesn't — either way the plan does not block on it.

Risks worth naming: the F4 mechanization is the one item with real
uncertainty (fairness over an abstract enumerator; keep the model
small and the hypotheses explicit rather than clever); saturation's
"all ways" quantifier must stay over the *known set* or F5's
decidability dies; and every benchmark-touching item inherits the RAM
discipline — stream, release, cap.

The vision is the means. The map is the end. This plan is the road.
