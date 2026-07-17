# Routes — composing pairs

A pair is one edge. A **route** is a walk along edges — a path, in the
graph-theoretic sense, through the registry graph. This document defines
route composition, how determinism and fidelity compose along a route,
and why **branching** routes raise fidelity beyond what any single pair
gives. It builds on [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 1. Composition

Two pairs **compose** when the target language of the first is the source
language of the second:

```text
   P1 : A → B        P2 : B → C        P2 ∘ P1 : A → C
```

A **route** is a sequence of pairs composed this way, from a starting
language to a destination. The language registry is therefore a directed
graph whose nodes are languages and whose edges are pairs; a route is a
walk through that graph.

Composition pastes commuting squares along their shared middle column —
the intermediate language `B` and its behavior:

```text
        T1              T2
   A ────────▶ B ────────▶ C
   │           │           │
  I_A         I_B         I_C
   ▼           ▼           ▼
   A' ◀─────── B' ◀─────── C'
        L1              L2
```

**Paste lemma.** If both inner squares commute (each pair is faithful),
the outer rectangle `A → C` over the top, `C' → A'` along the bottom
commutes too. So **a route's faithfulness is the conjunction of its pairs'
faithfulness**, and a broken outer rectangle is traced to whichever inner
square fails — per-pair error localization, for free. The shared middle
language `B` is a *named, registered* language with its own pair on each
side; it is never a hidden intermediate format
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §9).

The target-to-source interpreters compose right-to-left: a result
obtained at `C` is carried back to `B` by `L2`, then to `A` by `L1`, so an
answer found at the destination is delivered as a fact about the original
source.

## 2. Determinism composes

A route is deterministic iff **every** pair on it is. Because each pair's
output hash is a deterministic function of its input hash, the
content-addressed cache extends across the whole route for free — and one
nondeterministic pair collapses it. A route therefore inherits the
recompile-and-diff check: re-run the route on the same input, assert
byte-identical output at every step. A leak localizes to the one pair that
produced different bytes.

## 3. Fidelity composes — and can be re-established

A route is only as faithful as its **weakest** pair, on the assurance
ordering
`predicted, proved > checked > reproducible > trusted`
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §7) — **unless a later pair
re-establishes fidelity.**

- **Weakest-link (default).** A route through a `reproducible` compiler and
  a `proved` reasoning translation is, overall, `reproducible`: you can
  replay it but not foresee or prove the compiler step.
- **Re-establishment.** A pair (or a branch, §4) that independently
  validates the result *raises the effective fidelity of the prefix that
  fed it.* For example, an opaque `reproducible` compile step whose output
  is then checked against the source by a downstream differential is, for
  that run, lifted to `checked`. Re-establishment is per-run evidence; the
  statically-declared route fidelity stays the weakest-link meet.

A route must also report its **cumulative loss**: each pair declares what
its translation *keeps* and *discards* (its projection is the kept set);
a route's loss is the union of what its pairs discard. Loss is made
explicit so that "understanding through a long route" cannot quietly become
an illusion — the observables the destination can still speak about are
exactly those no pair on the route discarded.

**Direction composes too** ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §3;
`route_direction`): a route is `exact` iff every hop's square is exact,
else `over` — lax squares paste exactly as exact ones do (simulations
compose along the shared middle language). The composed direction governs
**verdict transfer** at the destination: along an `over` route a universal
verdict (`unreachable`) still holds at the source, while an existential
verdict never rests on the route at all — it is carried back and replayed
(the rule that already governs exact routes, [`SOLVERS.md`](./SOLVERS.md)
§4). A replay failure on an `over` route is a *spurious counterexample*, a
refinement demand on the abstraction hop rather than a bug in it. Loss and
direction are complementary honesty declarations: loss says which
observables a route can no longer speak about; direction says which
*quantifier* its answers still carry.

## 4. Branching routes increase fidelity

The registry graph is not a line; from one source there may be **several
routes to the same target**. When two routes reach the same destination
language, they can be run on the same input and their outputs
**cross-checked**. This is the central fidelity mechanism of the platform:

- **Agreement corroborates.** Two independently-built translators arriving
  at the same answer is strong evidence both are faithful — far stronger
  than either alone, even if each is only individually `checked`.
- **Disagreement localizes.** A mismatch means at least one route has a
  bug, and the per-pair squares (§1) pin it to a specific pair and step.
  The translators start checking *each other*.

A branch is therefore a way to manufacture high fidelity out of pairs that
are individually only `checked`: the joint guarantee of two corroborating
routes exceeds any single route's declared tier.

```text
            ┌──▶ (route 1)  ──┐
   source ──┤                 ├──▶ same target  ──▶ cross-check
            └──▶ (route 2)  ──┘
```

Branching is not the only place corroboration enters. For
reasoning-language destinations the same question can also be **decided two
ways** (a native solver vs. a bridge to another reasoning language) and its
answer's witness **re-checked by an independent checker**. Translate-step
branching, solve-step agreement, and proof-step checking are three stacked
layers of cross-check — see [`SOLVERS.md`](./SOLVERS.md) §7.

**Independence is declared and checked, not assumed** (`gurdy
trust-options`, `gurdy/core/trust.py`): what a branch's agreement rests on
is the diverse legs deriving from **different semantic artifacts**
([`SCALING.md`](./SCALING.md) §9 — the prose manual vs. the Sail model),
so each pair declares its `semantic_artifact` (protected provenance, the
`tools/provenance.py` vocabulary) and the trust advisor judges a branch by
the *diverse segments'* declared artifacts, the shared suffix removed. A
shared artifact is never independent; an undeclared pair is *unknown* —
never silently independent. When a player's assurance floor is unmet the
advisor names the honest option: run an existing independent branch,
generate a route from a *new* artifact — or **saturation**: every further
same-anchor route adds count, not trust; anchors, unlike pairs, do not
scale ([`POTENTIAL.md`](./POTENTIAL.md) §5). Advisory only: grades stay
declared, corroboration stays evidence the player runs.

## 5. The initial branch

The five spine pairs of the initial registry (the full graph — 15
registered pairs, 14 with implementations — is in
[`REGISTRY.md`](./REGISTRY.md)) already form a
branching graph whose payoff is exactly §4:

```text
   C ──▶ RISC-V ───────────────────▶ BTOR2 ──▶ SMT-LIB
   (c-riscv)  │   (riscv-btor2)        │   (btor2-smtlib)
              └──▶ SAIL ──▶ BTOR2 ─────┘
              (riscv-sail) (sail-btor2)
```

- **RISC-V reaches BTOR2 two ways.** Directly through `riscv-btor2` (a
  translator built from the RISC-V specification), and indirectly through
  `riscv-sail` then `sail-btor2` (via the RISC-V model written in Sail).
  Two independent encodings of RISC-V semantics into the same target — the
  prototypical fidelity-raising branch.
- **A longer reach with an opaque head.** `c-riscv` puts a pinned, opaque
  C compiler (`reproducible`) at the front. Either RISC-V→BTOR2 route then
  carries the result down to BTOR2, and `btor2-smtlib` bridges BTOR2 to
  SMT-LIB so a theory solver can finish the job. The opaque head's fidelity
  is re-established (§3) by the downstream checks and by the branch.

What a player gains from the branch: ask a question about a C or RISC-V
program, obtain the answer through *both* the direct and the Sail-mediated
route, and accept it with the joint fidelity of two corroborating
translations — or, on disagreement, a defect localized to a single pair.

## 6. Routing is enumerated, not chosen

The platform **enumerates** the routes between two languages (the simple
routes through the registry graph) and reports each route's composed
determinism, fidelity, direction, and loss. It does **not** decide which
route to take, or whether to spend a branch's extra cost for extra fidelity
— that is the player's call, exactly as choosing a solver or a budget is.
The platform's job ends at presenting faithful, deterministic routes and
cross-checking the ones the player runs.

**Endo-pairs** (source language = target language — an abstraction like
`btor2-havoc`, or a property transformation) enumerate **opt-in**
(`routes(..., endo=True)`, each pair at most once per route): an endo-hop
is a player-directed reduction whose parameters (which states to havoc,
what to instrument) are the player's call, so plain enumeration keeps the
simple-path reading above.

**The annotated report** (`route_report`, `gurdy routes --report`) does not
change the doctrine — it makes the tradeoff the player already owns
visible on all four axes at once. Each enumerated route is annotated with
its composed **fidelity/assurance** (weakest link on the class chain
universal > per-run > replay > none), composed **direction**, the
question's **feasibility** when the question is described (`observables`
checked against the head projection — a dynamic per-system projection
reports `dynamic`, never a silent pass; `shape` checked against the target
language's declared solver shapes, `question_shapes` in the registry), and
the measured **cost profile** from the host-local ledger
(`gurdy/core/ledger.py`, opt-in via `GURDY_LEDGER`; timings are
host-specific, so the ledger is a local file, not a repo artifact, and an
absent measurement reports `unmeasured`, never a guessed zero). Routes that
are **Pareto-dominated** — another route at least as good on assurance and
direction, no more expensive on the measured translate total, strictly
better somewhere — are *marked*, never hidden, and dominance is only ever
computed between fully measured routes: partial data never dis-ranks a
route. No scalar ranking exists; choosing is still the player's.

## 7. Measured composition

The composition laws above — determinism (§2), fidelity (§3), branching (§4)
— are not merely asserted; they are **measured**. A merge-triggered
**route-grader agent** runs capped, pinned route benchmarks driven by each
route's origin-language suite, computing end-to-end coverage and fidelity,
determinism, loss, and the headline **branch-agreement rate** (with
disagreements localized to a hop). Reasonable caps bound length, route count,
slice size, program size, unrolling, time/memory, and parallelism — and a
capped result says so. The full contract is [`BENCHMARKS.md`](./BENCHMARKS.md)
§6–7.

Grader runs also feed the **ledger** (its cost side): the CI slice
(`tools/route_grader.py`, the `route-grader` job in `.github/workflows/ci.yml`)
runs with `GURDY_LEDGER` set, so the instrumented call sites record
through exactly the paths the grader already exercises — translate on cache
miss, the square oracle, the decide backends — and the ledger accumulates
across CI runs (restored via cache, uploaded as an artifact, host-tagged so
runner-class profiles never mix with a developer's machine). That is where
the measured cost axis of the §6 route report comes from; the job measures
and reports, and never gates a merge.
