# `ebpf-btor2` Progress — Live State

> The single source of truth for "where is the `ebpf-btor2` bootstrap
> right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-27T00:00:00Z — P1 schema v1.0.0

- **Phase**: P1 complete. SCHEMA.md is frozen at v1.0.0.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/SCHEMA.md`: full schema v1.0.0.
    Defines sorts (`bv1`, `bv32`, `bv64`); state variables
    (`reg_r0`–`reg_r9`, `insn_idx : bv32`, `halted : bv1`);
    r10 as constant 512 in P1; program loading from `.bpf.o`
    ELF; instruction lowering for the P1 subset (ALU64 K/X 12
    ops, JMP K/X 12 branch flavours + JA + EXIT); dispatch
    layer structure; entry-state constraints; `RegisterBound`
    constraint encoding (unsigned); property expression DSL
    grammar; `bad`-node lowering table; verdict semantics;
    layer names; annotation conventions; stability profile;
    interpreter-semantics stub (P2/P3); explicit exclusions
    list (P8–P11 features).
  - `gurdy/pairs/ebpf_btor2/__init__.py`: added
    `SCHEMA_VERSION = "1.0.0"`.
  - `tests/pairs/ebpf_btor2/test_spec.py`: 25 unit tests
    covering `validate_ebpf_btor2_spec` (valid and error
    paths), canonical serialisation round-trips, spec-hash
    distinctness, and `from_jsonable` pair-rejection. All
    pass; full suite 412 passed / 12 skipped / 0 failed.
- **Next iteration's planned work**: P2 — source interpreter
  (`gurdy/pairs/ebpf_btor2/source_interp/`). Bytecode decoder
  + register-model step function for the P1 opcode set
  (ALU64 K/X, JMP K/X, EXIT). Trace recording, `halted`
  semantics, determinism test with a hand-written byte sequence.
- **Open BLOCKERs**: none.

---

## 2026-05-22T00:00:00Z — P0 scaffold

- **Phase**: P0 complete.
- **What changed**: Created full directory scaffold per
  `V2_BOOTSTRAP.md` §5.
  - `gurdy/pairs/ebpf_btor2/` package: `__init__.py`, `SCHEMA.md`
    (placeholder), `spec.py` (eBPF spec language — `EbpfBtor2Spec`,
    `RegisterBound`, `PacketBound`, `Property`, `AnalysisDirective`,
    `validate_ebpf_btor2_spec`); subpackage stubs for `source/`,
    `source_interp/`, `reasoning_interp/`, `translation/`, `lift/`,
    `solvers/`.
  - `bench/ebpf-btor2/corpus/{seed,kernel_rejects,external}/`
    (`.gitkeep`); `harness.py`, `oracle_align.py`, `oracle_cross.py`,
    `engine_bench.py` (stubs raising `NotImplementedError`);
    `baselines/{kernel_verifier,prevail,hurdy_gurdy,pareto}.py`
    (stubs).
  - `tests/pairs/ebpf_btor2/__init__.py`.
  - `gurdy/core/` already matched `v2-bootstrap` (identical tree
    SHAs) — no copy needed.
- **Next iteration's planned work**: P1 — define schema version
  1.0.0 in `SCHEMA.md` (sorts, machine-state layout, layer names,
  the minimal ALU64 + branch + exit opcode set, `QuestionSpec`
  reach-property). Freeze SCHEMA.md before any translator work.
- **Open BLOCKERs**: none.

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/ebpf-btor2/SCOPE.md` (benchmark scope). Everything else
  is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/ebpf_btor2/` package and `bench/ebpf-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §5. Copy `gurdy/core/`
  primitives from `v2-bootstrap` where they conform.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).
