# Language — SMT-LIB

SMT-LIB is the standard input language of SMT solvers. It is the platform's
**theory-rich reasoning target**: where BTOR2 is a bit-level transition
system, SMT-LIB opens onto the full menu of SMT theories and the mature
solvers that decide them. In the initial registry it is the destination of
the `btor2-smtlib` bridge — the terminal language where a question is
finally decided.

## Formal semantics (source of truth)

The SMT-LIB standard: its sorts, theory signatures, and the satisfiability
semantics of a script (a benchmark is `sat`/`unsat`/`unknown` under the
declared logic). The initial scope is the bit-vector-and-array fragment
that BTOR2 maps onto — `QF_ABV` and neighbors — chosen precisely because it
is the standard counterpart of BTOR2's operators, so the `btor2-smtlib`
translation is rule-for-rule and a native-BTOR2 verdict and a bridged
SMT-LIB verdict on the same system must agree.

A pair states the logic it targets; the language itself is the standard.

## Shared interpreter

**Role: target.** SMT-LIB is, today, only ever a target (its only
registered pair is `btor2-smtlib`).

The "interpreter" for a reasoning language is its **solver(s)** plus the
text I/O around them: a byte-exact SMT-LIB printer (and a reader for
witnesses/models), and a deterministic dispatch to a solver that returns a
verdict and, on `sat`, a model. Determinism here means the *translation to
SMT-LIB* is byte-identical for identical input; a solver's internal search
need not be, but the verdict it returns on a decidable query is, and the
model is carried back through the pair's target-to-source interpreter.

Because SMT-LIB is terminal, the "behavior" most pairs consume is a
**model/witness**: the assignment a solver returns for a `sat` query, which
`btor2-smtlib`'s target-to-source interpreter carries back to a BTOR2 (and
thence source-level) behavior.

## Pairs over this language

- [`btor2-smtlib`](../../pairs/btor2-smtlib/README.md) — target.
