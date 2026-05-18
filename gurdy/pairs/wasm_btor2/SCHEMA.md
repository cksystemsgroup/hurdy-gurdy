# `wasm-btor2` Schema

Schema-pinned translation contract for the `wasm-btor2` pair.

> **Status**: placeholder. The schema is frozen at version `1.0.0` at
> P1 per `V2_BOOTSTRAP.md` §6. Until P1 lands, this file documents
> only the intended structure.

## 1. Versioning

- `1.0.0` (P1, pending): WASM 1.0 MVP, integer-only seed corpus, BMC
  engine, reach-property `QuestionSpec`.
- Minor bumps: additive features (float opcodes, multi-module, etc.).
- Major bumps: breaking property-shape changes.

Every minor/major bump requires all prior corpus tasks to still align
under the new schema; that's a hard P1 invariant.

## 2. Layered artifact

The translator emits BTOR2 in the layered shape established by
`riscv-btor2` (header / machine / library / dispatch / init /
constraint / bad / binding). Layer linking is handled by
`gurdy/core/layers.py` (copied from `v2-bootstrap` at P0).

## 3. Machine layer (WASM specifics)

See `V2_BOOTSTRAP.md` §3.3 for the topology. Specifics deferred to
P1.

## 4. Library layer

Per-opcode lowering definitions. WASM 1.0 MVP opcode list per
`bench/wasm-btor2/SCOPE.md` §1. Each opcode becomes a parameterized
lowering keyed on operand types. Deferred to P4.

## 5. Out of scope at v1.0.0

Per `bench/wasm-btor2/SCOPE.md` §1: SIMD, threads, reference types
beyond funcref, tail calls, exception handling, GC, component model.
Each of these is a candidate for a future minor schema bump.
