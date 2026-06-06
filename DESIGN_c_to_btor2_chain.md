# Spec — the first chain: `C → RV64 ELF → BTOR2`

*Status: **built** (proposed 2026-06-04, implemented 2026-06-05). The
smallest concrete instance of the direction in
[`DESIGN_generalized_pairs.md`](./DESIGN_generalized_pairs.md). One two-hop
chain that exercises every chaining mechanism once, on a path with immediate
SV-COMP payoff. Mostly a **promotion** of machinery that already existed in
the corpus, not greenfield. This note records the as-built design; where it
diverged from the original proposal, the divergence is flagged inline
(**As built:** …). Code: `gurdy/hops/c_riscv/` (hop 1),
`gurdy/chains/c_to_btor2.py` (composer), `bench/riscv-btor2/oracle_chain.py`
(validation).*

## The chain

```
C source ──(hop 1: gcc, reproducible)──▶ RV64 ELF ──(hop 2: riscv-btor2, transparent)──▶ BTOR2 ──▶ solver
```

| Hop | Translator | Tier | Status |
|-----|------------|------|--------|
| 1. `c-riscv` | `riscv64-unknown-elf-gcc 14.2.0 -march=rv64imc -mabi=lp64 -g` | `reproducible` | **Built** — `gurdy/hops/c_riscv/`, pinned by **digest** in `gurdy/hops/c_riscv/toolchain.py` (`_DEFAULT_DIGEST`) |
| 2. `riscv-btor2` | the existing pair | `transparent` | **Reused** — `gurdy/pairs/riscv_btor2/`, SCHEMA.md v1.1.0 |

So this spec is: take the ad-hoc hop 1, make it a **first-class translator
with a tier + toolchain pin + preservation contract**, thread its provenance
and source-map through hop 2, and validate the composite.

> **As built:** hop 1 became a **compile-only hop** under `gurdy/hops/`, *not*
> a registered `Pair` under `gurdy/pairs/` — its output is an ELF, not a
> solver-terminating reasoning artifact, so it is not a pair (a `Pair` is the
> solver-terminating special case of a hop). Its contract lives in
> `gurdy/hops/c_riscv/CONTRACT.md`. The promoted code is a clean
> reimplementation of `_compile_c.py`'s gcc invocation, not a wrapper around
> it — the original script's host-gcc build turned out to be non-reproducible
> (below; `_compile_c.py` has since been migrated to drive this hop).
> Composition is a **dedicated composer** (`gurdy/chains/c_to_btor2.py`), not
> the existing pair-only oracle; validation is a **new** chain-aware oracle
> (`oracle_chain.py`) that starts from `task.c`.

## Hop 1 as a compile-only hop

A hop is just the **top edge `T`** of a commuting square (see
`DESIGN_generalized_pairs.md` Appendix A); a `Pair` is the special case whose
output language terminates in a solver. Hop 1 stops at ELF, so it needs far
less than a pair. Mapping onto PAIRING.md §3's "irreducible six", most
collapse:

- **Source loader** — C source `bytes`/`str`, plus per-task chain parameters
  (`opt_level`, `bound`, …) read by the composer/oracle from `task.toml`.
- **"Schema"** — *not* a byte-prediction contract. For a `reproducible` hop
  it is a **reproducibility + preservation contract** (`CONTRACT.md`): the
  image **digest**, compiler version, the exact ordered flag list, **plus** a
  statement of what is preserved (observable behavior of the C abstract
  machine on architectural state, modulo UB) and discarded (types,
  identifiers — except via DWARF — and source structure).
- **Translation function** — `compile_c()`: invoke pinned gcc in-container,
  source on stdin, ELF on stdout.
- **Lifter** — none of its own; lifting happens at the far end (below).
- **Source interpreter** — **deliberately omitted.** We do *not* need a C
  interpreter to validate the chain: the far-end alignment (RV64 sim vs BTOR2)
  plus the C abstract-machine semantics gcc implements cover it (see
  Validation). A real C interpreter later upgrades hop 1 to `checked`.
- **Solver wrappers** — inherited from hop 2.

> **As built:** rather than `Pair.extras`, hop 1 is a standalone module
> (`gurdy/hops/c_riscv/`) returning `CCompileResult(elf_bytes, provenance)` —
> no `Pair` protocol involvement at all, so no protocol change. Symbol
> resolution and spec synthesis — called "chain glue, a later increment" in
> the original proposal — are done **now**, in the composer, not the hop: the
> composer resolves the `trap` symbol's PC from the compiled ELF and
> synthesizes the corpus-convention `eq(pc, const(<trap pc>))` property.

## Reproducibility hazards (the real work of tier `reproducible`)

"Same container ⇒ same ELF bytes" is not automatic. PAIRING.md §8's
nondeterminism warnings apply to *third-party* tools too.

> **As built:** the empirically-locked set that achieved a deterministic,
> host-independent ELF (`sha256:953bcd83…` for `0100`) is: pin the image **by
> digest** (not `:latest`); compile at a fixed in-container path `/src` with
> `-ffile-prefix-map=/src=.` (rewrites DWARF `comp_dir`/name to `.`/`task.c`,
> so no host path enters the bytes); `SOURCE_DATE_EPOCH=0`; `--no-relax`;
> source via **stdin**, ELF via **stdout** (no bind mount). `-frandom-seed=`
> turned out unnecessary at these `-O` levels. A twice-compile-and-diff check
> is in `tests/hops/c_riscv/test_reproducible.py`.
>
> **Why this mattered (forensic finding):** the corpus `source.elf` files
> are a **gitignored build product** (only `task.c`/`task.toml`/`spec.json`
> are tracked), and the original `_compile_c.py` built them with the *local*
> gcc 13.2.0, embedding absolute host paths
> (`DW_AT_comp_dir: /Users/ck/hurdy-gurdy`), so a `make` produced bytes that
> did **not** match the nominally-pinned image (gcc 14.2.0) and differed
> across machines. The corpus C-build was non-reproducible — exactly the
> premise this hop fixes.
>
> **Done — corpus migrated (2026-06-05):** `_compile_c.py` now builds through
> hop 1 (`compile_c` for the ELF, in-process trap-PC resolution for
> `spec.json`, pinned `objdump` for the DWARF sidecar), so a fresh `make`
> yields byte-identical artifacts on any host. The change shifted the `trap`
> address on 5 tasks under gcc 14.2.0 (`0107/0112/0113/0114/0124`); their
> tracked `spec.json` was regenerated. Re-validated: `oracle_chain` 38/38
> PASS, every `spec` address matches the trap symbol in the freshly-built
> ELF, CBMC differential unchanged.

## Validation strategy (layered on existing machinery)

1. **Reproducibility.** Compile twice in the pinned image; assert
   byte-identical ELF. *Built* (`test_reproducible.py`).
2. **Chain-aware alignment (primary).** `bench/riscv-btor2/oracle_chain.py`
   starts from `task.c`, runs the whole chain (compile → translate →
   dispatch), replays any `reachable` witness, and walks source-interp vs
   reasoning-interp traces step-for-step. A divergence is a real
   C→ELF→BTOR2 translation bug, localized to a step. It scores **verdict_ok**
   (vs the task's manual-proof `expected.verdict`) and **align_ok** per task.
   *Built.*
   > **As built:** the existing `oracle_align.py` could *not* be reused
   > unchanged — it reads the committed (non-reproducible) `source.elf`. The
   > new oracle reads `task.c` and threads per-task `[c]` parameters
   > (`opt_level`, `bound`, `engine`, `included_callees`).
3. **C-line localization.** The transitive source-map is
   `BTOR2 nid → ELF pc → C file:line`.
   > **As built — gap found & fixed:** the proposal assumed this was "already
   > wired." It was not, on the byte path: the source loader's `from_elf` is a
   > **stub** (it reads a sidecar JSON only; there is no in-process
   > `.debug_line` decoder), so loading from ELF bytes yields an empty line
   > table. Fixed by `gurdy/hops/c_riscv/dwarf.py:extract_line_map`, which runs
   > `objdump --dwarf=decodedline` in the **pinned** image and parses it (the
   > same parse as `_emit_dwarfmap.py`); the composer wires the result into the
   > source before lifting. Because `-ffile-prefix-map` made DWARF paths
   > relative, the recovered map is host-independent. The oracle confirms
   > real C lines are recovered (`0101` → 7 distinct C lines).
4. **Differential vs CBMC (the `checked` upgrade).** *Built:*
   `gurdy/hops/c_riscv/verify.py:cbmc_verify` runs CBMC on the same C source
   in the **same pinned image** (so the check is reproducible too) and
   `classify_differential` compares its verdict to the chain's. Wired into
   `oracle_chain.py --cbmc`.
   > **As built — the lowering flag makes this checkable.** Plain CBMC reports
   > `reachable` on exactly the `lowering_sensitive` UB tasks
   > (`0115/0116/0117/0125/…`): it sees C-level UB (signed overflow,
   > div-by-zero) where the chain sees RV64-*defined* behavior. So a
   > disagreement is a **fault** (localized to hop 1, the gcc/UB hop) only on
   > a task that is **not** lowering-sensitive; on a lowering-sensitive task it
   > is `expected-divergence` — the documented gap, which actively shows the
   > chain reasoning about something a C-level verifier cannot. This turns the
   > `lowering_sensitive` flag into a checkable contract: every divergence must
   > be explained by it. (Verified: `0100–0103` agree; `0115/0116` expected-
   > divergence.) Default off (one extra container run per task).
5. **Provenance composition.** *Built:* `ChainResult.provenance` records
   `[{hop: c-riscv, digest, compiler_version, flags, …, elf_sha256},
   {hop: riscv-btor2, schema_version, spec_hash}]`.

## Code delta (as built)

- `gurdy/hops/` — new package; a hop is an edge, a `Pair` its
  solver-terminating special case.
- `gurdy/hops/c_riscv/` — the hop: `toolchain.py` (digest pin + canonical
  flags), `compile.py` (`compile_c`, provenance), `dwarf.py`
  (`extract_line_map`, the DWARF-gap fix), `verify.py` (`cbmc_verify` +
  `classify_differential`, the checked-tier CBMC differential),
  `CONTRACT.md` (the contract).
- `gurdy/chains/c_to_btor2.py` — the composer `compile_c_to_btor2(...) →
  ChainResult`: a 2-hop compose helper (no general router), translate-only,
  carrying the transitive source-map and both-hop provenance. `ChainResult`
  also exposes `.lift(raw)` (grounds witnesses in C — the standalone `lift`
  tool can't, since the annotation doesn't carry the binary).
- `bench/riscv-btor2/oracle_chain.py` — the chain-aware oracle.
- Tests: `tests/hops/c_riscv/` (compile reproducibility + DWARF),
  `tests/chains/` (composer end-to-end + oracle smoke).
- No framework redesign, no `Pair` protocol change, no router.

## Acceptance

- A C task compiles **reproducibly** (twice → identical ELF in-container). ✓
- `oracle_chain.py` reports `align=ok` on reachable tasks, with divergences
  (if any) labeled at the step (and the witness mapped to **C lines**). ✓
  (Verified across `0100–0125` samples: trivial, reachable+align, `-O2/-O3`
  loops, the overflow/sdiv lowering wedges, callee-promotion, mul-chain.)
- Artifact provenance records **both hops**. ✓
- CBMC differential agrees, or a disagreement localizes to a specific hop
  (a non-lowering-sensitive divergence is a `fault` at hop 1). ✓
  (`oracle_chain.py --cbmc`.)
- RAM safety: one task at a time; `oracle_chain.py` defaults to
  `--max-tasks 4` (the C chain adds a container compile + objdump per task,
  so the cap is tighter than the assembly oracle's 5). No new parallelism. ✓

## What this proves about the generalization

In one buildable path it exercises **all** the mechanisms the broader
proposal needs: **mixed-trust chaining** (`reproducible` + `transparent`),
**transitive source-maps**, **compositional alignment**, **provenance
composition**, and a **verifier hop** (the CBMC differential, the `checked`-
tier upgrade) — validated once, with SV-COMP payoff. If hop 1 ever wants to
be `transparent`/proven rather than merely reproducible, the drop-in is
CompCert.
