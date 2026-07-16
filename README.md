# hurdy-gurdy

An LLM-driven explorer of the **frontier of reducible decidability in
practice**: present it any benchmark whose questions reduce to decision
procedures, and the platform eventually learns **all ways feasible in
practice** to solve it — every feasible route enumerated,
cost-profiled, and trust-graded — and saves, as structured evidence,
**everything not yet solvable, and why**. The deliverable is a **map**:
the solved region with its way-census, and a surveyed frontier where
every open question carries the exact instrument that would move it, or
the stated reason none can. That story is
[`FRONTIER.md`](./FRONTIER.md); the vision below is its means.

The instrument is a platform for building **deterministic,
fidelity-graded translations** between formal languages, so that an LLM
(or a human) can move a program into whatever representation makes a
question answerable — and reason about it there through external
interpreters and solvers — without ever trusting an unaudited step.

- **Paper** — *Untrusted Authors, Trusted Answers: A Calculus of
  Fidelity-Graded Translations* (arXiv preprint:
  [`paper/arxiv.pdf`](./paper/arxiv.pdf), built from this repository at
  tag `arxiv.1`).
- **Video** — a five-minute narrated explainer of the vision and the
  core ideas:
  [`video/hurdy-gurdy-explainer.mp4`](./video/hurdy-gurdy-explainer.mp4)
  (rendered by [`scripts/explainer_video.py`](./scripts/explainer_video.py);
  a ready-to-paste YouTube description with chapters sits next to it).

The unit of the platform is the **pair**; pairs compose into **routes**.
This repository is the *lean architecture*: it defines what pairs and
routes are, the contract every pair must meet, and how pairs are
registered and implemented. The implementations themselves are built
**per pair, by independent agents**, against the contract here.

## What a pair is

A **pair** is a fixed combination of a **source language** and a
**target language** together with four deterministic functions:

1. a **translator** from source to target,
2. a **source interpreter**,
3. a **target interpreter**, and
4. a **target-to-source interpreter** — which carries a target-level
   behavior (a solver witness, a trace) back to a source-level behavior.

Both languages must carry a **formal semantics** — a definable meaning
function. Nothing else qualifies as a language here.

These six things — two languages and four functions — are exactly the
edges and corners of one **commuting square**:

```text
                 translate  (T)
   source ───────────────────────▶ target
     │                                │
   source                          target
 interpreter (I_s)              interpreter (I_t)
     ▼                                ▼
   source' ◀─────────────────────── target'
            target-to-source  (L)
```

`source'` and `target'` are the *behaviors* the two interpreters
produce. The square **commutes** when interpreting the source directly
(the left edge) yields the same observable behavior as translating,
interpreting the translation, and carrying it back (the other three
edges):

```text
   I_s(p)  ≡_π  L( I_t( T(p) ) )      for every source program p
```

up to a declared **projection** `π` — the observable fields the pair
promises to preserve (for an instruction set: the post-step program
counter, registers, halt flag). The square commuting *is* the pair's
correctness statement. A point where it fails to commute is a translator
bug, localized to a step and an observable.

A square may also be declared **directional**: an *abstraction pair*
promises `⊑_π` instead of `≡_π` — every source behavior has a target
counterpart, and the target may deliberately have more (e.g.
`btor2-havoc`, which havocs caller-named states to shrink the model a
solver must carry). Such a pair ships a *witness embedding* along which
its lax square is checked exactly like any other square, and its answers
transfer asymmetrically: universal verdicts flow back across the hop,
existential ones only ever by replay at the source. This is what lets
refinement loops (CEGAR) live *on* the platform, with the abstractions
as registered, reusable pairs — see [`POTENTIAL.md`](./POTENTIAL.md).

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full model.

## Determinism

Every translator and every interpreter is a **pure function**: the same
input produces byte-identical output, always. No internal state, no
learned heuristics, no adaptivity, no timestamps, no hash-order leakage.

Determinism is the load-bearing wall. Caching, cross-checking, proof
re-checking, and the very idea of an LLM *predicting* a translation all
collapse the instant one step is nondeterministic. Anywhere a translator
would otherwise make a heuristic choice, that choice becomes either fixed
in the pair's specification or a parameter the caller supplies. There is
no third option.

## Fidelity

Pairs do not all preserve meaning equally well, and they should not
pretend to. Each pair declares a **fidelity** level — how strong the
guarantee is that its square commutes, and how that guarantee is
established. Fidelity varies with the *kind* of source and target
languages, and the strongest level **involves a proof**:

| Fidelity      | The translator's output is…                                  | Established by |
|---------------|--------------------------------------------------------------|----------------|
| `predicted`   | derivable byte-for-byte from a written specification         | reading the spec |
| `reproducible`| not predictable, but pinned ⇒ identical bytes                | a digest-pinned toolchain |
| `checked`     | validated against the source on every run                    | the commuting-square oracle / a differential cross-check, on a corpus |
| `proved`      | accompanied by a machine-checked proof that the square commutes | a refinement proof or translation-validation certificate |
| `trusted`     | taken on faith                                               | quarantine; admit only behind a higher-fidelity check |

`predicted` and `proved` are the auditable summits — one you can foresee,
one you can re-check. `reproducible` only assures determinism, not
meaning. `trusted` assures nothing and is never shipped uncovered.

When the target is a **reasoning language** — one a solver consumes
directly — deciding a question and re-checking the answer is its own shared
contract: solvers produce, independent checkers verify, and `proved` is
graded by the checker. See [`SOLVERS.md`](./SOLVERS.md).

Fidelity has a companion axis, **coverage** — *how much* of a language a pair
actually handles, measured against the spec's construct inventory and public
benchmark suites. The two together are what stop a pair (or a route) from
passing while supporting only a trivial fragment; see
[`BENCHMARKS.md`](./BENCHMARKS.md).

## Shared interpreters

A source interpreter and a target interpreter belong to a *language*, not
to a pair. They are **shared across every pair that touches that
language.** The RISC-V interpreter is written once and used by every pair
with RISC-V on either side; the BTOR2 interpreter is written once and
used by every pair that targets BTOR2.

What a pair owns, and cannot share, is the **translator** and the
**target-to-source interpreter** — these are specific to the particular
source→target combination. Languages and their interpreters live under
[`languages/`](./languages/); pairs live under [`pairs/`](./pairs/).

## Routes

Two pairs **compose** when the target language of one is the source
language of the next. A **route** is such a composition — a path, in the
graph-theoretic sense, through the language graph from a starting language to a destination. Routes
inherit determinism (a route is deterministic iff every pair is) and
fidelity (a route is only as faithful as its weakest pair, unless a
higher-fidelity pair re-establishes it along the way).

Crucially, routes may **branch**: when two different routes reach the same
target from the same source, running both and cross-checking their
results **increases fidelity** — agreement corroborates both translators;
disagreement localizes a bug to one pair. Branching is how the platform
turns several merely-`checked` pairs into a jointly stronger guarantee.

See [`ROUTES.md`](./ROUTES.md).

## How pairs come to exist

Pairs are **recommended by evidence, registered by humans, and
implemented by agents**. The platform keeps books
([`AGENTS.md`](./AGENTS.md) §1): every question it cannot satisfy is
recorded as a demand naming the missing pair, and a pair must pay for
itself by removing a named obstacle — connectivity, loss, shape, cost,
or trust. A human reads the recommendation, decides the pair is worth
building, and writes its one-page registration brief under
[`pairs/`](./pairs/), citing the evidence. That registration **triggers
an independent, per-pair agent** whose sole job is to implement that one
pair against the [`PAIRING.md`](./PAIRING.md) contract — reusing the
shared, standalone interpreters for the languages it touches. Per-pair
agents run independently and must not break each other's pairs or the
shared interpreters they depend on. The framework every pair inherits —
registry, cache, the commuting-square oracle, the route runner, the player
surface — is itself built first, as a one-time platform deliverable,
followed by the per-language interpreters, then the pairs. See
[`AGENTS.md`](./AGENTS.md) and [`FRAMEWORK.md`](./FRAMEWORK.md).

That process is also the intended growth model: hurdy-gurdy is meant to
evolve into an open platform that **scales in language support**, where
anyone — working with LLMs, with agents, or by hand — develops a new
pair against the [`PAIRING.md`](./PAIRING.md) contract and lands it
through an ordinary pull request. The admission bar is the architecture,
not the author: a pair arrives with its declared projection and grade,
its typed partiality, and a square the harness runs on merge, and the
widening ratchet keeps every prior verdict standing as the graph grows.

## The initial registry

The registry centers on two reasoning **hubs** — BTOR2 (bit-level) and
SMT-LIB (theory-rich) — fed by several front-ends and bridged to each other.
Fifteen pairs are registered — the thirteen initial ones plus two
directional endo-pairs on the BTOR2 hub: `btor2-havoc` (an abstraction
hop, built) and `btor2-interval` (registered as a brief); the full
tables, with
every language, the formal model behind each source, and the solvers and
checkers, are in [`REGISTRY.md`](./REGISTRY.md).

The **spine** is the route from C to a theory solver:

| Pair | Source → Target | Note |
|------|-----------------|------|
| `c-riscv` | C → RISC-V | translator is a **pinned** C compiler (`reproducible`) |
| `riscv-btor2` | RISC-V → BTOR2 | translator built **from the RISC-V specification** |
| `riscv-sail` + `sail-btor2` | RISC-V → SAIL → BTOR2 | a second route, **from the RISC-V model in Sail** |
| `btor2-smtlib` | BTOR2 → SMT-LIB | reasoning-to-reasoning bridge |

Around it, more front-ends reach the **BTOR2 hub** — `aarch64-btor2`,
`wasm-btor2`, `ebpf-btor2`, `evm-btor2` — while `crn-smtlib` and
`python-smtlib` reach the **SMT-LIB hub** directly, and
`smiles-formula` exercises the calculus away from solvers entirely.

The spine already induces a **branching route** to BTOR2 from RISC-V:

```text
   C ──▶ RISC-V ──────────────▶ BTOR2 ──▶ SMT-LIB
              └──▶ SAIL ──▶ BTOR2 ──▶ SMT-LIB
```

RISC-V reaches BTOR2 two ways — directly (`riscv-btor2`) and via Sail
(`riscv-sail` → `sail-btor2`). Cross-checking the two BTOR2 outputs is the
fidelity payoff the architecture is built for; AArch64 has the same branch
registered (`aarch64-btor2` vs `aarch64-sail` → `sail-btor2`).

## Using hurdy-gurdy

The platform is mechanism; the **player** — an LLM, or a human — supplies
the reasoning. A player connects through a single, pair-generic interface
that exposes the edges of the square (translate, interpret, carry back,
cross-check), the registry (languages, pairs, routes), and — for reasoning
targets — deciding and witness-checking. The platform enumerates faithful,
deterministic options; it never chooses what to ask, which route to take,
or which solver to run. The same surface is exposed to LLM players as an
MCP server over stdio JSON-RPC (`gurdy mcp`). See
[`INTERFACE.md`](./INTERFACE.md).

## About the name

A hurdy-gurdy is a string instrument whose player cranks a mechanical
wheel; the wheel sounds the strings — paired as drone and melody — and a
keyboard of tangents deterministically sets the pitch. The player chooses
*what* to play; the mechanism turns that choice into sound the same way
every time.

The mapping is close. A **pair** is a drone+melody pairing — the unit
that produces meaningful output. The **translator** is the keyboard: a
fixed, deterministic mapping from input to output, same key → same pitch.
The **interpreters** are the wheel: the mechanical step that makes the
sound real. And the **player** — the LLM or the human — decides what to
ask and which keys to press, while the instrument handles the mechanics
faithfully and predictably.

## Reading order

1. This file — what hurdy-gurdy is.
2. [`FRONTIER.md`](./FRONTIER.md) — the destination the rest is a means
   to: benchmarks in, a map of decidability-in-practice out —
   saturation defined and made mechanical (`gurdy saturation`, the
   frontier loop), the two pair-production lanes, and the key
   experiment. Read it first to know what the rest is *for*.
3. [`ARCHITECTURE.md`](./ARCHITECTURE.md) — the pair as a commuting
   square; determinism, fidelity, and shared interpreters in full.
4. [`ROUTES.md`](./ROUTES.md) — composing pairs into routes; branching to
   increase fidelity.
5. [`SOLVERS.md`](./SOLVERS.md) — for reasoning-language targets: deciding
   questions and verifying the answers (solvers + witness checkers).
6. [`BENCHMARKS.md`](./BENCHMARKS.md) — fidelity vs. coverage; how trivial
   designs are caught, per-pair and per-route.
7. [`PAIRING.md`](./PAIRING.md) — the contract a pair must meet; what is
   shared vs. what each pair owns.
8. [`AGENTS.md`](./AGENTS.md) — how a registration triggers a per-pair
   agent, and the boundaries that agent works within.
9. [`FRAMEWORK.md`](./FRAMEWORK.md) — the platform layer pairs inherit, and
   the bootstrap order (framework → interpreters → pairs).
10. [`INTERFACE.md`](./INTERFACE.md) — the LLM-facing surface: how a player
   connects to and drives the platform.
11. [`REGISTRY.md`](./REGISTRY.md) — the live registry, then the briefs
   under [`languages/`](./languages/) and [`pairs/`](./pairs/).
12. [`DOCKER.md`](./DOCKER.md) — the pinned toolchain image for building and
   validating pairs.
13. [`SCALING.md`](./SCALING.md) — the plan for automating pair development at
   scale: independent builder agents into PRs, a coordinator that integrates
   shared-emitter edits without human sign-off, and the grader hardening that
   lets a green gate bear that trust.
14. [`POTENTIAL.md`](./POTENTIAL.md) — what the graph of pairs can and cannot
   grow into: an LLM generating pairs in a loop, directional squares and
   abstraction pairs, and the limit the loop converges to — read beside
   [`FRONTIER.md`](./FRONTIER.md), which says what that limit is *for*.

## Lineage

Hurdy-gurdy descends from rotor, originally developed as part of selfie
([`github.com/cksystemsteaching/selfie`](https://github.com/cksystemsteaching/selfie),
`tools/rotor.c`). The RISC-V–to–BTOR2 translation draws on rotor's
encoding choices. Hurdy-gurdy is not a port: it generalizes one fixed
translation into a graph of registered pairs, keeps all reasoning in the
player rather than in built-in policies, and makes each pair's
specification — not any source code — the authoritative contract.

## License

MIT. See [`LICENSE`](./LICENSE).
