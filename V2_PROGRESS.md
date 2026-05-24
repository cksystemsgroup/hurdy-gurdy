# `aarch64-btor2` Progress — Live State

> The single source of truth for "where is the `aarch64-btor2`
> bootstrap right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-24T00:00:00Z — P1: SCHEMA.md frozen + spec.py + pair registration

- **Phase**: P1 complete.
- **What changed**:
  - Created `gurdy/pairs/aarch64_btor2/SCHEMA.md` at schema version
    `1.0.0`. Covers: sorts (bv1/4/5/6/8/16/32/33/64/65/mem), state
    variables (x0–x30, sp, pc, nzcv, halted, nondet), ELF loading,
    full A64 base integer ISA lowering in §§5.1–5.14, dispatch,
    entry assumptions, constraint/bad/havoc/verdict semantics,
    annotation conventions, stability profile, interpreter semantics,
    and the AArch64-vs-RV64 divergence summary table (§14).
  - Key AArch64 divergences documented explicitly:
    - SDIV/UDIV div-by-zero → 0 (not −1 / 2^64−1 like RV64).
    - W-register operations **zero-extend** to 64 bits (RV64 ADDW
      etc. sign-extend).
    - R31 is context-sensitive (XZR in data-processing, SP in
      memory/stack); separate `sp` state declared.
    - NZCV 4-bit condition-flags state (RV64 has none).
    - Link register is x30 (RV64: x1/ra).
    - AArch64 SUB carry convention = no-borrow (C=1 = no borrow).
    - No MULW analogue (SMULL sign-extends inputs, not result).
  - Implemented `gurdy/pairs/aarch64_btor2/spec.py`:
    `Aarch64Btor2Spec` (frozen dataclass, `from_jsonable`, JSON
    round-trip decoders), `validate_aarch64_btor2_spec` structural
    validator. New AArch64-specific fields vs riscv-btor2: `SPAt`,
    `NZCVAt`, `SPInit`, `NZCVInit`, `AnalysisDirective.havoc_sp`.
    Register range validated as 0–30 (not 0–31).
  - Updated `gurdy/pairs/aarch64_btor2/__init__.py`: pair registered
    via `register_pair(PAIR)` with schema_version `1.0.0`, spec
    class, validator, reasoning_interp, all five solver backends.
    `translator`, `source_loader`, `lifter` are `NotImplementedError`
    stubs (P4, P2 respectively); `interpreter_version=""` to avoid
    framework enforcement until those land.
  - Smoke tests pass: validator catches out-of-range register (r31),
    missing binary path, missing entry function; pair registration
    returns correct PAIR_ID, SCHEMA_VERSION, solver list, layer names.
- **Next iteration's planned work**: P2 — implement the AArch64
  source interpreter (`source_interp/`): ELF loader
  (`source/loader.py`), A64 instruction decoder (`source/decoder.py`),
  concrete executor for the integer base ISA + branches + loads/stores
  (`source_interp/interpreter.py`). Validate against QEMU
  (`qemu-aarch64-static`) on hand-crafted golden traces covering the
  key divergence cases (SDIV div-by-zero → 0; W-register zero-
  extension; XZR reads; SP addressing; NZCV flag updates for ADDS,
  SUBS, ANDS).
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

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
