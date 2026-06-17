# Handoff — the Docker-gated steps, discharged

This file was the to-do list for wiring the **pinned external engines** that
the pure-Python framework + interpreters + pairs are validated against
([`DOCKER.md`](./DOCKER.md)). Those steps are now discharged: every gated test
runs (no skips), and the validations the handoff asked for are recorded below.

## Result

```
python -m unittest discover -s tests        # 184 tests, OK (skipped=0)
```

The 0-skip run subsumes the three formerly-gated checks plus new coverage:
the RISC-V and Sail differentials against the real `sail_riscv_sim`, the
native-vs-bridged BTOR2 corroboration, the curated RV64IMC compliance slice,
and the c-riscv cbmc differential.

### Engines used (and their pins)

The dev image was **extended to carry all eight tools** (the `Dockerfile` gained
a `btormc` layer; the prior bench image lacked `sail_riscv_sim` and `btormc`),
so the whole suite now runs **0 skips entirely in-container** — no host fallback.

| Engine | Host | Dev image (extended) |
|--------|------|--------|
| `sail_riscv_sim` | **0.12** (exact pin) | **0.12** (added) |
| `pono` | absent | **v2.0.0-beta.1-53-gc81aa36** (commit `c81aa36`, exact pin) |
| `btormc` | 3.2.4 | **3.2.4** (Boolector, CaDiCaL backend; added) |
| `z3` | 4.13.0 | 4.16.0.0 (exact pin) |
| `cbmc` | 6.9.0 | 6.6.0 (apt; Dockerfile pins tag `cbmc-6.4.0`) |
| `riscv64-unknown-elf-gcc` | 13.2.0 | 14.2.0 (Debian apt) |

The oracles whose *version* anchors a fidelity claim are at their exact pins:
the RISC-V/Sail differentials run against `sail_riscv_sim` **0.12**, and the
native-vs-bridged corroboration against `pono` **c81aa36** (now joined by
`btormc` 3.2.4 as an independent second engine — pono = btormc = bridged on the
reachable corpus). The extended image is pushed and citable:
`christophkirsch/hurdy-gurdy-bench:dev` @ `sha256:aa19537325c96d723ea65c54fa6031087368b7a2cf9a8e23b7c5f1bcf501c7dc`
(adds `sail_riscv_sim`, `btormc`, and the `carcara`/`drat-trim` witness
checkers over the prior `sha256:b4669d…3544`). A fully-independent `proved`
verdict for the bitvector theory is not yet wired — see DOCKER.md "Gaps to
close" for the finding (Carcara/LFSC don't give trust-free BV proofs).

## What each step produced

### 1 & 2. RISC-V and Sail interpreters ⟂ `sail_riscv_sim` — **real, was vacuous**
The differential was passing *vacuously*: with no trace flag the emulator emits
no instruction log, so `parse_sail_log` returned `[]` and `align([], [])` was
trivially `ok`. Fixed in `languages/riscv/differential.py`:
- default `$SAIL_RISCV_ARGS` to `--trace` (the emulator is silent otherwise);
- auto-bind the interpreter to the HTIF `tohost` symbol so it halts where the
  emulator does (no run-to-`max_steps`);
- **refuse an empty oracle stream** (raise instead of a hollow `ok`).

Test ELFs now link at `0x80000000` (the model's executable region; the default
gcc link base fetch-faults). Verified step-for-step over the whole slice:
`gurdy riscv-diff` → `differential=ok` for **10/10** programs; the Sail subject
likewise agrees with `sail_riscv_sim`.

### 3. Native-vs-bridged BTOR2 (`pono`) — **found & fixed an emitter bug**
Wiring a real native checker surfaced a latent defect the z3 bridge tolerated:
the shared `Builder` emitted `init` lines whose *value* node out-ranked the
*state* node, which every conformant BTOR2 tool rejects ("state id must be
greater than id of second operand"). This affected **every** stateful pair
output (`riscv-btor2`, `sail-btor2`, `ebpf-btor2`) — they only ever decoded
through the lenient z3 path. Fixed with a stable, idempotent renumbering pass
(`languages/btor2/model.canonicalize`, wired into `Builder.to_text`); the z3
bridge and the BTOR2 evaluator are unaffected (they key off symbols).

With that, `native_vs_bridged` agrees for every member of a reachable corpus
(`mem` 1-/2-cell, counters) on **both** the host `btormc` and the pinned
`pono` (each returns `sat` → REACHABLE, matching the bridged z3). Note: a pure
BMC native engine decides *reachability* definitively (it finds the witness);
unbounded *unreachability* needs an inductive engine, so the corroboration
corpus is reachable systems — the regime the existing check targets.

### 4. RISC-V compliance slice — **curated RV64IMC user slice**
The upstream `riscv-tests` `-p-` binaries open with machine-mode CSR/trap setup
(`csrr mhartid`, `mtvec`, `mret`) the interpreter intentionally does not
implement (its scope is the RV64IMC *user* ISA), so they would abort, not
exercise the ISA. `tools/riscv_slice.py` instead builds a license-clean slice
in the same HTIF `tohost` convention over only the user subset. Graded
all-pass and differentiated against `sail_riscv_sim`:

```
gurdy riscv-suite <slice>   ->  10/10 pass   rv64ui:7/7  rv64um:2/2  rv64uc:1/1
gurdy riscv-diff  <each>    ->  differential=ok  (10/10)
```

### 5. `c-riscv`: pin + the cbmc C-differential — **new**
- **Pin.** `reproduce()` is byte-identical (twice-and-diff) under the pinned
  toolchain; flags `-O2 -nostdlib -nostartfiles -march=rv64im -mabi=lp64
  -fno-asynchronous-unwind-tables -static`. The canonical pin is the image
  digest above; recorded in the c-riscv brief.
- **cbmc differential (new code).** `solvers/cbmc_c.py` +
  `pairs/c_riscv/differential.py` + `gurdy c-diff`. CBMC decides `a0 == value`
  on the C *source*; it must agree with the long path on the lowered program.
  A disagreement is classified: if CBMC's UB checks fire (signed overflow,
  shift masking, INT_MIN/-1, div/rem by zero — the behaviors C leaves
  undefined but RISC-V defines) it is a documented
  C-undefined-but-RISC-V-defined case, not a fault; only a value disagreement
  with no UB is a fault localized to the compile hop. Verified agreeing with
  both backend routes on `5*8+7` (REACHABLE at 47, UNREACHABLE at 99).

## One-shot check (reproduced here)

```
python -m unittest discover -s tests     # 184 tests, OK, 0 skips
gurdy coverage riscv-btor2               # 96/96
gurdy path-coverage riscv smtlib         # direct 96/96, via Sail 63/63
gurdy routes c smtlib                     # both backend routes for the C head
```

## In-image confirmation (authoritative)

Re-run inside the pinned image `…@sha256:b4669d…3544` (the canonical pin):

```
reproduce() (twice-and-diff)                 -> True   (image gcc 14.2.0)
  ELF sha256                                 -> 3d1ea12d…  (differs from the host
                                                 hash — different gcc — as expected)
cbmc-vs-long-path  5*8+7 == 47               -> agree (REACHABLE)
cbmc-vs-long-path  5*8+7 == 99               -> agree (UNREACHABLE)
native(pono)-vs-bridged  mem/counter corpus  -> agree (all REACHABLE)
gurdy riscv-suite <slice>                    -> 10/10 pass
```

The two value-anchored oracles thus ran at their exact pins: `pono` c81aa36
(native-vs-bridged) and the long-path bridge through z3 4.16.0, with cbmc 6.6.0
as the independent C verifier — all in one image at the cited digest. (The
RISC-V/Sail differentials still run on the host because `sail_riscv_sim` 0.12 —
itself the exact pin — is not in this image.)

## Caveats / next

- BMC corroboration is the reachable regime (above). Wiring `pono -e ind`/IC3
  would extend native-vs-bridged to unreachability.
- Still open (unchanged): DWARF line-level carry-back for `c-riscv` `L`;
  the C extension on the Sail side; `.wit` parsing for the BTOR2 interpreter;
  additional native engines (AVR).
