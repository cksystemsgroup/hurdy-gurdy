# Kernel — hurdy-gurdy judged whole

This document is the vision and the specification of the platform's
sixth generation, begun 2026-08-20 **from the initial commit**: the
tree behind this file contains a LICENSE and this specification —
nothing else; the kernel it specifies is the next commit and the only
hand-written code there will be. The generation before it (Era 5 on
branch `v5`) proved the founding rule — every implementation
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
kernel orders on (bound reached, budget spent) plus free-form progress
description and profiling, because its reader is the LLM.

Results order per question: `partial < all(k) below the asked bound <
settled`; within a level, higher bound, then higher grade rung, then
smaller gap. Cost is recorded in every path and never ranked; the
player reads costs across routes to find the cheap one and spends what
that frees on open questions. Two performance moves are new in this
generation, and both are trust-free because they are judged:

- **grade-raising replays**: carrying a stored certificate further
  back and re-discharging costs check time, not search time — the map
  can be re-graded without being re-solved, and a shrinking gap is a
  strictly improving best path under the ratchet;
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

**The frontier of a benchmark is the set of questions whose best path
is not settled**, each carrying that path and its progress evidence.
The registry and the log are append-only; best-per-question over an
append-only log is monotone: the ratchet is a property of the data
structure. **Expanding the frontier** means strictly improving some
question's best path — level, bound, grade, or gap; never cost.

The frontier is drawn, not only listed. Two renderings, both pure
functions of (registry, benchmark, log), both regenerating
byte-identically:

- **the board** (`frontier.md`): one row per question — its best
  graded path: result, grade, gap, residual trust, route, cost.
- **the graph** (`frontier.dot`): the registry drawn — languages as
  nodes, pairs as edges, searches as stops — with best paths overlaid.
  Grades being geometry, a missing channel is a visible conjecture:
  the dotted edge says which carry-back would move a grade, just as a
  dotted route says which pair would connect a stop.

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

Enforcement is layered, and worded no stronger than what each layer
verifies: **statically**, there is no manifest field for pointing at a
tool; **dynamically**, the runner is sealed — every registered
executable runs in its own process with an empty environment, a
temporary working directory, and a wall cap, and every check runs
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

**Availability is universal.** The registry is one space: every
admitted language, pair, and search serves every domain, including
domains that look wholly unrelated to the one an entry was grown in. A
domain is only a root and its anchors — it fences nothing. Routing
stays honest under openness because it is declarative — a route must
compose `prog` channels whose fragments admit the program, and its
stop must target the composed claim — so an absurd route can only
produce a partial, never a wrong answer, and junk never wins a route
because the result order, not arrival, picks the best path.

## 8. The loop, the conjecture order, and bootstrap from empty

The LLM is presented a benchmark and runs autonomously until a human
pulls the plug:

1. **Play**: for every question, run the admitted routes within
   budget; the kernel records results.
2. **Read the frontier**: the non-settled results with their profiles
   — and the grades: a map full of `claimed` and `checked` is itself
   frontier, since the gap is a dimension the ratchet moves on.
3. **Conjecture**, in this order — semantics first, then syntax:
   - **(a) new judging and searching for existing languages** — a
     search, a certificate schema with its checker, an accelerator
     for a proven bottleneck: new reasoning first;
   - **(b) new transports** — pairs, and channels retrofitted onto
     admitted pairs by revision: a `cert` carry-back added to a
     proven translation is the canonical (b)-move of this generation;
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
every later power move improves on a working, admitted baseline.

**Plug-pull** is safe at any moment: the driver appends every result
and registration as it happens, and the exit deliverables are pure
functions of the log — the board and the graph with the delta since
iteration zero, and, if the frontier moved, the evolved hurdy-gurdy:
the kernel unchanged plus everything registered, with admission
evidence. The next benchmark starts from it.

## 9. What the kernel proves

The kernel is the fixed part and the only hand-written code; it is
small on purpose (readable in an afternoon). Its load-bearing
properties are stated here and are the standing mechanization
obligation (a Lean development under `kernel/mechanization/`, grown
beside the code):

- the result order is a strict partial order (irreflexive,
  transitive, asymmetric);
- best-per-question is monotone under log append (the ratchet);
- once settled, always settled (the frontier never re-opens);
- per question, the gap never grows and grades only move up the
  ladder;
- the trust meet is well-defined: every evidence item's residual
  trust is exactly the lineage meet over its gap segment plus its
  judge.

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
  negative controls must fail, budget determinism must hold.

An entry that fails leaves no stamp and no trace in routing.

```
kernel/                  the fixed part (stdlib-only Python)
  registry.py runner.py results.py checker.py driver.py
  mechanization/         Lean: the kernel's proved properties (§9)
registry/                generated content, append-only
                         (revisions as sibling entries <name>@<r>)
  domains/<name>/        manifest.json (root + anchors)
  languages/<name>/      manifest.json, interp.py, vectors/, controls/
    evidence/<schema>/   check.py, vectors/, controls/  (the judges)
  pairs/<src>--<tgt>/    manifest.json (channel set), T.py,
                         lam_wit.py?, lam_obs.py?, lam_cert.py?,
                         corpus/, controls/
  searches/<name>/       manifest.json (targets), solve.py,
                         corpus/, controls/
runs/<benchmark>/        benchmark.json (pinned), log.jsonl (append-
                         only), frontier.md + frontier.dot
```

Every registered executable is a pure deterministic CLI — bytes in,
bytes out — run sealed (own process, **empty environment**, temp
working directory, wall cap) and run twice with byte-compared output
on every check. Manifests declare kind, the channel set with measured
cost per channel, direction, kept observables, lineage, budget schema,
`targets` on searches, optionally one `accelerator` (replaces `T.py`
or `solve.py`; source + built executable in the entry; admitted by
byte-agreement, §6), and optionally a proof obligation (§9).

**Revision, not mutation.** An admitted entry is never edited: every
stamp pins the entry's bytes (a content hash the loader re-verifies —
an admitted entry whose bytes changed is a hard error), and the log's
citations mean those bytes forever. Extension arrives as a new entry
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
admitted revision; predecessors stay in the tree; path records name
the revision they ran. Trust never transfers by assumption — a
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
- Pruning the registry is a human act between runs; during a run the
  registry only grows.
