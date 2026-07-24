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
`init` and `next`; a run is **valid** iff every `constraint` signal holds
at every one of its states; a `bad` is reachable iff there is a finite
*valid* run reaching a state where the `bad` signal is set). The meaning
of a BTOR2 program is exactly this transition system. Because every operator is a standard
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
  variable, each `bad` signal, and — when the system declares them — each
  `constraint` signal after each transition. Constraints are **enforced**:
  a row where any constraint is 0 is the run's last (no valid
  continuation — the trace truncates after the violating row), and a
  `bad` counts only on a constraint-valid row (`witness.check_witness`).
  A system with no constraint nodes produces byte-identical traces to the
  pre-enforcement evaluator (the additive guarantee,
  `tests/test_btor2_constraint.py`).
- **Observables.** State-variable values and `bad`/`constraint` signal
  status per step; a pair's projection selects the subset that
  corresponds to its source-level observables.
- **Determinism.** Pure; identical system + binding → identical trace.

The BTOR2 *behavior* is what each BTOR2-targeting pair's target-to-source
interpreter consumes when carrying a witness back to the source level.

**Reduction advisor** (`coi.py`, `gurdy suggest-reduction`; 2026-07-14) —
language-owned, advisory-only analysis guiding the abstraction dial: the
**cone of influence** of a question (closed backwards through `next`/`init`
supports, rooted in the `bad` conditions *and every `constraint`* — a state
gating run validity is never free), the **free havoc set** (bit-vector
states outside the cone: havocking them provably cannot move the question's
signal — an executable claim, locked with a negative control in
`tests/test_reduction_advisor.py`, not just asserted), the **refinement
ladder** (cone states farthest-from-the-question first, the CEGAR order for
`btor2-havoc`), and **interval seeds** (observed `[min, max]` per state over
deterministic + seeded runs — candidates for `btor2-interval`'s declared
ranges, falsifiable by that pair's lax square, exactly its brief's design).
Pure interpreter runs + syntactic analysis: no solver, no registration, no
choice made for the player.

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
`tests/test_btor2_interp.py`). **`constraint` enforcement is built**
(2026-07-13, a strictly additive increment): the evaluator records
`constraint{id}` beside `bad{id}` and truncates at a violating row, witness
replay and `corroborate_unreach` count a `bad` only on constraint-valid rows,
and the SMT bridge encodes the same per-frame reading (bad at step `j` guarded
by constraints at `0..j` — a constraint-free system's emission is
byte-identical); evaluator, bridged z3, and native `btormc` agree on the
constrained corpus, both directions (`tests/test_btor2_constraint.py`). The
`btorsim` / HWMCC differentials are still pending. A standalone deliverable on the framework MVP-1
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

*Wired so far:* **btormc**/**pono** decide reachability (native, gated;
btormc's clean `-kmax` exhaustion reads as bounded-unreachable, guarded by a
reachable-canary negative control); a
`reachable` `.wit` is checked by **interpreter replay** (`witness.py`, above),
and a bounded-`unreachable` verdict is **replay-corroborated** by
`corroborate_unreach` (same module): the strict interpreter runs the system
for the full bound — sampled inputs where the system has any — and no `bad`
may fire.
For `unreachable`, the bounded question is also bridged through `btor2-smtlib`
and run
through the shared `proved` tier (z3+bitwuzla corroboration → bit-blasted DRAT,
[`SOLVERS.md`](../../SOLVERS.md) §5-6). The unbounded inductive-invariant /
k-induction certificate route (re-discharge on an independent engine,
`certifaiger`) and AVR remain deferred
([#2](https://github.com/cksystemsgroup/hurdy-gurdy/issues/2)).

### Standing demand — the campaign's citation (promoted 2026-07-23)

Board entry **`d4c59dafc402`** (kind `native-procedure`, in-set),
derived from the `hwmcc-sosylab-beem` campaign books
(`paper/frontier/results/hwmcc-sosylab-beem/books.jsonl`, iterations
0–2): **31 distinct `btor2` reachability questions**, origin
`campaign`, budgets `{resource-out: 31}`, with the registered
reduction `btor2-havoc` cited **played-and-spent** (iterations 1–2:
free havoc empty on the whole cluster, every counterexample spurious
at the declared 4-round CEGAR cap). The demand names the atlas-charted
family — **"BMC / k-induction / IC3-class model checking"** — behind a
solver brief. The brief regenerates verbatim from the books
(`gurdy frontier-promote d4c59dafc402 --ledger …/books.jsonl`); its
registration is the **`pono`** entry in
[`gurdy/solvers/brief.py`](../../gurdy/solvers/brief.py), per
AGENTS.md §1 extended to solvers (SOLVERS.md §2.1). The binary is
host-built at the bench image's pin (v2.0.0 `c81aa36`), admitted
through the solver gate (`tools/solver_gate.py --engine pono`).

**Take-up.** [`tools/pono_player.py`](../../tools/pono_player.py)
(`frontier_loop.py --engine pono`) plays the brief against the
standing demand: unbounded-first for pins carrying the cost demand,
exact btormc first everywhere else. The portfolio and wall are the
brief's declared budget — as promoted (2026-07-23): `ic3bits` then
`ind` at 300 s per mode × property; **amended 2026-07-24** (after
iteration 3 spent both walls on 28 pins): `ind`, `ic3bits`, `mbic3`
at 600 s per mode × property, `ind` first because iteration 3's only
closure came from it, re-admitted through the gate at the widened
declaration. An unbounded `unreachable` books
`bounded: false` — the claim that closes the question at every depth;
`reachable` is believed only after pono's dumped BTOR2 witness replays
through the shared interpreter (`witness.py`, SOLVERS.md §4); a spent
wall re-books the cost demand citing the spent dials
(`spent_reductions`), so the board's memory survives the engine
change. The unbounded claim's certificate (invariant re-discharge on
an independent engine) stays the deferred upgrade above.

## Pairs over this language

- [`riscv-btor2`](../../pairs/riscv-btor2/README.md) — target.
- [`aarch64-btor2`](../../pairs/aarch64-btor2/README.md) — target.
- [`wasm-btor2`](../../pairs/wasm-btor2/README.md) — target.
- [`ebpf-btor2`](../../pairs/ebpf-btor2/README.md) — target.
- [`evm-btor2`](../../pairs/evm-btor2/README.md) — target.
- [`sail-btor2`](../../pairs/sail-btor2/README.md) — target.
- [`btor2-smtlib`](../../pairs/btor2-smtlib/README.md) — source.
