# `aarch64-btor2` Progress — Live State

> The single source of truth for "where is the `aarch64-btor2`
> bootstrap right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-23T00:00:00Z — P0: scaffold aarch64_btor2 package

- **Phase**: P0 complete.
- **What changed**:
  - Created `gurdy/pairs/aarch64_btor2/` package with directory shape
    per `V2_BOOTSTRAP.md` §6: `source/`, `source_interp/`,
    `reasoning_interp/`, `translation/`, `lift/`, `solvers/`.
  - Copied `reasoning_interp/` verbatim from
    `v2-bootstrap:gurdy/pairs/riscv_btor2/reasoning_interp/` with
    import paths updated to `aarch64_btor2` and `PAIR_ID` changed to
    `"aarch64-btor2"`. BTOR2 evaluator imports remain on
    `riscv_btor2.btor2` (ISA-agnostic parser, shared).
  - Copied `solvers/` verbatim from
    `v2-bootstrap:gurdy/pairs/riscv_btor2/solvers/` (engine-agnostic).
  - Created `__init__.py` stub (registration deferred to P1) and
    `spec.py` stub (schema deferred to P1).
  - Created `bench/aarch64-btor2/` structure: `corpus/seed/`,
    `corpus/svcomp_slice/`, `harness.py`, `oracle_align.py`,
    `oracle_cross.py`, `engine_bench.py`, `baselines/{cbmc,hurdy_gurdy,pareto}.py`
    — all P-phase stubs with TODO markers.
  - Created `tests/pairs/aarch64_btor2/__init__.py`.
- **Next iteration's planned work**: P1 — define `SCHEMA.md` for
  `aarch64-btor2` (AArch64 base integer ISA; register file x0–x30,
  sp, pc, NZCV, mem, halted; schema version 1.0.0). Freeze the
  schema, then stub `spec.py` (`Aarch64Btor2Spec` + validator) and
  register the pair in `__init__.py` with a `NotImplemented`
  translator placeholder.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/aarch64-btor2/SCOPE.md` (benchmark scope). Everything
  else is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/aarch64_btor2/` package and `bench/aarch64-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §6. Copy `gurdy/core/`,
  `reasoning_interp/`, dispatch infrastructure, and the
  layered-artifact builder from the `v2-bootstrap` branch
  aggressively.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — **primary copy source for this pair**).
