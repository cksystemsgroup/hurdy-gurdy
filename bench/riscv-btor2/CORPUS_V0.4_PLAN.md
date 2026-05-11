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

**Prototype tasks** (commit `a96a089`):

| Task | Verdict | Engine pin | Purpose |
|---|---|---|---|
| 0100-c-add-trap-correct | unreachable | z3-bmc | Smoke test: simplest possible C task; trap not reachable. |
| 0101-c-add-trap-bug | reachable   | z3-bmc | Bug-finding: the assertion always fires; exercises the witness path. |
| 0102-c-mul-chain-correct | unreachable | z3-bmc | C analogue of 0050-deep-mul-chain. |

**Optimization-level families** (each is one source × four `-O` levels):

`_compile_c.py` gained a `[c].opt_level` knob; each task in a family
pins a different level. Three families shipped, 12 tasks total.

#### Family A — loopsum (0103–0106)
Sum 0..9 into a `volatile`-bound counter.

| Task | -O | ELF | Instructions |
|---|---|---|---|
| 0103-c-loopsum-o0 | 0 | 6912 B | 34 |
| 0104-c-loopsum-o1 | 1 | 7232 B | 18 |
| 0105-c-loopsum-o2 | 2 | 7264 B | 18 |
| 0106-c-loopsum-o3 | 3 | 7264 B | 18 |

#### Family B — branchloop (0107–0110)
Loop with a parity-conditional inside the body (even iterations
contribute `2*i`, odd iterations contribute `i`).

| Task | -O | ELF | Instructions |
|---|---|---|---|
| 0107-c-branchloop-o0 | 0 | 6976 B | 49 |
| 0108-c-branchloop-o1 | 1 | 7304 B | 26 |
| 0109-c-branchloop-o2 | 2 | 7376 B | 26 |
| 0110-c-branchloop-o3 | 3 | 7376 B | 26 |

#### Family C — byteswap (0111–0114)
Reverse the byte order of `0xDEADBEEFCAFEBABE` via shift/mask/or.
Bitvector-arithmetic-heavy loop body.

| Task | -O | ELF | Instructions |
|---|---|---|---|
| 0111-c-byteswap-o0 | 0 | 7184 B | 52 |
| 0112-c-byteswap-o1 | 1 | 7440 B | 36 |
| 0113-c-byteswap-o2 | 2 | 7464 B | 36 |
| 0114-c-byteswap-o3 | 3 | 8752 B | **64** |

The byteswap **-O3 row is striking**: 64 instructions vs 36 at
-O1/-O2. gcc at -O3 unrolled the 8-iteration loop into straight-
line code, trading code size for fewer dynamic branches. This is
the v0.4 family pattern's first "what does -O3 actually do" data
point — the loopsum family's -O3 stayed at 18 instructions
(no unroll because the body is too small to amortize the cost),
the branchloop family's -O3 stayed at 26 (the inner branch
suppresses unrolling), and only the byteswap family hit gcc's
unroll heuristic.

All 15 C tasks (3 prototypes + 12 family) pass all four pre-flight
oracles (oracle.py, framework_oracle.py, audit_anchors.py,
oracle_cross.py).

#### Lowering-sensitive (0115–0116)

The first C tasks tagged `lowering_sensitive = true`
(SCOPE.md §4 criterion). Both pinned to -O0 because the lowering
surface they target depends on faithful per-instruction emission;
gcc -O1+ may optimise on UB assumptions and erase the
demonstration.

| Task | Lowering surface |
|---|---|
| 0115-c-int-overflow | Signed `INT_MAX + 1` overflow on RV64 wraps via `addw` to `INT_MIN`; the subsequent `int → long` widening sign-extends, giving `-2147483648L`. C reader thinking "UB → can't reason" misses the predictable RV64 behaviour. |
| 0116-c-divu-sentinel | `divuw` on `(42, 0)` returns the 32-bit sentinel `0xFFFFFFFF`; gcc emits a zero-extension shim to honour C's unsigned-widening rule, masking the `divuw`'s W-suffix sign-extension and giving `z = 0xFFFFFFFFUL` (not `0xFFFFFFFFFFFFFFFFUL`). Two layers of lowering compose. |
| 0117-c-int-min-div-neg-one | `INT_MIN / -1` is the canonical signed-overflow case (mathematical quotient 2³¹ doesn't fit in `int`). RV64 `divw` returns the `INT_MIN` sentinel; sign-extension to `long` preserves the negative value, giving `-2147483648L`. Signed counterpart of 0116; the asymmetry vs the unsigned case is itself a lowering observation. |
| 0118-c-shift-amount-mask | `x << 64` on RV64: SLL masks the shift amount to the low 6 bits, so `64 & 0x3f = 0` and `y = x << 0 = x`. C says shift ≥ width is UB; the BTOR2 lowering encodes the bvand-mask explicitly. The classic SCHEMA.md §13 shift-amount-masking surface, now in C form. |
| 0119-c-signed-vs-unsigned-shift-right | `int >> 2` vs `unsigned >> 2` on the same bit pattern (0xFFFFFFF8): SRAW gives -2 (sign-fill), SRLW gives 0x3FFFFFFE (zero-fill). The C operator is the same; the *type* dispatches to two different RV64 instructions. C-source analogue of 0011-srai-vs-srli. |
| 0120-c-byte-load-signedness | `signed char` vs `unsigned char` load of the same byte (0xFF) widened to int: `lb` gives -1 (sign-extend), `lbu` gives 255 (zero-extend). C-source analogue of 0005-lbu-vs-lb. |
| 0121-c-mulw-truncation | `int x = 0x10000; int p = x * x;` on RV64 lowers to MULW, which keeps low 32 bits of the product. 0x10000 × 0x10000 = 0x100000000 → MULW = 0. The *operand type*, not value, decides the lowering. C-source analogue of 0032-mulw-32bit-truncation-loop. |
| 0122-c-signed-vs-unsigned-cmp | `int(-1) < 5` (= true) vs `unsigned(0xFFFFFFFF) < 5` (= false): same `<` operator dispatches to BLT vs BLTU on RV64. Same bit pattern, opposite verdict. C-source analogue of 0013-bgeu-vs-bge / 0016-bge-signed. |
| 0124-c-call-arg-promotion | `signed char c = -10; add100(c)`: the C-level `char → int` promotion sign-extends -10 (bit pattern 0xF6) to 0xFFFFFFF6 in `a0` at the call boundary; gcc emits the `lb`-or-equivalent for the argument materialisation. First C task with `[c].included_callees`. |

The C-corpus lowering tier is now **9 tasks / 24 = 38%**, well
above SCOPE.md §4.3's 20% floor and at near-parity with the
hand-written corpus's lowering coverage. Each new task targets
a distinct surface from SCHEMA.md §13 / SCOPE.md §4.2 and
mirrors a specific hand-written analogue, so the C path's
coverage of the lowering inventory is now systematic rather
than spotty.

### v0.4 finding — sub-register memory access blows up the BTOR2 model

While drafting this batch, three planned tasks (`0123-c-endianness-le`,
`0125-c-strlen-fixed`, `0126-c-fnv1a-hash`) all hung z3 indefinitely
(>4 min wall-clock, >2 GB RAM) at modest bounds (40-200). The common
factor: each task did **per-byte stores into a stack buffer followed
by per-byte loads from it** — the C source pattern
`unsigned char buf[N]; buf[0] = ...; ... = buf[i];`. The bench's
BTOR2 memory model is byte-addressable (SCHEMA.md §4-§5) and the
unrolled SMT problem appears to scale super-linearly with the
number of distinct memory addresses touched per cycle.

By contrast, every C task that uses *only* register-resident
volatiles + immediate operands (0100-0122, 0124) framework-oracles
in seconds. Pure-register tasks (0102-c-mul-chain at -O0 ran in
1.7 s, 0107-c-branchloop-O0 in 3.8 s) handle the bound easily;
the moment the source touches `buf[]` the wall-clock goes through
the roof.

**Implication for v0.4 corpus design:** memory-pattern tasks
(byte buffers, struct fields, type-pun via `char *`) are
**currently impractical** at the bench's BMC bounds. Authoring
them requires either:

1. A bound small enough that the memory-model size stays
   manageable (probably ≤ 20 cycles for typical buffers).
2. A solver other than z3-bmc on the sub-register memory-access
   shape — bitwuzla / cvc5 may handle the byte-array model
   differently. (Not measured; engine_bench would surface it.)
3. A schema-side optimisation that recognises stack buffers
   accessed only locally and elides the per-byte memory-model
   cost. Out of scope for v0.4.

For now, lowering-sensitive *memory* tasks (endianness, strlen,
hash functions) are deferred. The C-corpus stays at register-
based access patterns until a workable approach for the byte-
array memory model lands. Real-program fragments that fit in
register-only patterns (call-boundary semantics, arithmetic
patterns) remain on the table.

Authoring 0116 itself surfaced a bug in my mental model: I
initially asserted `z != 0xFFFFFFFFFFFFFFFFUL` thinking the
RV64 W-suffix sign-extension would carry through, missed that
gcc emits a zero-extension shim per C's unsigned-widening rule,
and the framework_oracle FAIL caught it on the first compile.
This is exactly the value the lowering-sensitive tier is
supposed to surface — not just for the LLM under condition A,
but for *the corpus author* who wrote the assertion.

## Empirical findings

### Finding 1 — engine pins don't transfer through compilation

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

### Finding 2 — the bitwuzla penalty is highly non-linear in -O level, *and code-shape-dependent*

The three opt-level families together (12 tasks across loopsum,
branchloop, byteswap) reveal a more nuanced picture than any
one family alone hinted. engine_bench medians (3 samples each):

| Family | Engine | -O0 | -O1 | -O2 | -O3 |
|---|---|---:|---:|---:|---:|
| loopsum    | z3-bmc   |  3.06 s | 1.41 s | 1.40 s | 1.38 s |
| loopsum    | bitwuzla | **133.79 s** | 2.97 s | 3.03 s | 3.19 s |
| branchloop | z3-bmc   |  3.67 s | 1.72 s | 1.77 s | 1.75 s |
| branchloop | bitwuzla | **125.72 s** | 4.24 s | 5.24 s | 5.22 s |
| byteswap   | z3-bmc   |  2.64 s | 1.47 s | 1.51 s | 2.62 s |
| byteswap   | bitwuzla |  71.15 s | **0.29 s** | **0.31 s** | **0.63 s** |

bitwuzla / z3-bmc ratio:

| Family | -O0 | -O1 | -O2 | -O3 |
|---|---:|---:|---:|---:|
| loopsum    | 43.7× slower | 2.1× slower | 2.2× slower | 2.3× slower |
| branchloop | 34.2× slower | 2.5× slower | 3.0× slower | 3.0× slower |
| byteswap   | 27.0× slower | **5.0× faster** | **4.9× faster** | **4.2× faster** |

Two distinct effects compose:

**Effect 1 — the `-O0` spill/reload penalty on bitwuzla.** Across
all three families, bitwuzla is 27–44× slower than z3-bmc at
-O0 and the gap collapses dramatically at -O1. The
load/store-dominated trace shape that gcc -O0 produces is
uniquely expensive on bitwuzla's BMC unrolling path, irrespective
of the underlying arithmetic.

**Effect 2 — bitwuzla's bitvector-strength shows once spills are
gone.** Loopsum and branchloop are arithmetic-light (a sum
accumulator and a parity-conditional sum); their -O1+ rows show
bitwuzla 2–3× *slower* than z3-bmc. Byteswap is bitvector-heavy
(8 shifts + 8 masks + 8 ors per 8 iterations); its -O1+ rows
show bitwuzla 4–5× *faster*. The hand-written 0050-deep-mul-chain's
11× bitwuzla advantage is the same effect on a different
shape — bvmul vs shift+mask+or, both bitvector-arithmetic-heavy.

**Implication for v0.4 corpus design:** the right engine pin
on a C-derived task depends on **two** things, not one:

1. The *operation density* of the source code — bitvector-
   arithmetic-heavy code (shifts, masks, multiplications)
   favours bitwuzla; control-flow-heavy code favours z3-bmc.
2. The *optimization level* — at -O0, the spill/reload penalty
   dominates either way and z3-bmc is the safer pin; at -O1+ the
   underlying operation density takes over.

**Implication for v0.4 LLM-under-condition-B prompt design:**
the existing `condition_b.md` "Engine selection" block names
"bitwuzla for bitvector-heavy or large-bound queries." The v0.4
data refines that: **"bitwuzla for bitvector-heavy code at
-O1+; z3-bmc otherwise."** The condition_b prompt should be
updated when v0.4 publishes; deferred to that cycle.

## v0.4 scope shipped

- `bench/riscv-btor2/corpus/_compile_c.py` — auto-spec-gen, with
  the v0.4 expansion: `[c].opt_level` knob (default `"0"`,
  validates against `{"0", "1", "2", "3", "s", "g"}`).
- `bench/riscv-btor2/corpus/Makefile` — extended with a C path
  that runs `_compile_c.py` on tasks containing `task.c`.
- 3 prototype tasks (0100, 0101, 0102) demonstrating the
  pipeline end-to-end on the unreachable-correct, reachable-bug,
  and engine-pin variants.
- 4 optimization-level family tasks (0103-0106) demonstrating
  one-source-multi-level corpus expansion + the empirical
  bitwuzla vs z3-bmc gap collapse from -O0 to -O1.
- `coverage_tracker` test relaxed to count tasks-without-
  observables dynamically (the C tasks ship empty observables;
  the property carries the full question).

## v0.4 next (not yet shipped)

The acceptance for v0.4 publication would be an A/B/C sweep on
the C subset plus condition D (CBMC). Remaining sketches:

1. **More optimization-level families.** The 010X-c-loopsum-oN
   pattern works; replicate on 2-3 more sources to broaden the
   "what gcc does at each -O level" surface (sign-extension at
   call boundaries, loop-invariant hoisting, dead-code elim).

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
