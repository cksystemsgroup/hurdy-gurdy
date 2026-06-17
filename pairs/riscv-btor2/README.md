# Pair — `riscv-btor2`  ·  RISC-V → BTOR2

*Status: **partial** — the **RV64IMC** set is built (`gurdy/pairs/riscv_btor2/`,
tests in `tests/test_riscv_btor2_pair.py`): the base integer instructions
(LUI/AUIPC, JAL/JALR, branches, loads/stores with memory as an `Array bv64
bv8`, OP-IMM[/-32], OP[/-32], FENCE, ECALL/EBREAK), **the M extension**
(MUL/MULH·, DIV·/REM· and their W-variants, with RISC-V's defined
div-by-zero and INT_MIN/-1 results), and **the C extension** (16-bit
compressed instructions, decompressed to their base equivalents so the
variable-length dispatch covers a real `rv64imc` stream) are lowered to a
BTOR2 transition system (PC-keyed ITE dispatch). Ships the target-to-source
interpreter `L`, the projection `π = {pc, x1..x31, halted}`, and an optional
reachability property; construct coverage is 96/96 over the RV64IMC inventory.
The commuting square is validated against the shared RISC-V interpreter across
the instruction set (including real `riscv64-unknown-elf-gcc` ELF binaries),
and reachability is decidable end-to-end via the `btor2-smtlib` bridge.*

Translate a RISC-V program into a BTOR2 transition system whose runs are
exactly the program's architectural executions, so that a model checker can
decide reachability and safety questions about it. The translator is built
**directly from the RISC-V specification** — the rule-for-rule encoding of
each instruction's defined behavior. This is the **direct** arm of the
RISC-V→BTOR2 branch (the other arm goes through Sail); the two are meant to
be cross-checked ([`PATHS.md`](../../PATHS.md) §4–5).

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source language.** RISC-V —
  [`languages/riscv`](../../languages/riscv/README.md).
- **Target language.** BTOR2 —
  [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived, per-instruction lowering from a
  RISC-V image (+ a question's scope) to a BTOR2 transition system: a
  word-level state model (program counter, register file, memory as an
  array, trap flag), a per-PC instruction dispatch, and the init / next /
  constraint / bad declarations a question needs. Deterministic and
  schema-predictable: same image + scope → byte-identical BTOR2.
- **Source interpreter.** The **shared** RISC-V interpreter
  ([`languages/riscv`](../../languages/riscv/README.md)) — reused. If this
  is the first RISC-V pair built, it **contributes** that interpreter.
- **Target interpreter.** The **shared** BTOR2 interpreter
  ([`languages/btor2`](../../languages/btor2/README.md)) — reused. If this
  is the first BTOR2 pair built, it **contributes** that interpreter.
- **Target-to-source interpreter `L`.** Decodes a solver/BTOR2 witness and
  replays it as a RISC-V behavior (initial register/memory state + the run
  that reaches the bad state), so a counterexample is a concrete RISC-V
  execution. Pair-owned.

## Translator detail

The encoding is governed by a written **schema** derived from the RISC-V
specification: one documented lowering per in-scope instruction, every
state-variable convention, every default added at translation time. The
schema is authoritative — code follows schema ([`PAIRING.md`](../../PAIRING.md)
§2). State the in-scope ISA extensions and address width.

## Projection `π`

Post-step program counter, the general-purpose registers, and the halt/trap
flag — the RISC-V interpreter's observables
([`languages/riscv`](../../languages/riscv/README.md)) mapped onto the
corresponding BTOR2 state variables. `π` must be **compatible with the Sail
route's** projection so the branch cross-check is meaningful.

## Fidelity target + evidence

- **Declared: `checked`.** Evidence: the commuting-square oracle walks the
  RISC-V interpreter's trace against `L(I_btor2(T(p)))` step-for-step on a
  corpus, under `π`; every divergence localizes to a step and an observable.
- **Toward `proved`.** Where a question is discharged with an inductive
  invariant / k-induction / DRAT-style result, ship the certificate and an
  independent re-checker; that lifts the relevant answers to `proved`.

## Soundness story

The lowering and the witness replay (`L`) share one source of truth — the
per-instruction encoding — and a cross-check runs both on the same
instruction sequences, asserting agreement under `π`
([`PAIRING.md`](../../PAIRING.md) §6, rule-for-rule case). Additionally, the
**branch** against `riscv-sail`+`sail-btor2` corroborates the whole
translator: two independent encodings of RISC-V into BTOR2 must agree.

## Notes for the implementing agent

- Build BTOR2 text I/O first (round-trip golden tests) if the shared BTOR2
  interpreter does not yet exist; it belongs in
  [`languages/btor2`](../../languages/btor2/README.md), not in this pair.
- Write the schema before the lowering code.
- Keep `π` aligned with the Sail route — coordinate via the shared RISC-V
  observable conventions, since the branch is the point of the pair.
