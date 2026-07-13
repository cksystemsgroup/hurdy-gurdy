# Agents — how pairs get registered and built

Pairs are **registered by humans** and **implemented by independent,
per-pair agents.** This document describes that division of labor and the
boundaries each agent works within. The contract an agent implements
against is [`PAIRING.md`](./PAIRING.md).

## 1. Registration is a human act

A human decides a pair is worth building and registers it by adding a
one-page **brief** under [`pairs/<source>-<target>/README.md`](./pairs/).
A brief states:

- the source and target languages (both must have a formal semantics, and
  each must already be in [`languages/`](./languages/) or be introduced by
  this pair);
- the intended **translator** (e.g. "a pinned C compiler", "built from the
  RISC-V specification", "built from the RISC-V model in Sail", "rule-for-rule
  bit-vector mapping");
- the target **fidelity** the pair should reach, and the evidence that
  would establish it;
- the **projection** `π` — what observable agreement counts as faithful;
- the square's **direction** — `exact` (the default) or `over` (an
  abstraction pair, which also ships its witness embedding —
  [`ARCHITECTURE.md`](./ARCHITECTURE.md) §3); like `π`, the human's to set
  and the agent's not to flip;
- the **coverage target** — the in-scope construct set and the public
  benchmark suite (if any) the pair must clear
  ([`BENCHMARKS.md`](./BENCHMARKS.md)); this is the human's to set and the
  agent's not to shrink;
- which shared interpreters it **reuses** and which (if any) it must
  **contribute**.

The set of registered briefs *is* the platform's work queue. Registration
is the only point at which the scope of the platform grows; everything
downstream is implementation against a fixed brief.

### Deliverables and the bootstrap order

A pair is one of **four kinds of deliverable**, each human-registered and
each with its own agent ([`FRAMEWORK.md`](./FRAMEWORK.md) §1): the
**framework** (built first, by a platform agent — there is nothing to
inherit until it exists), the **language interpreters** (standalone, one per
language, built independently of any pair), the **pairs**, and the
**route-grader** (framework machinery, run on merges, §7). The order
`framework → interpreters → pairs` keeps each agent's task finite — no
deliverable assumes a later one.

## 2. One agent per pair, independent

Each registered brief **triggers one independent agent** whose entire job
is to deliver that one deliverable — a framework increment, a language
interpreter, or a pair — to its contract (for a pair,
[`PAIRING.md`](./PAIRING.md)).

- **Scoped.** An agent implements its one deliverable and nothing else. A
  pair agent reuses the shared interpreters; it contributes one only if that
  interpreter was not delivered standalone first
  ([`FRAMEWORK.md`](./FRAMEWORK.md) §1). It does not touch other pairs.
- **Independent.** Per-pair agents run concurrently and do not coordinate
  through each other; they coordinate only through the **shared,
  versioned** layer: the language registry and the shared interpreters.
- **Reuse-first.** Before writing an interpreter, an agent checks
  [`languages/`](./languages/). If the language is there, it imports the
  interpreter; it never forks one.

## 3. The shared layer is the only coupling

The one thing per-pair agents share is languages and their interpreters
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §6). This is also the only place
one agent's work can break another's. The rules that keep independent
agents safe:

- **A shared interpreter is owned by its language, not by the pair that
  first wrote it.** Once `languages/riscv/` exists, it serves `c-riscv`,
  `riscv-btor2`, and `riscv-sail` alike.
- **Changing a shared interpreter is a versioned event.** It bumps the
  language's interpreter version and obliges re-validation of every
  dependent pair's commuting square — not a quiet edit to satisfy one pair.
- **A new interpreter must satisfy the conventions in
  [`ARCHITECTURE.md`](./ARCHITECTURE.md) §5** (post-step state, projectable
  observables, determinism) so that *future* pairs can build their square
  on it without surprises.

If an agent finds itself reaching into another pair to borrow logic, that
logic belongs in the shared language layer; promote it there rather than
copying it.

## 4. Standing discipline for every agent

- **Determinism is non-negotiable.** Every function the agent ships is pure
  and byte-reproducible ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §4); ship
  the twice-and-diff checks.
- **Use the pinned toolchain.** Run translator, interpreter, oracle, and
  solver/checker steps inside the development image
  ([`DOCKER.md`](./DOCKER.md)) so versions are fixed and results
  reproducible; if the pair needs a tool the image lacks, add a pinned layer
  (DOCKER.md "Gaps to close").
- **Specification before code.** Write (or, for an opaque translator, pin
  and contract) the translation before implementing it
  ([`PAIRING.md`](./PAIRING.md) §2).
- **Honest fidelity.** Claim the tier the evidence supports, no higher
  ([`PAIRING.md`](./PAIRING.md) §4). A route inherits what a pair claims.
- **Honest coverage.** Translate the full in-scope set; abort on the rest
  with a typed `unsupported` error; never shrink scope to fake completion.
  Report measured coverage and let status be `partial` when it is — a visible
  partial beats a false `built` ([`BENCHMARKS.md`](./BENCHMARKS.md)).
- **No hidden intermediate representation.** If a translation wants to pass
  through another language, that language is named and registered as its
  own pair on a route ([`ROUTES.md`](./ROUTES.md)) — never buried inside one
  translator.
- **Leave the brief better than you found it.** On completion, flip the
  brief from *registered* to *built*, record what the
  [`PAIRING.md`](./PAIRING.md) §9 open questions taught you, and update
  [`REGISTRY.md`](./REGISTRY.md).

## 5. When an agent is blocked

If the brief is under-specified, two pairs would need to change the same
shared interpreter incompatibly, or the target fidelity or coverage is unreachable with
the proposed translator, the agent records the blocker in its pair's brief
and stops — it does not force a change through the shared layer or lower the
correctness bar to make progress. A blocked brief returns to the human who
registered it.

## 6. Done

A pair is done when it passes the [`PAIRING.md`](./PAIRING.md) §8
checklist: registered, deterministic, its square validated under its
declared projection, its fidelity backed by attached evidence, its
specification reviewable, and the registry and brief updated. At that point
the pair becomes a usable edge of the graph, and any route it lies on —
including the branches that raise fidelity ([`ROUTES.md`](./ROUTES.md) §4) —
becomes available to the player.

## 7. The route-grader agent

Per-pair agents own one edge; **composition is not their job**. A dedicated
**route-grader agent** is triggered **on merge** of any pair: it runs the
capped route benchmarks for the routes the merged pair participates in,
computes the composed metrics and the headline **branch-agreement rate**
([`BENCHMARKS.md`](./BENCHMARKS.md) §6), updates each route's status in
[`REGISTRY.md`](./REGISTRY.md), and enforces the **composition ratchet** — a
merge that breaks a route, raises a route's `unsupported` rate, or drops a
branch's agreement is a regression and fails.

It is the *externalized* grader: a pair does not grade the compositions it
sits in, just as it does not self-declare its own coverage. It runs at a
lower cadence than per-pair checks because it is the expensive, combinatorial
one — which is exactly why the size caps ([`BENCHMARKS.md`](./BENCHMARKS.md)
§6) are mandatory.
