# `riscv-btor2` v0.4 corpus expansion plan — C-derived tasks

## Why this exists

Through v0.3 the corpus is exclusively hand-written assembly. That
got the bench to a good place — defensible §3.A / §3.B / §3.C
results, every observable / property shape exercised, two
empirical engine pins — but it caps the corpus's scaling at the
30-min/task authoring rate of human assembly. It also leaves a
class of question unmeasured: *how does the pair behave on the
shape of code a real compiler emits*, with its register-allocation
patterns, calling-convention quirks, and lowering decisions that
hand-authors don't usually replicate.

v0.4 introduces a second authoring path: **C-source tasks compiled
to RV64 ELF with auto-generated `spec.json`**. A task is now one of
two shapes:

- **Assembly task** (v0.1–v0.3 convention): `source.S` + hand-written
  `spec.json` + `task.toml`.
- **C task** (v0.4+): `task.c` + `task.toml`. The auto-generator
  (`_compile_c.py`) compiles, resolves the `trap` symbol's PC, and
  writes `spec.json` + `pcs.json` + `source.elf.dwarfmap.json` in
  one shot.

Property convention for C tasks (the standard CBMC pattern):

```c
extern void trap(void) __attribute__((noreturn));

void _start(void) {
    // ... compute, then assert via the trap pattern:
    if (bad_condition) trap();
    __asm__ volatile ("ebreak");   // normal halt
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
```

The auto-generated property is `eq(pc, const(<addr of trap>))`.
"Trap reachable" = "assertion violated". "Trap unreachable" =
"assertion holds." Same semantics as CBMC / ESBMC.

## What's in v0.4 today

Three prototype tasks shipped, validating the full pipeline:

| Task | Verdict | Engine pin | Purpose |
|---|---|---|---|
| 0100-c-add-trap-correct | unreachable | z3-bmc | Smoke test: simplest possible C task; trap not reachable. |
| 0101-c-add-trap-bug | reachable   | z3-bmc | Bug-finding: the assertion always fires; exercises the witness path. |
| 0102-c-mul-chain-correct | unreachable | z3-bmc | C analogue of 0050-deep-mul-chain. |

All three pass all four pre-flight oracles (oracle.py,
framework_oracle.py, audit_anchors.py, oracle_cross.py).

## Empirical finding from the prototype

The single most important v0.4 finding so far:

> **Engine pins from hand-written tasks do NOT transfer
> automatically to their C analogues.**

The hand-written 0050-deep-mul-chain pinned to bitwuzla on the
basis of engine_bench measuring bitwuzla ≈ 11× faster than z3-bmc
on the deep bvmul shape. The C analogue 0102-c-mul-chain-correct,
compiling the *same arithmetic* via gcc -O0, measured:

| | hand-written 0050 | C-derived 0102 |
|---|---:|---:|
| z3-bmc median | 77 ms | 1659 ms |
| bitwuzla median | 7 ms | 2447 ms |
| ratio | bitwuzla 11× faster | bitwuzla 1.5× **slower** |

The cause is the gcc -O0 spill/reload pattern: the BTOR2 trace
gains many memory operations per arithmetic step, and z3-bmc's
bitblasting handles that load/store-dominated trace better than
bitwuzla's word-level rewriting on the v0.3 corpus's
arithmetic-dominated trace. The arithmetic favours bitwuzla, but
the surrounding -O0 plumbing flips the balance.

**Corpus discipline implication:** every C task's engine pin must
be re-validated empirically via `engine_bench.py` — never copy a
pin from the assembly cousin. The pin is "fastest engine that
returns the right verdict on this exact ELF," not "engine the
analogous question used."

## v0.4 scope (in this commit)

- `bench/riscv-btor2/corpus/_compile_c.py` — auto-spec-gen.
- `bench/riscv-btor2/corpus/Makefile` — extended with a C path
  that runs `_compile_c.py` on tasks containing `task.c`.
- 3 prototype tasks (0100, 0101, 0102) demonstrating the
  pipeline end-to-end on the unreachable-correct, reachable-bug,
  and engine-pin variants.

## v0.4 next (not in this commit)

The acceptance for v0.4 publication would be ≥ 5 more C tasks
plus an A/B/C sweep on the C subset. Sketches:

1. **Compiler optimization-level family.** The same `task.c`
   compiled at `-O0 / -O1 / -O2 / -O3` produces 4 tasks per
   source. The interesting bench questions ("did the compiler
   resolve UB the wrong way", "where did sign-extension actually
   happen") are exactly what differs across levels. This
   multiplies authoring speed dramatically once `_compile_c.py`
   gains an `[c].opt_level` knob.

2. **Lowering-sensitive C patterns.** Tasks where the C source
   *hides* something the BTOR2 lowering reveals: integer
   promotions at function-call boundaries (sign vs zero
   extension), bitfield masking under different widths,
   `INT_MIN / -1`, etc. These are §4.3 lowering-sensitive
   territory and the C path is the natural way to author them
   (writing each in hand-assembly is tedious and doesn't reflect
   how the bug appears in real code).

3. **Condition D — CBMC on the same C source.** With C source in
   the corpus, condition D
   (BENCHMARKING.md §3.D — source-level verifier baseline)
   becomes feasible. The pair's distinctive value claim becomes
   measurable: "B beats CBMC on lowering-sensitive cases" is a
   much stronger argument than "B beats no-tools-LLM."
   Requires a CBMC layer in the bench Docker image.

4. **Real-program fragments.** Once the synthetic patterns are
   settled, take small fragments from selfie or pico-libc and
   ship them as corpus tasks. The most credible "this works on
   actual code" demonstration the bench can produce.

## Acceptance criteria (for v0.4 publication, not this commit)

1. ≥ 5 C tasks beyond the prototypes, covering at least one
   each of: optimization-level family, lowering-sensitive
   pattern, real-program fragment.
2. Every C task PASSes all four pre-flight oracles.
3. Every C task's engine pin is empirically validated via
   `engine_bench.py`.
4. CBMC layer added to the bench Docker image and a condition D
   sweep run on the C subset.
5. A v0.4 results.md / results_C.md mirroring the v0.3
   structure, with a §3.D column added.

## How to validate v0.4 today

```sh
# Build the v0.4 prototypes.
make -C bench/riscv-btor2/corpus 0100-c-add-trap-correct \
                                  0101-c-add-trap-bug \
                                  0102-c-mul-chain-correct

# Run all four pre-flight oracles on the new tasks.
for t in 0100-c-add-trap-correct 0101-c-add-trap-bug 0102-c-mul-chain-correct; do
    python bench/riscv-btor2/oracle.py            --task "$t"
    python bench/riscv-btor2/framework_oracle.py  --task "$t"
    python bench/riscv-btor2/audit_anchors.py     --task "$t"
    python bench/riscv-btor2/oracle_cross.py      --task "$t"
done

# Engine differentiation evidence (the v0.4 surprise — see above).
python bench/riscv-btor2/engine_bench.py --task 0102 --repeat 3
```

All four oracles must report no failures. `engine_bench` records
z3-bmc beating bitwuzla on 0102 (the inverted finding vs 0050).
