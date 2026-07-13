# Handoff

This file is the transfer point for work that needs a differently-equipped
machine than the session that queued it. One open section, then the
discharged record.

## Open — one residue: delete a stale remote branch (needs the human)

- Delete the stale remote branch `claude/llm-hurdy-gurdy-graphs-3gg1rn`
  (superseded by `potential`). Two sessions have now failed on
  permissions: the cloud session could push but not delete (403), and
  the 2026-07-13 host session's permission gate requires the human to
  name the deletion explicitly. One command:
  `git push origin --delete claude/llm-hurdy-gurdy-graphs-3gg1rn`.

## Discharged — the `potential` branch's toolchain-gated steps (2026-07-13)

*Queued 2026-07-13 from a cloud session (no Lean, no LaTeX in that
container); discharged the same day on the host (Lean 4.31.0 via elan,
latexmk 4.79). Context: branch `potential` admitted **directional (lax)
squares** — a pair declares `direction: exact | over`; an `over` pair is
an abstraction checked as an exact square along its **witness
embedding**; universal verdicts transfer across `over` hops, existential
ones only ever by source replay. First inhabitant: the endo-pair
`btor2-havoc`. The standing constraint held throughout: the POPL
submission stays frozen; every paper edit sits inside `\ifarxiv … \fi`,
and only `arxiv.pdf` was rebuilt and committed, never `main.pdf`.*

### Result

```
lake build (paper/mechanization)         # green, no sorries, audit clean
python -m unittest discover -s tests     # 1349 tests, OK (skipped=3) — matches queue-time baseline
```

### 1. Lax extension mechanized (`prop:lax`) — commit `95ef17b`

`Calculus/Lax.lean` mechanizes Def. 3.10 / Prop. 3.11 exactly as
queued: `Direction` as data with `comp` the meet on `exact > over`; a
directional pair (`DPair`) as a `Pair` plus the witness embedding on
closing valuations; `LaxFaithfulAt` as the closed *exact* square along
`W`, with open programs as valuation-indexed families (the
`EndToEnd.lean` convention); (i) `lax_pasting` (binary) and
`DRoute.lax_route_pasting` (telescoped, over `OLang`/`DRoute` extending
`ILang`), composed embedding, exact hop = identity embedding
(`laxFaithful_of_faithful`), plus `DRoute.direction_exact_iff` ("exact
iff every hop is"); (ii) `lax_universal_transfer` as the contrapositive
one-liner. Audit footprint (printed at build): `laxFaithful_of_faithful`
axiom-free; `lax_pasting`, `direction_exact_iff`,
`lax_universal_transfer` `propext`-only; `lax_route_pasting` adds
`Quot.sound` — exactly the exact telescope's footprint. On green, the
queued doc updates landed: `conclusion.tex` (lax out of the paper-stated
list, future-work line retired — both inside `\ifarxiv`), `calculus.tex`
`sec:lax` closing paragraph (telescope covered), the mechanization
README (map rows + audit), `paper/README.md` (prop:lax mechanized).

### 2. arXiv PDF rebuilt, freeze guard proven — commit `1fd4167`

`make arxiv.pdf` only. The new subsection landed as **Definition 3.10 /
Proposition 3.11** (subsection 3.4, page 6 — confirmed in `arxiv.aux`),
with prior numbering spot-checked unmoved (3.7, 3.9, 4.7–4.9). The
guard was proven, not assumed: `main.pdf` was rebuilt from the same
sources, its extracted text layer diffed **byte-identical** against the
committed submission snapshot (22 pages; crosswalk check green, 9
frozen references), then restored via `git checkout -- main.pdf`.
`paper/README.md`'s "Post-`arxiv.1` sources" note trimmed accordingly.
(`make arxiv-dist` for the source bundle remains available if a new
arXiv revision is uploaded.)

### 3. Second directional pair registered: `btor2-interval` — commit `7c1aa46`

Of the two named candidates, the **interval abstraction** was
registered (brief at `pairs/btor2-interval/README.md` + REGISTRY.md
row, status *registered*, brief only) — chosen over liveness-to-safety
because it corroborates the direction axis itself: a second `over`
endo-pair whose witness embedding is genuinely different (the affine
decode `v ↦ v − lo`, not havoc's copy-through), and whose lax square
*is* a falsifiable interval claim — too tight fails the square (widen),
too loose yields spurious counterexamples (tighten), bracketing a CEGAR
ladder from havoc (full range) down to constant pinning (singleton).
Design pinned in the brief: no `constraint` nodes (the shared evaluator
parses but does not enforce them — the range lives in the `next`
arithmetic `lo + urem(iv, hi−lo+1)`, already decided by the shared
evaluator unchanged); full-range special-cased to havoc's rewrite;
fresh ids a pure function of the source text. Registration was covered
by the repo owner's explicit instruction to execute this handoff's Open
section; **liveness-to-safety remains the other named candidate,
deliberately unregistered** (an `exact` endo-pair is a work-queue
commitment the axis does not need for corroboration).

### Housekeeping residue

The stale-branch deletion could not be performed from this session
either (permission gate) — moved back to the Open section above with
the exact command for the human.

## Discharged — the Docker-gated engine steps (2026-07)

This file was the to-do list for wiring the **pinned external engines** that
the pure-Python framework + interpreters + pairs are validated against
([`DOCKER.md`](./DOCKER.md)). Those steps are now discharged: every gated test
runs in the equipped dev image, and the validations the handoff asked for are
recorded below.

### Result

```
python -m unittest discover -s tests        # 1215 tests, OK (host skipped=3, dev-image-gated; count grows — trust the command)
```

The in-image run subsumes the three formerly-gated checks plus new coverage:
the RISC-V and Sail differentials against the real `sail_riscv_sim`, the
native-vs-bridged BTOR2 corroboration, the curated RV64IMC compliance slice,
and the c-riscv cbmc differential.

#### Engines used (and their pins)

The dev image was **extended to carry all eight tools** (the `Dockerfile` gained
a `btormc` layer; the prior bench image lacked `sail_riscv_sim` and `btormc`),
so the whole suite now runs entirely in-container with **at most 1 legitimate
skip** (the host-only checker-absent test) — no host fallback (DOCKER.md).

| Engine | Host | Dev image (extended) |
|--------|------|--------|
| `sail_riscv_sim` | **0.12** (exact pin) | **0.12** (added) |
| `pono` | absent | **v2.0.0** (commit `c81aa36`, exact pin) |
| `btormc` | 3.2.4 | **3.2.4** (Boolector, CaDiCaL backend; added) |
| `z3` | 4.13.0 | 4.16.0.0 (exact pin) |
| `cbmc` | 6.9.0 | 6.6.0 (apt; Dockerfile pins tag `cbmc-6.4.0`) |
| `riscv64-unknown-elf-gcc` | 13.2.0 | 14.2.0 (Debian apt) |

The oracles whose *version* anchors a fidelity claim are at their exact pins:
the RISC-V/Sail differentials run against `sail_riscv_sim` **0.12**, and the
native-vs-bridged corroboration against `pono` **c81aa36** (now joined by
`btormc` 3.2.4 as an independent second engine — pono = btormc = bridged on the
reachable corpus). The image is pushed and citable, now a canonical
**multi-arch (amd64 + arm64)** build from the Dockerfile via the `dev-image` CI
workflow: `christophkirsch/hurdy-gurdy-bench:dev` @ `sha256:b5e944862e4290e7820cd3ae00addc966cf95826b6a1f5d0e158ce6d4e94bed5`
(adds `cadical` over `sha256:aa19537…`, which added `sail_riscv_sim`, `btormc`,
and the `carcara`/`drat-trim` witness checkers over `sha256:b4669d…3544`). A
fully-independent `proved` verdict for the bitvector theory **is now wired** via
route (a) — `prove(x*x==3)` → `tier=proved`, drat-trim `VERIFIED`, on **both
arches** of this image
(see DOCKER.md "Gaps to close" and [#2](https://github.com/cksystemsgroup/hurdy-gurdy/issues/2));
the Carcara/LFSC BV-proof limitation still stands, and route (b)
(`certifaiger`) is future.

### What each step produced

#### 1 & 2. RISC-V and Sail interpreters ⟂ `sail_riscv_sim` — **real, was vacuous**
The differential was passing *vacuously*: with no trace flag the emulator emits
no instruction log, so `parse_sail_log` returned `[]` and `align([], [])` was
trivially `ok`. Fixed in `gurdy/languages/riscv/differential.py`:
- default `$SAIL_RISCV_ARGS` to `--trace` (the emulator is silent otherwise);
- auto-bind the interpreter to the HTIF `tohost` symbol so it halts where the
  emulator does (no run-to-`max_steps`);
- **refuse an empty oracle stream** (raise instead of a hollow `ok`).

Test ELFs now link at `0x80000000` (the model's executable region; the default
gcc link base fetch-faults). Verified step-for-step over the whole slice:
`gurdy riscv-diff` → `differential=ok` for **10/10** programs; the Sail subject
likewise agrees with `sail_riscv_sim`.

#### 3. Native-vs-bridged BTOR2 (`pono`) — **found & fixed an emitter bug**
Wiring a real native checker surfaced a latent defect the z3 bridge tolerated:
the shared `Builder` emitted `init` lines whose *value* node out-ranked the
*state* node, which every conformant BTOR2 tool rejects ("state id must be
greater than id of second operand"). This affected **every** stateful pair
output (`riscv-btor2`, `sail-btor2`, `ebpf-btor2`) — they only ever decoded
through the lenient z3 route. Fixed with a stable, idempotent renumbering pass
(`gurdy/languages/btor2/model.canonicalize`, wired into `Builder.to_text`); the z3
bridge and the BTOR2 evaluator are unaffected (they key off symbols).

With that, `native_vs_bridged` agrees for every member of a reachable corpus
(`mem` 1-/2-cell, counters) on **both** the host `btormc` and the pinned
`pono` (each returns `sat` → REACHABLE, matching the bridged z3). Note: a pure
BMC native engine decides *reachability* definitively (it finds the witness);
unbounded *unreachability* needs an inductive engine, so the corroboration
corpus is reachable systems — the regime the existing check targets.

#### 4. RISC-V compliance slice — **curated RV64IMC user slice**
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

#### 5. `c-riscv`: pin + the cbmc C-differential — **new**
- **Pin.** `reproduce()` is byte-identical (twice-and-diff) under the pinned
  toolchain; flags `-O2 -nostdlib -nostartfiles -march=rv64im -mabi=lp64
  -fno-asynchronous-unwind-tables -static`. The canonical pin is the image
  digest above; recorded in the c-riscv brief.
- **cbmc differential (new code).** `gurdy/solvers/cbmc_c.py` +
  `gurdy/pairs/c_riscv/differential.py` + `gurdy c-diff`. CBMC decides `a0 == value`
  on the C *source*; it must agree with the long route on the lowered program.
  A disagreement is classified: if CBMC's UB checks fire (signed overflow,
  shift masking, INT_MIN/-1, div/rem by zero — the behaviors C leaves
  undefined but RISC-V defines) it is a documented
  C-undefined-but-RISC-V-defined case, not a fault; only a value disagreement
  with no UB is a fault localized to the compile hop. Verified agreeing with
  both backend routes on `5*8+7` (REACHABLE at 47, UNREACHABLE at 99).

### One-shot check (reproduced here)

```
python -m unittest discover -s tests     # 1215 tests, OK (host skipped=3; count grows)
gurdy coverage riscv-btor2               # 96/96
gurdy route-coverage riscv smtlib         # 96/96 along both routes
gurdy routes c smtlib                     # both backend routes for the C head
```

### In-image confirmation (authoritative)

Re-run inside the pinned image `…@sha256:b4669d…3544` (the layer this
confirmation was recorded in; the current canonical multi-arch image is
`…@sha256:b5e94486…`, which adds csmith/cadical/boolector over it — the gcc/cbmc
toolchain is unchanged, so the reproduce() hashes below still hold):

```
reproduce() (twice-and-diff)                 -> True   (image gcc 14.2.0)
  ELF sha256                                 -> 3d1ea12d…  (differs from the host
                                                 hash — different gcc — as expected)
cbmc-vs-long-route  5*8+7 == 47               -> agree (REACHABLE)
cbmc-vs-long-route  5*8+7 == 99               -> agree (UNREACHABLE)
native(pono)-vs-bridged  mem/counter corpus  -> agree (all REACHABLE)
gurdy riscv-suite <slice>                    -> 10/10 pass
```

The two value-anchored oracles thus ran at their exact pins: `pono` c81aa36
(native-vs-bridged) and the long-route bridge through z3 4.16.0, with cbmc 6.6.0
as the independent C verifier — all in one image at the cited digest. (The
RISC-V/Sail differentials still run on the host because `sail_riscv_sim` 0.12 —
itself the exact pin — is not in this image.)

### Caveats / next

- **`proved` tier → wired and demonstrated in-image, [#2](https://github.com/cksystemsgroup/hurdy-gurdy/issues/2) part 1 closed.**
  The `proved`-tier *unreachability* pipeline is built
  (`gurdy/solvers/proved.py`, `btor2-smtlib.prove`): multi-engine corroboration
  (z3 vs **bitwuzla**) → `checked`, plus a bit-blasted **DRAT** certificate
  (bitwuzla `--write-cnf` → cadical → DRAT) **independently checked by drat-trim**
  → `proved`. Run authoritatively **in the dev image**: `prove(x*x==3, 1)` →
  `tier=proved`, `checker_ok=True`, `tcb={bitwuzla:bit-blast, drat-trim}`,
  drat-trim `VERIFIED` (`tests/test_proved.py::TestDratCertificate`, gated). This
  needed **`cadical`** (the DRAT producer the image built for btormc but
  discarded) — now a pinned apt layer in the `Dockerfile` next to `drat-trim`.
  The SMT **solver inventory** is now broadened
  (`gurdy/solvers/inventory.py`, `smt_cli.py`): **boolector** joins z3+bitwuzla as
  a host-validated third engine, and **cvc5**/**yices2** are thin gated adapters
  that activate when present; corroboration spans every available engine and flags
  disagreement. Still deferred under #2: cvc5/yices2 *binaries* in the image, **AVR**
  (BTOR2 — needs the tool to build a correct adapter), and `certifaiger`/LFSC.
  Known TCB caveat:
  the BV→CNF bit-blaster is trusted (drat-trim certifies the CNF, not the
  blasting) — short of trust-free BV, recorded in every `proved` result's `tcb`.
- BTOR2 `.wit` parsing/replay is now **done** (`gurdy/languages/btor2/witness.py`):
  a native checker's witness replays through the shared interpreter to confirm
  the reaching run, validated end-to-end against a real `btormc`.
- Both formerly-open spine increments are now **done**: the Sail **C
  (compressed)** extension landed (sail-btor2 and the via-Sail route are full
  RV64IMC, 95/95), and **DWARF line-level carry-back** for `c-riscv` `L` is built
  (`gurdy/pairs/c_riscv/lift.py::c_line_at` — a parallel `-g` build, byte-identical
  in code to the reproducible ELF, resolved through `addr2line`;
  `tests/test_c_riscv.py::test_line_level_carry_back`). Still open are the named
  *future* increments (not spine-blocking): auto-deriving the Sail semantics from
  the Sail source, the AArch64 Sail route, and the dev-image residuals tracked in
  [#2](https://github.com/cksystemsgroup/hurdy-gurdy/issues/2) (cvc5/yices2 binaries,
  AVR, `certifaiger`/LFSC).
