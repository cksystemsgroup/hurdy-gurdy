# Pair — `wasm-btor2`  ·  WebAssembly → BTOR2

*Status: **registered** (not yet built). Ported from v2.*

Translate an integer-only WebAssembly 1.0 module into a BTOR2 transition
system. Wasm is attractive here because its **standard is itself a formal
operational semantics** ([`languages/wasm`](../../languages/wasm/README.md)),
so the source side is unusually well-defined.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** WebAssembly — [`languages/wasm`](../../languages/wasm/README.md).
- **Target.** BTOR2 — [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived lowering of the in-scope Wasm subset
  (integer core: locals, linear memory, structured control flow) to a BTOR2
  transition system. Deterministic and schema-predictable.
- **Source interpreter.** The **shared** Wasm interpreter
  ([`languages/wasm`](../../languages/wasm/README.md)) — reused; contributed
  by this pair if first.
- **Target interpreter.** The **shared** BTOR2 interpreter — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  a Wasm stack-machine behavior. Pair-owned.

## Projection `π`

Post-step value stack / locals / linear-memory observables (as the Wasm
interpreter exposes them) mapped onto the BTOR2 state variables.

## Fidelity target + evidence

- **`checked`** — the commuting-square oracle under `π` on a corpus.
  Because the Wasm spec is operational, the interpreter can mirror it
  rule-for-rule and itself be checked against **WasmCert** / the reference
  interpreter — an unusually strong source-side oracle.
- Certificates lift discharged questions to `proved`.

## Soundness story

Lowering vs. witness replay cross-check under `π`; the source interpreter is
independently anchored to the mechanized Wasm spec
([`PAIRING.md`](../../PAIRING.md) §6, [`languages/wasm`](../../languages/wasm/README.md)).

## Notes for the implementing agent

- Reuse the BTOR2 core; contribute the shared Wasm interpreter mirroring the
  official semantics, validated against WasmCert/KWasm.
- A `wasm → wasmcert/kwasm → …` route is a possible fidelity-raising branch.
