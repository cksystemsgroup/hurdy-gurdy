# Discovery — three widenings of what the loop can discover

The platform's scope sentence is "questions that reduce to decision
procedures" ([`README.md`](./README.md)). This document writes up three
findings, each an answer to a question of the form *could the loop
discover X?* — **proofs of mathematical statements** (§1), **universal
verdicts by decomposition over partial models** (§2), and **languages
themselves, programming languages included** (§3). The common finding,
stated once: in every case the architecture already has the slot cut —
the trust asymmetry, the direction axis, the typed hole — and what is
missing is a named extension of an existing judgment, never a new
architecture. It is a design document in the sense of
[`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md): everything below is named
work, not landed code.

A fourth observation closes the document (§4): the three widenings are
one seam used three times, and two of them share a single prerequisite
already named elsewhere.

## 1. Proof discovery — mathematics as a domain

### 1.1 What stands today

For statements inside the registered fragments, the platform already
*discovers proofs* in the literal sense. A universal statement
expressible in `QF_ABV`/`QF_LIA` or as a bit-level transition system is
decided at a hub, and the `proved` tier
([`gurdy/solvers/proved.py`](./gurdy/solvers/proved.py)) does not take
the solver's word: it obtains a DRAT proof, elaborates it to LRAT, and
re-validates it with `cake_lpr`, the formally verified checker, under
negative controls ([`SCALING.md`](./SCALING.md) §9). That certificate
*is* a machine-checked proof of the statement — the mechanism behind
SAT-solved mathematics (Pythagorean triples, Schur number five). The
membership rule already admits the reading: a language needs only a
definable meaning function, and "a logic … or a mathematical notation"
qualifies ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §1); `crn-smtlib` and
`smiles-formula` are the standing proof that non-program domains ride
the square unchanged ([`DOMAINS.md`](./DOMAINS.md) §1).

### 1.2 Why the architecture fits proof discovery specifically

"There exists a proof of `φ`" is an **existential** question over proof
terms, and checking a candidate proof is cheap and deterministic — a
kernel check. That lands exactly on the platform's central asymmetry
([`POTENTIAL.md`](./POTENTIAL.md) §2; paper Thm 4.8): existential
answers are self-certifying by replay through a deterministic checker,
so **the proof searcher can be completely untrusted** — an LLM, an ATP
portfolio, anything. This is the producer-quarantined /
checker-deterministic seam [`SOLVERS.md`](./SOLVERS.md) §1 already
mandates for `decide`; the §6 pedigree ladder already places
"reconstructed in a proof-assistant kernel" at the top of `proved`; and
[`paper/mechanization/`](./paper/mechanization/README.md) — pinned
toolchain, no mathlib, zero `sorry`s, axiom audit at every build — is
the in-repo precedent for the gate such a target inherits
([`PROVING.md`](./PROVING.md) §5 cites it for the same reason).

### 1.3 The design

Register a **proof language** (a proof-term calculus; in this registry's
practice, Lean) as a reasoning language: its "solver" is an untrusted
proof searcher, its witness is the proof term, its witness checker is
the kernel, its declared question shape is `provable`. A discovered
proof then comes back as what no standalone LLM-prover setup produces —
a graded, evidence-carrying answer with its trusted computing base
recorded. The frontier story extends verbatim: present a mathematics
benchmark (TPTP, miniF2F) and saturation deposits the map — the region
decidable or provable in practice, every route priced, and every open
statement carrying its obstacle ([`FRONTIER.md`](./FRONTIER.md) §1).

### 1.4 The named gaps

- **The behavior model.** A behavior is a step-indexed trace
  ([`DOMAINS.md`](./DOMAINS.md) §2, item 1); a logic's meaning function
  is not. The SMT-LIB interpreter already bends this (it is a model
  *evaluator*, not a stepper); the widened behavior contract is the
  named work this section leans on.
- **Proof objects as answers.** The four-verdict vocabulary carries
  `provable`/`disprovable`, but the proof *object* as a first-class
  result needs the `answer`-beside-`decide` calculus extension
  ([`DOMAINS.md`](./DOMAINS.md) §4, item 1).
- **The atlas.** [`gurdy/core/atlas.py`](./gurdy/core/atlas.py) charts
  verification shapes only; mathematics needs its own review-grown
  sections before the shape obstacle gives useful guidance
  ([`DOMAINS.md`](./DOMAINS.md) §4, item 3).
- **Not to be confused with [`PROVING.md`](./PROVING.md).** That
  document demands proofs *of the platform's translations* (the
  fidelity floor); this section delivers proofs *as answers*. They
  share the checker stack and nothing else.

### 1.5 The limit, worn honestly

General mathematics is only semi-decidable, and the platform inherits
that boundary exactly as [`POTENTIAL.md`](./POTENTIAL.md) §5 states it:
on the existential side it is complete-in-the-limit (a true `provable`
is eventually found and is then self-certifying), and it can never
promise termination on open conjectures. The platform's contribution to
proof discovery is not search creativity but the other half of the
problem: making an untrusted searcher's output a trusted, audited,
reusable answer — and mapping what fell to which route at what cost.

## 2. Partial-model branching — covers as the dual of abstraction

### 2.1 What branching is today

A branch runs the *same whole question* along two routes and
manufactures fidelity by agreement ([`ROUTES.md`](./ROUTES.md) §4);
doctrine says it "answers no new question at all"
([`POTENTIAL.md`](./POTENTIAL.md) §3). Allowing a branch's legs to
explore only **partial models** — restrictions of the input/state
space: a case, a cube, a fragment — changes what branching *is*: from a
trust instrument into a **decomposition instrument**. Two consequences
are immediate. Agreement stops being the check — legs on different
fragments may legitimately differ, and disagreement localizes a defect
only on the fragments' *overlap*. And each leg is an
**under-approximation**: the missing dual of the direction axis.

### 2.2 The `under` direction

[`gurdy/core/direction.py`](./gurdy/core/direction.py) admits `exact`
and `over`. The partial-model leg is `under` — the target has *fewer*
behaviors than the source — and verdict transfer dualizes cleanly: an
`under` leg's **existential** verdict transfers (and is replayed at the
source anyway, so it stays self-certifying —
[`SOLVERS.md`](./SOLVERS.md) §4), while its **universal** verdict
transfers nowhere on its own. The witness map runs opposite to `over`'s
embedding: target bindings embed into source bindings, which is what
the carry-back already does. With `under` alone the platform becomes
strictly better at existential search — legs are a parallel portfolio
of restricted searches, any hit replays, and **a wrong split cannot
forge anything**: the asymmetry survives untouched.

### 2.3 The one new judgment: the cover

Universal verdicts re-emerge only from a **covering family**: legs
whose fragments jointly cover the source's model space, every leg
returning `unreachable`. That is a genuinely new composition rule —
routes compose in sequence ([`ROUTES.md`](./ROUTES.md) §1) and branch
for agreement (§4); this is **parallel composition with a side
condition**, and the side condition carries the entire soundness
burden: a family that silently misses a sliver produces exactly the
false universal the platform is built to fear. The saving grace: the
cover claim is itself typically *decidable* — for a cube split, "the
disjunction of the cubes is a tautology" is one SAT query — so the
**cover certificate** discharges through the already-validated
DRAT → LRAT → `cake_lpr` chain, with the mandatory negative control
being a deliberately non-covering split that must fail (the I19
discipline, [`SCALING.md`](./SCALING.md) §9). The precedent is
industrial: **cube-and-conquer** is precisely this construction, and it
is how the SAT-solved mathematics of §1 actually scaled — per-cube
unsat proofs plus the split tautology composing into one checkable
proof.

### 2.4 What it buys, and the dual loop

[`POTENTIAL.md`](./POTENTIAL.md) §5 names cost as limit 3 and §6 says
only abstraction helps against it. Partial-model branching is
abstraction's exact dual — **`over` shrinks the model, `under` splits
it** — attacking the same limit from the other side, and it gets the
dual refinement loop: where an `over` route's spurious counterexample
demands a *finer abstraction*, an `under` leg returning `resource-out`
demands a *finer split* of that fragment. Both loops deposit
registered, reusable pairs rather than solver-internal state — the
splits found for one question cheapen the next thousand.

### 2.5 The honesty rules

- **Cover-legs buy capability, not trust.** A covering family built
  from one semantic artifact adds zero corroboration; the trust advisor
  ([`gurdy/core/trust.py`](./gurdy/core/trust.py),
  [`ROUTES.md`](./ROUTES.md) §4) must count cover-legs toward the cover
  certificate and *never* toward branch agreement, or anchor saturation
  ([`POTENTIAL.md`](./POTENTIAL.md) §5, limit 4) is quietly laundered.
  The disciplines compose: the same covering family run along two
  independent routes buys both.
- **Partial verdicts are first-class bounded claims.** "Unreachable on
  fragment `F`" is durable evidence, structurally identical to today's
  bounded-`k` universal claims, with the fragment as the declared
  bound. The frontier reading is exact: the unexplored fragments *are*
  the surveyed edge, each naming the leg that would close it.
- **Model-partiality is not construct-partiality.** The platform's
  existing partiality is coverage of the *translator* per construct
  ([`BENCHMARKS.md`](./BENCHMARKS.md)); a partial model restricts the
  *question's* space. The axes are orthogonal and must be reported
  apart.

### 2.6 How it lands

`under` as a third value in `direction.py`, composing on the chain and
refusing mixed `over`/`under` routes a meaning they do not have; splits
as parameterized endo-pair families (a `btor2-cube` constraining
inputs — the mirror of `btor2-havoc` havocking states); the covering
family plus its certificate as a route-level construct with its own
gate and negative control; the books extended so a `resource-out` on a
fragment records a re-split demand.

## 3. Language discovery — the typed hole, widened

### 3.1 What stands today

Frontier pairs already make the registry's *language set* part of the
searched space: a shape-blocked frontier pair "may name a
**hypothetical** target — a language sketch (name, needed question
shapes), not a registered language"
([`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md) §1.6), it carries a
**required contract** demanded from below, and conditional routes price
it by the questions its completed routes would unlock, chains included.
Nothing in the membership rule restricts the hole to solver front-ends:
executability is not required, "program" is not required
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §1), hubs are emergent
([`DOMAINS.md`](./DOMAINS.md) §1), and `smiles-formula` proves a target
with no solver near it is a first-class *compile pair*
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §5). What is narrow today is
the derivation, not the rule: only `reasoning-language` targets emit
the sketch, and its one structured field is question shapes.

### 3.2 Three demand routes to a programming-language target

- **A discovered hub.** [`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md) §1.5
  names the signal: players repeatedly hand-composing the same
  multi-hop reduction — the no-hidden-IR rule
  ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §9) surfacing at ecosystem
  level. Motif mining over that evidence is how a new intermediate
  language — a Horn-clause language, a WASM-like core, a C-light — gets
  its hole cut: exactly how IRs are born in the compiler world, here
  made evidence-driven and priced.
- **A synthesis target.** Instantiate the `answer` extension
  ([`DOMAINS.md`](./DOMAINS.md) §4, item 1) at *a program in a
  registered language* and the answer operation is program synthesis —
  and the asymmetry fits perfectly, once again: the synthesizer is the
  untrusted producer, and the certificate is checked by **executing the
  synthesized program through the shared deterministic interpreter**
  against the spec's observables. A synthesized program is an
  existential witness, self-certifying by replay. A demand stream of
  unfilled synthesis questions is what would cut a hole shaped like a
  target programming language.
- **A lifting target.** Nothing forbids a pair whose target is a
  higher-level language (binary → C-like), provided the declared `π`
  says honestly what the round trip preserves. The adequacy floor
  ([`POTENTIAL.md`](./POTENTIAL.md) §5, limit 2) excludes "is this
  readable"; it squarely admits "does the lifted program have the same
  observable behavior".

### 3.3 The widening

Generalize the hypothetical-target sketch from one kind to three, each
keyed by the evidence that cuts it: a **reasoning sketch** (question
shapes — today's), a **hub sketch** (the mined motif: the route prefix
and suffix populations that would compress through it), and an
**answer-target sketch** (the answer kinds and the canonical form).
All three are priced identically by conditional routes, remain derived
and never stored, and compound across benchmarks by target signature —
the §1.6 guard rails apply unchanged.

### 3.4 What does not move

Discovery stops at the sketch, **by design**. The design line
([`FRONTIER.md`](./FRONTIER.md) §4.2) already escalates any in-scope
target whose design needs a creative act — and inventing a language's
semantics is the maximal creative act. Frontier→registered *is*
registration, the one human valve ([`AGENTS.md`](./AGENTS.md) §1); a
frontier hop is refused execution at the type level; and a discovered
language becomes real only when a human admits it and the gate gets
what it demands of every language — a definable meaning function and a
shared deterministic interpreter. The loop derives that a language is
missing, what it must satisfy, and what it is worth; it never conjures
one. Given that a language is the deepest trusted artifact in the
calculus, that is the right refusal.

## 4. One seam, three findings

The three widenings are the same move: put an untrusted producer on one
side of a seam and a deterministic, independently-validated check on
the other — searcher/kernel (§1), splitter/cover-certificate (§2),
proposer/valve-and-gate (§3). Each attacks a different limit of
[`POTENTIAL.md`](./POTENTIAL.md) §5: §1 works the semi-decidable side
of computability, §2 works cost, §3 works the frontier's own vocabulary
— what may be named as missing. And two of them share one
prerequisite: the `answer`-beside-`decide` calculus extension
([`DOMAINS.md`](./DOMAINS.md) §4, item 1) underlies both proof objects
as answers (§1.4) and programs as answers (§3.2) — one extension, two
payoffs, which is where this document's work would begin. The nearest
fully-independent increment is §2's `under` direction: a third value on
an existing axis, a route-level construct, and a certificate the
existing checker stack already knows how to validate.

*Status (2026-07-18): nothing above is landed — no proof-language
registration, no `under` direction or cover certificate, no widened
hypothetical-target sketch. This document is the named future work.*
