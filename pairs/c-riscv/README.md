# Pair — `c-riscv`  ·  C → RISC-V

*Status: **partial** — built (`gurdy/pairs/c_riscv/`, tests in
`tests/test_c_riscv.py`): the translator is `riscv64-unknown-elf-gcc` pinned to
a fixed ordered flag list (rv64im, freestanding, no unwind tables / debug
paths), **reproducible** by twice-and-diff. Compiled C runs on the shared
RISC-V interpreter, and a property about the C program is decided end-to-end
through the long path — `c → riscv → btor2 → smtlib` directly and via Sail —
with the two backend routes required to **agree** (the opaque head
re-established downstream). `L` carries a witness back to the enclosing C
function via the symbol table. DWARF line-level carry-back, pinning the
compiler by image digest, and the in-container cbmc differential are the named
pending increments.*

Lift C source to a RISC-V ELF image with a **pinned** C compiler. This is
the platform's highest-altitude pair and the head of the long path to a
solver. Its defining feature is that its translator is **opaque** — nobody
predicts `gcc -O2` from a schema — so its honest fidelity is
`reproducible`, and meaning-preservation is established *downstream* rather
than by reading the translation.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source language.** C — [`languages/c`](../../languages/c/README.md).
- **Target language.** RISC-V —
  [`languages/riscv`](../../languages/riscv/README.md).
- **Translator `T`.** A specific C compiler, pinned **by image digest**,
  with a fixed, ordered flag list and a fixed target (ISA extensions, ABI,
  address width). Determinism is achieved by pinning the toolchain and
  eliminating host leakage (no embedded host paths, fixed source date, a
  fixed in-container build path, source on stdin / ELF on stdout). The
  brief must record the exact digest and flags; "same container ⇒
  byte-identical ELF" is the contract, verified by a twice-and-diff test.
- **Source interpreter.** *None required initially.* A C interpreter is
  deliberately omitted ([`languages/c`](../../languages/c/README.md)):
  faithfulness is checked on the lowered RISC-V program, not by mirroring C
  execution.
- **Target interpreter.** The **shared** RISC-V interpreter
  ([`languages/riscv`](../../languages/riscv/README.md)) — reused, not
  built here.
- **Target-to-source interpreter `L`.** Carries a RISC-V behavior back to
  the C level via the compiler's debug-line information (`RISC-V pc →
  C file:line`), so a result found on the lowered program is reported
  against the C source. Pair-owned.

## Translator detail

Pin by **digest**, not a moving tag. Record: the compiler and version, the
image digest, the exact ordered flags, and the measures that make the ELF
host-independent. Migrating the pin (new compiler version) is a versioned
change that may shift addresses and must re-validate.

## Projection `π`

The C-source observables recoverable from the RISC-V architectural state
via the debug map — primarily the reachability of a designated
source location / trap and the values of named source variables at it.
Because C is opaque, `π` is defined on the RISC-V side and mapped up to C
lines, not defined on a C interpreter's trace.

## Fidelity target + evidence

- **Declared: `reproducible`.** Evidence: the digest pin, the ordered
  flags, and the twice-and-diff reproducibility test.
- **Re-established downstream to `checked`.** On a path, the opaque head's
  fidelity is lifted per-run by a **differential against an independent C
  verifier** on the same source in the same pinned image, and by the
  **RISC-V→BTOR2 branch** ([`PATHS.md`](../../PATHS.md) §3–4). A divergence
  that is *not* explained by a documented C-undefined-but-RISC-V-defined
  behavior is a fault localized to this hop.
- A future C interpreter (built in [`languages/c`](../../languages/c/README.md))
  would let the square be `checked`/`proved` directly; out of initial scope.

## Soundness story

No per-construct schema to mirror (the compiler is opaque). The square is
established at the far end of the path: the shared RISC-V interpreter's
behavior is cross-checked against the BTOR2 route(s)
([`PAIRING.md`](../../PAIRING.md) §6, opaque-head case), and the C-level
differential turns every divergence into either a documented
lowering-sensitive case or a localized fault.

## Notes for the implementing agent

- Reuse the shared RISC-V interpreter; do not build a C interpreter.
- The real work is **reproducibility**: kill every source of host-dependent
  bytes before claiming `reproducible`.
- Build `L` (the debug-line carry-back) so witnesses land on real C lines;
  this is what makes the long path's answers legible.
