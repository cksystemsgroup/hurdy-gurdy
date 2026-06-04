# Spec — the first chain: `C → RV64 ELF → BTOR2`

*Status: proposal (recorded 2026-06-04). The smallest concrete instance of
the direction in [`DESIGN_generalized_pairs.md`](./DESIGN_generalized_pairs.md).
One two-hop chain that exercises every chaining mechanism once, on a path
with immediate SV-COMP payoff. Mostly a **promotion** of machinery that
already exists in the corpus, not greenfield.*

## The chain

```
C source ──(hop 1: gcc, reproducible)──▶ RV64 ELF ──(hop 2: riscv-btor2, transparent)──▶ BTOR2 ──▶ solver
```

| Hop | Translator | Tier | Already exists? |
|-----|------------|------|-----------------|
| 1. `c-riscv` | `riscv64-unknown-elf-gcc -march=rv64imc -mabi=lp64 -g` | `reproducible` | **Yes** — `bench/riscv-btor2/corpus/_compile_c.py` + `Makefile` (C path, v0.4+), pinned in `christophkirsch/hurdy-gurdy-bench:latest` |
| 2. `riscv-btor2` | the existing pair | `transparent` | **Yes** — `gurdy/pairs/riscv_btor2/`, SCHEMA.md v1.1.0 |

So this spec is: take the ad-hoc hop 1, make it a **first-class registered
pair with a tier + toolchain pin + preservation contract**, thread its
provenance and source-map through hop 2, and validate the composite with the
oracle that already exists.

## Hop 1 as a pair (the only new thing)

Map onto PAIRING.md §3's "irreducible six", noting most collapse for an
opaque/reproducible hop:

- **Source loader** — read C text + the task's `task.toml`. Trivial.
- **"Schema"** — *not* a byte-prediction contract. For a `reproducible`
  hop it is a **reproducibility + preservation contract**: the image digest,
  compiler version, exact flags (`-march=rv64imc -mabi=lp64 -g`,
  `-Ttext=0x10000 --no-relax`), **plus** a statement of what is preserved
  (observable I/O behavior of the C abstract machine, modulo UB) and what is
  discarded (types, identifiers — except as recovered via DWARF — and source
  structure).
- **Translation function** — invoke pinned gcc. Already `_compile_c.py`.
- **Lifter** — none of its own; lifting happens at the far end (below).
- **Source interpreter** — **deliberately omitted.** We do *not* need a C
  interpreter to validate the chain: the far-end alignment oracle plus the C
  abstract-machine semantics gcc implements cover it (see Validation). Adding
  a real C interpreter later upgrades hop 1 from `reproducible` to `checked`
  on its own.
- **Solver wrappers** — inherited from hop 2.

Near-term, declare the tier + pin in `Pair.extras` (`gurdy/core/pair.py:230`)
— **no protocol change required**.

## Reproducibility hazards (the real work of tier `reproducible`)

"Same container ⇒ same ELF bytes" is not automatic. PAIRING.md §8's
nondeterminism warnings apply to *third-party* tools too. Pin against:
`SOURCE_DATE_EPOCH`, `-ffile-prefix-map=` (strip build paths from DWARF),
`-frandom-seed=`, deterministic section/symbol ordering, and `--no-relax`
(already set). Acceptance includes a twice-compile-and-diff check.

## Validation strategy (layered on existing machinery)

1. **Reproducibility.** Compile twice in the pinned image; assert
   byte-identical ELF. (New: the diff check. Cheap.)
2. **Far-end alignment (primary).** Run `bench/riscv-btor2/oracle_align.py`
   unchanged: it compiles `(spec, ELF) → BTOR2`, dispatches, replays any
   `reachable` witness, and walks source-interp vs reasoning-interp traces.
   This already validates `ELF → BTOR2` faithfulness for the property; the
   chain inherits it.
3. **C-line localization (already wired).** `_emit_dwarfmap.py` emits
   `source.elf.dwarfmap.json`; the pair's lifter already populates
   `file:line` per step. So a divergence is reportable at the **C line**, and
   the transitive source-map `BTOR2 nid → ELF pc → C file:line` is *already
   present* — this spec only names it as the chain's lift contract.
4. **Differential vs CBMC (optional `checked` upgrade).** `_emit_cbmc.py`
   ("condition D") already emits `task.cbmc.c`. Running CBMC on the C and
   comparing verdicts gives an independent check of hop 1; disagreement that
   the alignment oracle *doesn't* see localizes the fault to hop 1 (the
   gcc/UB hop) rather than hop 2.
5. **Provenance composition.** Record the chain as
   `[c-riscv@<image-digest>+<flags>, riscv-btor2@1.1.0]` on the artifact.

## Minimal code delta

- Register a `c-riscv` pair wrapping the existing `_compile_c.py` gcc call;
  put `tier="reproducible"` + toolchain pin in `extras`.
- Add the twice-compile-and-diff reproducibility check.
- A 2-hop compose helper (no general router yet): `compile_chain([c-riscv,
  riscv-btor2], c_source) → CompiledArtifact` whose annotation carries the
  transitive source-map (steps 3 above) and whose provenance carries both
  hops (step 5).
- That's it. No framework redesign, no `Pair` protocol change, no router.

## Acceptance

- A C task compiles **reproducibly** (twice → identical ELF in-container).
- `oracle_align.py` reports `align=ok` on the chain's reachable tasks, with
  divergences (if any) labeled at the **C line**.
- Artifact provenance records **both hops**.
- (Optional) CBMC differential agrees, or a disagreement localizes to a
  specific hop.
- RAM safety: one task at a time; reuse the oracle's existing
  `--max-tasks 5` cap and per-dispatch memory limit. No new parallelism.

## What this proves about the generalization

In one buildable path it exercises: **mixed-trust chaining** (`reproducible`
+ `transparent`), **transitive source-maps**, **compositional alignment**,
a **verifier hop** (CBMC differential), and **provenance composition** —
every mechanism the broader proposal needs, validated once, with SV-COMP
payoff. If hop 1 ever wants to be `transparent`/proven rather than merely
reproducible, the drop-in is CompCert.
