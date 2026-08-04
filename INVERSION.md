# Inversion — the square solved for its other unknowns

[`DISCOVERY.md`](./DISCOVERY.md) widened what the loop can discover
*within* the calculus: proofs as answers, covers as abstraction's dual,
languages as typed holes. This document asks the next question — what
the loop can discover *of* the calculus, meaning the artifacts the
commuting square relates. The finding, stated once: the platform is one
equation solved for one unknown, and **the same equation with a
different unknown is property discovery, abstraction discovery,
semantics discovery, and procedure discovery** — each checked by the
gate that already exists, because the gate checks the square and not
the artifact.

The greater ambition this serves: an architecture in which an untrusted
syntactic generator **provably accumulates semantic knowledge**. §10
says what that does and does not claim. It is a design document in the
sense of [`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md) and
[`SYNTHESIS.md`](./SYNTHESIS.md): everything below is named work, and
the status notes say which parts of the machinery it leans on are
already landed.

## 1. What iteration 6 measured: the conservativity ceiling

### 1.1 The reading

The HWMCC campaign
([`paper/frontier/results/hwmcc-sosylab-beem/`](./paper/frontier/results/hwmcc-sosylab-beem/report.md))
ran seven iterations over 110 pinned questions. The answered fraction
moved 0.7182 → 0.7364; cost per answer fell 84.9 s → 56.5 s as the
surface sharpened. The terminal board holds **one entry**:
`d4c59dafc402` [in-set] `native-procedure`, 29 distinct citing
questions, every one `origin=campaign`. Seven iterations of a discovery
loop produced exactly one demand, and it reads *get a better engine*.

Every part of that is honest and pre-registered
([`FRONTIER.md`](./FRONTIER.md) §5: "the plateau is a finding"). The
question this document opens is not whether the campaign was run well.
It is why the board could not possibly have said anything else.

### 1.2 Why it is forced, not incidental

Every artifact the loop can build is **meaning-preserving by
construction** — `I_s(p) ≡_π Λ(I_t(T(p)))`, or its lax weakening
`⊑_π` ([`POTENTIAL.md`](./POTENTIAL.md) §6). The commuting square *is*
the statement that no new truth is created here. So the loop is
conservative over truth-content: what varies across iterations is only
the reachability of a fixed truth-set under budget.
[`FRONTIER.md`](./FRONTIER.md) §5 chose HWMCC because it is native to
the BTOR2 hub — "no translation debt to pay before the loop starts" —
which is exactly the condition under which a translation-producing loop
has nothing to produce. The campaign measured the closure of an
already-closed set, and it found the cost cliff, correctly.

### 1.3 The consequence

**The loop can discover instruments; it cannot discover facts.** A
terminal board can name only what would extend the map — a pair, a
reduction, a procedure, an anchor — and every one of those is
*exogenous good news* the loop cannot itself supply
([`FRONTIER.md`](./FRONTIER.md) §1). Nothing in the ledger has a shape
that could hold a discovered truth, because the only currency is
capability.

That is the ceiling. The rest of this document is the one structural
change that lifts it, and what follows from it.

## 2. The square has four unknowns

### 2.1 The equation

```text
   I_s(p)  ≡_π  Λ( I_t( T(p) ) )
```

Four artifacts appear: the source semantics `I_s`, the target semantics
`I_t`, the translation `T`, and the projection `π` (with its reading
map `Λ`) that says what is kept. Given any three, the equation
constrains the fourth.

### 2.2 The four inversions

| solve for | the discovered object | what it is called elsewhere | checked by |
|---|---|---|---|
| `T` | a translation | **the platform, today** | the square, per run |
| `π` | the coarsest projection that still commutes | an **abstract domain** | the lax square (`direction=over`) |
| `I_t` | an interpreter for a *new* target | a **stipulated semantics** | the square, against a fixed `I_s` |
| `I_s` | an interpreter for an *existing* source | **semantic reverse-engineering** | an external anchor (§7) |

The platform has only ever solved for `T`. Every pair under
[`pairs/`](./pairs/README.md), every builder run, every gate check, the
entire [`SCALING.md`](./SCALING.md) pipeline: one unknown, once per
registered pair.

### 2.3 One gate, four unknowns

The reason this is a small change rather than a new architecture: **the
gate checks the square, not the artifact.** Coverage, twice-and-diff
determinism, two-sided negative controls, the `PureOracle` sandbox seam
([`SCALING.md`](./SCALING.md) §12) — none of it asks which slot the
untrusted producer filled. A proposed `I_t` is falsified by running the
square on the coverage corpus with its negative controls, exactly as a
proposed `T` is. And because the square is stated over the domain
signature alone (paper F6), all four inversions are domain-generic by
the same argument that makes F1–F5 domain-generic; see §8.

### 2.4 The dual already named

[`DISCOVERY.md`](./DISCOVERY.md) §3.2 and §4 name the
`answer`-beside-`decide` extension: the *result* becomes an object
(a proof term, a synthesized program) rather than a verdict. The
inversion program is its **dual** — the *question* becomes a searched
object rather than a given. The two are independent extensions of the
same calculus and neither subsumes the other: `answer` widens what a
question may return, inversion widens what may be asked and of what.
Level 1 below is inversion at its cheapest.

## 3. The ladder, and why its order is forced

| level | object discovered | producer | checker | status |
|---|---|---|---|---|
| **L0** | routes, translations | LLM builder | the square, per run | **landed** |
| **L1** | properties `φ` | LLM proposer | `decide` at a hub | §4 — named work |
| **L2** | vocabularies, abstract domains | motif mining over L1 | leverage over a saturated board | §5 — named work |
| **L3a** | transfer functions (a semantics) | LLM proposer | the **lax** square | §6 — named work |
| **L3b** | the fixpoint algorithm (a procedure) | builder lane | soundness of L3a + [`tools/solver_gate.py`](./tools/solver_gate.py) | §6 — lane landed, discovery half excluded |

The ordering is not pedagogical. **Each level's checker is the previous
level's product**, so the dependency is architectural:

- L1's *interestingness* judgment is measured against a saturated
  board — which requires L0 to have run to the fixpoint.
- L2 mines the population of properties that survived L1; with no
  surviving population there is nothing to mine.
- L3a's lax square is checked against a concrete semantics reached
  through registered pairs — L0 again.
- L3b's soundness is inherited from L3a's square, and its census
  replay ([`SYNTHESIS.md`](./SYNTHESIS.md) §5) is the solved region L0
  deposited.

And one consequence matters more than the rest. The design line
([`FRONTIER.md`](./FRONTIER.md) §4.2) escalates any target whose design
needs a creative act; `mechanical_design` in
[`tools/mandate.py`](./tools/mandate.py) knows no procedure lane, so
"invent a decision procedure for this fragment" escalates under every
mandate, permanently and correctly. But "**compute the fixpoint over
*this* vocabulary**" is mechanical. **Discovering the language first is
what moves the algorithm across the design line** — which is the exact
sense in which languages and properties are a load-bearing prerequisite
for semantics and algorithms, and not merely a natural order of study.

## 4. Level 1 — properties as searched objects

### 4.1 The proposal grammar

A question is `(p, φ)` ([`gurdy/core/question.py`](./gurdy/core/question.py)).
Today `p` and `φ` both arrive from outside and the loop searches over
routes. Make `φ` the searched object over a fixed object population and
the loop discovers **properties**: statements about an artifact that
nobody asked for, and that are true.

The proposal space needs no invention. A hub already declares the
question shapes it consumes (paper, kit item 1), and **that declaration
is the grammar of proposable conjectures** — bit-level safety
properties over BTOR2 state, `QF_LIA` statements over CRN species
populations, whatever a future hub declares. The LLM proposes syntax in
a declared grammar; the hub decides truth. Nothing about the producer's
training touches the truth side, which is the asymmetry of
[`POTENTIAL.md`](./POTENTIAL.md) §2 used one slot over.

### 4.2 Interestingness is decidable here

The two standing objections to property mining — most true statements
are trivial, and *interesting* is a matter of taste — are both
**mechanical in this setting**, which is unusual and is what makes the
level admissible under the platform's own honesty rules:

- **Novel** iff `F ⊭ φ` for the accumulated fact set `F`. One query.
- **Useful** iff assuming `φ` closes a question standing on the
  terminal board. Measured directly against the open set — for the
  campaign of §1, against the 29 blocked pins.

Neither is a judgment call, and both are recorded with the deposit. The
side condition novelty carries is stated in §8 as K6.

### 4.3 The fact ledger

Deposit `(object-hash, φ, verdict, route, assurance, cost, novelty
evidence, leverage evidence)` beside the demand ledger
([`gurdy/core/ledger.py`](./gurdy/core/ledger.py)). Two disciplines are
non-negotiable:

- **A deposit is graded, never believed.** A fact enters later answers
  as an assumption, so a false deposit would corrupt every universal
  built over it. Deposits therefore carry certificates re-discharged by
  an engine of **disjoint declared lineage**
  ([`gurdy/solvers/brief.py`](./gurdy/solvers/brief.py)), and a
  lemma-carrying answer's assurance is the meet *including its weakest
  cited fact*. See F7 in §8.3.
- **A deposit is not a demand.** §9's first rule; it is what keeps F5
  intact.

The universal side has a landed, negative-controlled seam waiting for a
producer. [`gurdy/solvers/invariant.py`](./gurdy/solvers/invariant.py)
already exposes `redischarge_invariant(system, invariant, prop=0)`,
which takes an invariant *as a string*, frames it, and discharges
base/step/safe against every available SMT backend — with the fail-safe
direction its own docstring states: *a wrong or wrongly-mapped
invariant can only fail to upgrade, never fake a certificate.* Only
`certify_unreachable` hardwires the producer to pono's `--show-invar`.
A second producer is a parameter, not a redesign, and an LLM-proposed
invariant is *maximally* lineage-independent: the proposer sits inside
no engine's declared lineage, so the limit-4 anchor scarcity of
[`POTENTIAL.md`](./POTENTIAL.md) §5 does not bind it.

### 4.4 Conjectures: the second kind of board entry

A proposed `φ` the hub cannot decide within budget is not waste. It is
a **conjecture with a cost obstacle**, and it flows through
[`gurdy/core/whynot.py`](./gurdy/core/whynot.py) and the frontier
derivation unchanged. A saturation report then deposits two kinds of
open entry: **instruments missing** (today) and **conjectures open** —
machine-generated, machine-filtered, plausible-but-undecided statements
about real artifacts, each carrying a *bound* rather than a probability
("holds to `k` = 20"), which is already how this platform prices a
partial universal ([`ROUTES.md`](./ROUTES.md), bounded claims). That is
a deliverable no current pipeline produces, and it is the literal form
of "new unproven properties."

## 5. Level 2 — vocabularies, and the honest sense of "a new language"

### 5.1 What stays behind the valve

[`DISCOVERY.md`](./DISCOVERY.md) §3.4 refuses language *invention* by
design: registration is the human valve
([`AGENTS.md`](./AGENTS.md) §1), inventing a language's semantics is
the maximal creative act, and a language is the deepest trusted
artifact in the calculus. Nothing here relaxes that, and §7 says why
the refusal is load-bearing rather than merely cautious.

### 5.2 What is discoverable

A narrower object clears the membership rule
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §1) without argument: a
**vocabulary** — a finite set of predicate templates over the hub's
declared grammar. Its meaning function is "evaluate the predicate";
its interpreter is deterministic and one line. It is a formal language
in exactly the sense intervals, octagons, and polyhedra are formal
languages, and [`pairs/btor2-interval`](./pairs/btor2-interval/README.md)
is the landed proof that such a domain rides the pair machinery
unchanged. The difference the loop makes is that intervals were
*designed* and this vocabulary would be **mined**: the recurring
templates in the population of properties that survived L1, ranked by
measured leverage over the board.

This is the mechanical evidence source that
[`DISCOVERY.md`](./DISCOVERY.md) §3.3's *hub sketch* was missing. It
also inherits §3.3's guard rails verbatim: derived, never stored;
priced by conditional routes; compounded across benchmarks by target
signature.

### 5.3 The atlas grows a third tier

[`gurdy/core/atlas.py`](./gurdy/core/atlas.py) today draws the in/out
line by **charted** vs **uncharted**
([`SYNTHESIS.md`](./SYNTHESIS.md) §3). Discovery needs a third tier —
**discovered**: a fragment the loop mined, recorded with its
vocabulary, so the next benchmark classifies against it. Without that
tier nothing compounds and each discovery is a one-off, which would
break the one property that makes the maps worth keeping
([`FRONTIER.md`](./FRONTIER.md) §6). The tier is reference data and
protected like the rest of the atlas.

## 6. Level 3 — a stipulated semantics and the algorithm over it

### 6.1 What is already landed

More than the rest of this document. [`SYNTHESIS.md`](./SYNTHESIS.md)
§§3–7 are landed: the `native-procedure` target kind, solver briefs
with the certificate obligation and the lineage declaration
([`gurdy/solvers/brief.py`](./gurdy/solvers/brief.py)), the solver gate
— census replay, canaries, verdict-flip mutants, certificate
discipline, budget honesty
([`tools/solver_gate.py`](./tools/solver_gate.py)) — the builder lane
([`tools/procedure_dispatch.py`](./tools/procedure_dispatch.py)), and a
reference inhabitant admitted end to end
([`gurdy/solvers/enum_btor2.py`](./gurdy/solvers/enum_btor2.py)). The
books demand procedures, the gate falsifies them, the lane produces
them.

### 6.2 The exclusion

One clause of [`SYNTHESIS.md`](./SYNTHESIS.md) §7 is where this
document's ambition lives:

> the work list split by atlas chartedness (**uncharted is listed
> apart and never worked**)

By construction the loop can *instantiate* known procedure families and
can never *discover* one. The exclusion is right as written — see the
design-line argument of §3 — and the way through it is not to relax it
but to **insert L2 ahead of it**, so an uncharted fragment arrives
carrying a mined vocabulary and presents as instantiation-shaped work.

### 6.3 Transfer functions as a stipulated semantics

Given a mined vocabulary, its **transfer functions** — how each
construct of the source moves a predicate to a predicate — are its
semantics. They are *stipulated*, not reconstructed from anything, and
they are checked as a **lax square** in the sense
[`POTENTIAL.md`](./POTENTIAL.md) §6 already admits and
[`gurdy/core/direction.py`](./gurdy/core/direction.py) already carries
(`direction = over`): every source behavior has a target counterpart on
`π`. Universal verdicts transfer down the `⊑`; existential verdicts are
carried back and replayed, and a spurious one is a refinement demand.

This is the `I_t` inversion of §2.2, and it is *semantics discovery* in
the only sense the platform can mean the phrase: an untrusted producer
proposes an interpreter, and the square decides whether it means what
it claims.

### 6.4 The fixpoint is the procedure — and it is sound by square

The algorithm that saturates those transfer functions over an artifact
**is** a decision procedure for the fragment. Its epistemic status is
the payoff of taking this route rather than synthesizing a procedure
directly:

- **Census replay is testing.** A candidate that agrees with 110
  corroborated verdicts may be wrong on the 111th, and
  [`SYNTHESIS.md`](./SYNTHESIS.md) §8 already books that honestly as
  the corroboration bootstrap.
- **A fixpoint over a checked domain is sound by construction.** Its
  correctness follows from the lax square of §6.3, not from agreement
  on a corpus. The square is the proof obligation, and it is checked
  per artifact rather than per suite.

So the procedure clears [`tools/solver_gate.py`](./tools/solver_gate.py)
*besides*, not *instead*. Same gate, strictly better prior — and the
inversion of [`SYNTHESIS.md`](./SYNTHESIS.md) §6 holds: the
least-trusted author still produces the most-checkable artifact.

### 6.5 Lineage, one level up

[`SYNTHESIS.md`](./SYNTHESIS.md) §4 warns that a teacher and its
student launder agreement into independence. The same hazard climbs the
ladder: **a vocabulary mined from a corpus decided by engine `E` is not
independent of `E`**, and a procedure built over that vocabulary
inherits the entanglement. The `lineage` field must therefore carry the
*mining provenance* — which corpus, decided by which engines, under
which caps — or corroboration between a discovered procedure and the
engine that taught it is fiction. This is a strict extension of an
existing declaration, not a new mechanism.

## 7. The anchor ceiling, and the door in it

### 7.1 Solving for `I_s` is anchor-bound

Paper F1(i) assumes source-interpreter adequacy; the deterministic
shared interpreters are kit item 2, and they are the **trusted base**.
An LLM generating `I_s` puts the producer *inside* the TCB and the
central asymmetry collapses — the generator would no longer sit outside
what it is checked against. The only defence is an external semantic
anchor (kit item 3), and [`POTENTIAL.md`](./POTENTIAL.md) §5 limit 4
says anchors exist in small finite supply and do not scale with
generation. Semantic reverse-engineering is therefore **real, useful,
and permanently rate-limited by anchor supply** — and
[`DISCOVERY.md`](./DISCOVERY.md) §3.4's refusal is exactly the right
posture toward it.

### 7.2 New objects have nothing to be adequate to

The door: **when the object is new, adequacy is not a question.** A
mined vocabulary, its transfer functions, a synthesized procedure's own
state space — none of these is a formalization *of* anything in the
world, so there is no external truth they could fail to match. Their
semantics is stipulated, and every remaining question is internal and
checkable: does the square commute, is the abstraction sound, does the
fixpoint decide the fragment.

That is why the L1 → L2 → L3 pathway is **anchor-free** while the `I_s`
inversion is not, and it is the whole reason to prefer it. The concrete
semantics you already have is the anchor; everything discovered sits
*above* it. Stated at field scale: this is the shape of abstract
interpretation as a discipline — domains stipulated and proved sound
against a concrete semantics, never a concrete semantics guessed — with
the mining and the checking moved into a loop.

### 7.3 Where the wall stands

Unmoved. Nothing here crosses the four walls of the paper's conclusion:
computability, the adequacy floor, cost, anchor supply. Inversion does
not push the frontier of *reducible decidability* — it populates the
region **behind** the frontier with content, and (via §6) supplies one
new way to produce instruments that push it. The distinction should be
stated wherever this lands in the paper, because the temptation to
overclaim here is real.

## 8. Domain-independence: what the kit costs

### 8.1 A fact is an item

The paper's model is deliberately small: *a registry is a set of items,
a candidate is a list of items,* and the two monotonicities carry
F2–F5. A deposited fact **is an item**; using it as a lemma **is**
composition. So the moment deposits are modelled as registry items,
F2 (monotone), F3 (gradient), F4 (relative completeness) and
F5 (fixpoint) apply with **zero new proof burden**, and F1(ii)'s meet
already prices a lemma-carrying answer through `Contract.comp_glb` /
`weakest_link_universal`. Discovery is a new item kind, not a new
architecture — which is [`DISCOVERY.md`](./DISCOVERY.md)'s recurring
finding, holding once more.

### 8.2 Two obligations, and one that is optional

Pointing the *discovery* loop at a domain costs at most two items
beyond the frozen kit, graded the way kit item 3 is graded:

- **K5 — a proposable question grammar.** Kit item 1 already demands
  declared question shapes; K5 asks that the declaration be
  *generable*, not merely recognizable, so a candidate `φ` can be
  produced and typed before it is decided. Nearly free wherever item 1
  holds.
- **K6 — decidable relative entailment.** `F ⊭ φ` over the accumulated
  fact set is what makes novelty mechanical (§4.2). This is *not*
  automatic: it needs the hub's fragment closed under conjunction and
  negation. `QF_ABV` and `QF_LIA` are; Horn fragments are not. Where it
  fails, novelty degrades gracefully to a syntactic filter plus
  measured leverage, and **the map records which one was used** — the
  F6 discipline exactly: the theorems hold and the books measure the
  condition.
- **K7 (optional) — a certificate schema for at least one universal
  verdict class.** A function `(question, candidate) → finite set of
  hub-decidable obligations`, fail-safe in the direction that any
  counter-model refutes the *candidate* and never the *answer*; the
  inductive invariant of §4.3 is one instantiation. Without K7,
  discovery still runs on the **existential** side in every domain
  meeting the current kit — witness replay is kit item 2 and F1(i) is
  axiom-free — and the discovery axis simply saturates at *existential*
  with the map saying so, exactly as the trust axis saturates at
  *checked* without an anchor.

### 8.3 F7, and what it costs to prove

> **F7 (unfalsifiable deposit).** Whatever the proposer does — blind or
> adversarial — every entry in the fact ledger is truthful, and every
> answer citing one carries exactly the assurance computed by the
> componentwise meet over its route *and its cited facts*.

The proof burden is small and mostly discharged already: the fail-safe
direction is the certificate schema's defining property (K7, and
[`gurdy/solvers/invariant.py`](./gurdy/solvers/invariant.py)'s landed
instance), and the grading is `Contract.comp_glb` applied to a widened
item set. The residue is the same corner F1(ii) already states and does
not hide: a deposit that no independent lineage re-discharges is
`reproducible`, not `proved`, and the books say which.

### 8.4 The genericity control

The cheapest falsification of every claim above is already in the tree.
[`pairs/crn-smtlib`](./pairs/crn-smtlib/README.md) reduces chemical
reaction networks under discrete-population semantics to `QF_LIA`
bounded reachability — a hub with **no program anywhere near it**, and
the paper's own existence proof that the kit assumes nothing
computation-adjacent. `QF_LIA` is boolean-closed, so K6 holds there.

Run L1 over it: propose `φ` over species populations, decide at the SMT
hub, filter by relative entailment, measure leverage against that
suite's board. **If the loop needs one line of program-specific code,
domain-independence is false and it is found out cheaply.** If it does
not, the deposit is a discovery result in chemistry produced by an
architecture that was never told what a molecule is — a considerably
stronger claim than closing three HWMCC pins, and the right order in
which to seek the two.

## 9. The honesty rules

- **A deposit is not a demand — F5 must not be shared.** Saturation
  terminates because in-set target signatures form a finite pool that
  never recurs (`Frontier.saturation_terminates`). Conjectures are an
  infinite pool. If conjecture demand counted toward in-set demand,
  **saturation would never terminate and F5 would break.** The fact
  ledger is therefore a separate class that does not participate in the
  fixpoint — structurally the discipline that displays `origin=campaign`
  apart from organic, and that
  [`DISCOVERY.md`](./DISCOVERY.md) §2.5 imposes on cover-legs. The route
  loop remains a fixpoint over *instrument* demand; the discovery loop
  runs after it and terminates on a **declared proposal budget**, which
  rides in provenance like every other cap
  ([`BENCHMARKS.md`](./BENCHMARKS.md) §6).
- **Saturation is what makes discovery well-posed.** An unbounded
  proposer generates infinite trivia. A saturated benchmark supplies the
  three things that turn proposal into discovery: an **open set** (so
  useful is measurable), a **closed set plus accumulated facts** (so
  novel is measurable), and a **fixpoint** (so there is a defined moment
  to switch modes). Discovery is not bolted on beside saturation —
  **the saturation fixpoint is the phase transition at which the loop
  stops being able to find new routes and starts being able to find new
  facts.**
- **Base rates, pre-registered.** [`SYNTHESIS.md`](./SYNTHESIS.md) §8
  holds unchanged and applies to every level: most demand closes
  cheaper, instantiation dominates, discovery is rare, and hull
  overfitting is audited by whether the next benchmark ever cites the
  fragment again. The claim is not that the loop will routinely invent
  decision procedures. It is that procedure discovery becomes
  **expressible, falsifiable, and occasionally achieved**, with the
  books saying honestly when nothing cheaper would do.
- **Registration stays human at every level.** The valve is unchanged:
  the loop derives that a vocabulary is missing, what it must satisfy,
  and what it is worth; a human admits it. Nothing in §§4–6 opens a
  write path from a proposer to [`pairs/`](./pairs/README.md),
  [`languages/`](./languages/README.md), or the atlas.

## 10. What the platform becomes

The framing this document exists to support should be stated carefully,
because the natural slogan claims the wrong thing.

Nothing here puts semantics *into* a model. The LLM remains a syntax
engine permanently — that is the design and not a concession, and it is
what makes the producer safely untrusted. What hurdy-gurdy supplies is
a **semantic adjudicator with memory**: deterministic, *per-artifact*
rather than aggregate, and — the part no benchmark, score, or reward
model has — **depositing**, so the syntax that survives adjudication
accumulates as checked semantic artifacts that the next question
inherits and the ratchet never surrenders.

An LLM with a benchmark gets a score. An LLM with a reward model gets a
gradient. An LLM with this gets a growing registry of artifacts whose
meaning has been adjudicated one at a time, each carrying the trusted
base it was adjudicated against — and the four inversions of §2 set how
far "semantic knowledge" reaches: translations today, abstractions and
stipulated semantics reachable and anchor-free, reverse-engineered
real-world semantics anchor-bound and honestly walled.

[`POTENTIAL.md`](./POTENTIAL.md) hands the player a luthier;
[`FRONTIER.md`](./FRONTIER.md) says the luthier is for drawing maps.
This document says what the far side of a finished map is *for*: the
one place where an untrusted syntactic generator, pointed at a
saturated region and adjudicated by procedures it cannot fool, can add
something the map did not already contain.

*Status (2026-08-04): nothing above is landed. No fact ledger, no
conjecture board entries, no vocabulary mining, no discovered tier in
the atlas, no producer parameter on `certify_unreachable`, no K5/K6/K7
kit obligations, no F7. The machinery this leans on is landed and cited
inline — the invariant re-discharge seam, the lax-square direction
axis, the solver brief and solver gate, the procedure lane, the atlas,
the ledger. This document is the named future work; the nearest
independent increment is §4.3's producer parameter, and the cheapest
falsification is §8.4.*
