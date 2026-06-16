# Architecture — the pair

This document defines a **pair** precisely: its six components, the
commuting-square contract that ties them together, the determinism every
component must satisfy, the fidelity it declares, and the way interpreters
are shared across pairs. Composition of pairs into paths is the subject of
[`PATHS.md`](./PATHS.md); the obligations this places on an implementer are
spelled out in [`PAIRING.md`](./PAIRING.md).

## 1. Languages

A **language** is admissible in hurdy-gurdy iff it carries a **formal
semantics** — a definable meaning function over its programs. That is the
only membership rule. Executability is not required and "program" is not
required: an instruction set, a logic, a modeling language, or a
mathematical notation all qualify as long as their meaning is defined.

A language is field-blind. Today's languages are all close to
computation (C, RISC-V, BTOR2, SMT-LIB, Sail), but the architecture does
not assume that, and the contract below never appeals to it.

Each language brings, at most, two interpreters (§5): one that runs it as
a *source* and one that runs it as a *target*. In practice a single
interpreter serves both roles. These interpreters are **owned by the
language and shared by every pair that touches it** (§6).

## 2. The six components of a pair

A pair `P : L_s → L_t` is:

| # | Component | Type | Owned by |
|---|-----------|------|----------|
| 1 | source language `L_s` | a registered language | the language registry |
| 2 | target language `L_t` | a registered language | the language registry |
| 3 | **translator** `T` | `source program → target program` | the pair |
| 4 | **source interpreter** `I_s` | `source program → source behavior` | the language `L_s` (shared) |
| 5 | **target interpreter** `I_t` | `target program → target behavior` | the language `L_t` (shared) |
| 6 | **target-to-source interpreter** `L` | `target behavior → source behavior` | the pair |

The translator and the target-to-source interpreter are **pair-specific**:
they encode the particular correspondence between *this* source and *this*
target. The two ordinary interpreters are **language-specific and shared**.

> **Why a target-to-source interpreter, and not just a "lifter"?** Its job
> is to take what happened on the target side — a solver's
> counterexample, a concrete target trace — and replay/re-express it as a
> source-level behavior, so that an answer obtained in the target language
> is delivered as a fact about the source program. It is the bottom edge
> `L` of the square below, and the thing that makes a target-side result
> *mean something* about the source.

## 3. The commuting square

The six components are the corners and edges of a square:

```text
                 T  (translate)
   L_s program ───────────────────▶ L_t program
        │                                │
      I_s                              I_t
        ▼                                ▼
   source behavior ◀──────────────── target behavior
                    L  (target-to-source)
```

**The faithfulness contract.** For every source program `p`, with inputs
held in correspondence:

```text
   I_s(p)  ≡_π  L( I_t( T(p) ) )
```

The left-hand side runs the source program directly. The right-hand side
translates it, runs the translation, and carries the result back. They
must agree **up to the projection `π`** — the set of observable fields the
pair declares it preserves (post-step program counter, registers, halt
flag for an ISA; whatever the analogous observables are elsewhere). The
bottom edge is an identification *up to `π`*: the two behaviors are
compared through a shared observable space, not required to be identical
in their private representations.

The square **commuting is the pair's correctness statement.** A point
where it fails to commute is a translator (or interpreter) defect,
localized to a concrete step and a named observable — e.g. *"diverged at
step 14, observable `pc`."* That localization is what distinguishes this
architecture from a monolithic verifier: every translation has an
independent oracle of equal expressiveness, so a bug points at itself.

A pair must **declare its projection** `π`. The projection is part of the
pair's contract: it states exactly what "preserves meaning" is promised to
mean for this pair, and therefore exactly what the cross-check verifies.

## 4. Determinism (the standing invariant)

Every one of the four functions — `T`, `I_s`, `I_t`, `L` — is a **pure,
deterministic function**: identical input produces byte-identical output,
on every host, forever.

- **For the translator**, determinism is what makes a translation
  *predictable* (`predicted` fidelity) or at least *replayable*
  (`reproducible`), and what makes its output content-addressable for
  caching.
- **For the interpreters**, determinism is what makes the commuting-square
  check meaningful: a divergence must be a real defect, never a coin flip.

Common accidental sources of nondeterminism to forbid in any
implementation: dictionary/iteration order, hash randomization in symbol
emission, filesystem walk order in a loader, wall-clock or date stamps in
emitted output, and unpinned third-party tools. None of these may reach an
output's bytes.

A pair ships a cheap **recompile-and-diff** check: translate the same
input twice, assert byte-identical output. The same idea lifts to paths
(see [`PATHS.md`](./PATHS.md)).

## 5. Interpreters

An interpreter is a deterministic executor that produces a **behavior** —
a sequence of post-step observable states (a *trace*). Two conventions
keep cross-checking simple and are recommended for every language:

- **Post-step state.** Record observable state *after* each transition.
  This keeps the cross-check local and avoids off-by-one alignment bugs.
  A language that records pre-step state must say so, and both sides of
  any pair using it must agree.
- **Projectable observables.** The interpreter exposes its state through
  named observable fields, so that a pair's projection `π` can be defined
  as a subset of them.

The **target-to-source interpreter** `L` is the one interpreter-shaped
component that is *not* language-owned: it consumes a target behavior
(or a raw solver witness for it) and produces a source behavior. It is the
pair's, because the correspondence it encodes is the pair's.

**Reasoning-language targets carry more than an interpreter.** When the
target is a reasoning language — one a mechanized solver consumes directly
— the language also owns a *solver* (an oracle that decides a question over
*all* inputs) and a *witness checker* (which re-validates what the solver
claims). Both are distinct from the deterministic interpreter here, sit on
the opposite side of the determinism line (§4), and are shared across pairs
exactly as the interpreter is. Their contract is [`SOLVERS.md`](./SOLVERS.md).
(A pair whose target is a reasoning language is a *reasoning pair*; a pair
whose target is a plain representation that no solver consumes — like
`smiles-formula`, SMILES → molecular formula — is a *compile pair*, and
carries no solver, checker, or `proved` tier.)

## 6. Sharing interpreters across pairs

Interpreters are attached to languages, not pairs. A language's source and
target interpreters are written **once** and reused by **every** pair that
touches that language:

```text
   languages/riscv   ── interpreter shared by ──▶ c-riscv, riscv-btor2, riscv-sail
   languages/btor2   ── interpreter shared by ──▶ riscv-btor2, btor2-smtlib, sail-btor2
   languages/sail    ── interpreter shared by ──▶ riscv-sail, sail-btor2
```

Consequences that the implementation must honor:

- **First touch builds it; later touches reuse it.** The agent that
  implements the first pair over a new language also contributes that
  language's interpreter to [`languages/`](./languages/). Subsequent pairs
  import it; they do not fork it.
- **A shared interpreter is a shared contract.** Changing a language's
  interpreter affects every pair over that language. Such a change is a
  versioned event (it bumps the language's interpreter version and
  re-validates every dependent pair's square), never a quiet edit inside
  one pair.
- **No private copies.** A pair that reaches into another pair's internals
  to borrow an interpreter is a signal that the interpreter belongs in the
  shared language layer. Promote it; do not copy it.

This is the single most important structural rule for keeping `N` pairs
from becoming `N` reimplementations of the same `k` languages.

## 7. Fidelity and coverage — the two anti-trivial axes

A pair declares a **fidelity** — the strength of, and the evidence for,
its faithfulness contract (§3). Fidelity is *not* the same axis as
determinism: a translation can be perfectly deterministic and still only
weakly faithful (you can reproduce its bytes without being able to predict
or prove that they mean the right thing).

| Fidelity      | Guarantee | How it is established |
|---------------|-----------|-----------------------|
| `predicted`   | output derivable byte-for-byte from a written specification | a reader (LLM or human) reproduces the bytes from the spec |
| `reproducible`| determinism only — pinned ⇒ identical bytes | a digest-pinned toolchain and recorded flags |
| `checked`     | the square is validated against the source **every run** | the commuting-square oracle and/or a differential cross-check on a corpus |
| `proved`      | a machine-checked proof that the square commutes | a refinement proof or translation-validation certificate, re-checked by an **independent** tool; its strength is the checker's pedigree, and it records a trusted computing base ([`SOLVERS.md`](./SOLVERS.md) §6) |
| `trusted`     | none | quarantined; admitted only behind a higher-fidelity check |

Two notes that matter:

- **Fidelity tracks the kind of languages.** When both languages are
  formal and the translation is rule-for-rule (e.g. one reasoning logic to
  another, where every operator maps to a standard counterpart), `predicted`
  or even `proved` is reachable. When the translator is an opaque
  third-party tool (an optimizing compiler), `reproducible` is the
  honest ceiling for the tool itself — fidelity is then re-established
  *downstream*, by checking the result, or by a branch (see
  [`PATHS.md`](./PATHS.md)).
- **Proofs are first-class, not aspirational.** `proved` is a real tier
  with a real obligation: ship a certificate an independent checker can
  verify. Do not let the word "certified" drift from `checked` (validated
  on the inputs tried) up to `proved` (validated for all inputs by a
  proof). State which one a pair actually has. For reasoning-language
  targets — where a solver decides and a separate checker re-validates —
  this producer/checker split is specified in [`SOLVERS.md`](./SOLVERS.md).

The assurance ordering for composition is
`predicted, proved > checked > reproducible > trusted` — see
[`PATHS.md`](./PATHS.md) §3 for how a path computes its fidelity from its
pairs'.

### Coverage — fidelity's companion

Fidelity answers *is what you translated faithful?* It says nothing about
*how much* of the language you translated — a pair that handles a single
instruction can be vacuously `proved`. **Coverage** is the second axis: *how
much of the language does the pair actually handle?*, measured against a
yardstick the implementer does **not** choose (the spec-enumerable construct
inventory, and public benchmark suites).

The two axes are gamed in opposite directions — fidelity by **triviality**,
coverage by **unsoundness** — so a pair (and a path) must satisfy both,
reported **conjoined per construct**: a construct counts only when it is
*covered and faithful*. This is the platform's defense against trivial
designs; the full contract, per-pair and per-path (graded on merge by a
dedicated path-grader agent), is [`BENCHMARKS.md`](./BENCHMARKS.md).

## 8. What the framework provides vs. what a pair owns

The platform layer (shared by all pairs) provides: the language and pair
**registry**; the **shared interpreters** per language; for reasoning
targets, the per-language **solver and witness-checker inventories**
([`SOLVERS.md`](./SOLVERS.md)); the content-addressed **cache** keyed on
`(input hash, translator version)`; the generic **commuting-square oracle**
that walks `I_s(p)` against `L(I_t(T(p)))` and localizes a divergence; the
**path** runner and route enumerator ([`PATHS.md`](./PATHS.md)); and the
player-facing surface ([`INTERFACE.md`](./INTERFACE.md)) that exposes, per
pair, the operations named by the square's edges — *translate*,
*interpret-source*, *interpret-target*, *carry-back/target-to-source*, and
*cross-check* — plus, for reasoning targets, *decide* and *check-witness*.

A **pair** contributes only what is irreducibly its own: the
**translator**, the **target-to-source interpreter**, its declared
**projection** `π`, its declared **fidelity** and the evidence for it, and
— if it is the first pair over a language — that language's shared
interpreter. Everything else is inherited. The full implementer's contract
is [`PAIRING.md`](./PAIRING.md).

## 9. What hurdy-gurdy does not do

- It does not decide *what* to ask, choose which solver/budget to use, run
  refinement loops, or compose facts across questions. Those are the
  player's job; the platform translates, interprets, carries back, and
  cross-checks — mechanically and deterministically.
- It maintains **no hidden intermediate representation** inside a pair.
  When a translation genuinely needs to pass through another language,
  that language is *named*, registered, and given its own pair — a step on
  a path (§[`PATHS.md`](./PATHS.md)) — never a private, adaptive,
  unpredictable format buried inside one translator.
