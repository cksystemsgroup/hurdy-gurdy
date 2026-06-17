# Language — BTOR2

BTOR2 is a word-level format for **transition systems** over bit-vectors
and arrays, with a small set of state, init, next, constraint, and bad
declarations. It is a **reasoning language**: bit-level model checkers and
bounded model checkers consume it directly. In the registry it is the
common target that RISC-V reaches two ways, and the source of the bridge to
SMT-LIB.

## Formal semantics (source of truth)

The BTOR2 format definition: the sorts (bit-vectors and arrays), the
operators (the standard bit-vector and array operations), and the
transition-system semantics (a model is a sequence of states satisfying
`init` and `next`; a `bad` is reachable iff there is a finite run reaching
a state where the `bad` signal is set). The meaning of a BTOR2 program is
exactly this transition system. Because every operator is a standard
bit-vector/array operator, BTOR2's meaning lines up rule-for-rule with the
corresponding SMT-LIB theory — which is what makes `btor2-smtlib` a
`predicted`/`proved` bridge.

## Shared interpreter

**Role: source and target.** BTOR2 is a *target* of six front-ends
(`riscv-btor2`, `aarch64-btor2`, `wasm-btor2`, `ebpf-btor2`, `evm-btor2`,
`sail-btor2`) and a *source* of `btor2-smtlib`. One interpreter serves them
all — the most reused interpreter on the platform, and a single defect in it
would surface in every BTOR2-targeting pair, so it is worth getting exactly
right first.

Contract ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5):

- **Text I/O.** A byte-exact parser and printer for the BTOR2 text format,
  with round-trip golden tests. Nothing downstream can be trusted until
  round-tripping is byte-exact. Output must also be **native-checker
  conformant** — `model.canonicalize` (wired into `build.Builder.to_text`)
  renumbers so each `init` value precedes its state, which `pono`/`btormc`
  require but the lenient z3 bridge did not ([`HANDOFF.md`](../../HANDOFF.md)
  step 3).
- **Input.** A BTOR2 transition system plus a binding — initial state
  values keyed by symbol and per-step inputs.
- **Behavior.** A trace of **post-step** states: the value of each state
  variable and each `bad` signal after each transition.
- **Observables.** State-variable values and `bad`-signal status per step;
  a pair's projection selects the subset that corresponds to its
  source-level observables.
- **Determinism.** Pure; identical system + binding → identical trace.

The BTOR2 *behavior* is what each BTOR2-targeting pair's target-to-source
interpreter consumes when carrying a witness back to the source level.

## Interpreter build brief

*Status: **partial** — the parser/printer (canonical round-trip) and the
bit-vector + array evaluator (including signed `sdiv`/`srem`) are built
(`gurdy/languages/btor2/`, tests in `tests/test_btor2_interp.py`).
**`.wit` parsing + replay are now built** (`witness.py`,
`tests/test_btor2_witness.py`): a native checker's witness is parsed and
**replayed through the shared interpreter** to confirm a `bad` actually fires —
the positive-side validation of a `reachable` claim (SOLVERS.md §4). The loop is
exercised end-to-end against a real `btormc` (decide → `.wit` → replay reaches
the bad; for a `riscv-btor2` system the run carries back to `x3 == 42`). The
evaluator is arbitrary-precision with width masking, so **wide vectors (bv256,
for `evm-btor2`) and arrays** work with no special casing (locked in
`tests/test_btor2_interp.py`). The `btorsim` / HWMCC differentials are still
pending. A standalone deliverable on the framework MVP-1
([`FRAMEWORK.md`](../../FRAMEWORK.md) §6). Bootstrap-critical — the most reused
interpreter (six BTOR2-targeting pairs).*

- **MVP scope.** A byte-exact BTOR2 **parser/printer** (round-trip golden
  tests first) and a `step(system, binding) -> trace` evaluator over the
  operators the first pairs emit (bit-vectors, arrays, the transition
  declarations). Unsupported operators hard-abort
  ([`BENCHMARKS.md`](../../BENCHMARKS.md) §3).
- **Oracle.** Round-trip equality for I/O; for witness replay, agreement
  with a `btorsim`-style simulation of a solver `.wit`
  ([`SOLVERS.md`](../../SOLVERS.md) §4).
- **Coverage target.** The operator set `riscv-btor2` / `sail-btor2` emit,
  measured against the format's operator inventory; widen to bv256 + arrays
  for `evm-btor2`. Anchor: **HWMCC** ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4).
- **Acceptance.** Deterministic; byte-exact round-trip; a replayed witness
  reproduces the reaching run under the projection.
- **I/O before evaluator** — nothing downstream is trustworthy until parse /
  print is byte-exact ([`PAIRING.md`](../../PAIRING.md) §6).

## Solvers and witness checkers

BTOR2 is a reasoning language, so it owns — and shares — more than the
interpreter ([`SOLVERS.md`](../../SOLVERS.md)):

- **Solvers (decide, the oracle).** BtorMC, Pono, AVR — reachability,
  k-induction, IC3/PDR. Pinned by digest, resource-capped; verdict
  `reachable` / `unreachable` / `unknown` / `resource-out`. A solver may be
  internally non-deterministic; nothing it returns is believed until
  re-validated.
- **Witness checkers (verify, deterministic).** A `reachable` `.wit`
  witness is validated by **replay through the shared interpreter** — the
  positive-side check *is* the commuting square. An `unreachable` claim is
  validated by **re-discharging an inductive invariant or k-induction
  certificate on an independent engine**, or by a `certifaiger`-style
  certificate check.

Both inventories are shared by every BTOR2-targeting pair
(`riscv-btor2`, `sail-btor2`); a pair wires none of its own.

## Pairs over this language

- [`riscv-btor2`](../../pairs/riscv-btor2/README.md) — target.
- [`aarch64-btor2`](../../pairs/aarch64-btor2/README.md) — target.
- [`wasm-btor2`](../../pairs/wasm-btor2/README.md) — target.
- [`ebpf-btor2`](../../pairs/ebpf-btor2/README.md) — target.
- [`evm-btor2`](../../pairs/evm-btor2/README.md) — target.
- [`sail-btor2`](../../pairs/sail-btor2/README.md) — target.
- [`btor2-smtlib`](../../pairs/btor2-smtlib/README.md) — source.
