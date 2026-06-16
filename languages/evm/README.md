# Language — EVM

Ethereum Virtual Machine bytecode: a 256-bit stack machine, as a
**bytecode** source language. Source of `evm-btor2`. Initial scope is a
pure-function, single-contract subset (a London baseline plus Shanghai
`PUSH0`); calls/storage/gas semantics enter as a pair widens scope.

## Formal semantics (source of truth)

The EVM execution semantics from the Ethereum Yellow Paper and its
successors: a stack of 256-bit words, byte-addressed memory, word-addressed
storage, and the opcode transition relation (including modular 256-bit
arithmetic, `SDIV`/`SMOD` sign rules, `SIGNEXTEND`, and the trap/`REVERT`
behaviors). The authoritative behavior is now best captured by the
mechanized models below.

## Formal model — no Sail, use KEVM (or Dafny/Lem)

EVM is not an ISA Sail targets; its canonical mechanized semantics are:

- **KEVM** — a **K-framework** *complete, executable* EVM semantics. The
  recommended gold oracle and reference interpreter.
- **eth-isabelle** — a **Lem/Isabelle** formalization (all instructions),
  with Isabelle/HOL proofs.
- **EVM-Dafny** — an executable, *verification-friendly* **Dafny**
  semantics.

KEVM is the external oracle for the shared EVM interpreter; an
`evm → kevm-model → …` route is a candidate fidelity-raising branch. The
BTOR2 target needs bv256 and arrays.

## Shared interpreter

**Role: source.** A deterministic EVM executor over an input binding (256-bit
calldata / environment) → a trace of post-step machine states (stack,
memory, storage delta, program counter, halt/`REVERT`) per
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5, validated against KEVM.
Shared by every EVM pair.

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): the official
**`ethereum/tests`** state / VM tests (expected post-state) as a pinned
submodule — the same suite KEVM validates against. Scope the labeled subset
to the pair's pure-function fragment.

## Pairs over this language

- [`evm-btor2`](../../pairs/evm-btor2/README.md) — source.
