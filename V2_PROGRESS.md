# V2 Progress — Live State

> The single source of truth for "where is the v2 bootstrap right now."
> Each iteration appends one entry at the top. Older entries stay for
> history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

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
