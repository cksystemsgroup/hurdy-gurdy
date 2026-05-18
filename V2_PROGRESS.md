# `wasm-btor2` Progress — Live State

> The single source of truth for "where is the `wasm-btor2` bootstrap
> right now." Each iteration appends one entry at the top. Older
> entries stay for history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-18T07:30:00Z — P0a: package scaffold landed

- **Phase**: P0 in progress (P0a complete).
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/` with submodule directories
    `source/`, `source_interp/`, `reasoning_interp/`, `translation/`,
    `lift/`, `solvers/`. Each carries an `__init__.py` with a
    one-paragraph docstring stating its role and the phase at which
    implementation begins (per `V2_BOOTSTRAP.md` §6).
  - `gurdy/pairs/wasm_btor2/SCHEMA.md` placeholder noting the
    schema is frozen at `1.0.0` at P1.
  - `bench/wasm-btor2/{corpus/seed, corpus/external, baselines,
    experiments}/.gitkeep`.
  - `tests/pairs/wasm_btor2/__init__.py`.
- **Verification**: `python -c "import
  gurdy.pairs.wasm_btor2; ..."` succeeds for all seven submodules.
- **Next iteration's planned work**: P0b — copy `gurdy/core/`
  primitives from the `v2-bootstrap` branch where they conform to
  the pair-agnostic contract (`schema.py`, `pair.py`, `layers.py`,
  `dispatch.py`, `interp/` shared types). Audit each file against
  `V2_BOOTSTRAP.md` §3 before copying; do not pull WASM-incompatible
  code.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/wasm-btor2/SCOPE.md` (benchmark scope). Everything else
  is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/wasm_btor2/` package and `bench/wasm-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §5. Copy `gurdy/core/`
  primitives from the `v2-bootstrap` branch where they conform
  to the pair-agnostic contract.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).
