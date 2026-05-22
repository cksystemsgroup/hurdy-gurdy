# `evm-btor2` schema

> **Status: pre-release — schema not yet frozen.**
> This document will be filled in during P1 per V2_BOOTSTRAP.md §3.3.
> Schema version begins at `1.0.0` on freeze.

## 1. Versioning

- **Schema version:** `0.0.0` (pre-release, unstable).
- Frankfurt / London EVM (PUSH0 available, EIP-3855).
- Dominant sort: `bv256` for stack slots, storage, arithmetic; `bv8`
  for memory and calldata.

## 2. Scope (planned — P1)

Pure-function contracts: no `CALL`, no `DELEGATECALL`, no
`STATICCALL`.  Single contract, BMC engine, `reach`-property
`QuestionSpec`.

See V2_BOOTSTRAP.md §3.3 for the full translator topology.
