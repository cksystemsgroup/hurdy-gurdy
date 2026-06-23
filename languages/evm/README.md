# Language — EVM

Ethereum Virtual Machine bytecode: a 256-bit stack machine, as a
**bytecode** source language. Source of `evm-btor2`. Initial scope is a
pure-function, single-contract subset (a London baseline plus Shanghai
`PUSH0`); calls/gas semantics enter as a pair widens scope (persistent
**storage** data — `SLOAD`/`SSTORE`, modeled, not gas-costed — is now in scope).

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

**Interpreter version: v0.7** (a versioned shared-interpreter change,
[`AGENTS.md`](../../AGENTS.md) §3). Covered opcodes (the stack/arithmetic slice
plus byte-addressed memory and persistent storage, over bv256): the **full push
family** `PUSH1` .. `PUSH32` (an `n`-byte big-endian inline immediate), the binary
arithmetic `ADD` / `MUL` / `SUB` (`SUB` is top minus next; all wrap mod 2²⁵⁶), the
**unsigned** `DIV` / `MOD` and the **signed** `SDIV` / `SMOD` (each
division/modulo with the EVM **by-zero = 0** special case —
`DIV(a,0) = MOD(a,0) = SDIV(a,0) = SMOD(a,0) = 0`, not a trap; and `SDIV`
additionally with the **`INT_MIN / -1` = `INT_MIN`** wrap, signed overflow with no
trap), the stack shuffles `POP`, the duplications `DUP1` .. `DUP16` (copy the n-th
item onto the top) and the swaps `SWAP1` .. `SWAP16` (swap the top with the
(n+1)-th item), `STOP`, the **byte-addressed memory ops** `MLOAD` / `MSTORE` /
`MSTORE8` over a zero-initialized, unbounded byte map (`MSTORE`/`MLOAD` move a
32-byte **big-endian** word, `MSTORE8` a single low byte; memory is exposed as a
fixed `MEM_WINDOW = 64`-byte observable `m0 .. m63`), and the **persistent storage
ops** `SLOAD` / `SSTORE` over a zero-initialized 256-bit-key → 256-bit-value map
(`SSTORE key, val` sets `storage[key] := val`, `SLOAD key` pushes `storage[key]`,
0 if never written; storage is exposed as a fixed `STORE_WINDOW = 8`-key
observable `s_at_0 .. s_at_7`). The signed `SDIV`/`SMOD` interpret both operands
as two's-complement and use **truncating** (round-toward-zero) division, with the
remainder of `SMOD` taking the **sign of the dividend**. Stack
underflow/overflow and running off the end are *exceptional halts* (defined
deterministic edges that set `halted`), distinct from an *unsupported opcode* —
every opcode outside the covered set hard-aborts `unsupported: evm:<MNEMONIC>`
(BENCHMARKS.md §3). Control flow (`JUMP`/`JUMPI`), `PUSH0`, `MSIZE`, and EVM gas /
warm-cold accounting / memory-expansion cost are deferred to later rounds.

- **v0.6 → v0.7** added the **persistent storage ops** `SLOAD` / `SSTORE` to the
  v0.6 slice (additive; all v0.6 behavior preserved, no existing rule changed).
  Storage is a zero-initialized 256-bit-key → 256-bit-value `{key: value}` map —
  the word-keyed analogue of memory, but *simpler* (a single read/write, no byte
  assembly): `SSTORE key, val` sets `storage[key] := val`, `SLOAD key` pushes
  `storage[key]` (0 if never written). The post-step **storage observable** is a
  fixed window `s_at_0 .. s_at_7` of the values at keys 0..7 (a bit-vector
  projection of the word map). The one dependent pair (`evm-btor2`) lowers storage
  over a BTOR2 `Array bv256 bv256` (reusing `languages/btor2`'s array support
  unchanged) with the window mirrored as `bv256` states, and re-validates its
  commuting square every run (still green; coverage 76/144 → 78/144). EVM gas /
  warm-cold accounting / refunds are out of scope (the data is modeled, not the
  cost).
- **v0.5 → v0.6** added the **byte-addressed memory ops** `MLOAD` / `MSTORE` /
  `MSTORE8` to the v0.5 slice (additive; all v0.5 behavior preserved, no existing
  rule changed). Memory is a zero-initialized, unbounded `{byte_addr: byte}` map;
  `MSTORE off, val` writes the 32-byte big-endian encoding of `val` (MSB at
  `off`), `MLOAD off` reads it back big-endian onto the stack (never-written
  bytes read 0), `MSTORE8 off, val` writes `val`'s low byte. The post-step
  **memory observable** is a fixed window `m0 .. m63` of the lowest 64 bytes (a
  bit-vector projection of the byte map). The one dependent pair (`evm-btor2`)
  lowers memory over a BTOR2 `Array bv256 bv8` (reusing `languages/btor2`'s array
  support unchanged) with the window mirrored as `bv8` states, and re-validates
  its commuting square every run (still green; coverage 73/144 → 76/144). EVM gas
  / the memory-expansion cost is out of scope (the data is modeled, not the cost).
- **v0.4 → v0.5** added the **signed** `SDIV` / `SMOD` to the v0.4 slice
  (additive; all v0.4 behavior preserved, no existing rule changed). The signed
  ops interpret operands as two's-complement bv256 and use **truncating** (C-style,
  toward-zero) division — *not* Python's flooring `//`/`%`, which would round the
  wrong way for negative operands — so the interpreter implements the quotient as
  `±(abs(a)//abs(b))` (sign = signs differ) and the remainder as `±(abs(a)%abs(b))`
  (sign = sign of `a`). Two EVM special cases: by-zero is `0` (mirroring `DIV`/`MOD`),
  and `SDIV(INT_MIN, -1) = INT_MIN` — signed overflow that *wraps* (`2²⁵⁵` truncated
  to 256 bits is `INT_MIN` itself), explicitly guarded. The one dependent pair
  (`evm-btor2`) lowers these over BTOR2 `sdiv`/`srem` (which already give the same
  truncating, sign-of-dividend results) under the same two guards, and re-validates
  its commuting square every run (still green; coverage 71/144 → 73/144).
- **v0.3 → v0.4** added the **full stack-manipulation family** — the remaining
  push widths `PUSH3`/`PUSH5..PUSH32`, the duplications `DUP2..DUP16`, and the
  swaps `SWAP1..SWAP16` — to the v0.3 slice (additive; all v0.3 behavior
  preserved, no existing rule changed). The widening is *generic*, keyed on the
  index the opcode byte encodes (the shared `asm.PUSH_WIDTH` / `DUP_N` / `SWAP_N`
  maps): PUSH was already width-keyed, `DUP{n}` reads `s{sp-n}` (the `DUP1` rule
  with the read index generalized), and `SWAP{n}` swaps `s{sp-1}` ↔ `s{sp-1-n}`.
  The one dependent pair (`evm-btor2`) re-validates its commuting square every
  run (still green; coverage 11/144 → 71/144).
- **v0.2 → v0.3** added the unsigned `DIV` / `MOD` to the v0.2 slice (additive;
  all v0.2 behavior preserved). EVM by-zero is `0`; for unsigned operands
  Python's flooring `//`/`%` equal truncating unsigned division, so the
  by-zero-guarded `0 if b==0 else a//b` / `a%b` introduces no signed handling.
  The one dependent pair (`evm-btor2`) re-validates its commuting square every
  run (still green).
- **v0.1 → v0.2** added `PUSH2`/`PUSH4`, `MUL`/`SUB`, `POP`/`DUP1` to the
  v0.1 `PUSH1`/`ADD`/`STOP` slice (additive; all v0.1 behavior preserved). The
  one dependent pair (`evm-btor2`) re-validates its commuting square every run
  (still green).

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): the official
**`ethereum/tests`** state / VM tests (expected post-state) as a pinned
submodule — the same suite KEVM validates against. Scope the labeled subset
to the pair's pure-function fragment.

## Pairs over this language

- [`evm-btor2`](../../pairs/evm-btor2/README.md) — source.
