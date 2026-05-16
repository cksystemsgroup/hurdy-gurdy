# V2 Progress — Live State

> The single source of truth for "where is the v2 bootstrap right now."
> Each iteration appends one entry at the top. Older entries stay for
> history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

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
