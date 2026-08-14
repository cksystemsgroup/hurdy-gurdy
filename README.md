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

This tree is the platform's fifth generation, designed fresh from the
repository's initial commit. It contains the design ([`KERNEL.md`](./KERNEL.md))
and the **empty kernel** — five small, stdlib-only Python modules and
zero registered content — because in this generation everything else
is generated. The defining rule:

> **Every implementation — translator, interpreter, solver,
> certifier — is generated, in Python. There are no existing tools
> inside the system.**

No wrapped engines, no vendored binaries of someone else's reasoning.
The system owns its endpoints: every step it trusts is source it can
read, run, mutate, and re-derive — admitted through one gate, on
evidence. Performance-critical translation and solving may earn an
**accelerator** in a performance-oriented language, admitted only
beside its Python reference and only by byte-agreement with it; the
reference remains the semantics, and the check itself is never
accelerated. The one architectural sentence survives every
generation: **the LLM never writes a result; only the kernel does,
by running checked code.**

## How it works

**Languages and domains.** A language is a deterministic syntax plus
a generated, deterministic interpreter exposing named observables.
Root languages (the formats benchmarks arrive in) are the trusted
base; derived languages enter only together with a pair to a parent,
so they add nothing to it. A **domain** is a root language plus its
external anchors (labels, supplied vectors) — the ungenerable half,
and all that entering a new domain costs, since the loop bootstraps
everything else from empty. A domain owns nothing beyond that:
**every admitted pair and terminal is available to every domain**,
however unrelated the domains look — the gate, not topical
relatedness, is the only membership test, and what the kernel has to
offer is left open for discovery.

**Pairs.** The translation unit is the **pair**: source language,
target, a pure translator `T`, a carry-back map `Λ`, and declared
kept observables `π`, closing a directional commuting square checked
per program by running both sides. The square commuting *is* the
pair's correctness statement; a failure localizes to a step and an
observable.

**Terminals.** A route ends at a **terminal** — the place of actual
model reasoning, where syntax becomes a verdict. A terminal bundles a
generated **solver** (program + question + budget → witness,
universal claim with optional certificate, or an honest `partial`)
with its generated **certifiers** (`Λ` to carry witnesses back for
replay; `discharge` to interpret certificates against the problem).
Terminals inherit the whole solver-pair discipline of the previous
generation — witnesses must replay, certificates must discharge,
mutants must fail, determinism must hold — through the same gate as
everything else.

**Routes, paths, trust, and performance.** Pairs compose into routes
ending in a terminal; a route's contract is the componentwise meet —
the weakest hop on every axis — so a label never overstates. A
**path** is a route played on one question, logged with result,
grade, and cost. Playing another route is how both exploration axes
work: a disjoint-lineage or source-discharging route raises trust; a
cheaper route — or an admitted accelerator on the bottleneck hop —
raises performance, read from recorded costs; and the result order
guarantees an added play never worsens the map.

**Certification.** A witness is carried back and **replayed** through
the source interpreter — route-independent, unforgeable by a wrong or
adversarial pair. A universal claim grades on the strict ladder
*claimed < checked (certificate discharged at the target; route trust
rides along) < certified (discharged at the source;
route-independent)* — with *corroborated* (disjoint generated
lineages agree) an orthogonal flag. A replayed witness beside a
covering universal claim is a recorded **contradiction**, never
silently resolved.

**Two modes of operation.** *Automatic*: point the driver at a pinned
benchmark and the LLM runs the loop — play, read the frontier,
conjecture (semantics first: new solving, then new translation, then
new languages), generate the implementation in Python, pass it
through the gate, re-play — until a human pulls the plug, which is
safe at any moment because the log is append-only and
best-per-question only ever improves. *Manual*: write a registry
entry directory and run `python3 -m kernel.driver admit <entry-dir>`;
the kernel adjudicates through the same gate and stamps the evidence,
or refuses and stamps nothing. Same operations, same gate, no special
case; results are never written by hand in either mode.

**From empty.** The kernel ships with zero languages, zero pairs,
zero terminals, zero domains. On a fresh benchmark the first
admissions are the domain (root + anchors), the root's interpreter,
and a first naive terminal in pure Python — the naive generated
solver is not a stopgap but the first citizen, and every later power
move improves on a working, admitted baseline.

## About the name

A hurdy-gurdy is a string instrument whose player cranks a mechanical
wheel; the wheel sounds the strings — paired as drone and melody —
and a keyboard of tangents deterministically sets the pitch. The
player chooses *what* to play; the mechanism turns that choice into
sound the same way every time. A **pair** is a drone+melody pairing;
the **translator** is the keyboard — same key, same pitch; the
**interpreters** are the wheel that makes the sound real; the
**player** — LLM or human — decides what to ask. The previous
generation added the crank: the loop turns until the player stops.
This generation builds the instrument in its own workshop: no
store-bought strings, every part cut, checked, and replaceable —
which is what lets the same gate vouch for all of it.

## Layout

```
kernel/          the fixed, hand-written part: five stdlib-only
                 Python modules (KERNEL.md §8); ships empty of content
registry/        generated content, append-only — does not exist yet:
                 domains/, languages/, pairs/, terminals/ appear as
                 the loop (or a human) admits entries through the gate
runs/<name>/     pinned benchmark, append-only log, board + graph
KERNEL.md        the design: primitives, generation rule, gate, modes
```

## Run

```sh
python3 -m kernel.driver admit  <entry-dir>   # the gate (manual mode)
python3 -m kernel.driver play   runs/<name>   # one iteration over a benchmark
python3 -m kernel.driver report runs/<name>   # pure log -> frontier.md
python3 -m kernel.driver graph  runs/<name>   # pure log -> frontier.dot
```

On this commit every command works and answers honestly from
emptiness: `play` books every question as an open `partial` (no route:
no admitted terminal), and the board and graph draw the frontier as
everything. That is the intended starting state — see KERNEL.md §6,
bootstrap from empty.

## Lineage

Hurdy-gurdy descends from rotor, originally developed as part of
selfie ([github.com/cksystemsteaching/selfie](https://github.com/cksystemsteaching/selfie),
`tools/rotor.c`), generalizing its one fixed translation into a
growing, gated graph of them. Four prior generations live on branch
`main` of this repository — the pair calculus, the instrument and its
papers, the frontier program, and the Era-4 kernel whose vocabulary
and gate discipline this generation keeps — with the full genealogy
in `HISTORY.md` there. This branch restarts from the initial commit
on purpose: a generation defined by *generating everything* should
begin from a tree that contains nothing.

This work was co-funded by the Czech Science Foundation under Grant
No. 23-07580X and the European Union under the project Robotics and
Advanced Industrial Production (reg. no.
CZ.02.01.01/00/22_008/0004590).
