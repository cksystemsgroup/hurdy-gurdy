# `c-riscv` compile hop — contract

*Status: v0 (recorded 2026-06-04). Hop 1 of the `C → RV64 ELF → BTOR2`
chain specified in the repo-root [`DESIGN_c_to_btor2_chain.md`](../../../DESIGN_c_to_btor2_chain.md).
This file is the hop's contract — the opaque-hop analogue of a pair's
`SCHEMA.md`. For a transparent pair the contract is a byte-prediction
schema; for this `reproducible`-tier hop it is a **reproducibility +
preservation contract**.*

## What this hop is (and is not)

- **Is:** a deterministic translation `C source → RV64 ELF`, run by a
  pinned compiler. Trust tier **`reproducible`** — the bytes are not
  predictable from a schema, but the same inputs under the same pin
  produce byte-identical output on any host.
- **Is not:** a `Pair`. Its output is an ELF, not a solver-terminating
  reasoning artifact, so it lives under `gurdy/hops/`, not
  `gurdy/pairs/`. It does no reasoning, no spec generation, and no
  symbol resolution — those are chain glue (a later increment).

## The pinned toolchain

| Field | Value |
|---|---|
| image | `christophkirsch/hurdy-gurdy-bench` |
| digest | `sha256:b4669d9b5a186c99f4591eabdc1590fbc84dca0c714a6af8803c3101f6423544` |
| compiler | `riscv64-unknown-elf-gcc` 14.2.0 |
| container workdir | `/src` |

The image is pinned **by digest**, not by the `:latest` tag. Pinning by
tag would not be reproducible — `:latest` moves.

## Canonical translation rules (fix the bytes)

Ordered flag list (order is part of the contract — it can affect bytes):

```
-O<level>  -march=rv64imc  -mabi=lp64  -nostdlib  -nostartfiles
-ffreestanding  -g  -ffile-prefix-map=/src=.  -Wl,-Ttext=0x10000
-Wl,--no-relax
```

plus environment `SOURCE_DATE_EPOCH=0`. The ISA and `-Ttext` mirror the
corpus assembly/C build so the entry PC and instruction set match the
existing `riscv-btor2` corpus.

**Recorded parameters** (change the bytes; captured in provenance):

- `opt_level` ∈ {`0`,`1`,`2`,`3`,`s`,`g`} — the gcc `-O` level. Default `0`.
- `source_name` — the logical filename embedded in DWARF (and therefore
  in the source map). Default `module.c`.

Any other knob that would change emitted bytes must be added here, never
left implicit.

## Reproducibility

Guarantee: **same `(source, pin, opt_level, source_name)` → byte-identical
ELF, on any host that can resolve the pinned digest.**

Mechanism:

1. **Pin by digest.** The authoritative compiler is the image's gcc
   14.2.0, not the local toolchain.
2. **Fixed build path.** The source is compiled at `/src` regardless of
   where it came from on the host, and `-ffile-prefix-map=/src=.`
   rewrites the DWARF `comp_dir`/name to `.` / `<source_name>`. No host
   path enters the bytes.
3. **No bind mount.** Source goes in on stdin, the ELF comes back on
   stdout; the build is independent of host file-sharing config.
4. **`SOURCE_DATE_EPOCH=0`.** Pins any embedded timestamp.

Tested in `tests/hops/c_riscv/test_reproducible.py`: two compiles agree;
the output matches an independently-derived `docker run` baseline; and
the bytes contain no host path.

### What this fixes

The corpus C artifacts `source.elf`, `pcs.json`, and
`source.elf.dwarfmap.json` are **gitignored build products** (see
`bench/riscv-btor2/corpus/.gitignore`); what is version-controlled is
`task.c`, `task.toml`, and the auto-generated `spec.json` (which records
the trap address resolved at build time). The original
`_compile_c.py` build was **not** reproducible: it shelled out to the
*local* `gcc` (13.2.0 on the build host; DWARF `DW_AT_producer: GNU C17
13.2.0`) and the resulting `source.elf` embedded absolute host paths
(`DW_AT_comp_dir: /Users/ck/hurdy-gurdy`, `…/task.c`), so anyone running
`make` got bytes that differed from the nominally-pinned image (gcc
14.2.0) and from each other across machines.

**Done (corpus migration, 2026-06-05):** `_compile_c.py` now builds
through this hop — `compile_c` for the ELF, in-process trap-PC resolution
for `spec.json`, and the pinned `objdump` (`extract_line_map`) for the
DWARF sidecar — so a fresh `make` yields byte-identical artifacts on any
host that can resolve the pin. The migration shifted the `trap` address on
5 tasks under gcc 14.2.0 (`0107`, `0112`, `0113`, `0114`, `0124`); their
tracked `spec.json` was regenerated accordingly. Re-validated:
`oracle_chain` 38/38 PASS, the `spec` address matches the trap symbol in
the freshly-built ELF on all 38, and the CBMC differential is unchanged.

## Preservation contract

- **Preserved:** the observable behavior of the C abstract machine for
  the translated program — its effect on architectural state as
  exercised by the `riscv-btor2` interpreters — modulo undefined
  behavior. This is what the chain's downstream alignment oracle checks
  (the commuting square, below).
- **Discarded / not guaranteed:** source-level types and identifiers
  (recovered only via DWARF), source structure, and any guarantee about
  *which* instructions implement a construct — optimization may reorder,
  inline, or eliminate. Higher `opt_level` discards more.

## Trust tier and how to raise it

This hop is `reproducible`. To raise it:

- → **`checked`:** validate each build against an independent oracle.
  **Built:** `verify.py:cbmc_verify` runs CBMC on the *same C source* in the
  *same pinned image* and `classify_differential` compares its verdict to the
  chain's. A disagreement is a **fault** only on a non-`lowering_sensitive`
  task (it localizes to this hop — the gcc/UB hop — since hop 2 is checked
  independently by `oracle_align`); on a lowering-sensitive task it is the
  documented C-UB vs RV64-defined gap (`expected-divergence`). Wired into
  `bench/riscv-btor2/oracle_chain.py --cbmc`. Because CBMC is pinned by the
  same image digest, the check is itself reproducible.
- → **`transparent`/proven:** swap the pinned gcc for a verified compiler
  (CompCert). Only then are the bytes backed by a refinement proof.

## Output and handoff to hop 2

`compile_c` returns `CCompileResult(elf_bytes, provenance)`. The
`riscv-btor2` pair's loader (`load_riscv_binary`) accepts ELF **bytes**
directly, so the chain passes bytes — no intermediate files.

The transitive source map is

```
BTOR2 nid  ──annotation──▶  ELF pc  ──DWARF──▶  C file:line
```

but the loader's `from_elf` is a stub for byte input (it only reads a
sidecar JSON; there is no in-process `.debug_line` decoder), so the
`DWARF` step is recovered separately by `dwarf.extract_line_map`, which
runs `objdump --dwarf=decodedline` in the **pinned** image and parses it
(the same parse as `bench/.../corpus/_emit_dwarfmap.py`). The chain wires
the result into the source's line table before lifting. Because the
path-prefix map made DWARF paths relative (`task.c`, not `/Users/...`),
the recovered map is host-independent.

## Provenance fields

`Provenance.to_jsonable()` records: `image`, `digest`, `compiler`,
`compiler_version`, `flags`, `opt_level`, `source_name`,
`container_workdir`, `source_date_epoch`, `source_sha256`, `elf_sha256`.
A chain composes these into a per-hop record (`[c-riscv@digest,
riscv-btor2@schema]`).

## The commuting-square view

This hop is the **top edge `T`** of the first square in the chain (see
`DESIGN_generalized_pairs.md` Appendix A). Its left/right "interpreter"
edges are the C abstract machine and the RV64 simulator; its preservation
contract is the claim that the square commutes. Faithfulness is not
asserted here — it is *checked* at the end of the chain by the existing
`bench/riscv-btor2/oracle_align.py`, which localizes any divergence to a
hop.

## References

- `DESIGN_c_to_btor2_chain.md`, `DESIGN_generalized_pairs.md` (repo root)
- `bench/riscv-btor2/corpus/_compile_c.py` (the corpus build — migrated to
  drive this hop, so it is now reproducible)
- `gurdy/pairs/riscv_btor2/source/loader.py` (consumes ELF bytes + DWARF)
