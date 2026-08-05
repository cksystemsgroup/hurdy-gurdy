# Kernel — hurdy-gurdy designed fresh

This document is the vision and the specification of the re-designed
platform, approved 2026-08-05. It learns from the current shape
([`ARCHITECTURE.md`](./ARCHITECTURE.md) and everything downstream) but
is not an increment to it: the organizing move is that **translation
and solving are the same kind of edge, and results are the only
currency**. Everything the old design tracked in separate machinery —
books, boards, demand records, briefs, mandates, the valve, the lanes,
the oracle operators, the diagnosis filtration — collapses into one
object, the result, because the consumer of frontier evidence changes:
it used to feed mechanical derivation (which needs typed taxonomies);
now it feeds an LLM conjecturing (which wants rich evidence and
tolerates prose). The rule that keeps the collapse honest:

> **Structure only what the kernel must compute with; everything else
> is evidence for the LLM and stays prose.**

## 1. The primitives

**Language** = deterministic syntax (parser/validator) + deterministic
interpreter exposing named observables. Two kinds:

- **Root languages**: the formats benchmarks arrive in. Their
  interpreters are the trusted base — graded *stipulated* until
  corroborated by labels or supplied test vectors.
- **Derived languages**: always registered *with* a pair to a parent —
  **abstraction** (over-approximating, direction `⊑`) or
  **specialization** (a fragment with an exact embedding). A derived
  language's semantics is checked against its parent's, so it adds
  nothing to the trusted base. Only roots cost trust.

**Pair** = directed edge with translator `T`, back-translator `Λ`,
kept observables `π`, direction (exact / over / under), measured cost,
and a lineage declaration. Two kinds, **one gate**:

- **Translation pair** (language → language): checked per program by
  the directional square, exactly as today.
- **Solver pair** (language → result): `T` *is* solving under a
  declared budget. The square degenerates to result validity —
  witnesses must replay, certificates must re-discharge, negative
  controls must fail, determinism must hold. Same admission
  discipline; there is no separate solver gate.

Routes compose pairs and end in a solver pair; a route's contract is
the componentwise meet — weakest link — the one composition rule kept
from the current calculus.

**Result** — a fixed kernel schema with domain-specific payloads:

```
result = { question, route, budget: {caps, spent},
           value: witness(w+)                 -- exists: here is a w
                | all(bound: k | inf, cert?)  -- forall: none exists (to bound)
                | partial(progress)           -- how far, where it failed
         , grade }
```

`partial` is deliberately semi-structured: a small typed core the
kernel orders on (bound reached, budget spent) plus free-form progress
description and solver profiling, because its reader is the LLM.

## 2. Certification and the grade ladder

Both certifications are Λ-then-check; the difference is what checks.

- **Existential**: the witness is carried back (`Λ`) and replayed
  through the source interpreter. One run, always available,
  route-independent: a wrong or adversarial pair cannot forge it.
  A recorded witness is always *replayed* — a solver's unreplayable
  `sat` is never a witness result; it is evidence inside a `partial`
  (or, on an abstraction route, a refinement demand).
- **Universal**: a certificate is interpreted **against the problem**.
  Checked at the target it inherits the route's trust (the meet);
  carried back and **re-discharged at the source** (finitely many
  decidable obligations — for an invariant: base, step, safe) it
  becomes route-independent, the mirror of witness replay. The
  fail-safe direction is definitional: a wrong or wrongly-mapped
  certificate can only fail to upgrade, never fake one.

The ladder, with **strict naming** (decided 2026-08-05):

```
claimed  <  checked   (at target; route trust rides along, recorded)
         <  certified (re-discharged at source; route-independent)
         @  corroborated (disjoint lineages agree — orthogonal flag)
```

"Certified" is *reserved* for the route-independent form; every result
states its rung and what its residual trust rests on — the route meet
for *checked*, the discharge lineages for *certified*. The kernel
computes grades from lineage declarations, and grades only improve.
Second-order effect, intended: whatever earns the top grade is what
the autonomous loop learns to build, so the frontier evidence itself
pushes the LLM toward certificate printers, Λ-for-certificates, and
independent discharge engines.

A replayed witness is ground truth: if a question ever holds both a
replayed witness and a covering universal claim, the kernel records a
**contradiction event**, the witness stands, and the universal's
certification chain is marked falsified. Contradictions are never
silently resolved.

## 3. The frontier

A question is `(language, program, observable, mode: exists|forall,
bound: k|inf)`; a benchmark is a pinned finite set of questions with
recorded provenance (sha256 per program, labels where they exist).

Results order per question: `partial < all(k) below the asked bound <
terminal`, where terminal is a replayed witness or a universal claim
covering the ask; within a level, higher bound, then higher grade.
Cost is recorded and reported, never ranked.

**The frontier of a benchmark is the set of questions whose best
result is not terminal**, each carrying the route that produced it and
its progress evidence — exactly the "non-terminating results with the
route to get there". The registry and the log are append-only, and
best-per-question over an append-only log is monotone: the old F2 is
now a property of the data structure, not a theorem apparatus.
**Expanding the frontier** means strictly improving some question's
best result (level, bound, or grade — not cost).

## 4. The loop, and the conjecture order

The LLM is presented a benchmark and runs autonomously until a human
pulls the plug:

1. **Play**: for every question, run the best routes within budget;
   the kernel records results.
2. **Read the frontier**: the non-terminal results with their
   profiles.
3. **Conjecture**, in this order — this is the vision's core
   discipline, **semantics first, then syntax**:
   - **(a) new solving for existing languages** — a new solver pair,
     portfolio, budget policy, certificate printer, discharge engine:
     new *decision procedures* first;
   - **(b) new translation** — new pairs, new routes to existing
     solvers;
   - **(c) new languages** — abstraction or specialization deltas,
     proposed only when a translation or solving move keeps winning
     ad hoc and reifying it would make the win reusable and cheap.
     New syntax is earned by demonstrated semantics, never invented
     ahead of it.
4. **Build, check, register**: the LLM writes code; the kernel gates
   it; what passes is registered — autonomously, no valve. Manual
   registration is the same path, human-invoked; no special case.
5. Re-play affected questions; repeat.

The trust story in one sentence: **the LLM never writes a result;
only the kernel does, by running checked code.** What the old valve
protected (answer soundness) is protected by construction —
existential certification bypasses trust entirely, universal
certification is graded. What autonomy risks is registry clutter,
which the result ordering neutralizes (junk never wins a route) and
which pruning, a human act between runs, can clean.

**Plug-pull** is safe at any moment: the driver checkpoints after
every result and registration, and the exit deliverables are pure
functions of the log —

1. the **frontier summary**: best result, route, and cost per
   question; the non-terminal results with their evidence; and the
   delta since iteration zero (expanded or not);
2. if expanded, the **evolved hurdy-gurdy**: the kernel unchanged
   plus everything registered, with admission evidence. The next
   benchmark starts from it.

## 5. Bootstrap from empty

The kernel ships with zero languages and zero pairs. Presented a
benchmark, the LLM's first act is writing the root language's
interpreter (the trusted base, graded *stipulated*; benchmark labels
and supplied vectors are its only corroboration), then a first naive
solver pair, then growth. Grades bottom out at *claimed* until the
registry holds a second lineage. Everything must work at this point —
which is the design's simplicity test.

## 6. What the kernel proves, and what it asks of generated code

The kernel is the fixed part and the only hand-written code; it is
small on purpose (readable in an afternoon) and its properties are
mechanized in Lean (`kernel/mechanization/`):

- the result order is a strict partial order (irreflexive,
  transitive, asymmetric);
- best-per-question is monotone under log append (the ratchet);
- once terminal, always terminal (the frontier never re-opens);
- grades only move up the ladder.

Generated content is asked for proofs **when appropriate and
feasible**: a proof obligation is part of a manifest when the artifact
is kernel-adjacent — a certificate schema must come with its fail-safe
direction stated (and proved in Lean where feasible), a
specialization's embedding with its exactness argument, a new result
payload with its ordering. Per-program translation correctness is
*not* proved — that is what the square checks empirically, per run,
which is the platform's founding economy.

## 7. Carry-over: the current platform as the first generated content

The v3 tree is not discarded; it is mined. Existing languages and
pairs are carried over by wrapping them in kernel manifests and
admitting them through the new gate — two-sided controls and all — so
the first registry content is the old platform re-certified by the
new kernel. The carry-over recipe (demonstrated with `btor2` +
`btormc`; see `registry/`):

1. wrap the shared interpreter as `interp.py` (CLI shim over the
   existing `gurdy` module), with vectors from the existing tests;
2. wrap each solver as a solver pair (`solve.py` + `lam.py` shims);
3. wrap each translation pair (`T.py` + `lam.py` shims) with its
   coverage corpus;
4. supply mutants as negative controls (a checker that cannot be made
   to fail is unfalsifiable);
5. run admission; the evidence lands in the manifest.

The remaining v3 pairs are named work — and deliberately of the shape
the loop itself can do.

## 8. Kept and dropped

**Kept** (each earned its place in v3): determinism as the
checkability substrate; the directional square; witness-replay
asymmetry; contract meet; graded universal certification and the
re-discharge seam; lineage declarations; pinned benchmarks;
append-only logs with budgets in provenance; reports that regenerate
byte-identically; two-sided negative controls.

**Dropped**: the demand currency and everything downstream — books,
boards, required contracts, briefs, mandate/valve, the three lanes,
the extraction operators, the atlas, the five-condition filtration.
Their content survives inside `partial` results as evidence. The
Calculus Lean development stays as the record of the old model; the
kernel gets its own, smaller mechanization.

## 9. Layout and executable contracts

```
kernel/                  the fixed part (stdlib-only Python + Lean)
  registry.py runner.py results.py checker.py driver.py
  mechanization/         Lean: the kernel's proved properties
registry/                generated content, append-only
  languages/<name>/      manifest.json, interp.py, vectors/, controls/
  pairs/<src>--<tgt>/    manifest.json, T.py|solve.py, lam.py,
                         corpus/, controls/
runs/<benchmark>/        benchmark.json (pinned), log.jsonl (append-
                         only), frontier.md (regenerated)
```

Every registered executable is a pure deterministic CLI — bytes in,
bytes out — run sandboxed (own process, empty environment, temp
working directory, wall/memory caps) and **run twice with
byte-compared output on every check**. Manifests declare kind,
direction, kept observables, lineage, budget schema, and optionally a
Lean proof obligation; admission evidence is stamped into the
manifest directory by the checker, never self-reported.

## 10. Honesty rules

- The kernel never trusts a claim it can measure.
- Budgets ride in every result's provenance; capped is labeled capped.
- Grades state their residual trust; nothing is worded stronger than
  what was verified.
- Contradictions are recorded, never resolved silently.
- The frontier summary regenerates from the log byte-identically.
- Pruning the registry is a human act between runs; during a run the
  registry only grows.
