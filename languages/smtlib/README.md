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

*Status: **built (QF_ABV fragment)** — the shared text-I/O + model-evaluation
interpreter is implemented (`gurdy/languages/smtlib/`, tests in
`tests/test_smtlib_interp.py`): a byte-exact s-expression reader/printer
(`sexpr`, `script` — `read_script(t).to_text() == t` round-trips the emitted
scripts), a model reader (`model` — `(model …)` / `get-value` text and the z3
backend's normalized dict), and a deterministic model evaluator (`eval`) over
the `QF_ABV` bit-vector-and-array fragment the `btor2-smtlib` bridge emits, with
operators outside that fragment hard-aborting `unsupported: smtlib:…`. It is
wired as the language's shared target interpreter `I_t` (`interpret`) and reused
by `btor2-smtlib` to **check a `sat` witness** (`reach(...)["smt_model_ok"]`)
before the BTOR2 replay believes it. **Registered next increment (pending): a
`QF_LIA` model evaluator** — extend `eval` (additively, versioned) to linear
integer arithmetic (`Int`; `+`/`-`/`*`-by-constant; `<=`/`<`/`>=`/`>`/`=`/`distinct`;
`ite`; `div`/`mod`) so the shared evaluator can **check a `QF_LIA` `sat`
witness**. This unblocks `crn-smtlib` — whose `QF_LIA` script today returns
`smt_model_ok=None`, forcing a fall-back to source-interpreter replay — and the
registered `python-smtlib` pair. Other pending increments: array-valued model
text beyond `store`/const-array chains, and the **`unsat` proof checkers**
(Carcara/LFSC/`cake_lpr`) of the `proved` tier — see below and
[`HANDOFF.md`](../../HANDOFF.md).*

The deterministic, shared **interpreter** for SMT-LIB is its **text I/O
plus a model evaluator**: a byte-exact printer (and a reader for
models/proofs), and an evaluator that, given a model, substitutes it into a
script and computes its truth. This is the concrete executor `I_t` — it
runs *one* model and is fully deterministic. It is **not** the solver; the
solver is a separate, shared oracle described below.

The "behavior" a pair consumes here is a **model**: the assignment a solver
returns for a `sat` query, which `btor2-smtlib`'s target-to-source
interpreter carries back to a BTOR2 (and thence source-level) behavior. The
model is validated by the deterministic evaluator before it is believed.

## Solvers and witness checkers

SMT-LIB is a reasoning language, so it owns — and shares — solvers and
checkers in addition to the interpreter ([`SOLVERS.md`](../../SOLVERS.md)):

- **Solvers (decide, the oracle).** Bitwuzla, Z3, cvc5, Yices2 over the
  `QF_ABV` / `QF_BV` fragment. Pinned by digest, resource-capped; verdict
  `sat` / `unsat` / `unknown` / `resource-out`. A solver's internal search
  need not be deterministic; its claim is trusted only once re-validated.
- **Witness checkers (verify, deterministic).** A `sat` model is validated
  by **evaluation** (the interpreter above). An `unsat` claim is validated
  by an **independent proof checker** — Carcara on Alethe proofs, an LFSC
  checker, or `cake_lpr` (a *formally verified* LRAT checker) on
  bit-blasted proofs.

Both inventories are shared by every SMT-LIB-targeting pair; a pair wires
none of its own.

*Wired so far:* the shared **solver inventory** (`gurdy/solvers/inventory.py`)
registers **z3**, **bitwuzla**, **boolector**, **cvc5**, **yices2** — z3,
bitwuzla and boolector host-validated, cvc5/yices2 thin gated adapters
(`gurdy/solvers/smt_cli.py`) that activate when present. A `sat` model is checked
by the shared evaluator above. For an `unsat`/`unreachable` claim,
`gurdy/solvers/proved.py` corroborates across **every available engine** —
flagging any disagreement (SOLVERS.md §7) — and emits a bit-blasted **DRAT**
proof (bitwuzla `--write-cnf` → cadical) for an independent
`drat-trim`/`cake_lpr` check (`proved`; gated to the dev image). (boolector and
bitwuzla share lineage, so z3 is the strongest independence axis.)
([#2](https://github.com/cksystemsgroup/hurdy-gurdy/issues/2))

## Pairs over this language

- [`btor2-smtlib`](../../pairs/btor2-smtlib/README.md) — target.
- [`crn-smtlib`](../../pairs/crn-smtlib/README.md) — target.
- [`python-smtlib`](../../pairs/python-smtlib/README.md) — target (registered;
  gated on the `QF_LIA` extension above).
