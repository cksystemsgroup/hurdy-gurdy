# Initial Pareto findings — iter 18

> First defensible read of where hurdy-gurdy stands against CBMC on
> the C-corpus subset of `bench/riscv-btor2/corpus/`. Produced
> autonomously by the v2-bootstrap loop after the P3 build phases
> completed and P4+ iteration-to-dominance began.
>
> **Sample size: 10 tasks total** (5 in iter 17, 5 in iter 18).
> Small but informative. The wedge in §3 below is real and
> reproducible.

## 1. Headline

| Metric                        | CBMC      | Hurdy-gurdy |
|-------------------------------|-----------|-------------|
| Tasks attempted               | 10        | 10          |
| Solved (non-skip/error)       | 10        | 10          |
| **Correct**                   | **9**     | **10**      |
| False positives               | **1**     | 0           |
| Total wall-clock (s)          | 0.650     | 14.36       |
| Median per task (s)           | ~0.028    | ~1.40       |

**CBMC is ~50× faster median** on this slice. **Hurdy-gurdy is
strictly more accurate** — 10/10 vs 9/10 — and the one CBMC
false positive is a real semantic-gap case, not a tooling glitch.

## 2. Pareto dominance on the 10-task sample

- **CBMC strictly dominates 9 tasks** (both correct, CBMC ≤ 50×
  faster, varying with task complexity).
- **Hurdy-gurdy strictly dominates 1 task** (hurdy-gurdy correct,
  CBMC false-positive).

So the Pareto frontier intersects: neither tool is uniformly
better. CBMC owns the "fast, mostly correct" cell; hurdy-gurdy
owns the "slower, soundly correct on UB" cell.

## 3. The wedge: task `0117-c-int-min-div-neg-one`

The one task where hurdy-gurdy wins.

```c
// excerpt from task.cbmc.c
int main(void) {
    volatile int x = (int)0x80000000;   // INT_MIN
    volatile int y = -1;
    int q = x / y;                       // RV64 divw → INT_MIN sentinel
    long z = q;                          // sign-ext: -2147483648L
    __CPROVER_assert(!(z != -2147483648L), "trap reachable");
}
```

- The C expression `INT_MIN / -1` is **C-level UB** (signed
  overflow on integer division).
- On RV64, `divw` is **fully defined**: when the dividend is
  `INT_MIN` and the divisor is `-1`, the result is the
  dividend's bit pattern preserved (a sentinel-on-overflow
  contract; SCHEMA.md §13). After 32→64 sign-extension `z =
  -2147483648L = INT_MIN`. The assertion `z != INT_MIN` is
  **false**, so the trap is **unreachable**.

| Tool | Verdict | Correct? |
|------|---------|----------|
| Expected (ground truth from task.toml) | unreachable | — |
| CBMC | **reachable** | **❌ False positive** |
| Hurdy-gurdy | unreachable | ✅ |

CBMC, reasoning at the C-source level, treats the UB
conservatively — any path containing UB is "possibly anything",
so the trap is reachable. Hurdy-gurdy, reasoning on the RV64 ELF
produced by the v0.4 C-corpus toolchain, models `divw`'s actual
hardware semantics and proves the trap unreachable.

This is the cleanest possible answer to **"can hurdy-gurdy
outperform SOTA?"**: on a class of tasks where C-level UB
diverges from well-defined RISC-V semantics, **hurdy-gurdy's
ISA-precise translation is the more accurate oracle, regardless of
how fast CBMC is on tasks where the two semantics agree**.

## 4. Where hurdy-gurdy loses and why (the other 9 tasks)

| Task                              | CBMC s | HG s   | Ratio | Class |
|-----------------------------------|--------|--------|-------|-------|
| 0100-c-add-trap-correct           | 0.204  | (iter 17) | n/a | simple arithmetic |
| 0101-c-add-trap-bug               | 0.026  | (iter 17) | n/a | simple arithmetic |
| 0102-c-mul-chain-correct          | 0.026  | (iter 17) | n/a | mul chain |
| 0103-c-loopsum-o0                 | 0.026  | (iter 17) | n/a | loop sum |
| 0104-c-loopsum-o1                 | 0.029  | (iter 17) | n/a | loop sum, -O1 |
| 0105-c-loopsum-o2                 | 0.200  | 1.429  | ~7×   | loop sum, -O2 |
| 0110-c-branchloop-o3              | 0.029  | 1.772  | ~60×  | branching loop, -O3 |
| 0114-c-byteswap-o3                | 0.028  | 2.506  | ~89×  | bit twiddling, -O3 |
| 0119-c-signed-vs-unsigned-shift-right | 0.026 | 1.185 | ~46× | shift semantics |

Hurdy-gurdy's per-task time is roughly constant at 1–2.5s; CBMC
is sub-100ms on most tasks. The gap is **structural**: CBMC reads
C directly, while hurdy-gurdy goes
`ELF → BTOR2 → z3-bmc subprocess → witness lift`. Each step has
real cost; the four together swamp z3's actual solve time on
small programs.

### Where the time goes (informed guess, to be verified)

1. **BTOR2 emission**: the translator walks every instruction in
   the unrolled execution; with `bound=20`, that's hundreds of
   nodes.
2. **z3-bmc subprocess startup**: even on a trivial BTOR2 model,
   z3 takes ~100–200ms to spin up.
3. **Witness lift**: for `unreachable`, this is cheap; for
   `reachable`, the lift step walks the model.

Realistic levers (no implementation this iter):

- **Engine pinning**: bitwuzla is reportedly 6–13× faster on
  some classes (per `bench/riscv-btor2/CORPUS_V0.3_PLAN.md`).
  Swap `analysis.engine` per-spec when bitwuzla wins.
- **Tighter bounds**: `analysis.bound=20` is the default; many
  0100+ tasks have evident trip counts ≤ 5. An LLM-curated
  spec should set this per task.
- **Translator caching**: identical `(spec, source)` re-runs
  hit the framework cache, but per-task compile + dispatch is
  amortizable across the corpus only if a session-level cache
  is wired into the bench harness.
- **The P1.3a translator fix** (BLOCKER) — won't change
  wall-clock noticeably but removes the malformed-BTOR2
  emission. Worth doing for correctness, not perf.

## 5. What the wedge does and does not prove

**What it proves:** for at least one corpus task,
hurdy-gurdy is **more accurate than CBMC** because it reasons
through the RISC-V ISA rather than C semantics. The translation
to RV64 is not just a longer path — it's a *more faithful* path
when C UB diverges from RV64 behavior.

**What it doesn't prove:** that this advantage will scale. To
make the claim from V2_BOOTSTRAP.md §5 ("dominate the Pareto
frontier") defensible, the empirical work needed is:

1. **Find more such tasks.** Scan the corpus for UB-adjacent
   constructs: signed overflow, oversized shifts, divide-by-zero,
   `INT_MIN / -1`, oversized bitfields, pointer arithmetic.
   Each is a candidate wedge.
2. **Generate adversarial tasks.** For each UB class, hand-craft
   one task where C tools must either be unsound or refuse to
   answer, and where the RV64 ELF gives a deterministic answer.
3. **Run on a larger slice.** 10 tasks is too few for a
   defensible statistical claim. The next ratchet is 25 tasks,
   then 50.

## 6. Recommendations for the user

Priority order:

1. **Approve P1.3a translator fix.** It's a correctness fix.
   Won't change Pareto numbers materially but removes a latent
   bug the alignment oracle exposed.
2. **Pivot future P4+ iterations toward UB-class corpus
   expansion** rather than toward making hurdy-gurdy faster on
   tasks CBMC already wins. The latter is a losing race against
   30 years of CBMC engineering; the former is the design
   advantage hurdy-gurdy's name and architecture were built for.
3. **Install pono / docker images for the remaining SOTA tools**
   when convenient. The current Pareto table is CBMC-only; a
   richer comparison may show different wedges per-tool.
4. **Don't trust this 10-task headline.** Scale up the corpus
   before letting the loop iterate on translator changes — the
   sample is too small to distinguish signal from noise on
   wall-clock medians.

## 7. Reproducibility

```bash
# Re-run from a clean state on this branch (commit 12b5a90).
rm -f bench/riscv-btor2/baselines/_runs/*.jsonl
for t in 0100 0101 0102 0103 0104 0105 0110 0114 0117 0119 ; do
  python3 bench/riscv-btor2/baselines/cbmc.py --task "${t}-" --max-tasks 1 \
    >> bench/riscv-btor2/baselines/_runs/cbmc.jsonl
  python3 bench/riscv-btor2/baselines/hurdy_gurdy.py --task "${t}-" --max-tasks 1 \
    >> bench/riscv-btor2/baselines/_runs/hurdy-gurdy.jsonl
done
python3 bench/riscv-btor2/baselines/pareto.py
```

Aggregate output and 0117 finding are stable across runs. CBMC
6.9.0; hurdy-gurdy commit `12b5a90` on `v2-bootstrap`.

## 8. UB-class candidates (iter 19 inventory)

A read-only scan of `bench/riscv-btor2/corpus/01*` for tasks
that are (a) CBMC-ready (`task.cbmc.c` present), (b) flagged
`lowering_sensitive = true` in `task.toml`, and (c) reference
UB-class concepts in their notes (`UB`, `sentinel`, `signed
overflow`, `wrap`, `INT_MIN`, `shift mask`, `div-by-zero`,
`pointer`).

Ten tasks match. Every one of them has `expected = unreachable`
— i.e., the property *holds* under correct RV64 semantics —
which is exactly the shape where C-level UB reasoning is most
likely to over-approximate to `reachable` and produce a false
positive.

| Task                                       | UB markers                            |
|--------------------------------------------|---------------------------------------|
| **0115-c-int-overflow**                    | signed overflow, wrap, INT_MIN        |
| **0116-c-divu-sentinel**                   | UB, sentinel, divide-by-zero          |
| **0117-c-int-min-div-neg-one** ✅ wedge    | UB, sentinel, INT_MIN                 |
| **0118-c-shift-amount-mask**               | UB, shift-amount masking              |
| 0119-c-signed-vs-unsigned-shift-right ★    | (LS only — already tested iter 18)    |
| **0120-c-byte-load-signedness**            | pointer / byte loads                  |
| **0121-c-mulw-truncation**                 | RV64 `mulw` vs C int promotion        |
| **0122-c-signed-vs-unsigned-cmp**          | comparison semantics                  |
| **0123-c-endianness-le**                   | pointer / byte ordering               |
| **0124-c-call-arg-promotion**              | calling convention promotion          |

✅ marks 0117, the already-confirmed wedge.
★ marks 0119, already tested and matched (no wedge there).

The 8 unstarred tasks are the **prime candidates for the next
P4 iteration's measurement run**. If even half of them
reproduce the 0117 pattern (CBMC false-positive, hurdy-gurdy
correct), the Pareto-on-correctness story becomes a credible
defensible claim rather than a single anecdote.

### Why this list is high-value

The `lowering_sensitive = true` flag in `task.toml` is the
task author's explicit declaration that "the C-level reading
and the RV64-level reading of this program disagree at the
property-evaluation site". CBMC reads C; hurdy-gurdy reads
RV64. Disagreement is the expected outcome — when it happens,
the ground truth (which side the `expected` verdict came down
on, recorded by hand) decides who's correct.

For the 10 listed tasks, every `expected` is `unreachable`,
meaning the task author judged the *RV64* reading to be
correct in each case. If CBMC says `reachable` for any of
them, that's a false positive in CBMC's column — adding to the
0117 datapoint.

### Action items derived from this inventory

1. **Next iter** (P4.3): run both tools on the 8 untested
   candidate tasks (≤ 5 per RAM-safety; do this over 2 iters).
   Record per-task outcomes.
2. After both runs land: re-run the aggregator. Expected
   shape: total `correct` count for hurdy-gurdy stays at 100%;
   CBMC's count drops below 100% as each new wedge surfaces.
3. If the wedge ratio is >= 30% on this subset, the Pareto
   table becomes meaningfully two-dimensional (CBMC owns
   wall-clock; hurdy-gurdy owns correctness on lowering-
   sensitive tasks). The "outperform SOTA" claim has its
   first defensible numerical answer.

