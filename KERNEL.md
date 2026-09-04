# Kernel — hurdy-gurdy judged whole

This document is the vision and the specification of the platform's
sixth generation, begun 2026-08-20 **from the initial commit**: the
tree behind this file contained a LICENSE and this specification —
nothing else; the kernel it specifies is the only code that will
not enter through the gate — generated like everything else, and made
solid another way (§9). Since the 2026-09 consolidation this is the design on
branch `main`, with every earlier generation reachable in its history
and told in [`HISTORY.md`](./HISTORY.md). The generation before it
(Era 5) proved the founding rule — every implementation
generated, one gate adjudicating everything — and earned this design
with its last discovery: the correspondence between a program and its
model, computed inside every translator and discarded at the kernel
boundary, is where the missing half of the trust story lives.
Witnesses crossed the bridge home; proofs could not. What forces a
fresh lineage rather than an increment is one separation with
consequences everywhere:

> **Generation produces syntax; only interpretation produces truth.**

Era 5 owned its endpoints: everything was generated, so everything
could be gated. But its trust story kept two textures. Translations
were judged empirically — the square, run per program — while
terminals pronounced verdicts on their own admitted word: search,
checking, and inference bundled into one kind, marked by the one node
in the graph with no interpreter. The sixth generation removes the
seam. There is exactly one semantic device, the interpreter; exactly
one trust event, an interpreter run judging a transported artifact;
and every other executable — translator, carry-back, solver — is
untrusted syntax whose output faces a judge. **Solvers do not decide;
they write. Interpreters decide.** What Era 5 called certification
becomes geometry (§4); what it called a terminal dissolves into a
search that writes evidence (§3).

Two rules carry over unchanged:

> **Every implementation in the system — translator, interpreter,
> solver, checker — is generated, in Python. There are no existing
> tools inside the system.**

> **Structure only what the kernel must compute with; everything else
> is evidence for the LLM and stays prose.**

## 1. The two kinds

The registry holds exactly two primitive kinds. Everything else in
this specification — channels, pairs, evidence, grades, routes — is
derived from them; the kernel computes with the derived forms without
storing them as kinds.

**Language** = deterministic syntax (parser/validator) + deterministic
interpreter exposing named observables + declared **evidence schemas**
(§3). The interpreter is the system's only semantic device. The
**trusted base is the set of admitted judges** — interpreters and
evidence checkers — and nothing else; the kernel can print the base as
a list, each judge with the anchors and controls that corroborate it.
The base is a list, not a story.

- **Root languages**: the formats benchmarks arrive in. Their
  interpreters are the trusted floor — graded *stipulated* until
  corroborated by the domain's anchors (labels, supplied vectors).
- **Every other language** carries no parent taxonomy: a language is a
  language. Its interpreter is corroborated empirically by the squares
  of the pairs that connect it — and a language squeezed between two
  anchored neighbors, one square on each side against a different
  anchored interpreter, is corroborated from both sides at once, which
  no single pair can give.

**Transport** = a generated function on syntax between two languages.
Two disciplines, one kind:

- **total**: translation (`T`) and the carry-backs (`Λ`) — functions
  that must succeed on their declared fragment;
- **search** (`solve`): the one partial discipline — budget-indexed,
  deterministic given its budget, allowed to return `partial`. A route
  ends at exactly one search; hops compose, the stop happens once.

Every transport is untrusted, whatever it computes. A transport's
output never carries trust of its own — only the judgment it survives.

**Domain** = a root language together with its external anchors — the
two things the loop cannot generate for itself: the format questions
arrive in, and the ground truth (benchmark labels, supplied test
vectors, recorded testimony of outside oracles — §6) that corroborates
the root's interpreter. A benchmark lives in exactly one domain, and a
domain owns nothing else and fences nothing (§7).

## 2. Channels — the calculus of trust

A **channel** is one artifact kind, moved one direction across an edge
by an untrusted transport, validated by a named **arrival check** —
and a channel is exactly as trustworthy as its arrival check, nothing
more. Every arrival check is an interpreter run; there is no other
kind of check in the system.

| channel | carries          | flow | transport             | arrival check                                       |
|---------|------------------|------|-----------------------|-----------------------------------------------------|
| `prog`  | programs         | →    | `T.py`                | the square: both interpreters agree on `keeps`      |
| `wit`   | witness inputs   | ←    | `lam_wit.py`          | replay where the question lives (the kernel chains) |
| `obs`   | observable names | ←    | `maps` (+`lam_obs.py`)| checked against the carry-back per program          |
| `claim` | universal claims | ←    | `maps` + `bound_cap`  | **none — the checkless channel**                    |
| `cert`  | certificates     | ←    | `lam_cert.py`         | re-discharge by a checker where it lands            |
| `hint`  | seeds, candidates| →    | optional              | none needed: whatever it seeds is judged on arrival |

Three structural facts. The `claim` channel is the only one with no
executable and no check — pure declaration — which is exactly why it
cannot reset trust; the grade ladder (§4) is this table made visible.
`bound_cap` is a property of the two universal channels: an `all(inf)`
object crossing a hop that reifies an unrolling arrives as a bound-k
fact, invariant or not. And the `hint` channel is trust-inert by
construction — it can move cost, never a grade.

**Pair** = the transports that share one correspondence. The grouping
is not redundancy: a witness carried back by the `wit` transport of
one `T` and replayed against another `T`'s translation is nonsense;
the pair is precisely the statement that its channels are meaningful
together. The pair is the correspondence-as-text; its channels are the
correspondence in use. A pair declares `src`, `tgt`, `direction`
(exact / over / under), `keeps`, its channel set, measured cost per
channel, and lineage.

**The square is not a primitive**: it is the `prog` channel's arrival
check — two interpreter runs compared on kept observables, per corpus
program at admission. Witnesses cross back along exact and under
hops; universal objects cross back along exact and over; the
direction declares which channels may exist, and the square is the
empirical evidence for the direction claim. Per-program translation
correctness is *not* proved — the square checks it empirically, per
run, which remains the platform's founding economy.

**Certificate schemas belong to languages, not to searches.** For a
`cert` channel to exist, what a certificate looks like must be
declared where it lands: a schema is named at a language and shipped
with a generated checker (§3). A pair's `cert` channel then maps
schema to schema, per program, through the correspondence its `T`
already computes.

## 3. Evidence — the languages that carry their origins

For any language `L`, the **evidence language** `Evidence(L)` has
programs `(p, claim, payload)` — a program of `L`, a claim about its
interpretation, and the artifact that backs the claim — and an
interpreter that judges the payload against the claim. Evidence
languages are **induced, never written**: their interpreter is kernel
dispatch into admitted judges, adding no trusted code of its own.

- **Witness schemas are free for every language**: the payload is an
  input, the judge is `L`'s own interpreter — replay. No generated
  code at all. A fresh domain can therefore settle and fully certify
  existential questions on day one, with nothing but its root
  interpreter admitted.
- **Certificate schemas** are declared per language and shipped as
  generated checkers — `evidence/<schema>/check.py` inside the
  language entry — admitted like everything else: determinism,
  vectors, two-sided controls, including certificate mutants that must
  fail to discharge. Checkers are judges: part of the trusted base,
  and deliberately the simplest code in the system. Smallness of
  judges is the honesty metric.

**A search is a partial transport `L → Evidence(L)`** — what Era 5
called a terminal. It declares in `targets` which claims it can
write, and it *writes* evidence programs; it pronounces nothing. The
one node Era 5 left without an interpreter — the result target, where
"the square degenerates" — is gone: the graph is homogeneous, every
node interprets, every edge translates.

A result that decides its question is **settled**: a replayed witness,
or a universal claim covering the asked bound. A bare universal claim
— evidence with no certificate payload — is legal and floors at the
checkless grade (§4). This is intended selection pressure: the ladder
itself breeds certificate printers, because a search that writes
checkable payloads outgrades one that writes bare claims at the same
cost.

Question modes are not kernel vocabulary: `exists` is the witness
schema, `forall` is a universal schema, and a future mode — liveness,
resource bounds — is a new schema with a new checker, not a kernel
change.

**Origin-carrying languages** generalize this beyond results. A
product language — programs `(code, model, correspondence)`, its
interpreter running both sides in lock-step and treating divergence as
refusal — is an ordinary language under this specification; it makes
every play a square instance and gives view-switching searches
(execute the code, reason on the model) a lawful home. Products are
permitted and *earned*: they are (c)-moves in the conjecture order
(§8), reified only when hybrid wins keep repeating ad hoc.

## 4. Grades are geometry

Trust is computed, per evidence item, from where it was judged:

```
gap    = hops between the question and the last arrival check
         the evidence passed
grade  = certified   if gap = 0
         checked     if gap > 0
         claimed     if no arrival check ever ran
trust  = the meet (weakest link) of lineages over the gap
         segment only, plus the judge that ran
corroborated = disjoint-descent evidence agrees  (orthogonal flag)
```

**Each arrival check removes everything upstream of it from the
meet.** A certificate discharged at the stop's language removes the
search from a result's residual trust — the solver may be garbage; the
checker validated the object. Carried one hop back and re-discharged,
it removes that hop too. Discharged where the question lives, it
removes the route entirely: `certified` is route-independence, exactly
as before, now as the theorem `gap = 0`. The fail-safe direction is
definitional and universal: transport is untrusted, so a wrong or
adversarial carry-back can only lose a grade, never forge one.

Witnesses have a special property worth stating once: the kernel
always replays them where the question lives (chaining `wit` channels
across the route), so a witness is certified or it is not a result at
all — an unreplayable `sat` is evidence inside a `partial`, never an
answer. Their channel has never existed without its check.

A replayed witness is ground truth. If a question ever holds both a
replayed witness and a covering universal claim, the kernel records a
**contradiction event**, the witness stands, and the universal's
entire chain — evidence, checks, and every transport it crossed — is
marked falsified. Contradictions are never silently resolved.

Under the generation rule, lineage remains a declaration about descent
of generated procedures: two judges grown from the same ancestor never
corroborate each other, and the corroborated flag requires evidence
whose descent sets are disjoint. The second-order effect is intended:
whatever earns the top grades is what the autonomous loop learns to
build, so the frontier evidence itself pushes the LLM toward
certificate printers, certificate carry-backs, and independently
generated judges.

## 5. Routes, results, the frontier

A **question** is `(language, program, claim)`; a benchmark is a
pinned finite set of questions with recorded provenance (sha256 per
program, labels where they exist). A **route** is total hops, then the
stop: a composition of `prog` channels ending at one search. A route's
forward contract is the componentwise meet — fragments intersect,
`keeps` intersect, `bound_cap`s take the minimum, costs add — and its
backward reach is per channel: an artifact travels only as far as
every hop offers its channel, and its grade is computed from where it
last checked (§4), not from what the route promises. A **path** is one
play of a route on one question; the map and the frontier are stated
over paths — best path per question.

The result schema is fixed, with payloads drawn from evidence schemas:

```
result = { question, route, budget: {caps, spent},
           value: witness(w+)                 -- replayed: certified
                | all(bound: k | inf, cert?)  -- graded by its gap
                | partial(progress)           -- how far, where it failed
         , grade, gap, trust }
```

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
adjudication of an equally good path. Cost is recorded in every path
and never ranked; the player reads costs across routes to find the
cheap one and spends what that frees on open questions. Two
performance moves are new in this generation, and both are trust-free
because they are judged:

- **grade-raising replays**: carrying a stored certificate further
  back and re-discharging costs check time, not search time — the map
  can be re-graded without being re-solved, and a shrinking gap is a
  strictly improving best path under the ratchet; a revised judge
  re-derives the residual trust of a stored certificate the same way,
  and among equally good paths the board shows the latest
  adjudication, so a proof is always read under the judges the
  registry holds now;
- **hints**: a forward channel that can move minutes of search and not
  one grade.

**The ledger.** Cost says what a play spent; the ledger says what it
bought, in bits — profiling, not vocabulary: recorded in paths and
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
compression a certificate achieves over exhaustive checking —
infinite exactly at `bound: inf`. Channels then carry conversion
rates, measured on the pair's corpus at admission and recorded beside
cost: `prog` a dilution (bytes, and steps per source step), `wit` a
surprisal shift signed by the pair's direction (exact preserves `S`,
over can only lower it, under only raise it), `cert` an inflation,
`claim` a bound rescale. The ledger was piloted retroactively on the
fifth generation's logs before being written here: surprisal
stratified every witness by which searches could find it, and
clearance rate ordered every search family in one currency — with no
new trusted code, because every quantity is read off artifacts the
judges had already validated.

Every ledger quantity is also recorded **per search and per domain**:
questions settled and bits cleared, tabled on the board by the domain
the question lives in. A search grown on one domain that clears bits
on another is the measured form of the claim §7 makes — that
reasoning capabilities are properties of languages, not of the
domains they were grown in — and the dilution of the pair that
carried the questions there is that domain's exchange rate into the
hub. Both numbers are profiling: they move attention and budget,
never a grade.

**The frontier of a benchmark is the set of questions whose best path
is not settled**, each carrying that path and its progress evidence.
The registry and the log are append-only; best-per-question over an
append-only log is monotone: the ratchet is a property of the data
structure. **Expanding the frontier** means strictly improving some
question's best path — level, bound, grade, or gap; never cost.

**The capability frontier** is the same frontier read from the
registry's side. A search or a judge is a reasoning capability that
lives at one language; a root reaches it exactly when a route of
`prog` channels whose fragments admit its programs composes from the
root to that language. For every admitted domain's root and every
admitted search, the kernel can therefore say one of three things —
reaches it, by these routes; reaches it only for this fragment; or
does not reach it, and here is the one missing pair that would — and
that statement is a pure function of the registry, computed by the
routing the driver already performs. It is the platform's second
frontier: where the question frontier says which questions are open,
the capability frontier says which reasoning no domain can yet bring
to them. A missing pair on it is a conjecture, never a demand — the
registry records no obligations, and the conjecture order (§8) says
when the pair is the right next move.

The frontier is drawn, not only listed. Two renderings, both pure
functions of (registry, benchmark, log), both regenerating
byte-identically:

- **the board** (`frontier.md`): one row per question — its best
  graded path: result, grade, gap, residual trust, route, cost, and
  the best oracle's cost where the domain recorded one (§6) — and
  below the rows the reach matrix: every admitted root against every
  admitted search, each cell a route, a fragment, or the missing
  pair.
- **the graph** (`frontier.dot`): the whole registry drawn — every
  admitted domain's root, not only the benchmark's; languages as
  nodes, pairs as edges, searches as stops — with best paths overlaid.
  Grades being geometry, a missing channel is a visible conjecture:
  the dotted edge says which carry-back would move a grade, just as a
  dotted route says which pair would connect a stop — and a root
  drawn with no edge at all says which domain has not yet reached any
  reasoning.

Of the renderings above, the reach matrix, the oracle column, the
drawing of every admitted root, and the per-domain ledger table are
specified as of the 2026-09 consolidation and not yet drawn: the
kernel renders the board and graph of the first campaign, and
`HISTORY.md` names the rest as work. A specification that says so is
worded no stronger than what the tree does.

## 6. The generation rule

Every implementation is generated, in Python, and lives as committed
source inside its registry entry: the interpreter and checkers of
every language, every transport of every pair, every search. **No
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
The board then draws, per question, the best path's cost against the
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
built executable both in the entry — and only for the per-play
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

## 7. Two modes, and everything available to everyone

The system has exactly two modes of operation, and they share one
gate:

- **Automatic**: point the driver at a pinned benchmark; the LLM runs
  the loop (§8) autonomously — play, read the frontier, generate,
  admit, re-play — until a human pulls the plug.
- **Manual**: a human writes a registry entry directory and invokes
  the same admission (`python3 -m kernel.driver admit <entry-dir>`),
  or plays a benchmark by hand. Same operations, same gate, no
  special case.

Steering the system is only ever adding checked capability; results
are never written by hand in either mode.

**Availability is universal, and reuse is the cheap move.** The
registry is one space: every admitted language, pair, and search
serves every domain, including domains that look wholly unrelated to
the one an entry was grown in. A domain is only a root and its
anchors — it fences nothing. Routing stays honest under openness
because it is declarative — a route must compose `prog` channels
whose fragments admit the program, and its stop must target the
composed claim — so an absurd route can only produce a partial, never
a wrong answer, and junk never wins a route because the result order,
not arrival, picks the best path.

Openness is not merely permitted; the geometry makes it the cheapest
move there is. Searches and judges live at a few **hub languages** —
today the bit-vector transition systems of BTOR2; constraint
languages next — and a search at a hub is a reasoning capability:
bounded reachability, k-induction, property-directed reachability,
random simulation. **A domain enters a hub by one pair.** From the
moment its root's interpreter and one `prog` channel to a hub are
admitted, the domain owns every search at that hub: its existential
questions certify at gap 0 on day one, because replay needs no
generated judge; its universal claims arrive *checked* at gap 1, and
close to gap 0 the day the pair gains a `cert` channel by revision.
And because a search grown in another domain has, by construction, a
descent disjoint from anything grown in this one, routes through a
borrowed hub are also the cheapest source of the `corroborated` flag.
Whether a capability grown on hardware clears bits on a chemistry
corpus is not a hope but a ledger entry (§5), and the standing
experiment of the platform across domains is how few hubs suffice,
at what dilution. What a new domain costs is what it always cost —
its root's interpreter and its anchors — and the sciences supply both
the way the competitions did: a repository of models with known
answers, and the recorded testimony of the simulators and solvers
already trusted there, at the gate, never inside.

## 8. The loop, the conjecture order, and bootstrap from empty

The LLM is presented a benchmark and runs autonomously until a human
pulls the plug:

1. **Play**: for every question, run the admitted routes within
   budget; the kernel records results.
2. **Read the frontier**: the non-settled results with their profiles
   — and the grades: a map full of `claimed` and `checked` is itself
   frontier, since the gap is a dimension the ratchet moves on — and
   the capability frontier: which roots reach which searches, and the
   one pair each unreached search is missing.
3. **Conjecture**, in this order — semantics first, then syntax:
   - **(a) new judging and searching for existing languages** — a
     search, a certificate schema with its checker, an accelerator
     for a proven bottleneck: new reasoning first;
   - **(b) new transports** — pairs, and channels retrofitted onto
     admitted pairs by revision. Two (b)-moves are canonical in this
     generation: a `cert` carry-back added to a proven translation,
     and a `prog` channel from a root that reaches no hub to the
     nearest one — the entry move of every new domain, which outranks
     a domain-local search in this order because it inherits every
     search at the hub for the price of one translator (§7);
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
floor, graded *stipulated*; the anchors are its only corroboration),
then a first naive search in pure Python. The witness schema is
already there — replay needs no generated judge — so existential
questions can settle *certified* with a single admitted interpreter;
the first certificate schema and checker arrive when universal
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
   a channel each lose a grade and never gain one, and whatever a
   search writes about its own grade never reaches the record.
2. **The half that is mathematics is proved.** The Lean development
   under `kernel/mechanization/`, grown beside the code, proves for
   exactly the key of §5: the result order is a strict partial order
   (irreflexive, transitive, asymmetric); best-per-question is
   monotone under log append — the ratchet; once settled, always
   settled — the frontier never re-opens; at a fixed level and bound,
   the gap never grows and grades only move up the ladder, so a
   grade-raising replay, which keeps the value, is a strict
   improvement exactly when it moves either; and the trust meet is
   well-defined — the residual trust of a checked result is exactly
   the lineage union over its gap segment plus its judge — from which
   gap 0 rests on the judge alone (certified is route-independent as
   a theorem), every arrival check removes everything upstream of it,
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

- **language**: vectors interpret as expected against the anchors,
  and each shipped evidence checker discharges its example
  certificates and refuses its mutant ones;
- **pair**: **every declared channel round-trips** per corpus program
  — squares close, stimuli replay, certificates re-discharge — with
  mutants supplied per channel;
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
  registry.py runner.py results.py checker.py driver.py
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
    evidence/<schema>/   check.py, vectors/, controls/  (the judges)
  pairs/<src>--<tgt>/    manifest.json (channel set), T.py,
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
on every check. Manifests declare kind, the channel set with measured
cost per channel, direction, kept observables, lineage, budget schema,
`targets` on searches, optionally one `accelerator` (replaces `T.py`
or `solve.py`; source + built executable in the entry; admitted by
byte-agreement, §6), and optionally a proof obligation (§9). A search
may ship a `ledger.py` (§5) that reads the program and the value the
search wrote and reports what the play bought in bits; it is
trust-inert like `hint.py` — determinism is its whole gate — and what
it writes is recorded beside the path, never ranked, never a grade.

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
choice; predecessors stay in the tree; path records name the revision
they ran. Trust never transfers by assumption — a
revision that cannot agree is a different tool and must take a
different name. Adding a channel to an admitted pair is the intended
common case of revision: the old channels are the conserved surface,
the new channel is gated fresh.

## 11. Honesty rules

- The kernel never trusts a claim it can measure.
- The trusted base is a list, not a story: every judge printed with
  its anchors and controls; everything not on the list is untrusted
  syntax and named so.
- Every result states its grade, its gap, and what its residual trust
  rests on; nothing is worded stronger than what was verified.
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
- The capability frontier is a pure function of the registry; a
  missing pair on it is a conjecture, never a demand.
- Pruning the registry is a human act between runs; during a run the
  registry only grows.
- The kernel is generated too, and its trust is not a story either:
  proofs for what is mathematics, tests for what is operation, a
  second lineage's byte-agreement, and review — each claimed only as
  far as it verifies, and every disagreement between the two lineages
  settled in this specification, never papered over.
