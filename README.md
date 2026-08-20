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

This tree is the platform's sixth generation, designed fresh from the
repository's initial commit: first the design
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

## How it works

**Languages and domains.** A language is a deterministic syntax plus
a generated, deterministic interpreter exposing named observables,
plus the **evidence schemas** it can judge. The interpreter is the
system's only semantic device, and the **trusted base is the set of
admitted judges** — interpreters and certificate checkers — and
nothing else: a list the kernel can print, each judge with the
anchors and controls that corroborate it. The base is a list, not a
story. Root languages (the formats benchmarks arrive in) are
stipulated until corroborated by their domain's anchors; every other
language needs no parent taxonomy — it is corroborated empirically by
the commuting squares of the pairs that connect it, and a language
squeezed between two anchored neighbors is corroborated from both
sides at once. A **domain** is a root language plus its external
anchors (labels, supplied vectors) — the ungenerable half, and all
that entering a new domain costs. A domain owns nothing beyond that:
**every admitted language, pair, and search serves every domain**,
however unrelated the domains look — the gate, not topical
relatedness, is the only membership test.

**Transports and channels.** Everything that is not a language is a
**transport**: a generated function on syntax between two languages —
translators, carry-backs, and searches. All transports are untrusted,
whatever they compute; a transport's output never carries trust of
its own, only the judgment it survives. The unit of the trust
calculus is the **channel**: one artifact kind, moved one direction
by an untrusted transport, validated by a named **arrival check** —
always an interpreter run, the only kind of check in the system.
There are six: `prog` carries programs forward, checked by the
square; `wit` carries witnesses back, checked by replay; `obs`
carries observable names back; `claim` carries universal claims back
and is **the checkless channel** — pure declaration, which is exactly
why it cannot reset trust; `cert` carries certificates back, checked
by re-discharge; `hint` carries seeds forward and is trust-inert by
construction — it can move cost, never a grade. A **pair** is the
transports that share one correspondence: the pair is the
correspondence-as-text, its channels are the correspondence in use.
And the **commuting square** — every prior generation's correctness
statement — is not a primitive here but the `prog` channel's arrival
check, closed per program by running both sides:

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

Read with this generation's eyes, the square shows the whole design
in one picture: the **horizontal arrows are untrusted syntax, the
vertical arrows are the judges**, and nothing horizontal is ever
believed until something vertical has run. Every other channel
repeats the same shape in its own direction — a witness crosses
`wit` right to left and is judged by replay through `I_s`; a
certificate crosses `cert` and is judged by re-discharge at the
language where it lands; only `claim` crosses with no vertical arrow
waiting for it, which is exactly the grade it keeps.

**Evidence and searches.** For any language `L`, the induced evidence
language `Evidence(L)` has programs `(program, claim, payload)` and
an interpreter that judges the payload against the claim — induced,
never written: kernel dispatch into admitted judges, no new trusted
code. Witness schemas are free for every language (the judge is the
interpreter itself — replay), so a fresh domain can settle and fully
certify existential questions on day one. Certificate schemas ship
per language as generated checkers — judges, deliberately the
simplest code in the system; smallness of judges is the honesty
metric. A **search** is the one partial transport, `L → Evidence(L)`,
budgeted and allowed to return an honest `partial` — what earlier
generations called a terminal, minus the pronouncements: it *writes*
evidence programs. Bare universal claims are legal and floor at the
checkless grade — intended selection pressure that breeds certificate
printers.

**Grades are geometry.** A result's grade is the distance between its
question and the place its evidence last passed an arrival check: the
**gap**. Certified means gap zero — route-independent, as a theorem
rather than a definition; checked means the evidence validated some
hops away, with residual trust the weakest-link meet over the gap
segment plus the judge that ran; claimed means no check ever ran.
**Each arrival check removes everything upstream of it from the
meet** — a certificate discharged at the stop unburdens the result of
its solver; discharged where the question lives, of the entire route.
Witnesses are always replayed where the question lives, so a witness
is certified or it is not a result at all. A replayed witness beside
a covering universal claim is a recorded **contradiction**, never
silently resolved; *corroborated* (disjoint generated descent agrees)
remains an orthogonal flag.

**Routes, paths, trust, and performance.** Pairs compose into routes
ending at one search; a route's forward contract is the componentwise
meet — the weakest hop on every axis — and its backward reach is per
channel: an artifact travels only as far as every hop offers its
channel, and grades come from where evidence actually checked, never
from what the route promises. A **path** is a route played on one
question, logged with result, grade, gap, and cost. Trust rises by
playing routes that check closer to the question or carry disjoint
descent. Performance rises by cheaper routes read from recorded
costs, by **grade-raising replays** — carrying a stored certificate
further back and re-discharging costs check time, not search time, so
the map can be re-graded without being re-solved — by **hints**, and
by **accelerators**: *syntax may accelerate; semantics never does.*
The per-play transports `T` and `solve` may each earn a regenerated
implementation in a performance-oriented language, admitted only
beside the Python reference and only by byte-agreement with it,
per-program specialization included; judges always run the reference.

**Two modes of operation.** *Automatic*: point the driver at a pinned
benchmark and the LLM runs the loop — play, read the frontier,
conjecture (semantics first: new judging and searching, then new
transports, then new languages), generate the implementation in
Python, pass it through the gate, re-play — until a human pulls the
plug, which is safe at any moment because the log is append-only and
best-per-question only ever improves. *Manual*: write a registry
entry directory and run `python3 -m kernel.driver admit <entry-dir>`;
the kernel adjudicates through the same gate and stamps the evidence,
or refuses and stamps nothing. Same operations, same gate, no special
case; results are never written by hand in either mode.

**From empty.** The kernel ships with zero languages, zero
transports, zero domains. On a fresh benchmark the first admissions
are the domain (root + anchors), the root's interpreter, and a first
naive search in pure Python — and because the witness schema needs no
generated judge, existential questions certify from that moment; the
first certificate checker arrives when universal questions need
better than `claimed`. The naive generated search is not a stopgap
but the first citizen, and every later power move improves on a
working, admitted baseline.

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
                 Python modules (KERNEL.md §10); ships empty of content
registry/        generated content, append-only — does not exist yet:
                 domains/, languages/ (each with its evidence/ judges),
                 pairs/, searches/ appear as the loop (or a human)
                 admits entries through the gate
runs/<name>/     pinned benchmark, append-only log, board + graph
KERNEL.md        the design: the two kinds, channels, evidence,
                 grades as geometry, the gate, the modes
```

## Run

```sh
python3 -m kernel.driver admit  <entry-dir>   # the gate (manual mode)
python3 -m kernel.driver play   runs/<name>   # one iteration over a benchmark
python3 -m kernel.driver report runs/<name>   # pure log -> frontier.md
python3 -m kernel.driver graph  runs/<name>   # pure log -> frontier.dot
```

The kernel is the next hand-written commit; from the moment it lands,
every command works and answers honestly from emptiness: `play` books
every question as an open `partial` (no route: no admitted search),
and the board and graph draw the frontier as everything. That is the
intended starting state — see KERNEL.md §8, bootstrap from empty.

## Lineage

Hurdy-gurdy descends from rotor, originally developed as part of
selfie ([github.com/cksystemsteaching/selfie](https://github.com/cksystemsteaching/selfie),
`tools/rotor.c`), generalizing its one fixed translation into a
growing, gated graph of them. Five prior generations precede this
one: four on branch `main` — the pair calculus, the instrument and
its papers, the frontier program, and the Era-4 kernel — with the
full genealogy in `HISTORY.md` there, and the fifth on branch `v5`,
the generation that first generated everything, whose last discovery
forced this design: witnesses crossed the bridge home, proofs could
not. This branch restarts from the initial commit on purpose: a
generation that trusts nothing but interpretation should begin from a
tree with nothing to interpret.

This work was co-funded by the Czech Science Foundation under Grant
No. 23-07580X and the European Union under the project Robotics and
Advanced Industrial Production (reg. no.
CZ.02.01.01/00/22_008/0004590).
