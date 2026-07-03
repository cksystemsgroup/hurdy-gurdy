# Framework — the platform layer pairs inherit

A pair ships only its own irreducible parts ([`PAIRING.md`](./PAIRING.md) §1);
everything else — the registry, the cache, the commuting-square oracle, the
route runner, the solver/checker plumbing, the coverage harness, the player
surface — it **inherits**. That inherited layer is the **framework**, and it
is not magic: it is a real, **prerequisite deliverable**, built once before
the first pair. This document says what it is, who builds it, and in what
order — so that a pair agent's task is finite (it inherits a framework that
actually exists) rather than unbounded.

## 1. Deliverables and the bootstrap order

The platform is built as **four kinds of deliverable**, each human-registered
and each implemented by its own agent ([`AGENTS.md`](./AGENTS.md)):

```text
   1. framework        2. language interpreters     3. pairs            (4. route-grader,
   (this doc) ───────▶ (one per language, ────────▶ (translator + L  ───▶  on every merge)
   platform agent       standalone)                  per PAIRING.md)
```

- **The framework is first.** Until it exists there is nothing for a pair to
  inherit. A one-time **platform agent** builds it from this doc's contract.
- **Language interpreters are standalone.** A language's shared interpreter
  ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §§5–6) is its **own** deliverable —
  registered and built independently of any pair, by an interpreter agent —
  not bundled into "whichever pair lands first." This removes the race among
  independent pair agents that all need the same interpreter, and bounds each
  agent's effort.
- **Pairs come last** and inherit both the framework and the interpreters
  they touch; a pair contributes only its translator, its target-to-source
  interpreter, its projection, and its fidelity evidence.
- **The route-grader** ([`AGENTS.md`](./AGENTS.md) §7) is framework
  machinery, triggered on every merge once composing pairs exist.

This order is the answer to "can an agent do useful work with finite
effort?": each box is a finite chunk, and no chunk assumes a later one.

## 2. What the framework provides

The single source of truth for the "inherited" layer (the per-doc lists in
[`ARCHITECTURE.md`](./ARCHITECTURE.md) §8, [`SOLVERS.md`](./SOLVERS.md) §8,
and [`BENCHMARKS.md`](./BENCHMARKS.md) §8 are views of this one):

| Capability | What it is | Spec |
|------------|-----------|------|
| **Registry** | the language and pair graph; deliverable status (`registered`/`partial`/`built`) | [`REGISTRY.md`](./REGISTRY.md) |
| **Cache** | content-addressed store keyed `(input hash, translator version)`; extends across a route | [`ARCHITECTURE.md`](./ARCHITECTURE.md) §4, [`ROUTES.md`](./ROUTES.md) §2 |
| **Commuting-square oracle** | walks `I_s(p)` against `L(I_t(T(p)))` under `π`, localizing a divergence to a step/observable | [`ARCHITECTURE.md`](./ARCHITECTURE.md) §3 |
| **Route runner + route enumerator** | sequences a route's pairs, threads provenance and composed carry-back; enumerates routes (does not choose) | [`ROUTES.md`](./ROUTES.md) |
| **Solver / checker plumbing** | the `SolverBackend` and `WitnessChecker` protocols, pinning, limits, normalized `Result` | [`SOLVERS.md`](./SOLVERS.md) |
| **Coverage harness** | construct-inventory extractor, `unsupported` histogram, benchmark ingestion (submodule + streamed) | [`BENCHMARKS.md`](./BENCHMARKS.md) |
| **Route-grader** | merge trigger, capped route benchmarks, branch-agreement, the composition ratchet | [`AGENTS.md`](./AGENTS.md) §7, [`BENCHMARKS.md`](./BENCHMARKS.md) §6–7 |
| **Player surface** | the MCP server + `gurdy` CLI exposing the square edges, registry, decide/check | [`INTERFACE.md`](./INTERFACE.md) |

The framework holds **no pair semantics** — it is language- and
pair-agnostic mechanism. A pair plugs in through the `Pair`/language
registration interface; the framework never knows what a pair means.

## 3. Determinism and versioning

The framework is part of the deterministic core
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §4): the cache keys, the oracle's
projection walk, and the route fold must be byte-deterministic, and the
player surface must be a pure view over deterministic operations (only
`decide` is the quarantined oracle, [`SOLVERS.md`](./SOLVERS.md) §1). A
change to framework behavior that can alter any cached or compared bytes is
a **versioned event** that re-validates dependents — the same discipline a
shared interpreter change carries ([`AGENTS.md`](./AGENTS.md) §3).

## 4. The framework is itself staged (so the bootstrap is finite)

The platform agent does **not** build everything at once. It builds the
**minimum the first pair needs**, and the rest is demand-driven:

- **Minimum viable framework** (for the first single pair, end to end):
  the registry, the cache, the commuting-square oracle, one `SolverBackend`
  adapter, and a thin player-surface/CLI skeleton.
- **Added when a second pair demands it:** the rest of the solver/checker
  inventory and the layer/linker machinery.
- **Added when the first *route* demands it:** the route runner + route
  enumerator, and then the route-grader + composition ratchet.
- **Added when a `proved` claim demands it:** the `WitnessChecker` adapters
  ([`SOLVERS.md`](./SOLVERS.md) §5).
- **Added when coverage is gated:** the construct-inventory extractor and
  benchmark ingestion ([`BENCHMARKS.md`](./BENCHMARKS.md)).

Each increment is a finite deliverable with its own `partial`→`built`
status, exactly like a pair.

## 5. Who builds it

A one-time **platform agent**, from a human-registered framework brief, runs
before any per-pair agent and delivers the minimum-viable framework (§4); it
is the only agent permitted to write the shared framework code. Subsequent
framework increments are registered and triggered the same way. Per-pair and
interpreter agents then **inherit** it and never reimplement it — if a pair
agent finds itself writing framework, the contract is wrong
([`PAIRING.md`](./PAIRING.md) §1).

## 6. Registration — the minimum-viable framework (MVP-1)

The first deliverable on the whole platform. Status: **partial** — built so
far (`gurdy/`): the registry, cache, commuting-square oracle, the z3
`SolverBackend`, the CLI, the **route runner + route enumerator**
(`gurdy/core/route.py` / `gurdy routes`), the **coverage harness**
(`gurdy/core/coverage.py` / `gurdy coverage`), and the **route-grader**
measured-composition checks (`gurdy/core/grade.py`: composed determinism +
branch agreement), with a demo pair `demo-nat-smt` exercising compile →
decide → align end-to-end (`tests/test_framework_mvp1.py`). The rest of §4
(public-benchmark ingestion, witness checkers, and the merge-trigger /
regression-ratchet orchestration) is pending ([`REGISTRY.md`](./REGISTRY.md)).
A platform agent ([`AGENTS.md`](./AGENTS.md) §1) builds exactly the MVP slice
of §4 — no more.

**In scope (MVP-1):**

- the **registration interface** — `register_language` / `register_pair`,
  the `Language` / `Pair` objects, and the deliverable-status registry
  (`registered` / `partial` / `built`);
- the **trace / observable types** an interpreter produces and a projection
  selects over ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §5) — the contract the
  standalone interpreters plug into;
- the **content-addressed cache** keyed `(input hash, translator version)`;
- the generic **commuting-square oracle** — `align(I_s(p), L(I_t(T(p))), π)`
  with step/observable localization;
- **one `SolverBackend` adapter** (z3, from the dev image) and the
  normalized `Result` ([`SOLVERS.md`](./SOLVERS.md) §3);
- a thin **player surface** — the `gurdy` CLI + MCP skeleton exposing the
  square edges and registry introspection ([`INTERFACE.md`](./INTERFACE.md)).

**Out of scope (demand-driven, §4):** the route runner / route enumerator,
the route-grader + ratchet, the rest of the solver inventory, the
`WitnessChecker` adapters, the layer/linker machinery, and the coverage
harness. Each is its own later framework increment.

**Acceptance:** with MVP-1 installed, a trivial registered pair (a one-
construct fragment over an identity-like translator) can be compiled, its
square aligned, and one `decide` dispatched through z3 — end-to-end from the
CLI, deterministically (twice-and-diff). That is the rig the first real
interpreter and pair build against.

**Determinism:** everything above except `decide` is byte-deterministic
(§3); ship the twice-and-diff harness as part of MVP-1 so every later
deliverable inherits it.
