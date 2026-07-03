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

## 5. The initial branch

The five registered pairs ([`REGISTRY.md`](./REGISTRY.md)) already form a
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
determinism, fidelity, and loss. It does **not** decide which route to
take, or whether to spend a branch's extra cost for extra fidelity — that
is the player's call, exactly as choosing a solver or a budget is. The
platform's job ends at presenting faithful, deterministic routes and
cross-checking the ones the player runs.

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
