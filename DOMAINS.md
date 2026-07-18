# Domains — applying the platform to any domain with formal languages

The destination ([`FRONTIER.md`](./FRONTIER.md)) is stated over
benchmarks and questions, not over programs: eventually hurdy-gurdy
must apply to **any domain with formal languages** — any place a
definable meaning function exists, whether its objects are programs,
molecules, reaction networks, or something the registry has not met
yet. This document records the domain-specificity audit (2026-07-18)
against that goal and names the work the audit implies. The finding:
the mechanism core is **already domain-agnostic** — the
verification-domain commitment lives in exactly four load-bearing
places and two mechanical ones. It is a design document in the sense
of [`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md): §4 is named work, not
landed code.

## 1. What is already generic — the audit

- **The core is clean.** Grepping every module of
  [`gurdy/core/`](./gurdy/core/) for concrete language names (btor2,
  smtlib, riscv, sail, aarch64, wasm, ebpf, evm, crn, smiles) finds
  **four hits, all docstring examples** (`route.py`, `registry.py`,
  `grade.py`, `errors.py`) and none in logic. The framework's claim —
  it "holds no pair semantics" ([`FRAMEWORK.md`](./FRAMEWORK.md) §2)
  — holds in code.
- **Hubs are emergent, not hardcoded.** A reasoning language is any
  registered language that declares `question_shapes`
  ([`gurdy/core/registry.py`](./gurdy/core/registry.py));
  hub-connectivity is computed from the registry
  ([`gurdy/core/whynot.py`](./gurdy/core/whynot.py)). Register a new
  domain's reasoning language and the diagnosis, the books, and the
  frontier derivation serve it unchanged.
- **Question shape is a free string**, matched against per-language
  declarations — nothing about programs in the `Question` type.
- **The domain sits in per-language capabilities, where it belongs.**
  Solvers and checkers attach to languages
  ([`SOLVERS.md`](./SOLVERS.md) §2); the reduction advisor is
  [`gurdy/languages/btor2/coi.py`](./gurdy/languages/btor2/coi.py),
  not core.
- **Two domains beyond programs already inhabit the registry.**
  `smiles-formula` (chemistry — no solver anywhere near it, and zero
  special-casing in core) and `crn-smtlib` (reaction networks, routed
  into the SMT-LIB hub). The square, coverage, and the books served
  both without modification — the existence proof that the
  architecture, not just the intention, generalizes.
- **The theory is domain-neutral.** The five obstacles, the fidelity
  ladder, and the frontier derivation mention no domain; the
  mechanization models answerability as a filtration through `N`
  ordered conditions
  ([`paper/mechanization/`](./paper/mechanization/README.md),
  `Frontier.lean`) with nothing verification-shaped in it.

## 2. The four load-bearing commitments

Where the verification flavor actually lives, deepest first:

1. **The behavior model**
   ([`gurdy/core/types.py`](./gurdy/core/types.py)). A behavior is a
   `Trace = Sequence[State]` — an ordered sequence of post-step
   states — and the oracle localizes divergence to
   `(step, observable)`. That is a commitment to small-step
   operational semantics. Domains whose meaning function is not
   step-indexed (denotational, equational/algebraic, distributions as
   behaviors) must today encode into step sequences. The file already
   flags the widening as "a later increment"; this is the deepest
   commitment, because the commuting-square oracle's localization
   guarantee is built on it.
2. **Decision-shaped questions and the verdict vocabulary**
   ([`gurdy/core/question.py`](./gurdy/core/question.py),
   [`gurdy/core/solver.py`](./gurdy/core/solver.py)). Questions are
   `(p, φ)` asked existentially or universally; verdicts are
   `reachable` / `unreachable` / `unknown` / `resource-out`; and the
   trust asymmetry rests on a witness being an input binding replayed
   through the source interpreter. Function-shaped questions —
   *compute* the answer, optimize, count — do not fit the four-verdict
   vocabulary and live outside `decide` entirely: `smiles-formula`'s
   computed molecular formula is the standing example, checked today
   by the square alone. The platform's own scope sentence ("questions
   that reduce to decision procedures") declares this boundary — so
   widening it is a deliberate calculus extension, not a bug fix.
3. **The atlas** ([`gurdy/core/atlas.py`](./gurdy/core/atlas.py)).
   The one verification-specific table in core: eight charted shapes
   (reachability, bounded-unreachability, liveness, termination, LTL,
   CTL, hypersafety-2, probabilistic-reachability), each with its
   classical crossing. Any other domain's shape honestly reads
   `uncharted` — correct, but it means the shape obstacle's
   known-crossing guidance is verification-only until the atlas grows
   per-domain sections.
4. **Executable-semantics replay.** The checking discipline assumes
   both languages carry *executable* semantics — interpreters as the
   deterministic oracles everything replays through.
   [`SCALING.md`](./SCALING.md) §11's circular-interpreter residue is
   the near edge of this; a domain with non-executable or
   prohibitively expensive semantics is the far one, and there the
   existential-replay guarantee thins.

## 3. Two mechanical residues

Neither is semantic; both are refactors the next domain would force:

- **Registration bootstrap.**
  [`gurdy/cli.py`](./gurdy/cli.py) registers by hardcoded
  side-effecting imports of every pair and language; entry-point
  discovery would decentralize it as the registry grows.
- **The advisor dispatch.** `gurdy suggest-reduction` dispatches
  directly to the BTOR2 implementation; with one advisor registered,
  the per-language advisor protocol simply has not been forced yet.
  `coi.py` becomes its first implementation, not its definition.

## 4. The named work, ordered by depth

1. **Computed answers beside `decide`** — the calculus extension. An
   `answer` operation whose result is a value in a declared canonical
   form, with a per-answer-kind certificate obligation and a
   deterministic checker — the same producer-quarantined /
   checker-deterministic seam as `decide`/`check`
   ([`SOLVERS.md`](./SOLVERS.md) §1) — and a verdict vocabulary
   neutral enough to carry it. This is where the `smiles-formula`
   pattern becomes first-class instead of exceptional.
2. **The widened behavior contract.** Richer observable values and
   non-step-indexed behaviors, with the localization guarantee
   renegotiated per behavior kind — what replaces
   `(step, observable)` must be named, per kind, before the oracle
   accepts it; localization is the property, steps are one carrier.
3. **The per-family atlas.** Atlas sections keyed by language family
   or domain, still reference data, still review-grown and never
   builder-writable ([`SCALING.md`](./SCALING.md) §9) — so a
   shape-blocked chemistry demand can arrive naming chemistry's
   literature, not verification's.
4. **The advisor protocol.** A per-language capability slot for
   reduction advisors, dispatched by the language of the artifact.
5. **Registration discovery.** Entry-point registration replacing
   the import list in `cli.py`.

What does **not** change, on the audit's evidence: the pair as a
commuting square, determinism, the fidelity and coverage axes, the
five obstacles, the frontier currency, and the gate. Those are the
domain-neutral spine; the work above is confined to the four
commitments of §2 and the two residues of §3.

*Status (2026-07-18): §1 is the audit as measured; §4 items 1–5 are
named future work, none landed. Item 1 is the deep one — a calculus
extension with its own paper-side statement — and items 3–5 are
ordinary increments any second domain would justify on its own.*
