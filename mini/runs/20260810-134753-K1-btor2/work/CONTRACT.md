# The kernel contract

You are presented with a domain and pinned benchmarks. The kernel
(`kernel.py`) starts **empty**: no languages, no pairs. Your job is to
build what answering takes, get it admitted, and play — first until
every question is either answered or holds honest evidence of how far
you got (**reaching the frontier**), then further: strictly improve
best results — a bound pushed, a claim certified, an open question
closed by a new conjecture (**expanding the frontier**).

**The one rule**: you never write a result. Only the kernel does, by
running code it has checked. Everything you build is a file the
kernel executes.

## Concepts

- A **language** is a deterministic interpreter exposing named
  observables. A **pair** is a directed edge: a **translation pair**
  (language → language, checked per program by the commuting square)
  or a **solver pair** (language → result; translating *is* solving).
  Routes compose translation hops ending in a solver pair; a route's
  contract is the meet of its hops'.
- A **result** is `witness(payload, depth)` — always replayed at the
  source through your interpreter — or `all(bound: k|"inf", cert?)`,
  or `partial(progress)`. Partials are your evidence channel: say how
  far and why.
- **Grades**: an `all` is *claimed* until its certificate discharges —
  *certified* against the source program (route-independent), *checked*
  past translation hops. A replayed witness is ground truth. Two
  terminal results of the same kind with disjoint `lineage` mark the
  verdict *corroborated*.
- **Determinism is measured**: everything you register runs twice and
  is byte-compared. Nondeterminism is refusal.
- **Falsifiability is required**: every entry ships mutants that must
  *fail* its own check. A checker that cannot be made to fail is not
  admitted.
- **Conjecture order**: semantics first. (a) New decision procedures
  for existing languages, then (b) new translations, then (c) new
  languages (abstractions/specializations) — new syntax only when a
  win keeps repeating and reifying it makes it reusable.

## Registry layout

Each entry is a directory `registry/<id>/` with `entry.json` plus:

- **language** — `{"kind": "language", "lineage": [...]}`;
  `interp.py <program> <input>` → observables JSON;
  `vectors/NNN.{program,input,expect}`; `mutants/*.py` (bad
  interpreters your vectors must catch).
- **translation** — `{"kind": "translation", "src", "tgt",
  "direction": "exact"|"over"|"under", "keeps": [observables],
  "maps"?: {src_name: tgt_name}, "bound_cap"?: k, "lineage"}`;
  `T.py <program>` → target program; `lam.py <input> <src-program>` →
  source input (witness carry-back; without it witnesses cannot cross
  the hop); `lam_obs.py <tgt-obs-json>` → source observables (when
  observable names differ); `corpus/NNN.program` (+`.input`);
  `mutants/*.py` (bad translators the square must catch). A hop that
  reifies a bound declares `bound_cap`: a universal crossing back is
  capped, a k-unrolled unsat is a bound-k fact.
- **solver** — `{"kind": "solver", "src", "decides": [observables],
  "lineage"}`; `solve.py <program> <mode> <observable> <bound>
  <wall_s>` → one result-value JSON on stdout; `lam.py <payload>
  <program>` → interpreter input; `discharge.py <program> <cert>` →
  `{"ok": bool, "obligations": {...}}` if you emit certificates
  (then also `cert_mutants/*.json` — wrong certificates that must
  fail); `corpus/NNN.{program,q}` with labels; `mutants/*.py`.
  Declare honestly in `lineage` every codebase a verdict rests on —
  agreement inside one family is never corroboration.
  A solver's unreplayable `sat` is never a witness: return it as
  evidence inside a partial.

## Commands

    python3 kernel.py gate <entry-id> [--registry registry]
    python3 kernel.py play <run-dir>  [--registry registry] [--wall S]
    python3 kernel.py report <run-dir>

`gate` admits an entry (admission is an event in `registry/gate.jsonl`;
the kernel writes it, you never do). `play` runs every admitted route
on every question of `<run-dir>/benchmark.json` and appends results to
`<run-dir>/log.jsonl` — append-only; best-per-question only improves;
`frontier.md` regenerates from the log byte-identically. Play as often
as you like; each new entry you admit opens new routes.

Play can take long: every route gets the declared wall, twice
(determinism), and hard questions spend all of it. Scope with
`--question <id>` to play one question, run long plays in the
background, and size walls to the question. A killed play loses
nothing — every result is already in the log; `report` regenerates
the map at any moment.

## Honesty rules

Budgets are declared, capped is labeled capped. Cost is recorded,
never ranked. Contradictions (a replayed witness beside a covering
universal) are recorded, never resolved. If a question stays open,
its best partial must say what was tried and where it stopped — the
frontier is the point of the exercise, not a failure.
