# `aarch64-btor2` Progress — Live State

> The single source of truth for "where is the `aarch64-btor2`
> bootstrap right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

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
