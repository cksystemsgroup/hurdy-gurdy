# hurdy-gurdy

An LLM-driven explorer of the **frontier of reducible decidability in
practice**: present it a benchmark whose questions reduce to decision
procedures, and it plays every question along every feasible route,
grows itself by exactly what the open questions demand, and keeps —
as checked, durable artifacts — everything it learns along the way.
The deliverable is a **map**: per question its best path — result,
route, cost, and trust grade; and the **frontier** — the questions
not yet terminally answered, each carrying the evidence of how far
every route got and where it failed. Both render from the log alone,
as a graded board (`frontier.md`) and a drawn graph (`frontier.dot`).
The design is [`KERNEL.md`](./KERNEL.md); the story of how the
system reached this shape is [`HISTORY.md`](./HISTORY.md).

The instrument underneath is a platform for **deterministic,
fidelity-graded translations** between formal languages, so that an
LLM (or a human) can move a program into whatever representation
makes a question answerable — and reason about it there through
external interpreters and solvers — without ever trusting an
unaudited step. The one architectural sentence: **the LLM never
writes a result; only the kernel does, by running checked code.**

The system has exactly **two modes of operation**: *automatic* —
point the driver at a pinned benchmark and it plays every question
along every admitted route — and *manual* — write a new registry
entry (a language or a pair) and put it through the one gate with
``admit``. Steering the system is only ever adding checked
capability; results are never written by hand in either mode.

- **Paper** — *Untrusted Authors, Trusted Answers: A Calculus of
  Fidelity-Graded Translations* (arXiv preprint:
  [`paper/arxiv.pdf`](./paper/arxiv.pdf), built from this repository
  at tag `arxiv.2`), and the frontier paper (`paper/frontier/`) with
  the saturation campaign and the discovery program.
- **Video** — an eight-minute narrated explainer of the vision and
  the core ideas, following v2 of the paper: on YouTube at
  [youtu.be/8Wg33_T_u-s](https://youtu.be/8Wg33_T_u-s), or in-tree as
  [`video/hurdy-gurdy-explainer.mp4`](./video/hurdy-gurdy-explainer.mp4).

## How it works

**Languages.** A language is a deterministic syntax plus a
deterministic interpreter exposing named observables. Root languages
(the formats benchmarks arrive in) are the trusted base; derived
languages enter only together with a pair to a parent — an
abstraction or a specialization — so they add nothing to the trusted
base: their semantics is checked against the parent's. A **domain**
is a root language together with its external anchors (labels,
vectors, independent engines) — all that entering a new domain
requires, since the loop bootstraps everything else from empty.

**Pairs.** The unit of the platform is the **pair**: a source
language, a target, a pure translator `T`, a carry-back map `Λ`, and
a declared projection `π` — the observables the pair promises to
preserve. These close a **commuting square**, checked per program by
running both sides:

```text
                 translate  (T)
   source ───────────────────────▶ target
     │                                │
   source                          target
 interpreter (I_s)              interpreter (I_t)
     ▼                                ▼
   source' ◀─────────────────────── target'
            carry back  (Λ)

   I_s(p)  ≡_π  Λ( I_t( T(p) ) )      for every source program p
```

The square commuting *is* the pair's correctness statement; a failure
localizes to a step and an observable. A square may be
**directional**: an abstraction pair promises `⊑_π` — every source
behavior has a target counterpart, and the target may deliberately
have more — and universal verdicts transfer back across such a hop
while existential ones only ever return by replay.

**Solving is translation too.** A **solver pair**'s target is the
language of **results**: translating *is* solving under a declared
budget. A result is a witness, a universal claim `all(bound)`, or —
when the solver runs out — a `partial`: a description of how far it
got and where it failed, profiling included. There is no separate
bookkeeping for failure: **the frontier of a benchmark is exactly its
non-terminal results**, each carrying its route and its evidence.

**Certification.** Both sides are Λ-then-check. A witness is carried
back and **replayed** through the source interpreter — one run,
route-independent, unforgeable by a wrong or adversarial pair. A
universal claim grades on the strict ladder *claimed < checked
(certificate validated at the target; route trust rides along) <
certified (obligations re-discharged at the source;
route-independent)* — with *corroborated* (disjoint lineages agree)
an orthogonal flag. Nothing is ever worded stronger than what was
verified, and a replayed witness beside a covering universal claim is
a recorded **contradiction**, never silently resolved.

**Routes, paths, and trust.** Pairs compose into routes; a route's
contract is the componentwise meet — the weakest hop on every axis —
so a label never overstates. A **path** is a route played on one
question, logged with its result, grade, and cost — and playing
another route is how both exploration axes work: a disjoint-lineage
or source-discharging route raises trust, a cheaper route is found
by reading recorded costs, and the result order guarantees an added
play never worsens the map. Determinism is the load-bearing wall:
every registered executable is a pure function, and the kernel
measures it (every check runs twice, byte-compared) rather than
believing it.

**Automatic mode: the loop.** Pointed at a pinned benchmark, the LLM
runs autonomously until a human pulls the plug: play every question, read
the frontier, conjecture what would move it, build it, and pass it
through the one gate — determinism, the square (or result validity),
and **two-sided controls**: the intact artifact must pass and every
supplied mutant must fail, because a checker that cannot be made to
fail is unfalsifiable. What passes is registered, append-only.
Conjectures go **semantics first**: (a) new decision procedures for
existing languages, then (b) new translations, then (c) new
languages — new syntax is earned by demonstrated semantics, never
invented ahead of it. Pulling the plug is safe at any moment: the
log is append-only, the frontier report is a pure function of it
(regenerating is byte-identical), and best-per-question only ever
improves — the ratchet, proved in `kernel/mechanization/` along with
*once terminal, always terminal*.

**Manual mode: growing the registry.** The only other way to steer
the system is to grow it: write an entry directory — a language's
`interp.py` with vectors and mutants, or a pair's `T.py`/`solve.py`
with corpus and mutants — and run
`python3 -m kernel.driver admit <entry-dir>`. The kernel adjudicates
through the same gate the loop uses, stamps the evidence into the
manifest (or refuses, leaving no stamp), and the next `play` routes
over the new entry. From empty this same act bootstraps everything:
the kernel ships with zero languages and zero pairs, and on a fresh
instance the first admission is the benchmark's root interpreter (the
trusted base, graded honestly), then a first naive solver pair, then
growth — demonstrated three times over in `mini/runs/`.

## About the name

A hurdy-gurdy is a string instrument whose player cranks a mechanical
wheel; the wheel sounds the strings — paired as drone and melody —
and a keyboard of tangents deterministically sets the pitch. The
player chooses *what* to play; the mechanism turns that choice into
sound the same way every time.

The mapping is close. A **pair** is a drone+melody pairing — the unit
that produces meaningful output. The **translator** is the keyboard:
a fixed, deterministic mapping from input to output, same key → same
pitch. The **interpreters** are the wheel: the mechanical step that
makes the sound real. And the **player** — the LLM or the human —
decides what to ask and which keys to press, while the instrument
handles the mechanics faithfully and predictably. The kernel era adds
the crank itself: the loop turns until the player stops cranking, and
the tune it has proved playable — the map — remains.

## Layout

```
kernel/                the fixed, hand-written part: five stdlib-only
                       Python modules + its own Lean mechanization
registry/              generated content, append-only: languages and
                       pairs with manifests, admission evidence
                       stamped — today 14 languages (machine: riscv,
                       aarch64, wasm, ebpf, evm; constraint: btor2,
                       btor2-spec, smtlib; high-level: c, python,
                       crn, smiles, formula; plus sail) and 23 pairs,
                       8 of them solver pairs wrapping the engines
runs/<benchmark>/      pinned benchmark, append-only log, frontier
                       board + graph (regenerate byte-identically)
mini/                  the K1 minikernel program — the pre-registered
                       bootstrap-from-empty evidence (three domains)
paper/                 the papers and their mechanizations
gurdy/                 the carried-over library: Era-3 interpreters,
                       translators, and engine wrappers that registry
                       entries import (HISTORY.md — mined, not grown)
tools/                 two fuzz harnesses auditing the riscv and sail
                       semantics against external oracles
tests/                 the whole suite — kernel tests, entry
                       re-admission, and the library's own tests
Dockerfile, DOCKER.md  the pinned toolchain image: every external
                       engine at a fixed version, one digest
video/                 the narrated explainer and its render pipeline
```

## Run

```sh
python3 -m unittest discover -s tests            # the full suite
python3 -m kernel.driver play runs/btor2-demo --wall 30
python3 -m kernel.driver report runs/btor2-demo  # pure log -> board
python3 -m kernel.driver graph runs/btor2-demo   # pure log -> DOT graph
python3 -m kernel.driver admit registry/pairs/<id>   # the manual mode
cd kernel/mechanization && lake build            # the kernel's proofs
```

The demo (`runs/btor2-demo/`) is the first kernel-played map: a
witness replayed through the shared interpreter, a bounded universal
terminal at *claimed*, and an unbounded ask honestly on the frontier —
the shape of everything the platform does, in three questions.

## Lineage

Hurdy-gurdy descends from rotor, originally developed as part of
selfie ([github.com/cksystemsteaching/selfie](https://github.com/cksystemsteaching/selfie),
`tools/rotor.c`). The RISC-V–to–BTOR2 translation draws on rotor's
encoding choices. Hurdy-gurdy is not a port: it generalizes one fixed
translation into a growing, gated graph of them. The full genealogy —
eras, redesigns, and where everything retired still lives — is
[`HISTORY.md`](./HISTORY.md).

This work was co-funded by the Czech Science Foundation under Grant
No. 23-07580X and the European Union under the project Robotics and
Advanced Industrial Production (reg. no.
CZ.02.01.01/00/22_008/0004590).
