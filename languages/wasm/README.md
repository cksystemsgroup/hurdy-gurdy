# Language — WebAssembly (Wasm)

WebAssembly 1.0 (the MVP), as a **bytecode/VM** source language. Source of
`wasm-btor2`. The initial scope is the integer-only core (no floating
point, no GC/reference types, no threads) until a pair widens it.

## Formal semantics (source of truth)

WebAssembly is unusual — and ideal for this platform — in that its **official
standard *is* a formal small-step operational semantics**. A Wasm module's
meaning is defined by the spec's reduction rules over a stack machine with
typed values, linear memory, and structured control flow. There is no
undefined behavior to reconcile the way C/ISA pairs have; the gap a Wasm
pair exploits is between a high-level intuition and the precise spec.

## Formal model — no Sail (Sail targets ISAs), but strong mechanizations

Wasm has no Sail model (Sail describes hardware ISAs), but its official
formal semantics has been **mechanized** more completely than almost any
other language:

- **WasmCert-Isabelle** and **WasmCert-Coq** — mechanized Wasm 1.0 with
  *verified executable interpreters*.
- **KWasm** — a K-framework mechanization, tested against the official
  conformance suite.

Any of these is a gold oracle for the shared Wasm interpreter below, and a
candidate second route (`wasm → wasmcert/kwasm → …`) for a fidelity-raising
branch. Recommended: track the **official spec interpreter / WasmCert** as
the reference.

## Shared interpreter

**Role: source.** A deterministic executor of the in-scope Wasm subset over
an input binding → a trace of post-step stack-machine states (value stack,
locals, linear memory, program counter / control stack), per
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5. Because the spec is itself
operational, the interpreter can mirror it rule-for-rule and be checked
against WasmCert / the reference interpreter. Shared by every Wasm pair.

*Status: **partial** (interp v0.5) — the integer value-stack core at **two
widths** (i32 and i64) over a straight-line function body is built
([`gurdy/languages/wasm/`](../../gurdy/languages/wasm/), contributed by the
`wasm-btor2` slice), mirroring the official operational semantics rule-for-rule:
the operand producers `i32.const` / `i64.const` / `local.get` (a local declares
its width), the conditional `select`, the unary comparisons `i32.eqz` /
`i64.eqz`, the full **binary-operator family at each width** —
`{i32,i64}.add`/`sub`/`mul`/`and`/`or`/`xor`, the shifts `shl`/`shr_u`/`shr_s`
(shift amount taken mod the width — mod 32 for i32, mod 64 for i64), and the
comparisons `eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}` (the `_s`
variants two's-complement signed; **every comparison yields an i32** result at
both widths) — and the **division / remainder family** `{i32,i64}.div_s`/`div_u`/
`rem_s`/`rem_u` with the Wasm **trap** semantics (a zero divisor — and `div_s`
signed overflow `INT_MIN / −1` — traps, setting a `trapped` observable, a
*defined* halt; `rem_s` of `INT_MIN % −1` is `0`, no trap). The value stack
carries two widths. Post-step observables are `pc / halted / trapped / sp /
stack / locals` (stack/local values are width-masked integers; `trapped` flags a
defined div/rem trap, distinct from a normal off-the-end halt). Every other
opcode hard-aborts with a typed `Unsupported`
([`BENCHMARKS.md`](../../BENCHMARKS.md) §3). The `0.4 → 0.5` bump (AGENTS.md §3)
added the **div/rem trap family** **additively** — no existing rule's value
changed and the `trapped` field defaults `False` on every prior state, so the
dependent `wasm-btor2` square re-validated green (earlier bumps: `0.3 → 0.4` the
i64 value type, `0.2 → 0.3` the i32 binop family, `0.1 → 0.2` `select` (`0x1b`) +
`i32.eqz` (`0x45`)). WasmCert / `.wast` anchoring and the rest of the integer
core (rotates, the i32↔i64 width conversions, control flow, linear memory) are
pending.*

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): the **official
WebAssembly spec tests** (`.wast` conformance, expected results) as a pinned
submodule — the same suite WasmCert/KWasm use — plus **wasm-smith** for
fuzz/mutation coverage. Includes rejection (invalid-module) cases.

## Pairs over this language

- [`wasm-btor2`](../../pairs/wasm-btor2/README.md) — source.
