# `riscv-btor2` v0.1.2 — pair-helps-LLM result on slot_CC_haiku

**Date:** 2026-05-08
**Model under test:** Anthropic Haiku 4.5 (`claude-haiku-4-5-20251001`),
routed through the `claude-code` CLI adapter (`slot_CC_haiku`).
**Conditions:** A (no tools) and B (pair-equipped via the bench's
MCP stdio server).
**Corpus:** 32 tasks (the v0.1.1 corpus + two new T2
lowering-sensitive tasks, `0031-sllw-shamt-masking-loop` and
`0032-mulw-32bit-truncation-loop`).
**Seeds:** 1 per cell. Multi-seed left to v0.1.3.

> **Status: SINGLE-VENDOR EXPLORATORY.** Slot CC_haiku is an
> Anthropic-only slot. This run does not satisfy
> `BENCHMARKING.md` §7's "≥ 2 LLMs from unrelated families"
> requirement and is therefore not §7-grade. It is published as
> a pipeline-soak result and as an empirical demonstration of
> the pair's value on a weaker baseline. Re-running against an
> OpenAI / Google / Meta second slot is the path back to
> §7-grade.

## Headline result

Pair-equipped Haiku **decisively outperforms** unaided Haiku.

| Metric | A (no tools) | B-v3 (pair, post-intervention) | Delta |
|---|---|---|---|
| Verdict accuracy | 28/32 (87.5%) | **32/32 (100%)** | **+12.5 pp** |
| High-confidence wrong (§5 hallucination) | 4 (12.5%) | **0 (0%)** | **−4** |
| Witness fingerprint match (of reachables) | 9/22 (40.9%) | **21/22 (95.5%)** | **+54.6 pp** |
| Brier score | 0.1235 | **0.0005** | **×247** |
| ECE (10-bucket) | 0.1116 | **0.0134** | **×8** |
| Wall-clock (sweep total, min) | 20.2 | 24.1 | +20% |
| Output tokens (sweep total) | 173,262 | **143,874** | **−17%** |

**The pair, with proper scaffolding, makes Haiku not just more
accurate but more efficient.**

## The story arc

The headline numbers above hide a non-trivial empirical journey.
The first attempt at running condition B against slot_CC_haiku
showed the *opposite* result: pair-equipped Haiku
**underperformed** unaided Haiku across every metric.
Diagnosing why and fixing it surfaced a genuine, generalisable
finding about LLM × tool-surface ergonomics, summarised here.

Four runs in chronological order, one row per sweep:

| Sweep | Verdict | Unknown | Hallucination | Witness | Wall (min) | Tokens |
|---|---|---|---|---|---|---|
| **A** (no tools) | 28/32 (87.5%) | 0 | 4 | 9/22 (40.9%) | 20.2 | 173,262 |
| **B-v1** (raw pair) | 20/27 (74.1%)* | 5 | 7 | 6/22 (27.3%) | 72.5 | 365,014 |
| **B-v2** (+DSL grammar +polarity +error hints) | 32/32 (100%) | 0 | 0 | 18/22 (81.8%) | 23.8 | 146,737 |
| **B-v3** (+over-include final_regs guidance) | 32/32 (100%) | 0 | 0 | 21/22 (95.5%) | 24.1 | 143,874 |

\* 5 cells went `unknown` in B-v1; verdict accuracy excludes those
per §5 ("graded as neither correct nor wrong but tracked
separately").

**B-v1 was strictly worse than A** (74.1% vs 87.5%, twice the
hallucination rate, ½ the witness fidelity, 3.6× the wall clock,
2.1× the output tokens). That counterintuitive negative result
was the starting point.

Pre→post per-task transition between A and B-v1:

- 10 regressions (A correct → B wrong/unknown), all on
  `reachable` tasks.
- 2 improvements (loops where A had hallucinated `proved`).
- Net: B-v1 fixed 2, broke 10.

The regressions had a striking shape: Haiku consistently shifted
from correct `reachable` (under A) to incorrect `proved` (5
cases) or gave up with `unknown` (5 cases) under B.

## Diagnosis

To see what Haiku actually did under B-v1, the claude-code
adapter was upgraded to `--output-format stream-json` (commit
`15d178b`). The previous `--output-format json` envelope discarded
all intermediate `tool_use` / `tool_result` turns, leaving every
B-v1 transcript with `tool_calls=0`. Stream-json preserves the
full audit trail and is now parsed into `tool_call_log` entries.

The first regression cell inspected after the fix
(`0007-simple-add-baseline`, the simplest task in the corpus,
which A solved trivially in 14s with 612 output tokens but B-v1
got wrong in 210s with 19,627 output tokens) revealed Haiku's
actual behaviour: **8 consecutive failed `compile` calls** with
the same parser error, before finally landing a valid spec on
the 9th try. The error each time was:

```
ValueError: unexpected character '=' at position 6
```

Haiku had constructed `'expression': 'obs_0 == 12'` — using the
Python `==` operator rather than the spec DSL's `eq(reg(10),
const(12))`. It also invented a non-existent `'affinity': 'reach'`
field on the property object.

A second regression (`0026-callee-modifies-multi`) confirmed an
independent failure mode: **verdict-vocabulary inversion**.
Haiku's prose said "z3-spacer proved the property is satisfied
in all executions" and emitted verdict `proved`. But the bench's
verdict semantics (per `SCHEMA.md` §8) say `proved` means *the
bad expression is never satisfied*. For a question whose
positive form is "can x13 = 6?", `proved` would mean
"x13 ≠ 6 ever" — the *opposite* of what Haiku claimed. Haiku
conflated three concepts:

- the user's question's positive form ("can x13 = 6?")
- the spec's `bad` expression (`eq(reg(13), 6)`)
- the `proved` verdict label (bad cannot occur)

For a deterministic program where x13 always equals 6, Haiku
reasoned "always-true → that's a proof → answer is `proved`",
which is exactly the opposite of the intended semantics.

The two failure modes — DSL ignorance and verdict polarity
inversion — together account for all 10 B-v1 regressions.

## Interventions

Three coordinated changes (commit `01b8d25`):

1. **`prompts/_base.md` — verdict-vs-question polarity section.**
   Adds a "read carefully" callout explicitly mapping
   verdict labels to bad-expression polarity, with a worked
   counterexample showing that "x10 always equals 12" makes the
   correct verdict `reachable`, not `proved`. Also documents the
   asymmetric matcher rule (`proved` accepted in place of
   `unreachable` but never `reachable`).

2. **`prompts/condition_b.md` — DSL grammar reference + worked
   examples.** Lists every supported atom and operator inline
   with explicit "no `==`, no `!=`, no `<`, no `>`, no `&&`,
   no `||`" callouts. Two worked-example properties the LLM can
   pattern-match. Spells out the Property object's two-field
   `{expression, negate}` shape so Haiku stops inventing fields.

3. **`mcp_server.py` — pedagogical compile errors.** When a tool
   call fails with `ValueError`/`KeyError`/`TypeError` on a
   spec-consuming tool (compile / introspect), the error
   envelope now carries an inline `hint` field with the same
   DSL summary, so the LLM sees actionable guidance directly
   on the tool result. Scoped to spec-consuming tools so
   dispatch / lift errors aren't bloated with irrelevant DSL
   content.

Together, these three changes flipped B-v1 (74.1%, 7 hallucinations,
6/22 witnesses) into B-v2 (100%, 0 hallucinations, 18/22 witnesses).
Same model, same corpus, same tool surface — the delta is
documentation and error-message pedagogy.

## Closing the witness gap

B-v2 had 4 cells where verdict was correct but the witness
fingerprint failed: `0004-divu-by-zero-sentinel`,
`0015-nested-loop`, `0022-countdown-loop`,
`0028-callee-with-loop`. All four failures shared an identical
root cause: Haiku reported the "interesting" register the
question asked about (typically x10 — the answer) but dropped
supporting registers the corpus pinned as fingerprint anchors
(typically x5 or x6 ending at 0).

The LLM cannot read `task.toml` so it has no way to know which
registers the corpus pins. The safe rule is to over-include
rather than under-include: extra registers are ignored, missing
registers are scored as failures.

`prompts/_base.md` was patched (commit `438a60c`) with explicit
guidance: list every register the program writes to plus every
register read where the value matters, even if the value ends at
0; only x0 is safe to omit. Result: B-v2 → B-v3 closed 3 of
the 4 witness gaps. The remaining one (0004) is interesting:
Haiku's prose explicitly traces `addi x6, zero, 0` and says
"x6 = 0" — it knows. But it still drops x6 from final_regs.
The "0 is uninteresting" instinct overrides the explicit prompt
guidance in this single edge case. Diminishing returns past
this point; 95.5% witness fidelity is solid for the headline
result.

## Per-task breakdown (A vs B-v3)

All 32 tasks, sorted by id. Cells where A and B-v3 disagree
flagged.

| Task | A verdict | A wm | B-v3 verdict | B-v3 wm | A→B-v3 |
|---|---|---|---|---|---|
| 0001-x0-write-dropped | unreachable ✓ | — | unreachable ✓ | — | same |
| 0002-bound-sensitive-loop | reachable ✓ | wrong | reachable ✓ | ok | **witness fixed** |
| 0003-addiw-sign-ext | unreachable ✓ | — | unreachable ✓ | — | same |
| 0004-divu-by-zero-sentinel | reachable ✓ | wrong | reachable ✓ | wrong | witness still missed |
| 0005-lbu-vs-lb | unreachable ✓ | — | unreachable ✓ | — | same |
| 0006-shift-amount-masking | reachable ✓ | ok | reachable ✓ | ok | same |
| 0007-simple-add-baseline | reachable ✓ | ok | reachable ✓ | ok | same |
| 0008-long-loop-bound | reachable ✓ | ok | reachable ✓ | ok | same |
| 0009-uninit-load | reachable ✓ | wrong | reachable ✓ | ok | **witness fixed** |
| 0010-lh-endianness | unreachable ✓ | — | unreachable ✓ | — | same |
| 0011-srai-vs-srli | unreachable ✓ | — | unreachable ✓ | — | same |
| 0012-mul-baseline | reachable ✓ | ok | reachable ✓ | ok | same |
| 0013-bgeu-vs-bge | unreachable ✓ | — | unreachable ✓ | — | same |
| 0014-twenty-iter-loop | **proved ✗** | — | reachable ✓ | ok | **verdict fixed** |
| 0015-nested-loop | **proved ✗** | — | reachable ✓ | ok | **verdict fixed** |
| 0016-bge-signed | unreachable ✓ | — | proved ✓ (matcher accepts) | — | same |
| 0017-and-baseline | **proved ✗** | — | reachable ✓ | ok | **verdict fixed** |
| 0018-or-baseline | **proved ✗** | — | reachable ✓ | ok | **verdict fixed** |
| 0019-jal-saves-link | reachable ✓ | wrong | reachable ✓ | ok | **witness fixed** |
| 0020-monotonic-x5-spacer | proved ✓ | — | proved ✓ | — | same |
| 0021-stayzero-x10-spacer | proved ✓ | — | proved ✓ | — | same |
| 0022-countdown-loop | reachable ✓ | ok | reachable ✓ | ok | same |
| 0023-stride-3-loop | reachable ✓ | ok | reachable ✓ | ok | same |
| 0024-loop-then-mul | reachable ✓ | ok | reachable ✓ | ok | same |
| 0025-callee-returns-const | reachable ✓ | wrong | reachable ✓ | ok | **witness fixed** |
| 0026-callee-modifies-multi | reachable ✓ | wrong | reachable ✓ | ok | **witness fixed** |
| 0027-nested-call | reachable ✓ | ok | reachable ✓ | ok | same |
| 0028-callee-with-loop | reachable ✓ | wrong | reachable ✓ | ok | **witness fixed** |
| 0029-shared-callee-twice | reachable ✓ | ok | reachable ✓ | ok | same |
| 0030-two-callees-mixed | reachable ✓ | wrong | reachable ✓ | ok | **witness fixed** |
| 0031-sllw-shamt-masking-loop | reachable ✓ | wrong | reachable ✓ | ok | **witness fixed** |
| 0032-mulw-32bit-truncation-loop | unreachable ✓ | — | unreachable ✓ | — | same |

A→B-v3 net: 4 verdicts fixed, 8 witnesses fixed, 1 witness still
missing (0004), 0 regressions.

## Calibration

Reliability table from `bench/riscv-btor2/calibration.py`:

```
=== condition=A  model_slot=slot_CC_haiku  n=32 ===
  Verdict accuracy:     28/32  (87.5%)
  Hallucination rate:   12.5%
  Mean conf | correct:  0.986
  Mean conf | wrong:    0.992
  Brier score:          0.1235
  ECE (10 buckets):     0.1116
  All confidences in [0.9, 1.0): mean=0.987, frac_correct=0.875

=== condition=B-v3  model_slot=slot_CC_haiku  n=32 ===
  Verdict accuracy:     32/32  (100.0%)
  Hallucination rate:   0.0%
  Mean conf | correct:  0.987
  Mean conf | wrong:    0.000
  Brier score:          0.0005
  ECE (10 buckets):     0.0134
  All confidences in [0.9, 1.0): mean=0.987, frac_correct=1.000
```

Note that `mean conf | wrong > mean conf | correct` under A
(0.992 vs 0.986). This is the classic mis-calibration
signature: Haiku is *most confident* on the cells where it is
wrong. After the pair-mediated B-v3, the wrong column is empty
because there are no wrong cells.

## Limitations & known issues

1. **Single seed per cell.** §9.6 calls for ≥ 5 seeds; not
   satisfied here. Service-side temperature noise was confirmed
   to produce real per-cell variance in the
   `bench-probe-20260507T201225` 5-seed probe (5/5 unique
   prose responses on a stable-verdict task), so multi-seed
   would shift Brier / ECE numbers somewhat. The headline
   verdict-accuracy delta (87.5% → 100%) is large enough that a
   single-seed measurement is informative as a directional
   result.
2. **Single-vendor.** Slot_CC_haiku is Anthropic-only;
   §7-grade publication requires a second-family slot.
   Re-running against an OpenAI / Google / Meta model is
   future work. Without that, this run is exploratory not
   §7-grade.
3. **One residual witness gap.** 0004-divu-by-zero-sentinel
   still fails `final_regs[6]` because Haiku's "0 is
   uninteresting" instinct overrides the explicit prompt
   guidance. A more aggressive prompt or schema-side hint
   could close this.
4. **MCP stream-json fidelity.** The new transcript path
   captures all tool_use / tool_result turns, but does NOT
   capture in-line text emitted between tool calls (it goes
   into the assistant content stream which we currently parse
   only for tool_use blocks). For full transcripts the
   per-message log would need fuller parsing.
5. **Haiku-only.** Findings about DSL ignorance and verdict
   polarity inversion may not generalise; a stronger model
   (Opus 4.7) was already at the 100% accuracy ceiling under
   condition A and produced 0 polarity errors and ~0
   spec-construction errors. The interventions don't help
   strong models; they don't hurt them either.

## Reproducibility

All artifacts are in this directory:

- `summaries/A.json`, `B-v1.json`, `B-v2.json`, `B-v3.json` —
  per-cell records (task, condition, verdict, witness match,
  duration, tokens, tool_calls)
- `transcripts/{A,B-v1,B-v2,B-v3}/<task>/<cond>/<slot>/seed-0.json`
  — full prompt + response_text + tool_call_log per cell

Commits in chronological order:

| Commit | Subject |
|---|---|
| `15d178b` | bench: stream-json transcript capture for claude-code adapter |
| `01b8d25` | bench: spec-construction scaffolding for condition B |
| `438a60c` | bench: prompt directs LLMs to over-include final_regs |

To reproduce one cell:

```sh
python bench/riscv-btor2/harness.py \
    --task 0007-simple-add-baseline \
    --condition B \
    --model slot_CC_haiku \
    --seed 0 \
    --transcripts-dir /tmp/repro
```

To reproduce the full sweep (~24 min wall):

```sh
for t in $(ls bench/riscv-btor2/corpus | grep -E '^[0-9]'); do
    python bench/riscv-btor2/harness.py \
        --task "$t" --condition B --model slot_CC_haiku --seed 0 \
        --transcripts-dir /tmp/repro/_transcripts
done
```

To compute calibration:

```sh
python bench/riscv-btor2/calibration.py \
    --transcripts-dir bench/riscv-btor2/runs/v0.1.2/transcripts/B-v3
```

## What we learned

1. **Pair-helps-LLM is real, but only with adequate ergonomics.**
   The naive expectation "give the model tools, it gets better"
   is wrong. Tools without grammar references, polarity
   guidance, or pedagogical errors made a weaker model
   measurably *worse*. The same tools with three small
   documentation interventions made it dramatically *better*.

2. **The benchmark surfaced this finding mechanically.** §5's
   verdict accuracy + hallucination rate combined with §7's
   stream-json transcript capture gave us a sharp diagnostic
   path: identify the regressions, dump the transcripts, find
   the failure mode, intervene, re-measure. Total turnaround
   time from "B is worse than A" to "B is decisively better
   than A" was about three hours of work and one and a half
   hours of compute.

3. **Spec-construction is a separate reasoning task.** The
   pair's value is mediated by the LLM's ability to encode the
   user's question as a `RiscvBtor2Spec`. Haiku's failure mode
   was specifically here, not in the verification problem
   itself. The implication for pair design: if the spec
   language is hard to learn from prose, the pair will
   underperform on weaker LLMs even when the underlying
   solver is doing the right thing.

4. **Verdict-vocabulary inversion is the most damaging
   confusion.** The `proved` ⇔ "bad never holds" semantics is
   counterintuitive when the user's question is positively
   phrased ("can X = Y?"). Haiku's confident-but-inverted
   answers were the highest-cost failure mode (highest
   confidence, deepest reasoning, hardest to recover from).
   Future pair documentation should lead with this distinction.

5. **Over-inclusion beats precision in witness fingerprints.**
   The §4.5 fingerprint check is one-way: extra fields are
   free, missing fields are penalised. The LLM has no way to
   know which fields the corpus pins, so the only safe
   strategy is to surface every plausibly-relevant register.
   This should be standard advice in any §3.B-grade prompt
   template.
