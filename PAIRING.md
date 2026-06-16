# Pairing — the contract for implementing a pair

This is what it takes to turn a registered pair brief ([`pairs/`](./pairs/))
into a working pair. It is the contract a per-pair agent
([`AGENTS.md`](./AGENTS.md)) implements against. Read
[`ARCHITECTURE.md`](./ARCHITECTURE.md) first: the vocabulary (the six
components, the commuting square, determinism, fidelity, shared
interpreters) is defined there and used here without re-deriving it.

## 1. What you must deliver

A pair `L_s → L_t` ships exactly these, and nothing the framework already
provides:

1. **The translator** `T : source program → target program`. Deterministic.
   Implements the pair's written translation specification mechanically;
   makes no adaptive choices.
2. **The target-to-source interpreter** `L : target behavior → source
   behavior`. Carries a target trace or a raw solver witness back to a
   source-level behavior.
3. **The projection** `π`. The named observable fields the pair promises to
   preserve — the precise statement of what "faithful" means here, and what
   the cross-check checks.
4. **The fidelity declaration** and its **evidence** — which tier (§4) and
   the artifact that backs it (a specification to read, a toolchain digest,
   a corpus the oracle passes, or a re-checkable proof certificate).
5. **A source loader**, if the source language needs one (bytes → an
   in-memory model the translator consumes).
6. **The shared interpreter for any *new* language** this pair introduces
   (§3). If both languages already exist in [`languages/`](./languages/),
   you write none.

**If the target is a reasoning language**, the pair additionally declares
which shared solvers and witness checkers it dispatches to, the model /
witness shape its target-to-source interpreter consumes, and — for any
`proved` claim — the checker and trusted computing base behind it. It
implements no solver or checker of its own beyond what the language shares
([`SOLVERS.md`](./SOLVERS.md) §8).

**Coverage is a deliverable, not an afterthought.** Translate the full
in-scope construct set the brief fixes (which the agent cannot shrink), abort
on anything else with a typed `unsupported: <construct>` (never a silent
drop), and wire the language's public benchmark suite where one exists. A
pair is measured on **coverage** as much as **fidelity**, conjoined per
construct ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §7,
[`BENCHMARKS.md`](./BENCHMARKS.md)).

Everything else — the registry, the cache, the generic commuting-square
oracle, the path runner, the player-facing surface — is inherited. If you
find yourself writing one of those, the contract is wrong; fix the
contract, not the framework.

## 2. Specification-first discipline

Two rules hold for every pair:

1. **Code follows the specification.** A pair's translation is governed by
   a written specification (a schema for a `predicted` pair; a
   reproducibility-and-preservation contract for a `reproducible` one). If
   the implementation and the specification disagree, the implementation is
   wrong. Changing the specification is a versioned event that invalidates
   caches.
2. **The predictability test.** For a `predicted` pair, anyone who has read
   the source, the inputs, and the specification must in principle be able
   to reproduce the translator's output byte-for-byte. Anywhere the
   translator would otherwise make a heuristic choice, that choice becomes
   either fixed in the specification or a caller-supplied parameter — never
   an internal, learned, or adaptive decision. (A `reproducible` pair
   relaxes "predict" to "replay from a pin," but the no-hidden-state rule is
   unchanged.)

The litmus question for any line of pair code: *would deleting it make
hurdy-gurdy simpler without changing what a player could in principle do or
predict?* If yes, it should not be there.

## 3. Reusing and contributing shared interpreters

Source and target interpreters are owned by languages, not pairs
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §6).

- **If a language already exists** under [`languages/`](./languages/),
  import its interpreter. Do not copy it, fork it, or write a second one.
- **If your pair is the first to touch a language**, you build that
  language's shared interpreter and place it under
  `languages/<language>/`, with its own determinism check and its
  observable/projection conventions documented. The next pair over that
  language will depend on exactly what you ship.
- **A shared interpreter is a shared contract.** Treat any change to it as
  affecting every dependent pair: bump the language's interpreter version
  and re-validate every dependent pair's square. Never make a
  language-interpreter change to satisfy one pair in a way that silently
  alters another.

## 4. Declaring fidelity honestly

Pick the tier your evidence actually supports
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §7):

- `predicted` — ship the specification from which the bytes follow.
- `reproducible` — ship the digest-pinned toolchain and the exact,
  ordered invocation; ship a twice-and-diff test.
- `checked` — ship the corpus and wire the commuting-square oracle (and/or
  a differential against an independent tool) so the square is validated
  every run.
- `proved` — ship a certificate an independent checker re-verifies; state
  exactly what it proves (the square, for which programs and inputs).
- `trusted` — only if unavoidable, and only behind a higher-fidelity check
  or a corroborating branch ([`PATHS.md`](./PATHS.md) §4).

Do not inflate the tier. "Validated on the inputs we tried" is `checked`,
not `proved`. The fidelity a pair claims is the fidelity a path inherits.

## 5. The determinism contract

- `T`, `I_s`, `I_t`, `L` are all pure: same input → byte-identical output,
  on any host.
- Guard against the usual leaks: iteration/hash order, filesystem walk
  order, timestamps, unpinned tools (see
  [`ARCHITECTURE.md`](./ARCHITECTURE.md) §4).
- Ship a recompile-and-diff test for the translator. If the pair
  introduces a new language interpreter, ship one for the interpreter too.
- Build and run these checks against the **pinned toolchain image**
  ([`DOCKER.md`](./DOCKER.md)) so the compiler, solvers, checkers, and
  interpreter oracles are at fixed versions; cite its digest with any
  `reproducible` / `checked` / `proved` claim.
- A **solver is the one exception**: it is an oracle and may be internally
  non-deterministic. Its verdict earns trust by pinning, by agreement, or
  by an independently-checked witness — never by assumption. Witness
  *checkers*, by contrast, are deterministic and pinned like interpreters
  ([`SOLVERS.md`](./SOLVERS.md) §1, §5).

## 6. The faithfulness story

State, in the pair's specification, how the square is shown to commute —
the pair's soundness story:

- For a rule-for-rule `predicted` translation, the translator and the
  target-to-source interpreter share one source of truth (the per-construct
  lowering), and a cross-check runs both on the same inputs and asserts
  agreement under `π`.
- For an opaque `reproducible` head, there is no per-construct schema to
  mirror; faithfulness is established **downstream** — by the
  commuting-square oracle at the far end of the path, by a differential
  against an independent tool, or by a corroborating branch.
- For a `proved` pair, the certificate *is* the story; document what it
  discharges and which independent checker re-verifies it.

Whichever applies, the projection `π` makes it concrete: the cross-check is
"the two behaviors agree on `π`," and a divergence is reported at a step and
an observable.

## 7. Tests every pair ships (minimum)

- **Determinism**: twice-and-diff on the translator (and any new
  interpreter).
- **Per-construct translation** unit tests against the specification.
- **Commuting-square / soundness** check: `I_s(p)` vs `L(I_t(T(p)))` under
  `π`, on a small corpus (or the pair's declared alternative soundness
  story, §6).
- **Carry-back**: a target witness replays through `L` to a source-level
  behavior that exhibits the property.
- **Registration smoke test**: from a fresh import, the pair is listed in
  the registry and every edge-operation of its square is callable.

## 8. Registration checklist

A pair is *done* when, mechanically:

- [ ] It is registered in the pair registry under its kebab-case id
  `<source>-<target>` (the directory name under `pairs/`).
- [ ] Both languages are registered under [`languages/`](./languages/);
  any new one ships its shared interpreter.
- [ ] The translator and target-to-source interpreter are deterministic
  (twice-and-diff passes).
- [ ] The projection `π` is declared and the commuting-square check passes
  on the pair's corpus (or the declared soundness story holds).
- [ ] The fidelity tier is declared with its evidence attached, and is not
  inflated.
- [ ] The pair's specification is self-contained and reviewable.
- [ ] Coverage meets the brief's target on the external yardstick (construct
  inventory + public suite); unsupported constructs hard-abort with a typed
  error; the `unsupported` histogram is attached; status reflects measured
  coverage (`partial` below target, `built` only at/above it)
  ([`BENCHMARKS.md`](./BENCHMARKS.md)).
- [ ] If the target is a reasoning language: the shared solvers and witness
  checkers it uses are wired, the witness shape `L` consumes is declared,
  and any `proved` claim names its checker and TCB
  ([`SOLVERS.md`](./SOLVERS.md)).
- [ ] The pair appears in [`REGISTRY.md`](./REGISTRY.md) and its brief
  under [`pairs/`](./pairs/) is updated from *registered* to *built*.

## 9. What we still expect to learn

This contract is written from a small number of pairs and will evolve.
Known open questions:

- The right soundness story for a source language whose real interpreter is
  large (you may re-execute against the real interpreter rather than mirror
  it in a purpose-built one).
- Whether one language's interpreter conventions (post-step state,
  projection shape) generalize cleanly to very different languages.
- How far a result lifted across a long path stays meaningful — the loss
  accounting of [`PATHS.md`](./PATHS.md) §3 is the current honest answer.

Record what you learn in the pair's brief when you finish, so the next
agent inherits it.
