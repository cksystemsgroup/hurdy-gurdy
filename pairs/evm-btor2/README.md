# Pair — `evm-btor2`  ·  EVM → BTOR2

*Status: **registered** (absorbed in v2, not previously a registered pair).
Not yet built.*

Translate EVM bytecode (a pure-function, single-contract subset) into a
BTOR2 transition system over 256-bit words and arrays.

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
