# Kernel — hurdy-gurdy generated whole

This document is the vision and the specification of the platform's
fifth generation, begun 2026-08-14 **from the initial commit**: the
tree behind this file contains a README, this specification, and the
empty kernel — nothing else. The generation before it (Era 4 on branch
`main`, its story in `HISTORY.md` there) settled the vocabulary this
design keeps: results as the only currency, one gate, two modes, the
frontier as the non-terminal remainder. What forces a fresh lineage
rather than an increment is one rule with consequences everywhere:

> **Every implementation in the system — translator, interpreter,
> solver, certifier — is generated, in Python. There are no existing
> tools inside the system.**

The previous generation wrapped engines; its trust story leaned, at
the endpoints, on decades of other people's solvers. This generation
owns its endpoints. What that costs in raw power it returns in
uniformity — one gate can adjudicate *everything*, because everything
is the same kind of thing: generated source, admitted on evidence —
and in honesty: there is no step whose implementation the system
cannot read, run, mutate, and re-derive. The rule that keeps the
design small survives from Era 4 unchanged:

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

**Domain** = a root language together with its external anchors — the
two things the loop cannot generate for itself: the format questions
arrive in, and the ground truth (benchmark labels, supplied test
vectors) that corroborates the root's interpreter. A benchmark lives
in exactly one domain — the root its programs parse in — and a domain
owns **nothing else**: no pair, terminal, or derived language belongs
to a domain (§4). Entering a new domain costs a benchmark plus
anchors, nothing more, because the loop bootstraps the rest from
empty (§6).

**Pair** = directed translation edge between languages, with
translator `T`, back-translator `Λ`, kept observables `π`, direction
(exact / over / under), measured cost, and a lineage declaration. The
pair's correctness statement is the directional square, checked per
program by running both sides; its declarative surface for routing is
its observable **maps** (source name → target name, checked against
its executable carry-back per program) and its **bound_cap** (a hop
that reifies an unrolling caps every universal claim crossing back —
a k=20 unsat is a bound-20 fact).

**Terminal** = the endpoint where a route stops being syntax and
becomes a verdict: the place of actual model reasoning. Era 4 modeled
this as a *solver pair* — an edge from a language to the result — and
the terminal keeps that entire discipline while naming what the
generation rule makes unavoidable: the endpoint carries not one
implementation but two kinds. A terminal at language `L` bundles

- a **solver**: `solve` takes a program of `L`, a question mode, an
  observable, a bound, and a budget, and returns a result value —
  witness, universal claim (with an optional certificate), or partial;
- its **certifiers**: `Λ` carries a witness payload back to an
  interpreter input so the kernel can replay it, and the optional
  `discharge` interprets a certificate against the problem — finitely
  many decidable obligations, the fail-safe direction definitional
  (§3).

A result target has no interpreter, only validity, so the square
degenerates to exactly that — witnesses must replay, certificates
must re-discharge, negative controls must fail, determinism must
hold. Same admission discipline as every pair; there is no separate
solver gate (§8). Terminals declare what they **decide**; the driver
composes a question's observable through the hops' maps and requires
the terminal to decide it — anything else is a partial, never an
answer.

**Route** = a composition of pairs ending in a terminal: translation
hops, then the solving stop. A route's contract is the componentwise
meet — weakest link — the one composition rule the calculus keeps.
Routes to the same question differ on exactly two axes, and both are
reasons to play another one — exploration the result order makes
free, since an added play can only improve the map:

- **trust**: the meet bounds what any *checked* result on the route
  may rest on; a route whose certificate re-discharges at the source
  is what *certified* requires; a route of disjoint lineage is what
  *corroborated* means — so a second route can raise a grade that
  re-playing the first never will;
- **performance**: cost is recorded in every path and never ranked by
  the kernel; the player reads costs across routes to find the cheap
  one, and spends what that frees on open questions. The generation
  rule gives this axis its second lever: a hop or terminal whose
  Python reference is the bottleneck can grow an **accelerator** (§2)
  without touching the trust story.

**Path** = one play of a route on one question: the log record of the
route taken, the budget spent, the result, and its grade. Routes are
what the registry affords; paths are what happened. The map and the
frontier are stated over paths — best path per question.

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

One rename keeps the vocabulary honest: a result that decides its
question — a replayed witness, or a universal claim covering the
asked bound — is **settled** (Era 4 said "terminal result"). The
entity holds the name *terminal* now; the predicate holds *settled*.
A question settles at a terminal.

## 2. The generation rule

Every implementation is generated, in Python, and lives as committed
source inside its registry entry: the interpreter of every language,
the `T` and `Λ` of every pair, the solver and certifiers of every
terminal. **No existing tools**: no wrapped engines, no shelling out,
no vendored binaries of someone else's reasoning. The substrate is
infrastructure, not tooling — the Python interpreter the kernel
itself runs on, and a declared compiler where an accelerator needs
building — but nothing that *reasons* enters except as generated
text through the gate.

Enforcement is layered, and worded no stronger than what each layer
verifies:

- **statically**, the gate requires every reference implementation to
  be a Python file inside the entry — there is no manifest field for
  pointing at a tool, because there is nothing to point at;
- **dynamically**, the runner is sealed: every registered executable
  runs in its own process with an **empty environment** — no `PATH`,
  nothing to discover an existing tool with — a temporary working
  directory, and a wall cap, and every check runs twice with
  byte-compared output;
- **socially**, every implementation is committed source in the
  registry, auditable and mutable — which is what the two-sided
  controls need anyway. The seal makes reaching for a tool loud and
  the registry makes it visible; neither is claimed to be a proof.

**Performance-critical code may be implemented in a
performance-oriented language.** The seam is narrow and principled:
an entry may ship one **accelerator** — the same implementation
generated again in a performance-oriented language (C, Rust, …),
source and built executable both in the entry — and only for
**translation and solving**, because those are the steps whose
outputs the kernel checks downstream: witnesses replay, universal
claims grade, squares close. The check itself is never accelerated —
interpretation, carry-back, and discharge always run the Python
reference. An accelerator is admitted solely by byte-agreement with
its reference on every admission invocation, determinism measured
like everything else; the reference remains the semantics, and the
accelerator is only ever a cheaper way to the same bytes. Second-order
effect, intended: the naive generated solver comes first and stays
the meaning; speed is earned separately, per entry, with evidence.

## 3. Certification and the grade ladder

Both certifications are Λ-then-check; the difference is what checks.

- **Existential**: the witness is carried back (`Λ`) and replayed
  through the source interpreter. One run, always available,
  route-independent: a wrong or adversarial pair cannot forge it. A
  recorded witness is always *replayed* — a terminal's unreplayable
  `sat` is never a witness result; it is evidence inside a `partial`
  (or, on an abstraction route, a refinement demand).
- **Universal**: a certificate is interpreted **against the problem**
  by the terminal's certifier. Checked at the target it inherits the
  route's trust (the meet); on a hop-free route the target *is* the
  source, so a validated discharge is route-independent — the mirror
  of witness replay. The fail-safe direction is definitional: a wrong
  or wrongly-mapped certificate can only fail to upgrade, never fake
  one.

The ladder, with strict naming:

```
claimed  <  checked   (at target; route trust rides along, recorded)
         <  certified (discharged at source; route-independent)
         @  corroborated (disjoint lineages agree — orthogonal flag)
```

"Certified" is *reserved* for the route-independent form; every result
states its rung and what its residual trust rests on — the route meet
for *checked*, the discharge lineages for *certified*. The kernel
computes grades from lineage declarations, and grades only improve.
Under the generation rule, lineage is a declaration about *descent of
generated procedures*: two terminals grown from the same ancestor
implementation declare so, and never corroborate each other. The
second-order effect is intended: whatever earns the top grade is what
the autonomous loop learns to build, so the frontier evidence itself
pushes the LLM toward certificate printers, Λ-for-certificates, and
independently generated discharge procedures.

A replayed witness is ground truth: if a question ever holds both a
replayed witness and a covering universal claim, the kernel records a
**contradiction event**, the witness stands, and the universal's
certification chain is marked falsified. Contradictions are never
silently resolved.

## 4. Two modes, and everything available to everyone

The system has exactly two modes of operation, and they share one
gate:

- **Automatic**: point the driver at a pinned benchmark; the LLM runs
  the loop (§6) autonomously — play, read the frontier, generate,
  admit, re-play — until a human pulls the plug.
- **Manual**: a human writes a registry entry directory and invokes
  the same admission (`python3 -m kernel.driver admit <entry-dir>`),
  or plays a benchmark by hand. Same operations, same gate, no
  special case.

Steering the system is only ever adding checked capability; results
are never written by hand in either mode.

**Availability is universal.** The registry is one space: every
admitted pair and terminal is available to every domain, including
domains that look wholly unrelated to the one an entry was grown in.
A domain is only a root and its anchors (§1) — it fences nothing.
This is deliberate openness for discovery: whether a constraint
terminal grown for one root serves a machine-code root three hops
away is exactly the kind of fact the kernel exists to surface, and
the admission gate — not topical relatedness — is the only
membership test. The graph (§5) draws every admitted terminal for
every benchmark, so an unreachable terminal is a visible conjecture:
the dotted gap says which missing pair would connect it. Routing
stays honest under openness because it is declarative — composed
maps must land in a terminal's `decides`, contracts meet
componentwise — so an absurd route can only produce a partial, never
a wrong answer, and junk never wins a route because the result
order, not arrival, picks the best path.

## 5. The frontier

A question is `(language, program, observable, mode: exists|forall,
bound: k|inf)`; a benchmark is a pinned finite set of questions with
recorded provenance (sha256 per program, labels where they exist).

Results order per question: `partial < all(k) below the asked bound <
settled`, where settled is a replayed witness or a universal claim
covering the ask; within a level, higher bound, then higher grade.
Cost is recorded and reported, never ranked.

**The frontier of a benchmark is the set of questions whose best path
is not settled**, each carrying that path and its progress evidence —
the non-settled results with the route to get there. The registry and
the log are append-only, and best-per-question over an append-only
log is monotone: the ratchet is a property of the data structure.
**Expanding the frontier** means strictly improving some question's
best path (level, bound, or grade — not cost).

The frontier is drawn, not only listed. Two renderings, both pure
functions of (registry, benchmark, log), both regenerating
byte-identically:

- **the board** (`frontier.md`): one row per question — its best
  graded path: result, grade, route, cost. Settled rows are the map;
  the rest are the frontier, listed with their evidence.
- **the graph** (`frontier.dot`): the registry drawn — languages as
  nodes, pairs as edges, terminals as sinks — with the benchmark's
  best paths overlaid: bold where every crossing question is settled,
  solid while one is still open, dotted where no best path runs.
  Where the frontier sits, and which missing edge would move it, is
  visible at a glance.

## 6. The loop, the conjecture order, and bootstrap from empty

The LLM is presented a benchmark and runs autonomously until a human
pulls the plug:

1. **Play**: for every question, run the admitted routes within
   budget; the kernel records results.
2. **Read the frontier**: the non-settled results with their profiles.
3. **Conjecture**, in this order — semantics first, then syntax:
   - **(a) new solving and certifying for existing languages** — a
     terminal, a decision procedure, a certificate printer, a
     discharge procedure, an accelerator for a proven bottleneck:
     new *reasoning* first;
   - **(b) new translation** — new pairs, new routes to existing
     terminals, including routes into superficially unrelated
     domains (§4);
   - **(c) new languages** — abstraction or specialization deltas,
     proposed only when a translation or solving move keeps winning
     ad hoc and reifying it would make the win reusable and cheap.
     New syntax is earned by demonstrated semantics, never invented
     ahead of it.
4. **Generate, check, register**: the LLM writes Python (or, behind
   a reference, an accelerator); the kernel gates it; what passes is
   registered. This step *is* the generation rule in motion — there
   is no tool to reach for, so every conjecture lands as source the
   gate can adjudicate.
5. Re-play affected questions; repeat.

The trust story in one sentence: **the LLM never writes a result;
only the kernel does, by running checked code.** What autonomy risks
is registry clutter, which the result ordering neutralizes (junk
never wins a route) and which pruning, a human act between runs, can
clean.

**Bootstrap from empty.** The kernel ships with zero languages, zero
pairs, zero terminals, zero domains. Presented a benchmark, the LLM's
first acts are: admit the domain (root name + anchors — the
ungenerable half, nothing executes), write the root language's
interpreter (the trusted base, graded *stipulated*; the anchors are
its only corroboration), then a first naive terminal in pure Python,
then growth. Grades bottom out at *claimed* until the registry holds
a second lineage. Everything must work at this point — which is the
design's simplicity test, and under the generation rule it is also
the design's *totality* test: there is no engine to lean on while
bootstrapping, so the naive generated solver is not a stopgap but the
first citizen, and every later power move (a stronger procedure, a
certificate printer, an accelerator) improves on a working, admitted
baseline.

**Plug-pull** is safe at any moment: the driver appends every result
and registration as it happens, and the exit deliverables are pure
functions of the log — the board and the graph with the delta since
iteration zero, and, if the frontier moved, the evolved hurdy-gurdy:
the kernel unchanged plus everything registered, with admission
evidence. The next benchmark starts from it.

## 7. What the kernel proves, and what it asks of generated code

The kernel is the fixed part and the only hand-written code; it is
small on purpose (readable in an afternoon). Its load-bearing
properties are stated here and are the standing mechanization
obligation (a Lean development under `kernel/mechanization/`, to be
grown beside the code as in Era 4):

- the result order is a strict partial order (irreflexive,
  transitive, asymmetric);
- best-per-question is monotone under log append (the ratchet);
- once settled, always settled (the frontier never re-opens);
- grades only move up the ladder.

Generated content is asked for proofs **when appropriate and
feasible**: a proof obligation is part of a manifest when the artifact
is kernel-adjacent — a certificate schema must come with its fail-safe
direction stated, a specialization's embedding with its exactness
argument, a new result payload with its ordering. Per-program
translation correctness is *not* proved — that is what the square
checks empirically, per run, which is the platform's founding
economy. Accelerator equivalence is likewise not proved — it is
measured, invocation by invocation, and the reference stays the
semantics.

## 8. The gate, the layout, and the executable contracts

The kernel is the ultimate gate: nothing — no language, pair,
terminal, domain, or any of their implementations, accelerators
included — enters the system except by admission, and admission
evidence is stamped into the entry by the checker, never
self-reported. One discipline for every kind: determinism measured
(run twice, byte-compare), the checkable relation run on the entry's
own corpus, and **two-sided controls** — the intact implementation
must pass and every supplied mutant must fail, because a checker that
cannot be made to fail is unfalsifiable. A terminal that ships a
certifier must exercise it during admission and supply certificate
mutants that fail to discharge. An entry that fails leaves no stamp
and no trace in routing.

```
kernel/                  the fixed part (stdlib-only Python)
  registry.py runner.py results.py checker.py driver.py
  mechanization/         Lean: the kernel's proved properties (§7)
registry/                generated content, append-only
  domains/<name>/        manifest.json (root + anchors)
  languages/<name>/      manifest.json, interp.py, vectors/, controls/
  pairs/<src>--<tgt>/    manifest.json, T.py, lam.py,
                         lam_obs.py (optional Λ on observables),
                         corpus/, controls/
  terminals/<name>/      manifest.json, solve.py, lam.py,
                         discharge.py (optional certifier),
                         corpus/, controls/
runs/<benchmark>/        benchmark.json (pinned), log.jsonl (append-
                         only), frontier.md + frontier.dot (the board
                         and the graph, regenerated)
```

Every registered executable is a pure deterministic CLI — bytes in,
bytes out — run sealed (own process, **empty environment**, temp
working directory, wall cap) and run twice with byte-compared output
on every check. Manifests declare kind, direction, kept observables,
lineage, budget schema, the routing contract (`decides` on terminals;
`maps` and `bound_cap` on pairs), optionally one `accelerator`
(replaces `T.py` or `solve.py`; source + built executable in the
entry; admitted by byte-agreement, §2), and optionally a proof
obligation (§7).

## 9. Honesty rules

- The kernel never trusts a claim it can measure.
- Budgets ride in every result's provenance; capped is labeled capped.
- Grades state their residual trust; nothing is worded stronger than
  what was verified.
- Contradictions are recorded, never resolved silently.
- The frontier summary — board and graph — regenerates from the log
  byte-identically.
- The generation rule states what each layer enforces (§2) and claims
  no more; an accelerator's agreement is measured, never assumed.
- Pruning the registry is a human act between runs; during a run the
  registry only grows.
