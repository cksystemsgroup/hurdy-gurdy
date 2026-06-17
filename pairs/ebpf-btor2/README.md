# Pair — `ebpf-btor2`  ·  eBPF → BTOR2

*Status: **partial** — the ALU / jump / load-store core is built
(`gurdy/pairs/ebpf_btor2/`, tests in `tests/test_ebpf_btor2_pair.py`): ALU64
and ALU32 (reg/imm, with 32-bit zero-extension and the eBPF-defined
`DIV`/0 -> 0 and `MOD`/0 -> destination-unchanged edges), the conditional
jumps (JMP/JMP32) plus `JA` and `EXIT`, `LDDW`, and the MEM-mode loads/stores
are lowered to a BTOR2 transition system (PC-keyed ITE dispatch over
`r0`–`r10`, data memory as an `Array bv64 bv8`). Construct coverage is
109/109 over the spec-derived inventory; the commuting square is validated
against the shared eBPF interpreter, and the emitted `bad` is decided
end-to-end through the `btor2-smtlib` bridge. `CALL` (helper calls),
byte-swap (`END`), and the legacy `ABS`/`IND` packet loads remain the named
pending increments and hard-abort. Ported from v2.*

Translate eBPF bytecode into a BTOR2 transition system. Initial scope is the
arithmetic / jump / load-store core; unsupported opcodes (e.g. `CALL`) abort
loading rather than translate unsoundly.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** eBPF — [`languages/ebpf`](../../languages/ebpf/README.md).
- **Target.** BTOR2 — [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived per-opcode lowering from eBPF bytecode
  (+ scope) to a BTOR2 transition system: state for `r0`–`r10`, a bounded
  stack/memory as an array, `pc`, a halt flag; PC-keyed dispatch;
  init/next/constraint/bad. Deterministic and schema-predictable.
- **Source interpreter.** The **shared** eBPF interpreter
  ([`languages/ebpf`](../../languages/ebpf/README.md)) — reused; contributed
  by this pair if first.
- **Target interpreter.** The **shared** BTOR2 interpreter — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  an eBPF behavior (entry registers + the reaching run / halt cycle).
  Pair-owned.

## Projection `π`

Post-step `r0`–`r10`, memory observables, and halt — the eBPF interpreter's
observables mapped onto the BTOR2 state variables.

## Fidelity target + evidence

- **`checked`** — the commuting-square oracle under `π` on a corpus.
- Certificates lift discharged questions to `proved`.

## Soundness story

Lowering vs. witness replay cross-check under `π`; the shared eBPF
interpreter is anchored to **CertrBPF** (the Coq rBPF reference) or the
kernel interpreter ([`languages/ebpf`](../../languages/ebpf/README.md),
[`PAIRING.md`](../../PAIRING.md) §6).

## Notes for the implementing agent

- Reuse the BTOR2 core; contribute the shared eBPF interpreter validated
  against CertrBPF.
- Keep unsupported opcodes a hard load-time abort — never a silent unsound
  lowering.
