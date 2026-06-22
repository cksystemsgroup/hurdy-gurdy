# Pair — `evm-btor2`  ·  EVM → BTOR2

*Status: **partial** — the pure stack/arithmetic slice (`PUSH1`/`PUSH2`/`PUSH4`,
`ADD`/`MUL`/`SUB`, `POP`/`DUP1`, `STOP` over 256-bit words) is built end-to-end
through the commuting square; 9 / 144 spec-derived opcodes covered. Every other
opcode hard-aborts `unsupported: evm:<opcode>`. Not yet `built` (PAIRING.md §1
"start thin"). Built on EVM shared interpreter **v0.2**.*

Translate EVM bytecode (a pure-function, single-contract subset) into a
BTOR2 transition system over 256-bit words and arrays.

## Implemented slice (PAIRING.md §1, §7)

- **Constructs covered end-to-end:** the single-successor bv256 stack family —
  push immediates `PUSH1` (0x60) / `PUSH2` (0x61) / `PUSH4` (0x63), binary
  arithmetic `ADD` (0x01) / `MUL` (0x02) / `SUB` (0x03), stack shuffles `POP`
  (0x50) / `DUP1` (0x80), and `STOP` (0x00) — over a bounded bv256 operand stack
  (`STACK_SIZE = 16`). `SUB` is top-minus-next; `SUB`/`MUL` wrap mod 2²⁵⁶ via
  the native BTOR2 `sub`/`mul` on bv256. Off-the-end execution and stack
  underflow/overflow are EVM exceptional halts (defined edges), distinct from
  the typed `unsupported` abort. No control flow this round (`JUMP`/`JUMPI`,
  `DIV`/`MOD`, memory, storage stay deferred).
- **Files.** Translator `T` + carry-back `L` + coverage inventory + spec:
  `gurdy/pairs/evm_btor2/` (`translate.py`, `lift.py`, `inventory.py`,
  `SPEC.md`, `__init__.py`). Shared EVM interpreter (contributed by this pair,
  first touch): `gurdy/languages/evm/` (`interp.py`, `asm.py`). Tests:
  `tests/test_evm_btor2_pair.py`.
- **Fidelity: `checked`.** The commuting-square oracle validates
  `I_s(p) ≡_π L(I_t(T(p)))` under `π` on the test corpus every run; the emitted
  `bad` is additionally decided through `btor2-smtlib` (z3), with the witness
  replayed back through `L`. Not inflated to `proved`: validated on the inputs
  tried, no all-inputs certificate.
- **Coverage 9 / 144 opcodes (6.3 %).** Covered: `PUSH1`/`PUSH2`/`PUSH4`,
  `ADD`/`MUL`/`SUB`, `POP`/`DUP1`, `STOP`. `unsupported` histogram: every other
  EVM opcode blocks one task — 135 distinct opcodes (`DIV`/`SDIV`/`MOD`/`SMOD`,
  `LT`/`GT`/`EQ`, `AND`/`OR`/`XOR`, `PUSH0` and `PUSH3`/`PUSH5..PUSH32`,
  `DUP2..16`, `SWAP1..16`, `MLOAD`/`MSTORE`, `SLOAD`/`SSTORE`, `JUMP`/`JUMPI`,
  `CALL`/`RETURN`/`REVERT`, …), each ×1 over the inventory's one-probe-per-opcode
  denominator (`gurdy/pairs/evm_btor2/inventory.py`; `coverage()`).

### What this slice taught us (PAIRING.md §9)

- A bounded bv256 stack modeled as fixed state cells `s0..s15` + a depth `sp`
  (rather than a BTOR2 array) keeps the slice purely bit-vector and lets the
  translator and `L` share the exact per-opcode cell-update rule — including
  *not clearing popped cells* — so the square aligns cell-by-cell. Storage /
  byte-memory will need the array path (`languages/btor2` already supports it,
  used by `ebpf-btor2`).
- bv256 round-trips through the shared BTOR2 I/O and evaluator with no special
  casing (confirmed first, per the brief's note), and the `bad` decides cleanly
  through the existing `btor2-smtlib` z3 bridge.
- *Widening round (3/144 → 9/144, interp v0.1 → v0.2):* `MUL`/`SUB` reuse the
  `ADD` lowering verbatim — only the BTOR2 op kind (`add`/`mul`/`sub`) changes,
  and all three wrap mod 2²⁵⁶ natively on bv256, so no masking was needed. `SUB`
  is the one non-commutative case (top minus next), so operand order is part of
  the spec. `POP` is the simplest opcode (only `sp -= 1`; the dropped cell is
  left stale, exactly the cell-update convention `ADD` already relies on).
  `DUP1` is a read-`s{sp-1}`/write-`s{sp}` pair reusing both the index mux and
  the write mux. `PUSH2`/`PUSH4` generalize `PUSH1` by keying the inline-operand
  width (and the `pc` advance) on a single `asm.PUSH_WIDTH` map shared by the
  interpreter and the translator — the only source-of-truth change the widths
  needed. All single-successor, no jump-dest machinery, so the existing PC-keyed
  ITE dispatch absorbed them unchanged.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** EVM — [`languages/evm`](../../languages/evm/README.md).
- **Target.** BTOR2 — [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived per-opcode lowering to a BTOR2
  transition system: a 256-bit stack, byte-addressed memory and
  word-addressed storage as arrays, `pc`, halt/`REVERT`; PC-keyed dispatch;
  init/next/constraint/bad. Deterministic and schema-predictable. Requires
  bv256.
- **Source interpreter.** The **shared** EVM interpreter
  ([`languages/evm`](../../languages/evm/README.md)) — reused; contributed
  by this pair if first.
- **Target interpreter.** The **shared** BTOR2 interpreter — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  an EVM behavior (calldata/environment + the reaching run). Pair-owned.

## Projection `π`

Post-step stack / memory / storage-delta / halt observables (as the EVM
interpreter exposes them) mapped onto the BTOR2 state variables.

*Slice `π` (as built):* `{ pc, sp, s0 … s15, halted }` — the program counter
(a byte offset), the operand-stack depth, the 16 bv256 stack cells, and the
halt flag. Byte-memory and storage-delta observables enter `π` when those
opcodes do (future work).

## Fidelity target + evidence

- **`checked`** — the commuting-square oracle under `π` on a corpus; the
  bv256 + array translator output is additionally corroborated by deciding
  it native-vs-bridged through [`btor2-smtlib`](../btor2-smtlib/README.md)
  ([`SOLVERS.md`](../../SOLVERS.md) §7).
- Certificates lift discharged questions to `proved`.

## Soundness story

Lowering vs. witness replay cross-check under `π`; the shared EVM
interpreter is anchored to **KEVM** (or EVM-Dafny / eth-isabelle) as the
gold reference ([`languages/evm`](../../languages/evm/README.md),
[`PAIRING.md`](../../PAIRING.md) §6).

## Notes for the implementing agent

- v2 absorbed the EVM translator but never registered it as a pair because
  its translator emitted a flat BTOR2 string; the registration work is to
  restructure it into a faithful **layered** artifact ([`ARCHITECTURE.md`](../../ARCHITECTURE.md)).
- Reuse the BTOR2 core; contribute the shared EVM interpreter validated
  against KEVM. Confirm bv256 + arrays round-trip in the BTOR2 I/O first.
