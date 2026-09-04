# Kernel — hurdy-gurdy judged whole

## The shape of the system, before the sections

A **benchmark** is a pinned set of **questions**; a question is a
program, the **language** it is written in, and an **ask** — an
**observable** to watch, a **mode** (`exists`: is there an input that
makes it fire? `forall`: can none?), and a **bound** on the steps in
play. A language is a syntax with an **interpreter** — the program
that runs its programs and reports its named observables — and, where
the language declares **certificate forms**, a **checker** for each;
interpreters and checkers are the **judges**, the only code the
system trusts. A **transport** is any other generated function on
syntax: a **translator** from one language to another, a
**carry-back** that brings a target-side artifact home, or a **search** that looks for **evidence** about a program — a
**witness**, an input that makes the observable fire, or a
**certificate**, an object from which a checker can re-derive that no
input does — within a **budget** of time. A **domain** is a **root**
language, one that benchmarks arrive in, together with its
**anchors**, the ground truth a benchmark brings from outside; a
**hub** is a language where searches live. A **pair** is a translator and its carry-backs
between two languages; a **route** is a sequence of pairs — its hops
— ending at one search — its stop; a **result** is what one play of a
route on one question produced, appended to an append-only **log**.
The **registry** is the append-only store of everything generated
that has passed the **gate** — the admission check that runs each
entry against its own **controls** (its shipped cases, which the
intact implementation must pass and every shipped **mutant** must
fail) before the system may use it, and **stamps** the entry with what
it checked. An admitted entry is never edited: a **revision** is a new
entry that must agree with its predecessor on everything the
predecessor was checked on. The **kernel** is the small fixed
program that runs the gate, plays routes, keeps the log, and draws
the **frontier** — the questions no result has decided — as a
**board** and a **graph**. The **loop** is the LLM playing a
benchmark, reading the frontier, generating the next entry, and
passing it through the gate, until a human pulls the plug. Each
section below makes one of these exact; §12 lists the words.

This document is the vision and the specification of the platform's
sixth generation, begun 2026-08-20 **from the initial commit**: the
tree behind this file contained a LICENSE and this specification —
nothing else; the kernel it specifies is the only code that does not
enter through the gate — generated like everything else, and made
solid another way (§9). Since the 2026-09 consolidation this is the
design on branch `main`, with every earlier generation reachable in
its history and told in [`HISTORY.md`](./HISTORY.md). The generation
before it (Era 5) proved the founding rule — every implementation
generated, one gate adjudicating everything — and earned this design
with its last discovery: witnesses crossed the bridge home; proofs
could not, because the correspondence between a program and its
model, computed inside every translator, was discarded at the kernel
boundary. What forces a fresh lineage rather than an increment is one
separation with consequences everywhere:

> **Generation produces syntax; only interpretation produces truth.**

Era 5 owned its endpoints: everything was generated, so everything
could be gated. But its trust story kept two textures: translations
were judged empirically, per program, while solvers pronounced
verdicts on their own admitted word. The sixth generation removes the
seam. There is exactly one semantic device, the interpreter; exactly
one trust event, an interpreter run judging a transported artifact;
and every other executable — translator, carry-back, search — is
untrusted syntax whose output faces a judge. **Searches do not
decide; they write. Judges decide.**

Two rules carry over unchanged:

> **Every implementation in the system — translator, interpreter,
> search, checker — is generated, in Python. There are no existing
> tools inside the system.**

> **Structure only what the kernel must compute with; everything else
> is evidence for the LLM and stays prose.**

Every word below is one of §12's, or a phrase made of them.

## 1. The two kinds

The registry holds exactly two primitive kinds. Everything else here —
pairs, evidence, grades, routes — is derived from them; the kernel
computes with the derived forms without storing them as kinds.

**Language** = a deterministic syntax plus a deterministic
**interpreter** exposing named observables, plus the certificate forms
the language can judge, each shipped with a generated **checker**
(§3). Interpreters and checkers are the **judges** — the system's only
semantic devices — and the **trusted base is exactly the set of
admitted judges**, nothing else: a list the kernel prints, each judge
with the anchors and controls that corroborate it. The base is a
list, not a story.

- A **root** is a language benchmarks arrive in. Its interpreter is
  the trusted floor, corroborated by the domain's anchors (labels,
  supplied vectors) and by nothing generated.
- Every other language carries no parent taxonomy: a language is a
  language. Its interpreter is corroborated empirically by the squares (§2) of
  the pairs that connect it — and a language between two anchored
  neighbours, one square on each side against a different anchored
  interpreter, is corroborated from both sides at once, which no
  single pair can give.

**Transport** = a generated function on syntax, declaring its
**fragment** — the programs it accepts; outside it, a transport refuses
rather than guesses. There are three:

- the **translator** `T` — a source program to a target program;
- the **carry-backs** `Λ` — a target-side artifact to its source-side
  form: a witness input, a certificate, an observable name;
- the **search** — the one partial transport: given a budget (a wall clock cap), deterministic for that budget,
  allowed to return `partial` (§3). A route (§5) ends at exactly one search: its pairs, the
  hops, compose, and the stop happens once.

Every transport is untrusted, whatever it computes. Its output never
carries trust of its own — only the judgment it survives.

**Domain** = a root language together with its **anchors** — the two
things the loop cannot generate for itself: the format questions
arrive in, and the ground truth (benchmark labels, supplied test
vectors, the recorded testimony of outside **oracles**, §6) that
corroborates the root's interpreter. A benchmark lives in exactly one
domain, and a domain owns nothing else and fences nothing (§7).

## 2. Pairs — the three judgments

A **pair** is the transports that share one correspondence between a
source and a target language: its translator and its carry-backs,
declared with `src`, `tgt`, a **direction** (exact, over, under), the
observables it **keeps**, the artifacts it carries, measured cost, and
its lineage (§4), together with its **corpus** — the programs it
ships as its own controls. The grouping is not redundancy: a witness carried back by one
translator's carry-back and replayed against another translator's
output is nonsense; the pair is the statement that its transports are
meaningful together — the correspondence as text, its transports the
correspondence in use.

Three kinds of artifact move across a pair, and each is judged on
arrival by an interpreter run. There is no other kind of check in the
system:

| artifact      | moves   | transport     | judged on arrival by                                       |
|---------------|---------|---------------|------------------------------------------------------------|
| a program     | forward | `T.py`        | **the square**: both interpreters agree on what is kept    |
| a witness     | back    | `lam_wit.py`  | **replay**: the source interpreter runs the program on it  |
| a certificate | back    | `lam_cert.py` | **discharge**: the source language's checker re-checks it  |

Two more things cross a pair, and neither is judged. A **bare claim**
— "no failure within bound k" with no certificate behind it — crosses
back needing no transport, only the pair's observable renaming and its
**bound cap**; nothing judges it, and that is exactly why it cannot
raise trust (§4). A **hint** — seeds, candidates — crosses forward
into a search, trust-inert by construction: whatever it seeds is
judged on arrival, so a hint can move cost and never a grade.

**The square** is the judgment on programs: `I_s(p) ≡ Λ(I_t(T(p)))`
on the kept observables, for every program of the pair's corpus, both
interpreters run at admission; the observable renaming (`maps`, or a
generated `lam_obs.py`) is the projection inside it. The square is not
a primitive and not a proof — it is checked empirically, per program,
which remains the platform's founding economy. **Direction** declares
what may cross back — witnesses along exact and under pairs, universal
objects (claims and certificates) along exact and over — and the
square is the empirical evidence for the direction claim. A pair that
reifies an unrolling declares a bound cap: an unbounded object
crossing it arrives as a bound-k fact, invariant or not.

**Certificate forms belong to languages, not to searches.** For a
certificate to come home, what it looks like must be declared where it
lands: a form named at a language and shipped with a generated checker
(§3). A pair's certificate carry-back then maps form to form, per
program, through the correspondence its translator already computes.

## 3. Evidence — what a search writes

A **search** is a transport from a language to evidence about its
programs. It declares which observables it can target, it writes —
and it pronounces nothing. Three kinds of evidence, and one honest
non-answer:

- A **witness** is an input. Its judge is the language's own
  interpreter, by replay: no generated code stands between the
  payload and the trust event. Witnesses therefore need no declared
  form, and a fresh domain can settle and fully certify existential
  questions with nothing but its root interpreter admitted.
- A **certificate** is an object of a form the language declares — a
  k-induction kernel, a clause invariant — shipped with a generated
  checker under the language entry (`evidence/<form>/check.py`) and
  admitted like everything else: determinism, example certificates
  that must discharge, mutant certificates that must not. Checkers
  are judges: part of the trusted base, and deliberately the simplest
  code in the system. Smallness of judges is the honesty metric.
- A **bare claim** — a universal claim with nothing to check — is
  legal and floors at the lowest grade (§4). This is intended
  selection pressure: a search that writes checkable certificates
  outgrades one that writes bare claims at the same cost, so the
  ladder itself breeds certificate printers.
- A **partial** — how far the search got, where it failed — is what
  a route returns when nothing above came home.

A result that decides its question is **settled**: a replayed witness,
or a universal claim covering the asked bound. Question modes are not
kernel vocabulary: `exists` asks for a witness, `forall` for a
universal claim, and a future mode — liveness, resource bounds — is a
new certificate form with a new checker, not a kernel change.

A language whose programs are triples (code, model, correspondence),
interpreted in lock-step with divergence as refusal, is an ordinary
language under this specification; it makes every play a square
instance and gives view-switching searches a lawful home. Such
languages are earned, as (c)-moves of §8, only when a hybrid win keeps
repeating ad hoc.

## 4. Grades are geometry

Trust is computed, per result, from where its evidence was judged:

```
gap       = hops between the question and the last judgment the
            evidence passed
grade     = certified   if gap = 0
            checked     if gap > 0
            claimed     if no judgment ever ran
residual  = the lineages of the hops still between the question and
            that judgment, plus the judge that ran — what the result
            still rests on
corroborated = results of disjoint lineage agree   (an orthogonal flag)
```

**Each judgment removes everything upstream of it from the residual.**
A certificate discharged at the search's language removes the search
from what the result rests on — the search may be garbage; the
checker validated the object. Carried one hop back and discharged
again, it removes that hop too. Discharged where the question lives,
it removes the route entirely: `certified` is route-independence, as
the theorem `gap = 0` (§9). The fail-safe direction is definitional
and universal: transport is untrusted, so a wrong or adversarial
carry-back can only lose a grade, never forge one.

Witnesses have one property worth stating once: the kernel always
replays them where the question lives, chaining carry-backs across
the route, so a witness is certified or it is not a result at all — an
unreplayable witness is evidence inside a `partial`, never an answer.

A replayed witness is ground truth. If a question ever holds both a
replayed witness and a universal claim covering its depth, the kernel
records a **contradiction**: the witness stands, and the universal's
entire chain — evidence, judgments, and every transport it crossed —
is marked falsified. Contradictions are never silently resolved.

**Lineage** is a declaration about the descent of generated
procedures. Two judges grown from the same ancestor never corroborate
each other; the corroborated flag requires evidence whose descent sets
are disjoint. The second-order effect is intended: whatever earns the
top grades is what the loop learns to build, so the frontier itself
pushes the LLM toward certificate printers, certificate carry-backs,
and independently generated judges.

## 5. Routes, results, the frontier

A **question** is a program, the language it lives in, and its
**ask**: an observable, a mode (`exists` or `forall`), and a bound. A
**benchmark** is a pinned finite set of questions with recorded
provenance (sha256 per program, labels where they exist). A **route**
is a sequence of pairs ending at one search. Its forward contract is
the componentwise meet — fragments intersect, kept observables
intersect, bound caps take the minimum, costs add — and how far an
artifact travels back is per kind: as far as every pair on the way
carries it, its grade computed from where it was last judged (§4),
not from what the route promises.

A **result** is one play of a route on one question, appended to the
log with everything the board needs:

```
result = { question, route, budget: {caps, spent},
           value: witness(w)                   -- replayed: certified
                | all(bound: k | inf, cert?)   -- graded by its gap
                | partial(progress)            -- how far, where it failed
         , grade, gap, residual, lineage }
```

(The log spells the residual as `trust`; field names never change
under a vocabulary.)

`partial` is deliberately semi-structured: a small typed core the
kernel orders on (`progress.bound_reached`, the bound reached) plus
free-form progress description and profiling — budget spent among it,
recorded and never ranked — because its reader is the LLM.

Results order per question by one key, stated here exactly because
the mechanization and the second lineage of the kernel (§9) are both
held to it: `(level, bound, grade, gap)`, compared lexicographically,
strictly greater is better. *Level*: 0 a partial, 1 a universal claim
below the asked bound, 2 settled — a replayed witness, or a universal
claim covering the ask. *Bound*: for a universal claim its bound,
`inf` above every number; for a witness, above `inf` itself — a
replayed witness stands above any universal claim on its question; for
a partial the bound it reached, none below zero. *Grade*: the rung —
ungraded below claimed below checked below certified. *Gap*: a smaller
gap is better, and "no check ever ran" sits below every finite gap.
The incumbent survives only while it is strictly better: among records
of equal key the latest wins, so the board shows the most recent
adjudication of an equally good result. Cost is recorded in every
result
and never ranked; the player reads costs across routes to find the
cheap one and spends what that frees on open questions. Two performance moves are trust-free because they are judged:

- **regrade**: re-discharging a stored certificate closer to home
  costs check time, not search time — the board is re-graded without
  being re-solved, and a shrinking gap is a strictly improving result under the ratchet
  defined below; a revised judge re-derives a stored certificate's
  residual the same way, and among equally good results the board
  shows the latest adjudication, so a proof is always read under the
  judges the registry holds now;
- **hints** (§2): a forward artifact that can move minutes of search
  and not one grade.

**The ledger.** Cost says what a play spent; the ledger says what it
bought, in bits — profiling, not vocabulary: recorded in results and
manifests, never ranked by the kernel, never touching a grade. Three
quantities, each computable from artifacts the kernel already holds.
**Witness surprisal** `S = -log2 Pr[a random stimulus is a witness]`,
under the uniform measure the interpreter's havoc rule already fixes:
every failed concrete trial tightens a lower bound as free profiling,
an exact count is a lawful search by-product, and `S` separates the
two ways a question can be open — evidence rare (a needle, symbolic
work) versus searches weak (low `S`, still unsettled). **Cleared
bits** `B(k)`, the log-size of the stimulus space a bound-k universal
claim exhausts, making `B/spent` one clearance currency across every
search family, concrete or symbolic. **Certificate length** `L`,
compressed size under a pinned stdlib compressor, making `B/L` the
compression a certificate achieves over exhaustive checking — infinite
exactly at `bound: inf`. Each pair then carries an **exchange rate**,
measured on its corpus at admission and recorded beside cost: how a
program dilutes in bytes and in steps, how a witness's surprisal
shifts (exact preserves it, over can only lower it, under only raise
it), how a certificate inflates, how a bound rescales. The ledger was
piloted retroactively on the fifth generation's logs before being
written here: surprisal stratified every witness by which searches
could find it, and clearance rate ordered every search family in one
currency — with no new trusted code, because every quantity is read
off artifacts the judges had already validated.

Every ledger quantity is also recorded **per search and per domain**:
questions settled and bits cleared, tabled on the board by the domain
the question lives in. A search grown on one domain that clears bits
on another is the measured form of the claim §7 makes — that
reasoning capabilities are properties of languages, not of the
domains they were grown in — and the exchange rate of the pair that
carried the questions there is that domain's rate into the hub. Both
numbers are profiling: they move attention and budget, never a grade.

**The frontier of a benchmark is the set of questions whose best
result is not settled**, each carrying that result and its progress.
The registry and the log are append-only; best-per-question over an
append-only log is monotone: the **ratchet** is a property of the
data structure. **Expanding the frontier** means strictly improving
some question's best result — level, bound, grade, or gap; never cost.

The frontier has a **second reading**, from the registry alone. A
search or a judge is a reasoning capability that lives at one
language; a root reaches it exactly when a route of translators whose
fragments admit its programs composes from the root to that language.
For every admitted root and every admitted search the kernel can
therefore say one of three things — reaches it, by these routes;
reaches it only for this fragment; or does not reach it, and here is
the one missing pair that would — as a pure function of the registry,
computed by the routing the driver already performs. Where the first
reading says which questions are open, the second says which
reasoning no domain can yet bring to them. A missing pair on it is a
conjecture, never a demand — the registry records no obligations, and
the conjecture order (§8) says when the pair is the right next move.

The frontier is drawn, not only listed. Two renderings, both pure
functions of (registry, benchmark, log), both regenerating
byte-identically:

- **the board** (`frontier.md`): one row per question — its best
  result: value, grade, gap, residual, route, cost, and the best
  oracle's cost where the domain recorded one (§6) — and below the
  rows the second reading as a table: every admitted root against
  every admitted search, each cell a route, a fragment, or the
  missing pair.
- **the graph** (`frontier.dot`): the whole registry drawn — every
  admitted domain's root, not only the benchmark's; languages as
  nodes, pairs as edges, searches as stops — with best results
  overlaid. Grades being geometry, a missing carry-back is a visible
  conjecture: the dotted edge says which one would move a grade, just
  as a dotted route says which pair would connect a stop — and a root
  drawn with no edge at all says which domain has not yet reached any
  reasoning.

Of the renderings above, the reach table, the oracle column, the
drawing of every admitted root, and the per-domain ledger table are
specified as of the 2026-09 consolidation and not yet drawn: the
kernel renders the board and graph of the first campaign, and
`HISTORY.md` names the rest as work. A specification that says so is
worded no stronger than what the tree does.

## 6. The generation rule — oracles, not organs

Every implementation is generated, in Python, and lives as committed
source inside its registry entry: the judges of every language, the
transports of every pair, every search. **No
existing tools**: no wrapped engines, no shelling out, no vendored
binaries of someone else's reasoning. The substrate is infrastructure,
not tooling — the Python interpreter the kernel itself runs on, and a
declared compiler where an accelerator needs building — but nothing
that *reasons* enters except as generated text through the gate.

**Oracles, not organs.** The rule bounds the system, not the evidence
about it. At admission time a human or the LLM may consult an
**oracle** — an existing compiler, solver, or reference implementation
run entirely outside the sealed runner — and what the oracle says
enters the registry the only way ground truth ever enters: as anchors,
vectors and labels with recorded provenance, corroborating a judge or
a transport exactly the way a benchmark label corroborates a root
interpreter. No new kernel vocabulary, no manifest field, no seam in
the seal: an oracle never enters the trusted base, never runs inside a
play, and its disagreement is evidence to adjudicate — recorded and
attributed — never a verdict. The fifth generation set the precedent
when its C spine was cross-checked against the compiler that never
entered; the rule generalizes it: inherit the world's hard-won
semantics — floating point, the ISO C corners, a competition solver's
decades of tuning — as testimony at the gate, never as organs in the
body.

Testimony has three uses, and the same rule governs all of them.
**Trust**, as above: verdicts, vectors, and labels that corroborate a
judge or a transport. **Relative performance**: an oracle's cost on
the same question is testimony too. The per-question verdicts and
wall times a competition archive publishes are pinned into the
domain's anchors beside its labels, and one calibration run of the
pinned oracle bench on the host that plays — recorded at domain
admission with machine and image digest — makes the ratio honest.
The board then draws, per question, the best result's cost against the
best oracle's, and the ledger converts an oracle's time into a
reference clearance rate in the same bits-per-second currency —
recorded beside cost, never ranked, never a grade — so that a
generated search is read beside the state of the art without the
state of the art ever entering the seal. **Disputes**: when a judge
and an oracle disagree on an anchor, the disagreement is recorded as
an event carrying both testimonies and the adjudication — a bug in
the generated judge, a stipulation the fragment makes deliberately,
or a corner the oracle gets wrong — and the anchor is marked
contested until adjudicated; a contested anchor corroborates nothing.
That record is how the world's semantic archaeology is inherited one
dispute at a time, and it is the stipulation-sensitivity instrument
of `POTENTIAL.md` pointed at admission. Oracles may also testify
about **transports**, not only judges: a compiler's output for a
corpus program, run under the generated interpreter of the target
language and compared on kept observables with the source
interpreter's run, corroborates both the generated translator and
the target judge from a lineage that shares nothing with either. The
oracles live outside the tree's executable surface: `oracles/bench/`
pins the tools by digest, `oracles/packs/` holds recorded testimony
awaiting a regenerated language to be admitted against; nothing
under `oracles/` is ever imported, invoked, or routed by the kernel.

Enforcement is layered, and worded no stronger than what each layer
verifies: **statically**, there is no manifest field for pointing at a
tool; **dynamically**, the runner is sealed — every registered
executable runs in its own process with an environment emptied to a
blank `PATH` — blank rather than absent, because an unset `PATH` is
replaced by the platform's default search path, where a tool may sit —
a temporary working directory, and a wall cap, and every check runs
twice with byte-compared output; **socially**, every implementation is
committed source, auditable and mutable, which is what the two-sided
controls need anyway. The seal makes reaching for a tool loud and the
registry makes it visible; neither is claimed to be a proof.

**Accelerators: syntax may accelerate; semantics never does.** An
entry may ship one accelerator — the same implementation generated
again in a performance-oriented language (C, Rust, …), source and
built executable both in the entry — and only for the play-time
transports, `T` and `solve`, because their outputs face judges
downstream. Carry-backs run once per evidence item and never need
one; judges — interpreters and checkers — always run the Python
reference, because the trust events must stay in the semantics-bearing
implementation. An accelerator is admitted solely by byte-agreement
with its reference on every admission invocation; the reference
remains the semantics, and the accelerator is only ever a cheaper way
to the same bytes. Per-program specialization is explicitly lawful for
accelerated transports — compiling the program into the search loop —
for the same reason everything about transports is lawful: the output
is judged, per artifact, on arrival.

This is where untrusted generation becomes the design's engine rather
than its risk. The architecture maximizes the surface where the LLM
may be wrong for free: a wrong translator loses squares, a wrong
solver loses discharge, a wrong carry-back loses replay — none can
forge. At gap 0 nothing generated can corrupt a result; at gap > 0 the
meet names exactly which generated text could be wrong. The only
things needing care are the judges, and the design keeps them few,
small, anchored, and mutant-tested.

## 7. One gate for everyone, and everything available to everyone

There is one way into the system, and the loop and a human use it the
same way: write an entry directory and pass it through the gate
(`python3 -m kernel.driver admit <entry-dir>`); play a benchmark
(`play`); regrade it (`regrade`). No special case for either author.
Steering the system is only ever adding checked capability; results
are never written by hand.

**Availability is universal, and reuse is the cheap move.** The
registry is one space: every admitted language, pair, and search
serves every domain, including domains that look wholly unrelated to
the one an entry was grown in. A domain is only a root and its
anchors — it fences nothing. Routing stays honest under openness
because it is declarative — a route must compose translators whose
fragments admit the program, and its search must target the composed
observable — so an absurd route can only produce a partial, never a
wrong answer, and junk never wins a route because the result order,
not arrival, picks the best.

Openness is not merely permitted; the geometry makes it the cheapest
move there is. Searches and judges live at a few **hub** languages —
today the bit-vector transition systems of BTOR2; constraint
languages next — and a search at a hub is a reasoning capability:
bounded reachability, k-induction, property-directed reachability,
random simulation. **A domain enters a hub by one pair.** From the
moment its root's interpreter and one translator to a hub are
admitted, the domain owns every search at that hub: its existential
questions certify at gap 0 on day one, because replay needs no
generated judge; its universal claims arrive *checked* at gap 1, and
close to gap 0 the day the pair gains a certificate carry-back by
revision. And because a search grown in another domain has, by
construction, a descent disjoint from anything grown in this one,
routes through a borrowed hub are also the cheapest source of the
corroborated flag. Whether a capability grown on hardware clears bits
on a chemistry corpus is not a hope but a ledger entry (§5), and the
standing experiment of the platform across domains is how few hubs
suffice, at what exchange rate. What a new domain costs is what it
always cost — its root's interpreter and its anchors — and the
sciences supply both the way the competitions did: a repository of
models with known answers, and the recorded testimony of the
simulators and solvers already trusted there, at the gate, never
inside.

## 8. The loop, the conjecture order, and bootstrap from empty

The LLM is presented a benchmark and runs autonomously until a human
pulls the plug:

1. **Play** — one **iteration**: for every question, run the admitted
   routes within budget; the kernel records results.
2. **Read the frontier**: the open questions with their progress —
   and the grades: a board full of `claimed` and `checked` is itself
   frontier, since the gap is a dimension the ratchet moves on — and
   the frontier's second reading: which roots reach which searches,
   and the one pair each unreached search is missing.
3. **Conjecture**, in this order — the **conjecture order**: semantics
   first, then syntax:
   - **(a) new judging and searching for existing languages** — a
     search, a certificate schema with its checker, an accelerator
     for a proven bottleneck: new reasoning first;
   - **(b) new transports** — pairs, and carry-backs retrofitted onto
     admitted pairs by revision. Two (b)-moves are canonical in this
     generation: a certificate carry-back added to a proven
     translator, and a translator from a root that reaches no hub to
     the nearest one — the entry move of every new domain, which
     outranks a domain-local search in this order because it inherits
     every search at the hub for the price of one translator (§7);
   - **(c) new languages** — products and other origin-carrying
     forms — proposed only when a translation or solving move keeps
     winning ad hoc and reifying it would make the win reusable and
     cheap. New syntax is earned by demonstrated semantics, never
     invented ahead of it.
4. **Generate, check, register**: the LLM writes Python (or, behind a
   reference, an accelerator); the kernel gates it; what passes is
   registered.
5. Re-play affected questions; repeat.

The trust story in one sentence: **the LLM never writes a result; only
the kernel does, by running judges over transported evidence.** What
autonomy risks is registry clutter, which the result ordering
neutralizes and which pruning, a human act between runs, can clean.

**Bootstrap from empty.** The kernel ships with zero languages, zero
transports, zero domains. Presented a benchmark, the LLM's first acts
are: admit the domain (root name + anchors — the ungenerable half,
nothing executes), write the root language's interpreter (the trusted
floor, corroborated by the anchors and by nothing generated),
then a first naive search in pure Python. Witnesses need no
declared form — replay needs no generated judge — so existential
questions can settle *certified* with a single admitted interpreter;
the first certificate form and checker arrive when universal
questions need better than `claimed`. Everything must work at this
point — the design's simplicity test and its totality test at once:
the naive generated search is not a stopgap but the first citizen, and
every later power move improves on a working, admitted baseline. On a
registry that already holds a hub, the first pair to it plays the
same role (§7): the baseline is whatever the first admitted route can
answer, and a borrowed search is as much a first citizen as a naive
one.

**Plug-pull** is safe at any moment: the driver appends every result
and registration as it happens, and the exit deliverables are pure
functions of the log — the board and the graph with the delta since
iteration zero, and, if the frontier moved, the evolved hurdy-gurdy:
the kernel unchanged plus everything registered, with admission
evidence. The next benchmark starts from it.

## 9. The kernel — generated, and made solid four ways

The kernel is the fixed part: the gate, the sealed runner, the result
order, the registry loader, and the driver that plays, regrades, and
renders. It is small on purpose (readable in an afternoon), and it is
the one piece of code the gate cannot judge, because it *is* the gate.
It is generated like everything else in the tree — but it does not
enter through admission, so four disciplines stand in for the gate,
each worded no stronger than what it verifies:

1. **It computes no truth of its own.** The kernel runs judges,
   compares bytes, orders results, and draws the log. A kernel bug can
   lose a result or misgrade one; the property that it can never
   *forge* one — no record reaches `certified` unless an interpreter
   run where the question lives passed, whatever a search, a
   carry-back, or a translator wrote — is stated here and falsified by
   test (`kernel/tests/test_forge.py`): on a registry bootstrapped
   from empty through the real gate, a lying search, a broken
   carry-back, a bogus certificate, a bare claim, and a route missing
   a carry-back each lose a grade and never gain one, and whatever a
   search writes about its own grade never reaches the record.
2. **The half that is mathematics is proved.** The Lean development
   under `kernel/mechanization/`, grown beside the code, proves for
   exactly the key of §5: the result order is a strict partial order
   (irreflexive, transitive, asymmetric); best-per-question is
   monotone under log append — the ratchet; once settled, always
   settled — the frontier never re-opens; at a fixed level and bound,
   the gap never grows and grades only move up the ladder, so a
   regrade, which keeps the value, is a strict
   improvement exactly when it moves either; and the trust meet is
   well-defined — the residual of a checked result is exactly the
   lineage union over its gap segment plus its judge — from which
   gap 0 rests on the judge alone (certified is route-independent as
   a theorem), every judgment removes everything upstream of it,
   a smaller gap never adds trust, and the stop is never in the
   residual. The proofs are generated and machine-checked; the theorem
   statements are what a human reads; the axiom audit printed at every
   build is the development's own trusted-base list.
3. **The half that is operation is falsified**, the way every entry
   is (`python3 -m kernel.tests`): the gate is run against the
   registry's own controls — every bound entry's stamp re-derived by
   re-running its admission, every supplied mutant refused again, and
   with `HG_SLOW=1` every admitted entry of every kind — and, on the
   toy registry, every way of failing the gate fails it; the seal is
   measured — no environment but a blank `PATH`, so that not even the
   platform's default search path finds a tool, a scratch working
   directory, a wall that is a result rather than an exception,
   determinism twice; the content pin is recomputed from its
   definition in §10 for every stamp; and the board and the graph of
   every pinned run regenerate byte-identically. A test that found the
   seal weaker than this section claimed (an unset `PATH` still found
   `/usr/bin/python3`) is how the blank `PATH` got here.
4. **A second lineage agrees.** `kernel/second/` is the kernel's pure
   half — registry loading with pin verification, benchmark pins, the
   order, best-per-question, the frontier, contradictions,
   corroboration, the board, the graph, the base — generated
   clean-room from this specification and the committed data alone,
   never from the first kernel's source (its README records the
   protocol, what it read, and where the specification left it
   guessing), and held to byte-agreement with the first on `base`,
   `report`, and `graph` over every pinned run and over a synthetic
   run holding the corners no pinned run exercises. This is the
   accelerator discipline of §6 turned on the kernel: two
   implementations of disjoint descent that agree on every byte
   corroborate each other, as two judges do. Where they disagreed
   while being built, the specification was made to say which is
   right (§5's key, §10's pin and binding rule), and now does.

Manual review is the last discipline, and the four above are what make
it tractable: what must be read is exactly the trusted base — the
admitted judges, printed by `base`, and the kernel's five modules — and
the reviewer reads theorem statements, tests, and a second
implementation's disagreements rather than a story.

Generated content is asked for proofs **when appropriate and
feasible**: a certificate schema must come with its fail-safe
direction stated, a new result payload with its ordering. Per-program
translation correctness is *not* proved — the square checks it
empirically, per run. Accelerator equivalence is likewise not proved —
it is measured, invocation by invocation, and the reference stays the
semantics.

## 10. The gate, the layout, and the executable contracts

The kernel is the ultimate gate: nothing — no language, pair, search,
domain, or any of their implementations, accelerators included —
enters the system except by admission, and admission evidence is
stamped into the entry by the checker, never self-reported. One
discipline for every kind: determinism measured (run twice,
byte-compare), the checkable relation run on the entry's own corpus,
and **two-sided controls** — the intact implementation must pass and
every supplied mutant must fail, because a checker that cannot be made
to fail is unfalsifiable.

Per kind, the checkable relation is:

- **language**: its **vectors** — programs with pinned observables —
  interpret as expected against the anchors,
  and each shipped checker discharges its example certificates and
  refuses its mutant ones;
- **pair**: **every artifact the pair carries round-trips** per
  corpus program — squares close, stimuli replay, certificates
  discharge — with mutants supplied per artifact kind;
- **search**: on its corpus, written evidence must judge valid,
  negative controls must fail, budget determinism must hold;
- **domain**: the root is named, every anchor carries its provenance,
  and performance testimony, where present, names the machine and the
  bench digest it was measured on; a contested anchor (§6) is
  admitted as contested and counts for nothing until adjudicated.

An entry that fails leaves no stamp and no trace in routing.

```
kernel/                  the fixed part (stdlib-only Python), outside
                         the gate and made solid four ways (§9)
  registry.py runner.py results.py gate.py driver.py
  mechanization/         Lean: the proved half (§9)
  tests/                 the falsified half: python3 -m kernel.tests
  second/                the second lineage of the pure half, held to
                         byte-agreement with the first
registry/                generated content, append-only
                         (revisions as sibling entries <name>@<r>)
  domains/<name>/        manifest.json (root + anchors); optional
                         bench.jsonl: per-question oracle verdict and
                         wall, with machine and digest (§6)
  languages/<name>/      manifest.json, interp.py, vectors/, controls/
    evidence/<form>/     check.py, vectors/, controls/  (the checkers)
  pairs/<src>--<tgt>/    manifest.json (artifacts carried), T.py,
                         lam_wit.py?, lam_obs.py?, lam_cert.py?,
                         corpus/, controls/
  searches/<name>/       manifest.json (targets), solve.py,
                         corpus/, controls/
runs/<benchmark>/        benchmark.json (pinned), log.jsonl (append-
                         only), frontier.md + frontier.dot
oracles/                 outside the executable surface (§6): bench/
                         (the pinned tool image that testifies),
                         packs/ (recorded testimony awaiting a
                         regenerated language); never imported,
                         invoked, or routed by the kernel
paper/, video/           documents; each names the era it describes
HISTORY.md               the generations, and where each one lives
```

Every registered executable is a pure deterministic CLI — bytes in,
bytes out — run sealed (own process, **an environment emptied to a
blank `PATH`**, temp working directory, wall cap) and run twice with byte-compared output
on every check. Manifests declare kind, the artifacts carried (the
`channels` field: `prog`, `wit`, `obs`, `claim`, `cert`, `hint` — the
six names the executable contract keeps for programs, witnesses,
observable renaming, bare claims, certificates, and hints) with
measured cost per artifact kind, direction, kept observables, lineage,
budget schema,
`targets` on searches, optionally one `accelerator` (replaces `T.py`
or `solve.py`; source + built executable in the entry; admitted by
byte-agreement, §6), and optionally a proof obligation (§9). A search
may ship a `ledger.py` (§5) that reads the program and the value the
search wrote and reports what the play bought in bits; it is
trust-inert like `hint.py` — determinism is its whole gate — and what
it writes is recorded beside the result, never ranked, never a grade.

**Revision, not mutation.** An admitted entry is never edited: every
stamp pins the entry's bytes (a content hash the loader re-verifies —
an admitted entry whose bytes changed is a hard error), and the log's
citations mean those bytes forever. The pin is defined here, not left
to an implementation, so that any lineage of the kernel can re-verify
it (§9): over every regular file under the entry — the top-level
`manifest.json`, dotfiles, `__pycache__` directories and `.pyc` files
excluded — take the map from entry-relative path to the sha256 hex
digest of the file's bytes, serialize it as JSON with sorted keys and
the separators `, ` and `: `, and sha256 that text once more; the
stamp records the result as `tree`, and a stamp that carries no pin is
refused by the loader as if its bytes had changed. Extension arrives as a new entry
`<name>@<r>` carrying the same name, a `revision` number, and
`previous` — the predecessor's content hash. The gate for a revision
is the ordinary kind gate **plus conservativity**: the new
implementation must byte-agree with its predecessor on the
predecessor's whole checkable surface — its vectors or corpus, and
for a language the corpora of every admitted pair bound to it,
through the pair's translator where the pair only lands in the
language. Agreement on the old fragment is exactly the evidence that
lets dependent stamps keep their meaning; the new fragment is checked
and falsified like any first admission. A name binds to its highest
admitted revision, and to exactly one entry per revision — two entries
claiming the same name at the same revision are a hard error, not a
choice; predecessors stay in the tree; results name the revision
they ran. Trust never transfers by assumption — a
revision that cannot agree is a different tool and must take a
different name. Adding a carry-back to an admitted pair is the
intended common case of revision: the old transports are the conserved
surface, the new one is gated fresh.

## 11. Honesty rules

- The kernel never trusts a claim it can measure.
- The trusted base is a list, not a story: every judge printed with
  its anchors and controls; everything not on the list is untrusted
  syntax and named so.
- Every result states its grade, its gap, and its residual — what it
  still rests on; nothing is worded stronger than what was verified.
- Budgets ride in every result's provenance; capped is labeled capped.
- Contradictions are recorded, never resolved silently.
- The frontier summary — board and graph — regenerates from the log
  byte-identically.
- The generation rule states what each layer enforces (§6) and claims
  no more; an accelerator's agreement is measured, never assumed.
- An oracle testifies from outside: its output enters as anchors with
  provenance, it never joins the trusted base, and it never runs
  inside a play.
- Oracle performance is testimony: recorded beside cost, drawn as a
  ratio, never ranked and never a grade; a contested anchor
  corroborates nothing until adjudicated.
- The frontier's second reading is a pure function of the registry;
  a missing pair on it is a conjecture, never a demand.
- Pruning the registry is a human act between runs; during a run the
  registry only grows.
- The kernel is generated too, and its trust is not a story either:
  proofs for what is mathematics, tests for what is operation, a
  second lineage's byte-agreement, and review — each claimed only as
  far as it verifies, and every disagreement between the two lineages
  settled in this specification, never papered over.

## 12. The words

The specification above is written in these words; anything else is a
phrase made of them.

| word | means |
|---|---|
| **language** | a syntax with an interpreter; a **root** is one benchmarks arrive in, a **hub** one searches live at |
| **judge** | an interpreter or a certificate **checker**; the **trusted base** is the admitted judges |
| **transport** | a generated function on syntax — a **translator**, a **carry-back**, or a **search** — untrusted whatever it computes |
| **pair** | the transports sharing one correspondence, with a **direction**; its judgment on programs is **the square** |
| **evidence** | what a search writes: a **witness** (judged by **replay**), a **certificate** (judged by **discharge**), or a **bare claim** (judged by nothing) — else a **partial** |
| **domain** | a root plus its **anchors**; an **oracle** is an outside tool whose recorded testimony is an anchor |
| **question**, **benchmark** | a program, its language, and its **ask**; a pinned set of questions |
| **route**, **result** | pairs ending at a search; one play of a route on one question, logged |
| **gap**, **grade** | hops from the question to the last judgment; the gap read as certified, checked, or claimed |
| **residual**, **lineage** | what a result still rests on; the declared descent of generated procedures |
| **corroborated**, **contradiction** | disjoint lineages agreeing; a witness beside a covering claim |
| **frontier** | the open questions and, read the other way, the searches no root reaches; drawn as **board** and **graph** |
| **ratchet**, **ledger**, **cost** | best only improves; bits bought; time spent |
| **gate** | admission: one discipline, **controls** (the intact passes, every mutant fails), a **stamp** with a content pin, **revision** not mutation |
| **loop** | play, read the frontier, conjecture in order, generate, admit, re-play |
| **kernel**, **registry** | the fixed part outside the gate (§9); everything admitted |

Words this generation used before 2026-09-04 and retired, so that old
logs, manifests, and documents still read: *channel* and *arrival
check* (now the three judgments and what they judge), *path* (now
result), *terminal* and *solver* (search), *the meet* and *residual
trust* (residual), *capability frontier* and *reach matrix* (the
frontier's second reading), *map* (board), *stipulated* (corroborated
by anchors only), *evidence schema* (certificate form), *grade-raising
replay* (regrade), *the two modes* (one gate). Field names in logs and
manifests — `trust`, `channels`, `evidence/` — keep their old spelling,
because content pins hash paths and the second lineage of the kernel
reads the same bytes.
