# hurdy-gurdy

A platform for building **deterministic, fidelity-graded translations**
between formal languages, so that an LLM (or a human) can move a program
into whatever representation makes a question answerable — and reason
about it there through external interpreters and solvers — without ever
trusting an unaudited step.

The unit of the platform is the **pair**; pairs compose into **paths**.
This repository is the *lean architecture*: it defines what pairs and
paths are, the contract every pair must meet, and how pairs are
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

## Paths

Two pairs **compose** when the target language of one is the source
language of the next. A **path** is such a composition — a route through
the language graph from a starting language to a destination. Paths
inherit determinism (a path is deterministic iff every pair is) and
fidelity (a path is only as faithful as its weakest pair, unless a
higher-fidelity pair re-establishes it along the way).

Crucially, paths may **branch**: when two different routes reach the same
target from the same source, running both and cross-checking their
results **increases fidelity** — agreement corroborates both translators;
disagreement localizes a bug to one pair. Branching is how the platform
turns several merely-`checked` pairs into a jointly stronger guarantee.

See [`PATHS.md`](./PATHS.md).

## How pairs come to exist

Pairs are **registered by humans** and **implemented by agents**. A human
decides a pair is worth building and writes its one-page registration
brief under [`pairs/`](./pairs/). That registration **triggers an
independent, per-pair agent** whose sole job is to implement that one
pair against the [`PAIRING.md`](./PAIRING.md) contract — reusing the
shared interpreters for languages that already exist, and contributing a
new shared interpreter for any language that does not. Per-pair agents
run independently and must not break each other's pairs or the shared
interpreters they depend on. See [`AGENTS.md`](./AGENTS.md).

## The initial registry

Five pairs are registered. Their full briefs are under [`pairs/`](./pairs/);
the live registry — languages, shared interpreters, pairs, and the paths
they induce — is [`REGISTRY.md`](./REGISTRY.md).

| Pair          | Source → Target  | Note |
|---------------|------------------|------|
| `c-riscv`     | C → RISC-V       | translator is a **pinned** C compiler (`reproducible`) |
| `riscv-btor2` | RISC-V → BTOR2   | translator built **from the RISC-V specification** |
| `btor2-smtlib`| BTOR2 → SMT-LIB  | reasoning-to-reasoning bridge |
| `riscv-sail`  | RISC-V → SAIL    | translator built **from the RISC-V model in Sail** |
| `sail-btor2`  | SAIL → BTOR2     | |

These five already induce a **branching path** to BTOR2 from RISC-V:

```text
   C ──▶ RISC-V ──────────────▶ BTOR2 ──▶ SMT-LIB
              └──▶ SAIL ──▶ BTOR2 ──▶ SMT-LIB
```

RISC-V reaches BTOR2 two ways — directly (`riscv-btor2`) and via Sail
(`riscv-sail` → `sail-btor2`). Cross-checking the two BTOR2 outputs is the
fidelity payoff the architecture is built for.

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
2. [`ARCHITECTURE.md`](./ARCHITECTURE.md) — the pair as a commuting
   square; determinism, fidelity, and shared interpreters in full.
3. [`PATHS.md`](./PATHS.md) — composing pairs into paths; branching to
   increase fidelity.
4. [`PAIRING.md`](./PAIRING.md) — the contract a pair must meet; what is
   shared vs. what each pair owns.
5. [`AGENTS.md`](./AGENTS.md) — how a registration triggers a per-pair
   agent, and the boundaries that agent works within.
6. [`REGISTRY.md`](./REGISTRY.md) — the live registry, then the briefs
   under [`languages/`](./languages/) and [`pairs/`](./pairs/).

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
