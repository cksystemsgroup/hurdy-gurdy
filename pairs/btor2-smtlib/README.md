# Pair — `btor2-smtlib`  ·  BTOR2 → SMT-LIB

*Status: **partial** — the bridge is built (`gurdy/pairs/btor2_smtlib/`, tests
in `tests/test_btor2_smtlib.py`): a BTOR2 transition system is unrolled to
bound `k` as `QF_ABV` SMT-LIB (`predicted` — byte-determined by `(system,
k)`), decided with the z3 `SolverBackend`, and on `sat` the witness is
replayed through the shared BTOR2 interpreter to confirm a `bad` is reached
(SOLVERS.md §4-5). Demonstrated end-to-end via RISC-V and eBPF → BTOR2 →
SMT-LIB → z3; the full RV64IMC and eBPF operator sets (incl. signed div/rem,
the 128-bit multiplies behind MULH, and memory arrays) bridge with no loss
(composed coverage 96/96 and 118/118). **Array-witness decoding** is built
(`tests/test_btor2_smtlib_depth.py`): an array-valued initial state — the
const-array default and the explicit stores — is decoded from the z3 model and
replayed, so a witness that depends on initial memory is confirmed faithfully.
The **native-vs-bridged** cross-check is wired (`native_vs_bridged` runs the
native `btormc` and requires its verdict to match the bridged z3 one); running
it in-container against the pinned `btormc` is the remaining step.
**Construct coverage 56/56 = 100%** of BTOR2's operator/sort/directive
inventory (`inventory.py`, `gurdy coverage btor2-smtlib`,
`tests/test_btor2_smtlib_inventory.py`) — the finite-bridge floor
([`BENCHMARKS.md`](../../BENCHMARKS.md) §5). Reaching it closed two latent
holes: `redxor` (formerly a hard-abort) now lowers to a parity xor-fold, and a
BTOR2 `constraint` (formerly **silently dropped**, a soundness leak) is now
genuinely bridged — since 2026-07-13 with the **per-frame reading**: a `bad`
at step `j` counts only with every constraint holding at steps `0..j`
(asserting constraints globally over `0..k` instead masked a bad reached on
a valid prefix before a later, inevitable violation, and disagreed with
`btormc`/`pono` on exactly that system; constraint-free emission is
byte-for-byte unchanged — `tests/test_btor2_constraint.py`). On `sat`, the
model is additionally checked
by the **shared SMT-LIB evaluator** (`reach(...)["smt_model_ok"]`,
[`languages/smtlib`](../../languages/smtlib/README.md)) before the BTOR2
replay — an independent witness check at the SMT level.
The **unreachable** counterpart `prove(system, k)` is wired
(`gurdy/solvers/proved.py`): it corroborates the `unsat` across two independent
SMT engines (z3 + **bitwuzla**) → `checked`, and produces a bit-blasted **DRAT**
certificate (bitwuzla `--write-cnf` → cadical) whose independent check
(`drat-trim`/`cake_lpr`) upgrades it to `proved`; the checker is gated to the dev
image, so on the host the certificate is produced and the result records
`proved`-pending with its TCB
([#2](https://github.com/cksystemsgroup/hurdy-gurdy/issues/2)).*

A **reasoning-to-reasoning** bridge: unroll a BTOR2 transition system to a
bound `k` and emit an SMT-LIB script that is `sat` iff a `bad` is reachable
within `k` steps. Because every BTOR2 operator maps to the standard SMT
bit-vector/array operator a native BTOR2 solver also uses, the bridged
verdict and a native BTOR2 verdict on the same system **must agree** —
deciding one question two ways is itself a cross-check. This edge connects
the bit-level hub (BTOR2) to the theory-rich hub (SMT-LIB).

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source language.** BTOR2 —
  [`languages/btor2`](../../languages/btor2/README.md).
- **Target language.** SMT-LIB —
  [`languages/smtlib`](../../languages/smtlib/README.md).
- **Translator `T`.** A rule-for-rule, bound-`k` unrolling: each BTOR2 sort
  to its SMT-LIB sort, each operator to its standard SMT-LIB counterpart,
  the transition system to an unrolled formula whose satisfiability is
  bad-state reachability within `k`. `k` is a caller-supplied parameter, not
  a heuristic. Deterministic and **schema-predictable**: same system + `k` →
  byte-identical SMT-LIB.
- **Source interpreter.** The **shared** BTOR2 interpreter
  ([`languages/btor2`](../../languages/btor2/README.md)) — reused.
- **Target interpreter.** SMT-LIB's solver-backed evaluator
  ([`languages/smtlib`](../../languages/smtlib/README.md)) — reused; the
  "behavior" is a verdict and, on `sat`, a model.
- **Target-to-source interpreter `L`.** Decodes an SMT-LIB model into a
  BTOR2 behavior — the per-step state assignment and the reached bad state —
  i.e. the same witness shape a native BTOR2 solver would produce. Pair-owned.

## Translator detail

The mapping is the standard BTOR2↔SMT-LIB correspondence; the only
parameter is the unrolling bound `k`. State the SMT-LIB logic targeted
(the bit-vector-and-array fragment). No adaptive choice enters the bytes.

## Projection `π`

The BTOR2 state-variable values and bad-signal status per step
([`languages/btor2`](../../languages/btor2/README.md)) — i.e. the bridged
model, decoded by `L`, must reproduce the same per-step BTOR2 behavior a
native solver's witness would, and the **verdict** must match the native
BTOR2 verdict.

## Fidelity target + evidence

- **Declared: `predicted`.** The SMT-LIB is determined byte-for-byte by the
  BTOR2 system, `k`, and the documented operator mapping.
- **`proved` on the operator mapping.** Each BTOR2-operator-to-SMT-operator
  equivalence is a standard, checkable fact; ship it as the certificate that
  the bridge preserves meaning, and use the **native-vs-bridged verdict
  agreement** as the per-run check.

## Soundness story

Byte-prediction plus the native-vs-bridged cross-check: decide a BTOR2
system both with a native BTOR2 solver and through this bridge; the verdicts
must agree, and on `sat` the decoded models must describe the same run. A
disagreement localizes either to this translator or to a solver and is a
real bug ([`PAIRING.md`](../../PAIRING.md) §6).

## Notes for the implementing agent

- Reuse the shared BTOR2 interpreter and I/O; this pair adds no BTOR2 core.
- The bridge doubles as a **cross-checker for every pair that targets
  BTOR2** (`riscv-btor2`, `sail-btor2`): it corroborates their output by
  deciding it two ways. Build it with that second role in mind.
