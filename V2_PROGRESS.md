# V2 Progress — Live State

> The single source of truth for "where is the v2 bootstrap right now."
> Each iteration appends one entry at the top. Older entries stay for
> history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-16T02:10:00Z — P0.4 schema audit: PLAN.md was misframed

- **Phase**: P0 (P0.4 done; P0.5 next).
- **What changed**: `V2_AUDIT.md` extended with §"P0.4 — schema
  audit". Two material findings:
  1. SCHEMA.md is at v1.1.0, but v1.1.0 is **byte-compatible** with
     v1.0.0 for specs that opt out of §14 vocabulary (line 443–446
     in SCHEMA.md pins this with a regression test). The PLAN.md
     framing of "v1.0.0 minimal viable downgrade" was wrong — v2's
     starting schema is just v1.1.0, with §14 features opt-in.
  2. The v1 schema baseline ISA is **RV64I+M+C** (per §12 line 341),
     not RV64I. PLAN.md P9 (add M) and P10 (add C) describe work
     that is already done. Same for P11 (multi-callee scope) —
     already in §6 Dispatch.
- Filed as **P0.5b — PLAN.md correction**: revise P1/P9/P10/P11.
  P0.5a (bench-side primary alignment oracle) is unchanged.
- **Next iteration's planned work**: P0.5b — apply the PLAN.md
  corrections (≤ 20 LOC). Specifically: rewrite P1 to "accept
  v1.1.0 schema as v2's starting schema, no downgrade"; delete P9,
  P10, P11 as phases (note in PLAN.md that they were retrospective);
  renumber if it improves clarity; cross-link the V2_AUDIT.md P0.4
  finding.
- **Open blockers**: none. This is the third plan-side correction
  in P0 (iter 3 was alongside-v1; this is schema-baseline). Pattern:
  the plan was written before reading the repo carefully. Worth
  noting if a future iteration is tempted to plan-by-assumption
  again.

---

## 2026-05-16T01:50:00Z — P0.3 pair audit landed

- **Phase**: P0 (P0.3 done; P0.4 next).
- **What changed**: `V2_AUDIT.md` extended with §"P0.3 — pair audit".
  All three §3 pillars (source_interp, reasoning_interp,
  translation) conform. All five solver adapters present (z3-bmc,
  z3-spacer, bitwuzla, cvc5, pono). The §4 alignment-oracle
  machinery exists in `gurdy/core/interp/align.py` +
  `gurdy/pairs/riscv_btor2/lift/replayer.py` (builds `JoinedTrace`
  from witness, framework walks via `align_traces`). **One
  operational gap**: this machinery is invoked per-witness via the
  `replay` tool, not as a bench-side per-task primary oracle. The
  bench-side files are `oracle.py` (concrete-execution,
  solver-free, §9.10), `framework_oracle.py` (compile→dispatch→
  lift verdict comparison, §B0), and `oracle_cross.py` (engine
  agreement, §4.5) — none of them runs `align_traces` per task.
  Filed as **P0.5a — `bench/riscv-btor2/oracle_align.py`** (≤ 150
  LOC).
- **Next iteration's planned work**: P0.4 — schema audit. Read
  `gurdy/pairs/riscv_btor2/SCHEMA.md`, identify what's at v1.1.0
  scope that exceeds the v2-target v1.0.0 scope (BranchPin,
  CycleInvariant.dual_role, volatile layer, M extension, C
  extension, multi-callee scope). Append §"P0.4 — schema audit"
  to V2_AUDIT.md.
- **Open blockers**: none.

---

## 2026-05-16T01:30:00Z — P0.2 v1-core audit landed

- **Phase**: P0 (P0.2 done; P0.3–P0.5 queued).
- **What changed**: `V2_AUDIT.md` created. Maps every
  `V2_BOOTSTRAP.md` §3 contract (three pillars, alignment oracle,
  spec, schema discipline, pair protocol, determinism) to v1 status.
  Headline: v1 **broadly conforms**. Two documentation-class gaps
  (P0.2a: assert load-bearing-from-day-one in
  `core/interp/README.md`; P0.2b: verify bench-harness uses
  `align_traces` as primary oracle, deferred to P0.3). Three
  follow-up audits queued: P0.3 (pair), P0.4 (schema), P0.5 (gap
  numbering). No code touched.
- **Next iteration's planned work**: P0.3 — `gurdy/pairs/
  riscv_btor2/` audit. Read source_interp, reasoning_interp,
  translation, solvers, lift surfaces; append §"riscv-btor2 pair"
  to `V2_AUDIT.md`. Also resolve P0.2b: search `bench/riscv-btor2/`
  for the primary-oracle wiring.
- **Open blockers**: none.

---

## 2026-05-16T01:10:00Z — P0 reframed: alongside-v1 audit, not wipe

- **Phase**: P0 (revised).
- **What changed**: I noticed (when an attempted `git rm -r gurdy/`
  was correctly blocked) that the original P0.2 wording — "create
  `gurdy/core/schema.py` skeleton" — would shadow v1's
  `gurdy/core/schema/` subpackage on this branch, forcing a
  destructive wipe of v1 code that my own iter-2 progress note
  forbade. Reframed P0 in `PLAN.md` as an *audit-first* phase: v2
  builds alongside v1 on this branch (per `V2_BOOTSTRAP.md` §12);
  P0.2–P0.5 produce a `V2_AUDIT.md` mapping each §3 contract to
  "v1 conforms" or to a sub-increment. P0.6 is the green-baseline
  acceptance: v1's existing tests pass unchanged.
  Also added a clarifying note to `V2_BOOTSTRAP.md` §6 that the
  scaffold layout is **logical**, not a literal "wipe and replace".
- **Next iteration's planned work**: P0.2 — the v1-core audit.
  Read `gurdy/core/schema/`, `gurdy/core/spec/`,
  `gurdy/core/pair.py`, `gurdy/core/interp/` on this branch. Map
  the public symbols to `V2_BOOTSTRAP.md` §3 pillars. Create
  `V2_AUDIT.md` with one row per contract. Read-only; commit only
  the audit doc.
- **Open blockers**: none. (The course-correction was caught by
  the automated classifier — exactly the right behaviour. Worth
  noting in case a future iteration is tempted to expand scope.)

---

## 2026-05-16T00:50:00Z — P0.1 pyproject.toml

- **Phase**: P0 (P0.1 done).
- **What changed**: `pyproject.toml` version bumped to `0.2.0.dev0`
  to mark v2-track development; added `solvers-pono` extra
  (subprocess binary; no Python pkg dep) and `solvers-all`
  convenience extra (z3 + bitwuzla + cvc5). All other fields
  identical to `main`'s.
- **Next iteration's planned work**: P0.2 — `gurdy/core/{schema,
  spec,pair}.py` skeletons. Inspect `git show main:gurdy/core/
  schema.py` etc. and copy the public-surface protocol/dataclass
  shapes verbatim where they conform to V2_BOOTSTRAP.md §3/§6.
  Strip any v1.1.0-specific concretions (BranchPin, CycleInvariant
  dual_role, volatile layer) — those belong to schema versions
  later than the v1.0.0 target. Skeletons only; no implementation.
- **Open blockers**: none.

---

## 2026-05-16T00:30:00Z — P0 plan landed

- **Phase**: pre-P0 → P0 (planned, not yet implemented).
- **What changed**: `PLAN.md` rewritten as the v2 phase plan. v1
  PLAN.md is preserved on `main`. Phases P0–P16+ defined with
  per-phase Goal / Increments / Acceptance / References. RAM-safety
  and `no-main-edits` listed as cross-cutting concerns.
- **Next iteration's planned work**: P0.1 — update `pyproject.toml`
  for the v2 package layout (declare optional extras for solvers;
  keep `gurdy` script entry point). Inspect `main:pyproject.toml`
  first via `git show main:pyproject.toml`. Do not delete or rename
  any existing v1 files yet — v2 scaffold lives alongside until P0
  is fully green.
- **Open blockers**: none.

---

## 2026-05-16T00:00:00Z — Bootstrap created

- **Phase**: pre-P0 (scaffold not yet written).
- **What changed**: branch `v2-bootstrap` created from `main` at
  commit `59afce8`. `V2_BOOTSTRAP.md`, `V2_AGENT_LOOP.md`, and this
  file added. No code changes yet.
- **Next iteration's planned work**: P0 increment 1 — write the v2
  `PLAN.md` (phase-by-phase, in the spirit of `main`'s `PLAN.md` but
  reorganized around the three pillars per `V2_BOOTSTRAP.md` §3).
  Do not start coding until `PLAN.md` is in.
- **Open blockers**: none.

---

<!--
Format for future entries:

## YYYY-MM-DDTHH:MM:SSZ — <short subject>

- **Phase**: <P0 | P1 | ... | iteration-only>
- **What changed**: <one or two lines>
- **Next iteration's planned work**: <one or two lines>
- **Open blockers**: <none | BLOCKER: ...>
- **Pareto snapshot** (only when §6/D ran this iteration):
  - hurdy-gurdy: <solved/correct/false-pos/time>
  - CBMC: ...
  - ESBMC: ...
  - SeaHorn: ...

Use `BLOCKER:` at the start of a line to mark something needing
user input. Use `UNBLOCKED:` (from the user) to mark resolution.
-->
