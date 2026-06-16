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

**Role: source and target.** BTOR2 is a *target* of `riscv-btor2` and
`sail-btor2`, and a *source* of `btor2-smtlib`. One interpreter serves all
three — this is the most reused interpreter after RISC-V, and a single
defect in it would surface in three pairs, so it is worth getting exactly
right first.

Contract ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5):

- **Text I/O.** A byte-exact parser and printer for the BTOR2 text format,
  with round-trip golden tests. Nothing downstream can be trusted until
  round-tripping is byte-exact.
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

## Pairs over this language

- [`riscv-btor2`](../../pairs/riscv-btor2/README.md) — target.
- [`sail-btor2`](../../pairs/sail-btor2/README.md) — target.
- [`btor2-smtlib`](../../pairs/btor2-smtlib/README.md) — source.
