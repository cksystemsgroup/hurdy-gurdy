# hurdy-gurdy

An LLM-driven explorer of the **frontier of reducible decidability in
practice**: present it a benchmark whose questions reduce to decision
procedures, and it plays every question along every feasible route,
grows itself by exactly what the open questions demand, and keeps —
as checked, durable artifacts — everything it learns along the way.
The deliverable is a **map**: per question its best path — result,
route, cost, and trust grade; and the **frontier** — the questions
not yet settled, each carrying the evidence of how far every route
got and where it failed. Both render from the log alone, as a graded
board (`frontier.md`) and a drawn graph (`frontier.dot`).

This tree is the platform's sixth generation — designed fresh from
the repository's initial commit and, since the 2026-09 consolidation,
the only generation on branch `main`, the five before it reachable in
its history and told in [`HISTORY.md`](./HISTORY.md): first the design
([`KERNEL.md`](./KERNEL.md)), then the **empty kernel** it specifies —
five small, stdlib-only Python modules, the only hand-written code,
with zero registered content — because in this generation everything
else is generated, and generated code is never trusted, only judged.
The defining separation:

> **Generation produces syntax; only interpretation produces truth.**

The previous generation's rule carries over — every implementation is
generated, in Python; no wrapped engines, no vendored binaries of
someone else's reasoning — and this generation finishes its thought.
There is exactly one semantic device, the interpreter, and exactly
one trust event, an interpreter run judging a transported artifact.
Every other executable — translator, carry-back, solver — is
untrusted syntax whose output faces a judge: **solvers do not decide;
they write. Interpreters decide.** The one architectural sentence
survives every generation, sharpened: **the LLM never writes a
result; only the kernel does, by running judges over transported
evidence.**

## How it works — one question, two routes

Everything the kernel does can be told as the story of one question.
Suppose a benchmark pins a C program `p` — a loop over values read
from the outside world, an assertion inside — and asks: *can the
assertion fail within twenty steps?* In this generation that sentence
is already formal. C is a **language**: a deterministic syntax plus a
generated, deterministic interpreter `I_C` exposing named
**observables** — here `bad`, whether an assertion failed, and
`depth`, how many statements have run — plus the evidence schemas it
can judge. Interpreters and certificate checkers are the **judges**,
and the **trusted base is exactly the set of admitted judges**: a
list the kernel can print, not a story. The question
`(c, p, exists bad within 20)` lives at C, and every grade it will
ever receive is a distance from that home. The benchmark itself
enters as a **domain**: a root language plus its external anchors
(labels, supplied vectors) — the ungenerable half, and all that
entering a new domain costs. Anchors may include the recorded
testimony of an **oracle** — an existing compiler or solver consulted
from outside at admission time, corroborating a judge the way a
benchmark label does, never entering the trusted base, never running
inside a play: oracles, not organs.

**Route one: C → BTOR2.** No search reasons about C directly; the
model-checking searches live at BTOR2, a language of bit-vector
machines. What connects the two languages is a **pair** — one
correspondence, written down as generated code: a translator `T` that
turns the elaborated control flow of `p` into a machine, one
statement one transition, `bad` a predicate on machine state; and
carry-back maps `Λ` for whatever will need to come home. Every such
function is a **transport**: untrusted syntax, whatever it computes,
however it was generated. The unit of the trust calculus is the
**channel** — one artifact kind, moved one direction by an untrusted
transport, validated by a named **arrival check**, always an
interpreter run. The program `T(p)` crosses the `prog` channel, and
its arrival check is the **commuting square**, closed per corpus
program by running both interpreters:

```text
                 translate  (T)
   source ───────────────────────▶ target
     │                                │
   source                          target
 interpreter (I_s)              interpreter (I_t)
     ▼                                ▼
   source' ◀─────────────────────── target'
            carry back  (Λ)

   I_s(p)  ≡_π  Λ( I_t( T(p) ) )      for every corpus program p
```

The horizontal arrows are untrusted syntax; the vertical arrows are
the judges; nothing horizontal is ever believed until something
vertical has run. A wrong translator — buggy, lazy, adversarial —
does not produce wrong results; it loses squares and is refused at
the gate. Admission also measures what the crossing costs: the pair's
**dilution** — target bytes per source byte, machine steps per source
step — recorded in the manifest beside cost, part of the ledger
below.

**At the stop.** The route ends where evidence is written: a
**search**, the one *partial* transport, `L → Evidence(L)` — budgeted
and allowed to return an honest `partial` (how far it got, where it
failed). For any language `L`, `Evidence(L)` is the induced evidence
language: programs `(program, claim, payload)` judged by kernel
dispatch into `L`'s admitted judges — induced, never written, no new
trusted code. The searches at BTOR2 are generated solvers — random
simulation, bounded model checking, k-induction, IC3; the fifth
generation's BDD reachability is named work — and none of them is
believed. Three kinds of evidence can come back down the route.

*A witness.* The failing input sequence crosses the `wit` channel —
`Λ` renames machine stimuli back to the input sites of `p` — and its
arrival check is **replay**: `I_C` runs `p` on it where the question
lives. The **gap** — hops between the question and the last arrival
check its evidence passed — is zero, and gap zero is the top grade,
**certified**: route-independent as a theorem, not a definition. No
generated code can corrupt it — a wrong solver, carry-back, or
translator all fail the same way, by not producing a stimulus that
replays. Witness schemas are free for every language, because the
judge is the interpreter itself; a fresh domain certifies
existentials on day one.

*A bare universal claim.* "No failure within bound k" crosses the
`claim` channel — **the checkless channel**, pure declaration, which
is exactly why it cannot reset trust. Its grade floors at
**claimed** — intended selection pressure that breeds certificate
printers.

*A certificate.* A k-induction kernel or a clause invariant crosses
`cert`, and its arrival check is **re-discharge** by the checker of
the language where it lands — generated judges, deliberately the
simplest code in the system; smallness of judges is the honesty
metric. Discharged at BTOR2, the claim grades **checked**: gap one,
residual trust the weakest-link **meet** over the segment the
evidence has not cleared. Discharged at C — once the pair learns to
carry the certificate itself home — the gap closes and the claim is
**certified**. **Each arrival check removes everything upstream of it
from the meet**: grades are geometry, not bookkeeping. And if a
replayed witness ever stands beside a covering universal claim, that
is a recorded **contradiction**, never silently resolved — the
witness stands, and the universal's entire lineage is marked.

**Route two: C → RISC-V → BTOR2.** The same question also travels a
longer way: compiled to RISC-V — a language whose interpreter *is*
execution of real machine code, so reasoning can happen directly on
the executable whenever that is the faster place — then encoded to
BTOR2. Pairs compose into a **route**; its forward contract is the
componentwise meet — the weakest hop on every axis — so a compiler
hop that keeps only `bad` (optimization does not preserve statement
counts) makes the whole route a `bad`-only route, and a bound in
machine transitions comes home rescaled by the recorded dilution:
several instructions per statement is the exchange rate, measured at
admission. What the longer route buys is trust: its generated descent
shares nothing with route one — different translators, different
lineage — so agreement between the two earns the **corroborated**
flag, and RISC-V itself, squeezed by squares against anchored
neighbors on both sides, is corroborated from both directions at
once. What it also buys is performance. A **path** is one play of a
route on one question, logged with result, grade, gap, and cost; cost
is recorded and never ranked, and the player reads it to decide where
the next budget goes. Three moves raise performance without touching
trust: **grade-raising replays** — re-discharging a stored
certificate closer to home costs check time, not search time, so the
map is re-graded without being re-solved; **hints** — a forward
channel that can move minutes of search and not one grade; and
**accelerators** — *syntax may accelerate, semantics never does*: the
per-play transports `T` and `solve` may earn regenerated
implementations in a performance-oriented language, admitted only by
byte-agreement beside their Python reference, and judges always run
the reference.

All of this is now in the tree. The first campaign admitted, through
that one gate and in this order: the hardware domain with its
anchors; the BTOR2 interpreter — the trusted floor; the naive
explicit-state search, which settled six of seventy-four HWMCC'24
questions with nothing but replay; bounded model checking with its C
mirror byte-agreed; the software domain and the C interpreter; the
RISC-V interpreter as the middle vertex, anchored by no domain and
corroborated only by its pairs' squares; the pairs C→BTOR2, C→RISC-V,
and RISC-V→BTOR2, each with `prog`, `wit`, `obs`, and `claim`
channels, per-channel mutants, and its dilution measured; then two
certificate schemas on BTOR2 — `induction` and `clauses`, judges
re-checking bit-invariants, k-induction, and IC3's clause invariants
from scratch — with the two searches that write them. Every entry is
a directory under `registry/` carrying its admission stamp; the
boards under `runs/` are what the plays found. The story above is
what the design guarantees from the moment each entry passes the
gate, and the trusted base at any moment is one command away:
`python3 -m kernel.driver base`.

Where the boards stand after the first campaign (2026-08-30, wall
60 s per route on hardware, 30 s on software, every route played
every iteration): **hwmcc24-mini 43 of 74 settled** — 14 universal
answers *certified* at gap 0 by BTOR2's own judges, the searches that
found them no longer in the trust set, among them one question no
competitor solved; 9 witnesses certified by replay; the rest bounded
claims with their cleared bits on the ledger. **svcomp25-mini 26 of
79 settled** — 14 witnesses certified at the C level, 12 of which
also walked home across both bridges of the triangle; 3 universal
answers first *checked* at gap 1 — k-induction certificates
discharged one hop from home — and then, once C shipped its own
`induction` judge and the C→BTOR2 pair gained a `cert` channel by
revision, lifted to *certified* at gap 0 by `regrade` alone, without
re-solving anything, in half a second each — and then, when C's judge
was revised to build its machine by the RISC-V road (front end →
fenced RV64 blocks → transition system, no text shared with the
C→BTOR2 encoding), re-judged again by `regrade` so that their
residual trust no longer names the road the evidence travelled; then
the judges and the certifying search learned the bounded checker's
array reasoning — the eager reduction with its congruence and
extensionality lemmas — and a fourth proof, about a C program with a
2048-element array, was found k-inductive, discharged at BTOR2,
carried home, and certified at C with every array a state of its own;
no contradiction anywhere; no `+corroborated` flag either, and honestly
so: every route shares the C front end and one generator, and the
flag is reserved for disjoint descent.

## The ledger

Cost says what a play spent; the **ledger** says what it bought — in
bits. Three quantities, all computed from artifacts the judges have
already validated, all profiling: recorded, never ranked, able to
move attention and budget but never a grade. **Witness surprisal**
`S` = −log₂ of the chance that a random stimulus is a witness: every
failed random trial tightens a lower bound for free, an exact count
is a lawful by-product of a BDD search, and `S` separates the two
ways a question can be open — evidence rare (a needle, symbolic work
required) versus searches weak (low `S` and still unsettled).
**Cleared bits** `B(k)` — the log-size of the stimulus space a
bound-k universal claim exhausts — make `B` per second a single
clearance currency across every search family, concrete or symbolic.
**Certificate length** `L` — compressed size under a pinned
compressor — makes `B/L` the compression a proof achieves over
exhaustive checking, infinite exactly at `bound: inf`: the
information-theoretic reading of why certified unbounded facts are
the crown jewels. Each channel then carries a conversion rate,
measured on the pair's corpus at admission: `prog` a dilution, `wit`
a surprisal shift whose sign is the pair's direction — exact
preserves `S`, over-approximation can only lower it, under- only
raise it — `cert` an inflation, `claim` a bound rescale.

The ledger was piloted retroactively on the fifth generation's logs
before being written into the design. On a hardware benchmark, the
bugs random simulation could find sat at `S` ≈ 1–4 bits and every
search family found them; the rest lay beyond the sampler's reach
(`S` ≥ 12–16, lower-bounded by its logged failures), and five of
those only the accelerated bounded model checker ever hit — the
finder set shrinks as surprisal rises. Median clearance rates ordered
the search families in one currency: accelerated BMC near 7,000
bits/s, its reference near 900, IC3 near 180, k-induction near 150,
BDD near 40. K-induction certificates of 272 bits cleared infinite
stimulus space. And the C-to-BTOR2 crossing measured 2.7× in raw
bytes and 2.5× compressed: a machine genuinely carries about two and
a half times the description of its program, even after compression
strips the boilerplate.

Existing tools testify in the same currency. The per-question
verdicts and wall times a competition archive publishes, and one
calibration run of the pinned oracle bench (`oracles/bench/`) on the
host that plays, enter a domain's anchors beside its labels, to be
drawn on the board beside every best path — ours against the state
of the art, recorded and never ranked, the oracle never inside the
seal (KERNEL.md §6). Where a generated judge and an oracle disagree,
the dispute is recorded and adjudicated in the open, and the anchor
counts for nothing until it is. As of the 2026-09 consolidation this
is specified and not yet drawn: no domain records performance
testimony yet, and the board has no oracle column — named work in
HISTORY.md.

## Growing and operating

A domain owns nothing beyond its root and anchors: **every admitted
language, pair, and search serves every domain**, however unrelated
the domains look — the gate, not topical relatedness, is the only
membership test. Two modes of operation, same gate, no special case.
*Automatic*: point the driver at a pinned benchmark and the LLM runs
the loop — play, read the frontier, conjecture (semantics first: new
judging and searching, then new transports, then new languages),
generate the implementation in Python, pass it through the gate,
re-play — until a human pulls the plug, which is safe at any moment
because the log is append-only and best-per-question only ever
improves. *Manual*: write a registry entry directory and run
`python3 -m kernel.driver admit <entry-dir>`; the kernel adjudicates
through the same gate and stamps the evidence, or refuses and stamps
nothing. Results are never written by hand in either mode.

Openness is the cheap move, not only a permission. The searches live
at **hub languages** — today BTOR2 — and each is a reasoning
capability: bounded reachability, k-induction, IC3, random
simulation. A new domain enters a hub by **one pair**: the moment its
root's interpreter and one translation to the hub are admitted, it
owns every search there — its existential questions certify on day
one by replay, its universal claims arrive *checked* one hop from
home and close to *certified* when the pair learns to carry
certificates. A capability grown on hardware that clears bits on a
chemistry corpus is a ledger entry, not a hope; the board's reach
matrix — specified in KERNEL.md §5, not yet drawn by the kernel —
says which roots reach which searches and which single pair would
connect the rest; and the standing experiment across domains is how
few hubs suffice, at what dilution. Entering the sciences
costs what entering hardware and software cost — a root interpreter
and anchors — and the sciences supply anchors the way the
competitions did: model repositories with known answers, and the
recorded testimony of the simulators and solvers already trusted
there. Boolean networks are bit-vector transition systems already;
reaction networks are Petri nets with a bounded-counter fragment and
an over-approximating pair beyond it; hybrid systems discretize into
fixed-point machines, or ask for the first constraint hub with a
generated real-arithmetic search.

The kernel ships with zero languages, zero transports, zero domains.
On a fresh benchmark the first admissions are the domain (root +
anchors), the root's interpreter, and a first naive search in pure
Python — and because the witness schema needs no generated judge,
existential questions certify from that moment; the first certificate
checker arrives when universal questions need better than `claimed`.
The naive generated search is not a stopgap but the first citizen,
and every later power move improves on a working, admitted baseline.

## About the name

A hurdy-gurdy is a string instrument whose player cranks a mechanical
wheel; the wheel sounds the strings — paired as drone and melody —
and a keyboard of tangents deterministically sets the pitch. The
player chooses *what* to play; the mechanism turns that choice into
sound the same way every time. A **pair** is a drone+melody pairing;
the **translator** is the keyboard — same key, same pitch; the
**interpreters** are the wheel that makes the sound real; the
**player** — LLM or human — decides what to ask. One generation added
the crank: the loop turns until the player stops. The next built the
instrument in its own workshop: every part cut, checked, replaceable.
This generation tunes the trust to the mechanism itself: only the
wheel sounds — keys, tangents, and the player's hand merely position
the strings, and no note is true until the wheel has turned over it.

## Layout

```
kernel/          the fixed, hand-written part: five stdlib-only
                 Python modules (KERNEL.md §10) and, under
                 mechanization/, the Lean seed of its proofs (§9)
registry/        generated content, append-only, every entry stamped
                 by the gate: domains/ (hardware, software),
                 languages/ (btor2 and c with their evidence/
                 judges — c's built by the RISC-V road — and riscv),
                 pairs/ (c--btor2 with a cert channel,
                 c--riscv, riscv--btor2),
                 searches/ (btor2-sim, -bmc, -ind, -ic3); revisions
                 as sibling entries <name>@<r>
runs/<name>/     pinned benchmark, append-only log, board + graph
                 (hwmcc24-mini: 74 questions; svcomp25-mini: 79;
                 hwmcc24-arrays: 55 and hwmcc24-mid: 80, pinned,
                 not yet played in this generation)
oracles/         outside the executable surface: bench/ — the pinned
                 image of the tools that testify at admission and
                 never run in a play; packs/ — recorded testimony
                 (vectors, corpora, verdicts with provenance) for
                 languages the loop has yet to regenerate
paper/, video/   the papers, their results and mechanization, and the
                 explainer; each names the era it describes
KERNEL.md        the design: the two kinds, channels, evidence,
                 grades as geometry, the ledger, the gate, the modes
POTENTIAL.md     what owning every implementation is worth beyond
                 trust: instruments, conjectures, seams, oracles
HISTORY.md       the six generations, and where each retired part
                 still lives
```

## Run

```sh
python3 -m kernel.driver admit   <entry-dir>  # the gate (manual mode)
python3 -m kernel.driver play    runs/<name>  # one iteration over a benchmark
python3 -m kernel.driver regrade runs/<name>  # re-discharge stored certificates
python3 -m kernel.driver report  runs/<name>  # pure log -> frontier.md
python3 -m kernel.driver graph   runs/<name>  # pure log -> frontier.dot
python3 -m kernel.driver base                 # print the trusted base
```

The kernel is five stdlib-only modules under `kernel/`, the only
hand-written code; everything under `registry/` was generated and
admitted, and every command answers honestly from any state — from
emptiness (`play` books every question as an open `partial`, `base`
prints zero judges) to the campaign as it stands. Searches may ship a
trust-inert `ledger.py` whose report — bits bought, never a grade —
is recorded beside every path and tabled on the board.

## Lineage

Hurdy-gurdy descends from rotor, originally developed as part of
selfie ([github.com/cksystemsteaching/selfie](https://github.com/cksystemsteaching/selfie),
`tools/rotor.c`), generalizing its one fixed translation into a
growing, gated graph of them. Five prior generations precede this
one, all in this branch's history since the 2026-09 consolidation —
the pair calculus, the instrument and its papers, the frontier
program, the Era-4 kernel (last state at tag `era4-final`), and the
fifth generation that first generated everything (tag `era5-final`),
whose last discovery forced this design: witnesses crossed the bridge
home, proofs could not. The genealogy, and where everything retired
still lives, is [`HISTORY.md`](./HISTORY.md). This generation
restarted from the initial commit on purpose — a generation that
trusts nothing but interpretation should begin from a tree with
nothing to interpret — and was merged back onto `main` with its whole
history once its first campaign closed.

This work was co-funded by the Czech Science Foundation under Grant
No. 23-07580X and the European Union under the project Robotics and
Advanced Industrial Production (reg. no.
CZ.02.01.01/00/22_008/0004590).
