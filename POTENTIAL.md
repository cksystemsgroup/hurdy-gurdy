# Potential — an LLM generating pairs in a loop

This document explores a question about the ceiling of the platform:

> Can an LLM be put in a loop with hurdy-gurdy so that it generates more
> and more pairs to answer a question about a given program that the
> existing pairs cannot answer? Can it build larger and larger graphs to
> get at least closer and closer to answering *eventually any* question
> about a given program? What is the potential of graphs of pairs,
> really?

The short answer: **yes, the loop is sound, monotone, and already
specified in outline — but it converges to a precise limit, and naming
that limit is the honest way to state the potential.** Growing the graph
removes three of the four obstacles that make a question unanswerable
today; the fourth is the boundary of formal methods itself, and no
number of pairs crosses it. Within that boundary, the graph of pairs is
something genuinely new: a *ratcheting, machine-audited library of
reductions* in which every pair built to answer one question answers
infinitely many later ones.

It builds on [`ARCHITECTURE.md`](./ARCHITECTURE.md),
[`ROUTES.md`](./ROUTES.md), [`SOLVERS.md`](./SOLVERS.md),
[`INTERFACE.md`](./INTERFACE.md), and the automation plan in
[`SCALING.md`](./SCALING.md); theorem references are to the paper
([`paper/`](./paper/)).

## 1. What "answerable" means, mechanically

A question about a source program `p` is a condition `φ` over
observables of `p`, asked existentially (is `φ` reachable?) or
universally (does `φ` hold for all inputs, within bounds?). In platform
terms, `(p, φ)` is **answerable** iff:

1. **Connectivity** — a route `R` exists from `p`'s language to some
   reasoning language `Z` ([`ROUTES.md`](./ROUTES.md) §1);
2. **Loss** — `φ` mentions only observables in `keep(R)`: no pair on
   the route discards them ([`ROUTES.md`](./ROUTES.md) §3);
3. **Shape** — `φ`'s logical form is one `Z`'s solvers decide
   (today: reachability/safety over finite-state transition systems and
   quantifier-free theories, [`SOLVERS.md`](./SOLVERS.md) §9);
4. **Cost** — a registered solver returns a verdict other than
   `unknown` / `resource-out` within the player's budget.

When a question is unanswerable, exactly one of these four fails
*first*, and — this matters for the loop — the failure is
**mechanically diagnosable** through the existing interface:
`routes(from, to)` returns empty (obstacle 1) or returns routes whose
reported cumulative loss drops the observable `φ` needs (obstacle 2);
no registered `Z` can express the question (obstacle 3); `decide`
returns `unknown`/`resource-out` (obstacle 4). The platform cannot
answer the question, but it can always say *why not*, and the why-not
names the missing edge. (Since 2026-07-14 the diagnosis is a
first-class call, not a player composition: `gurdy why-not` /
`gurdy/core/whynot.py` walks these four obstacles in order — plus a
fifth, **trust**, when the player states an assurance floor no route
meets and no independent branch corroborates past — and returns
the demand record — obstacle, generation target, and for pair-shaped
targets a draft brief stub. Registration stays the human act of
[`AGENTS.md`](./AGENTS.md) §1.)

## 2. The loop, concretely

That diagnosis makes the loop well-defined. Nothing in it is
hypothetical — every stage exists in the architecture, and stages 3–5
are the [`SCALING.md`](./SCALING.md) pipeline (phases 1–7, landed):

1. The player receives `(p, φ)`, enumerates routes, and attempts the
   answer with the existing graph.
2. On failure, the diagnosis names a **generation target**: a missing
   pair (obstacle 1), a pair with a wider projection `π` (obstacle 2),
   a missing reasoning language plus the bridge into it (obstacle 3),
   or a missing *reduction* — an abstraction or property
   transformation (obstacle 4, §5–6 below).
3. The LLM writes the registration brief; a human admits it
   (registration is the one human act and the scope valve,
   [`SCALING.md`](./SCALING.md) §1).
4. A builder agent implements the pair against
   [`PAIRING.md`](./PAIRING.md); the gate — square, conjoined
   coverage, negative controls, provenance — admits or rejects it.
5. The ratchet keeps every prior verdict standing; the player re-asks.

Two properties make the loop *safe to run aggressively*, and both are
already the platform's central results:

- **Monotonicity.** Adding a pair never removes a route, never weakens
  an existing verdict (the widening ratchet,
  [`BENCHMARKS.md`](./BENCHMARKS.md) §5). The answerable set only
  grows. The loop cannot regress.
- **The asymmetry bounds the damage of a bad generator.** An LLM that
  writes a wrong pair — blindly or adversarially — **cannot forge an
  existential answer**: every `reachable` is carried back to a concrete
  input and replayed through the shared source interpreter
  (paper Thm 4.8; [`SCALING.md`](./SCALING.md) §2). Its worst case is a
  false *universal* in the uncorroborated corner, which is exactly the
  corner branches, certificates, and the common-mode gate exist to
  shrink. The loop's generator is untrusted by construction; that is
  why it may be an LLM at all.

## 3. What a larger graph buys: three growth directions

"More pairs" conflates three different kinds of growth with three
different payoffs:

- **Breadth — new front-ends** (`X → hub`). More source languages reach
  the hubs. This grows the set of *programs* the platform can speak
  about; it adds nothing for a given program already connected. Most of
  the initial registry is breadth.
- **Depth — new reasoning languages and the bridges into them.** New
  hubs (Horn clauses/CHC for invariant synthesis, temporal logics,
  cost/resource logics, probabilistic model checkers…) grow the set of
  *question shapes* per program. For "more questions about a *given*
  program," depth is where the growth actually comes from — obstacle 3
  is only ever removed here.
- **Redundancy — branches.** A second route to the same target answers
  **no new question at all**. It manufactures *fidelity*
  ([`ROUTES.md`](./ROUTES.md) §4). Redundancy grows the *trustworthy*
  set, not the answerable set.

So the loop, properly run, is two loops with different payoffs: a
**capability loop** (breadth + depth) triggered by unanswerable
questions, and a **trust loop** (redundancy) triggered by answers whose
evidence is weaker than the player wants. An LLM can drive both; the
diagnosis of §1 tells it which one a given failure calls for — and the
failing obstacle is the platform's one demand taxonomy, kept as
**books**: unmet demand is recorded beside measured cost in the one
ledger (`gurdy/core/ledger.py`), `gurdy recommendations` aggregates it
per generation target, and a registration brief cites its evidence —
the recommended-then-registered discipline of [`AGENTS.md`](./AGENTS.md)
§1.

## 4. The endo-pair observation: reductions are pairs too

The registry today is shaped like a funnel — front-ends flowing into
two hubs. Nothing in the architecture requires that shape, and the
question's real leverage hides in the pairs the funnel picture misses:
**pairs from a language to itself, and from a hub to the same hub**,
whose translator is a *property transformation* rather than a change of
notation. These are ordinary pairs — a translator, the shared
interpreters, a carry-back, a square — but each one multiplies the
question space of *every* language upstream of it:

- **Self-composition** (`L → L`, `p ↦ p × p`): turns 2-safety
  hyperproperties — noninterference, determinism of an output,
  equivalence of two programs — into plain reachability on the product,
  which the existing BTOR2 hub already decides. The square commutes
  exactly (the carry-back projects one component).
- **Liveness-to-safety** (`BTOR2 → BTOR2`, the loop-detection
  construction): makes termination-within-bounds and liveness questions
  BMC-able with no new solver.
- **Monitor weaving** (`L → L`): compiles a temporal `φ` into an
  observer whose `bad` state is `φ`'s violation — new question shapes
  without a new logic.
- **Abstraction** (`L → L'`, smaller state): the deepest one — now
  admitted as a *directional* pair, and inhabited by `btor2-havoc` — §6.

The honest reformulation of the user's question is therefore not "can
the graph get *bigger*" but "can the graph get *denser in
reductions*" — and the answer is yes: a reduction is exactly what a
pair is. The formal-methods literature is, in large part, a catalog of
such reductions; each is a candidate registration brief; an LLM is a
serviceable enumerator of that catalog. That is the growth model of
[`SCALING.md`](./SCALING.md) pointed at depth instead of breadth.

## 5. The limits no number of pairs crosses

Four boundaries stand at any graph size. Stating them is what makes the
convergence claim precise rather than wishful.

1. **Computability.** For unbounded-input universal questions,
   undecidability (Rice, halting) is untouched by translation: a route
   *re-expresses* a question; it never changes the question's degree.
   The platform already wears this honestly — universal answers are
   bounded claims under declared unrolling `k`, resting on
   `universal`-tier hypotheses that per-run evidence corroborates but
   does not entail (paper Thm 4.9; conclusion, "Limitations"). The
   existential side is exactly semi-decidable, and there the platform
   is complete-in-the-limit: a true `reachable` is eventually found at
   some bound and is then self-certifying by replay.
2. **The adequacy floor.** A pair's projection can only keep what the
   source interpreter exposes; `π ⊆` the observables of `I_s`, and
   interpreter adequacy (paper, Assumption: `I_A` means `⟦·⟧_A`) is the
   assumption below every verdict. A question about something the
   source semantics does not define — intent, readability, "is this
   code good" — is not a question *about the program* in the
   platform's sense, and no pair can make it one. The membership rule
   ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §1) is also the question
   rule.
3. **Cost.** Deciding is exponential in the worst case everywhere that
   matters. More routes to the same solver do not shrink the state
   space; only *abstraction* does (§6). Budgets (`resource-out`) are a
   permanent verdict class, not a transitional one.
4. **Trust saturation.** Branch corroboration is only as strong as the
   *independence* of the semantic artifacts behind the legs
   ([`SCALING.md`](./SCALING.md) §9, §11). Pairs can be generated
   without bound; independent formalizations of a real ISA exist in
   small finite supply. The capability of the graph scales with the
   LLM's output; its *trust* scales with the supply of external
   anchors — and saturates there. Pairs scale; anchors don't.

## 6. The finite-state pivot — and the missing axis

Here the question's optimism gets its strongest support. For a *given*
program — a concrete binary on a machine with bounded state, which is
what every program at the bottom of the spine is — the semantics is a
**finite transition system**. Over a finite system, *every* question
expressible over the kept observables is decidable in principle:
reachability, unbounded safety (inductive invariants and k-induction
are already in the BTOR2 checker inventory,
[`SOLVERS.md`](./SOLVERS.md) §10 — the escape from bounded `k` exists
today), liveness (via §4's endo-pair), temporal logic, hyperproperties.
For a fixed program, **the binding constraint is not computability but
cost** — limit 1 recedes and limit 3 takes its place.

And against cost, the one reduction that helps is the **abstraction
pair**, a deliberately behavior-adding translation to a *smaller* system
that still decides the question. The original calculus's loss was
*fieldwise* — a pair drops named observables (`keep`/`loss`,
[`ROUTES.md`](./ROUTES.md) §3) — and its fidelity *equational*
(`I_s(p) ≡_π Λ(I_t(T(p)))`). An over-approximating abstraction breaks
the equation: the target has *more* behaviors than the source, on
purpose. What it satisfies is the inequation

```text
   I_s(p)  ⊑_π  Λ( I_t( T(p) ) )      (every source behavior has a
                                       target counterpart on π)
```

— a **lax square**, a simulation rather than a bisimulation, the
Galois-connection half of abstract interpretation. One-sided fidelity
composes exactly as two-sided does (simulations paste), and the
asymmetry theorems come out *unharmed and load-bearing*: a universal
answer on the abstraction transfers soundly down the `⊑` (no behavior
of `p` reaches `bad` if none of the abstraction's do), while an
existential answer on the abstraction is *not* trusted — it is carried
back and replayed, and the replay either certifies it at the source or
exposes it as spurious. A spurious counterexample is precisely a
**refinement demand**: the LLM's next generation target is a finer
abstraction pair. The loop becomes CEGAR — counterexample-guided
abstraction refinement — with one structural difference from every
CEGAR engine ever built: **the refinements are not throwaway internal
state of a solver run; they are registered, audited, reusable pairs.**
The abstraction found for one question joins the graph and cheapens the
next thousand questions.

Lax squares are, we think, the single extension that unlocks most of
the remaining potential of graphs of pairs — and they are now
**admitted**: a pair declares a *direction* alongside its projection
(`exact` or `over`, [`ARCHITECTURE.md`](./ARCHITECTURE.md) §3,
[`gurdy/core/direction.py`](./gurdy/core/direction.py)), a directional
pair ships the witness embedding its lax square is checked along, routes
compose direction as a meet and report it beside fidelity and loss, and
verdict transfer is the executable asymmetry of `direction.transfers`.
The first inhabitant is the endo-pair
[`btor2-havoc`](./pairs/btor2-havoc/README.md) — localization
abstraction on the BTOR2 hub, graded and negative-controlled like any
exact pair, with the CEGAR loop above demonstrated in its tests; a
second, interval abstraction
([`btor2-interval`](./pairs/btor2-interval/README.md)), is registered
as a brief under the recommended-then-registered discipline. It was
a calculus change (a new judgment beside `≡_π`), not an architecture
change: determinism, sharing, routes, branches, the ratchet, and the
gate all applied unchanged.

## 7. What the loop converges to

Putting it together. The graph of pairs is a **monotone closure
operator**: at any moment the answerable set is the closure of the
source language's questions under the registered reductions, and each
loop iteration extends the closure. The LLM is an *enumerator of
candidate reductions*; the gate — squares, coverage, negative controls,
provenance — is the *acceptor* that admits only the sound ones; and
because sound reductions are enumerable, the loop is a
**semi-algorithm for answerability itself**:

> Any question about a given program that *can* be answered by some
> finite chain of sound, deterministic reductions to some mechanized
> decision procedure will *eventually* be answered by the loop, with
> quantified trust — and a question outside that closure stays outside
> it at every graph size.

So "closer and closer to eventually any question" is exactly right
with one qualifier and exactly wrong without it: the limit is not the
set of all questions but the set of all *reducibly decidable* ones —
which is to say, the reflection of everything formal methods knows how
to decide, unified behind one interface, with the trust of every answer
itself measured. For a fixed finite-state program the qualifier nearly
vanishes (every observable question is in the closure in principle) and
the convergence is in *cost*, driven by abstraction pairs and solver
progress rather than by connectivity.

The potential of graphs of pairs, then, is not that they approach an
oracle. It is three quieter properties that no monolithic verifier
has, and that compound:

- **The answerable set only grows** (the ratchet), and every failure
  names the edge that would extend it (the diagnosis of §1) — the graph
  is *self-directing*.
- **Answers are durable and shared**: a pair generated for one question
  serves all later questions through it, so the marginal cost of
  answerability falls as the graph grows — the graph is
  *an accumulating instrument*, not a per-query expense.
- **Capability and trust are separated and separately purchasable**
  (§3), and the generator sits outside the trusted base (§2) — which is
  the property that lets the generator be an LLM in a loop in the first
  place.

The instrument metaphor of the README extends: the loop does not teach
the hurdy-gurdy to play itself. It hands the player a luthier.

What the luthier is *for* — the loop run to saturation against
benchmarks designed by others, and the map of the frontier it leaves
behind — is the story of [`FRONTIER.md`](./FRONTIER.md).
