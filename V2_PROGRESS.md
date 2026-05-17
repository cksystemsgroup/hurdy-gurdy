# `evm-btor2` Progress — Live State

> The single source of truth for "where is the `evm-btor2` bootstrap
> right now." Each iteration appends one entry at the top. Older
> entries stay for history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/evm-btor2/SCOPE.md` (benchmark scope). Everything else
  is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/evm_btor2/` package and `bench/evm-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §5. Copy `gurdy/core/`
  primitives from `v2-bootstrap` where they conform.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).
