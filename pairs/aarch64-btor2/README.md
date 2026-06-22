# Pair — `aarch64-btor2`  ·  AArch64 → BTOR2

*Status: **partial** — a simple-ALU slice (`ADD`/`SUB` immediate + `MOVZ`) is
built and mergeable (`gurdy/pairs/aarch64_btor2/`, `gurdy/languages/aarch64/`,
interp v0.2); see "Implementation status" below. Ported from v2.*

Translate an AArch64 (A64) ELF into a BTOR2 transition system, the same
shape as `riscv-btor2` on a second ISA. Its purpose is to demonstrate the
translator architecture is **ISA-portable**: the same layered encoding,
re-aimed at A64's register file and instruction semantics. The C-undefined-
but-ISA-defined wedge (signed overflow, shift masking, `mul` truncation)
reproduces here because the C side is identical — only the defining ISA
changes.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** AArch64 — [`languages/aarch64`](../../languages/aarch64/README.md).
- **Target.** BTOR2 — [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived per-instruction lowering from an
  AArch64 image (+ scope) to a BTOR2 transition system: state for
  `x0`–`x30`, `sp`, `pc`, `NZCV`, a trap flag, and memory as an array;
  PC-keyed dispatch; init/next/constraint/bad. Deterministic and
  schema-predictable. Each A64-vs-RV64 semantic difference is documented
  inline in the schema as a divergence note, so every ISA-portability
  assumption is auditable.
- **Source interpreter.** The **shared** AArch64 interpreter
  ([`languages/aarch64`](../../languages/aarch64/README.md)) — reused;
  contributed by this pair if it is the first AArch64 pair built.
- **Target interpreter.** The **shared** BTOR2 interpreter
  ([`languages/btor2`](../../languages/btor2/README.md)) — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  an AArch64 behavior (initial register/memory state + the reaching run).
  Pair-owned.

## Projection `π`

Post-step `pc`, `x0`–`x30`, `sp`, `NZCV`, halt/trap — the AArch64
interpreter's observables mapped onto the BTOR2 state variables.

## Fidelity target + evidence

- **`checked`** — the commuting-square oracle walks the shared AArch64
  interpreter's trace against `L(I_btor2(T(p)))` under `π` on a corpus;
  divergences localize to a step/observable.
- Ship re-checkable certificates (inductive invariant / k-induction) to lift
  discharged questions to `proved` ([`SOLVERS.md`](../../SOLVERS.md) §5–6).

## Soundness story

Lowering and witness replay share one source of truth (the per-instruction
encoding); a cross-check runs both under `π`
([`PAIRING.md`](../../PAIRING.md) §6).

## Fidelity-raising branch (registered)

Arm has an official **Sail** model (`sail-arm`, from ASL). The registered
**[`aarch64-sail`](../aarch64-sail/README.md)** pair, reusing `sail-btor2`,
gives a second, independent A64→BTOR2 encoding to cross-check against this
one — the same branch RISC-V has ([`PATHS.md`](../../PATHS.md) §4). Keep this
pair's projection `π` compatible with `aarch64-sail`.

## Notes for the implementing agent

- Maximize reuse of the BTOR2 core and the riscv-btor2 layer shape; only the
  register-file (machine) and per-instruction (library) layers are
  ISA-specific.
- Validate the shared AArch64 interpreter against the Sail ARM model or QEMU.

## Implementation status — simple-ALU slice (widened 2026-06-22)

A simple-ALU vertical slice is built end-to-end through the commuting square and
is mergeable at **`partial`** (PAIRING.md §1). It does **not** attempt the
whole A64 ISA. This is a coverage-ratchet **widening** of the original thin
`ADD`-only slice (BENCHMARKS.md §5): `4/12 → 8/12`, interp `v0.1 → v0.2`.

- **In-scope constructs (a simple, no-flag / no-control-flow ALU family):**
  - `ADD (immediate)`, 64-bit (`ADD Xd|SP, Xn|SP, #imm12{, LSL #0|#12}`) — the
    original construct, field-31 ⇒ SP, `LSL #12`.
  - `SUB (immediate)`, 64-bit (`SUB Xd|SP, Xn|SP, #imm12{, LSL #0|#12}`) — same
    Add/subtract-immediate encoding class (`op=1`); identical SP / `LSL #12`
    semantics; result `read(Rn) - imm`.
  - `MOVZ`, 64-bit (`MOVZ Xd, #imm16{, LSL #0|#16|#32|#48}`) — move-wide, zeroing
    the rest of `Rd`; in this class field 31 is `XZR` (the write is discarded),
    *not* SP.

  Each is a single pure register write with successor `pc+4` and no `NZCV`
  write — translated `T → I_btor2 → L`, cross-checked under `π` by the framework
  oracle.
- **Out of scope → typed hard-abort.** Every other A64 instruction raises
  `unsupported: aarch64:<construct>` at the shared `decode_insn` (one rejection
  point for `T` and the interpreter) — never a silent drop.
- **Shared AArch64 interpreter widened** (`gurdy/languages/aarch64/`,
  interpreter version **`0.2`**) — a strictly **additive** bump of the standalone
  shared deliverable (AGENTS.md §3): the `0.1` `ADD` behavior is byte-for-byte
  unchanged, and the original `ADD`-only `decode` is retained verbatim, so the
  cross-checked **`aarch64-sail`** route is undisturbed until its sibling agent
  mirrors the new ops (the new family is decoded by the new `decode_insn`).
  Observables unchanged: `pc` (byte address), `x0`–`x30`, `sp`, `nzcv` (bv4),
  `halted`. The BTOR2 interpreter is **reused** unchanged.
- **Translation spec:** `gurdy/pairs/aarch64_btor2/SPEC.md` (self-contained;
  rule-for-rule per op, with the A64-vs-RV64 divergence notes the brief asks to
  be auditable — incl. the SP-vs-XZR field-31 distinction).
- **Fidelity:** **`checked`** — evidence is the commuting-square oracle on the
  test corpus (`tests/test_aarch64_btor2_pair.py`), twice-and-diff determinism
  for `T` and the interpreter, carry-back of a BTOR2 witness through `L`, and the
  end-to-end decide→witness→carry-back through `btor2-smtlib` (z3-gated, incl. a
  `MOVZ`+`SUB` program). Honest tier — "validated on the inputs we tried," not
  `proved`.
- **Scope deferred (named future work, not silently dropped):** memory as an
  array, the trap flag, flag-setting forms (`ADDS`/`SUBS`, the `NZCV`
  computation), the 32-bit (`sf=0`) forms, the move-wide siblings `MOVN`/`MOVK`,
  branches/loads/stores, and the C-undefined-but-ISA-defined wedge (`SDIV`
  edges, shift masking, `MUL` truncation) — each lands as a further widening step
  under the coverage ratchet (BENCHMARKS.md §5). The brief's "memory as an array"
  and "trap flag" target state remain in the *design* (`π` already carries
  `nzcv`/`halted`) but only `nzcv`/`halted` are realized in this slice.

### Construct coverage + `unsupported` histogram

Measured over the pair's spec-derived 12-probe slice (`inventory.py`,
`gurdy/pairs/aarch64_btor2`; the denominator is held fixed across widenings so
the ratchet is honest): **8 / 12 probes covered = 0.667** (was `4/12`). The
covered 8 are the in-scope ALU family in its legal forms — `ADD_imm`,
`ADD_imm_lsl12`, `ADD_imm_sp_src`, `ADD_imm_sp_dst`, `SUB_imm`, `SUB_imm_sp`,
`MOVZ`, `MOVZ_lsl16`. The 4 out-of-scope probes each hard-abort, itemized:

| `unsupported` construct | probes blocked |
|--------------------------|---------------:|
| `adds.immediate` (flag-setting) | 1 |
| `add.immediate.w` (32-bit, `sf=0`) | 1 |
| `opcode=0xf9400000` (LDR — memory) | 1 |
| `opcode=0x14000000` (B — control flow) | 1 |

The status stays `partial` until the in-scope set widens toward the brief's
base-ISA target (a machine ISA must fully cover its declared base ISA to reach
`built`, BENCHMARKS.md §5).

### What the open questions taught us (PAIRING.md §9)

- The `riscv-btor2` / `ebpf-btor2` BTOR2-hub shape ports cleanly to a second
  ISA: the BTOR2 core, the PC-keyed ITE dispatch, the `square()` one-cycle
  trace shift, and the `{"reg_eq": [...]}` property hook were reused verbatim;
  only the decoder, the register file (SP vs a zero register), and the
  byte-addressed PC are ISA-specific — confirming the architecture is
  ISA-portable as the brief predicted.
- Keeping `π` carrying `nzcv` from the first slice (even though no in-scope op
  writes it) preserves compatibility with the registered `aarch64-sail` branch
  ahead of time, at no cost.
- **Widening a shared decoder under a branch-agreement constraint.** Because the
  `aarch64-sail` route shares this language's decoder and currently executes only
  `ADD`, widening the *shared* `decode` to accept `SUB`/`MOVZ` would have either
  broken `aarch64-sail`'s rejection gate or silently mis-executed those ops there
  until its sibling caught up. The additive resolution — keep `decode` as the
  `ADD`-only gate, add a richer `decode_insn` for the widened family, and dispatch
  the interpreter/translator on an op tag — lets one pair widen without forcing a
  lockstep change on its branch sibling, which is exactly the AGENTS.md §3
  "versioned, additive shared-interpreter change" the design calls for.
