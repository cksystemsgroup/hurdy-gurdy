# `riscv-btor2` v0.3 corpus expansion plan

## Why this exists

The v0.2 corpus (49 tasks, 51 cells) gave the pair every
schema-declared capability axis except one: **engine choice**.
Every BMC task in v0.2 is pinned to `z3-bmc`; every inductive task
is pinned to `z3-spacer`. The other three engines in the
inventory — `bitwuzla`, `cvc5`, `pono` — are present, registered,
and exercised by `oracle_cross.py` (the §9.12 cross oracle), but
not by any task that an LLM under condition B will see.

That is a real coverage gap. The pair documents five engines and
two condition classes (BMC vs inductive); the corpus covers two
engines and two classes. An LLM that *only ever needs to pick
z3-bmc or z3-spacer* will trivially hit the right pin every time.
The benchmark cannot then claim to measure engine-selection
behaviour.

The first move toward closing this — done in v0.3 — is to add a
small number of tasks where engine choice is *empirically* the
right call, not merely a stylistic preference. The empirical
basis is `bench/riscv-btor2/engine_bench.py`'s per-engine wall-
clock comparison on the v0.2 corpus, which shows bitwuzla beating
z3-bmc by 6–13× on every BMC task.

## Acceptance criteria

1. ≥ 1 task pinned to `bitwuzla` whose engine perf records
   bitwuzla ≥ 5× faster than z3-bmc on a 5-sample median.
2. ≥ 1 task pinned to `bitwuzla` whose `bound` ≥ 100 (the high-
   end of the BMC frontier this corpus exercises).
3. Every new task PASSes:
   - `framework_oracle.py` (verdict matches `expected_verdict`),
   - `oracle_cross.py` (cross-engine agreement),
   - `audit_anchors.py` (BMC anchor matches `halted_step ± tol`),
   - `oracle.py` (concrete-trace check).
4. Condition B's prompt (`prompts/condition_b.md`) carries an
   "Engine selection" section that names every engine, its
   verdict vocabulary, and when to pick it. The bitwuzla pin
   on the new tasks then becomes a measurable signal: an LLM
   that read the section will keep the pin (or pick another
   engine for an articulated reason); an LLM that defaults to
   z3-bmc will get the same verdict at ~10× wall-clock.

## v0.3 deltas in this commit

### `0050-deep-mul-chain` — bvmul stress (T2)

Nine sequential `mul x10, x10, x11` over 64-bit registers. Property:
`reg(10) == 39366` at halt PC. Pin: bitwuzla, bound 14. Engine
perf: bitwuzla 7ms vs z3-bmc 77ms (≈11× faster). Why it stresses
BMC: each `mul` produces a polynomial bvmul gate; bitwuzla's word-
level rewriting compresses where z3's bitblasting does not.

### `0051-large-bound-loop-bitwuzla` — large-bound stress (T2)

80-iteration counter loop. Property: `reg(10) == 99` at halt PC.
Pin: bitwuzla, bound 170. Engine perf: bitwuzla 57ms vs z3-bmc
508ms (≈9× faster). Why it stresses BMC: long unrolling, where
z3's bitblasting depth dominates.

Both tasks have the same `task_class` (`register-equality`) and
difficulty (T2) as their v0.1 / v0.2 BMC siblings. The point is
not new lowering surface; the point is the engine pin.

## Framework changes shipped with v0.3

To make these tasks audit-clean:

- `gurdy/pairs/riscv_btor2/lift/witness.py` — bumped the witness
  simulator's `max_steps` from 64 to 256. The cap existed because
  most v0.2 traces fit in 64 steps; 0051 halts at cycle 164 and
  needs the larger cap. No other lifter behaviour changes.
- `bench/riscv-btor2/audit_anchors.py` — for tasks pinned to a
  non-z3-bmc engine, audit_anchors now re-dispatches under
  `z3-bmc` to obtain the lifted trace it needs. The anchor
  concept is engine-independent (which cycle hits `bad_pc`); BMC
  engines that agree on the verdict will agree on the anchor.

## Stream 6 wiring (no LLM run yet)

`prompts/condition_b.md` now ships an "Engine selection" section
between the property DSL and the workflow guidance. It lists every
engine in the inventory with verdict semantics and a one-line
"use it when" rule, citing the v0.2 perf data as the empirical
case for considering bitwuzla over the default z3-bmc.

This is the *prompt half* of Stream 6 (engine-selection
measurement). The *measurement half* — running A and B sweeps
against the v0.3 corpus and looking for whether the LLM keeps the
bitwuzla pin under B — is left as a paid-LLM follow-up. The
infrastructure is ready: same harness, same matcher, same MCP
server; only the corpus tag and the prompt have changed.

## Not in v0.3

- New observables / assumptions / property shapes (v0.2 already
  exercises every declared one above 50% utilisation).
- A second LLM family (still single-vendor; the §7-grade gap from
  v0.1.2 / v0.2 carries forward).
- Multi-seed sweeps (still single-seed; same caveat).
- T4 rubric LLM run (still wired, still unused on the new tasks).
- Condition C operationalisation (Stream 5; deferred to v0.4).

## How to validate v0.3

```sh
# Build the new corpus binaries.
make -C bench/riscv-btor2/corpus 0050-deep-mul-chain 0051-large-bound-loop-bitwuzla

# Pre-flight oracles.
python bench/riscv-btor2/oracle.py
python bench/riscv-btor2/framework_oracle.py
python bench/riscv-btor2/audit_anchors.py
python bench/riscv-btor2/oracle_cross.py

# Engine differentiation evidence.
python bench/riscv-btor2/engine_bench.py --task 0050 --repeat 5
python bench/riscv-btor2/engine_bench.py --task 0051 --repeat 5
```

All four oracles must report no failures. `engine_bench.py` should
record bitwuzla ≥ 5× faster than z3-bmc on each new task.
